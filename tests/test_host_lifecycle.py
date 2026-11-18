"""Fault injection at the boundaries that can leave hardware ownership uncertain."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'board'))
from ffn_host import FFNSession
from session_guard import SessionGuard, _LIVE


class Buffer:
    device_address=0x123456780
    def __init__(self): self.freed=False
    def freebuffer(self): self.freed=True


class IP:
    def __init__(self, done=True):
        self.done=done; self.writes=[]; self.started=False
    def write(self, offset, value):
        self.writes.append((offset,value))
        if offset==0 and value==1: self.started=True
    def read(self, offset):
        if offset!=0: return 0
        return (6 if self.done else 0) if self.started else 4


def session(done=True):
    s=object.__new__(FFNSession)
    s.busy=s.poisoned=s.closed=False
    s.ready=True; s.stage='allocated'; s.validation=['previous']; s.guard=None
    s.params=Buffer(); s.input=Buffer(); s.output=Buffer()
    s.buffers=[s.params,s.input,s.output]
    s.ip=IP(done)
    s.interface={'offsets':{'parameters':[24,28],'input':[36,40],'output':[48,52],
                            'operation':60,'return':16}}
    s._log=lambda event: None
    return s


class HostLifecycle(unittest.TestCase):
    def assert_blocked(self,s):
        writes=list(s.ip.writes)
        with self.assertRaises(RuntimeError): s._call(1)
        with self.assertRaises(RuntimeError): s.close()
        self.assertEqual(writes,s.ip.writes)
        self.assertFalse(any(b.freed for b in s.buffers))
        self.assertIsNone(s.validation)

    def test_success_writes_both_pointer_halves_and_closes(self):
        s=session()
        self.assertEqual(s._call(1),0)
        self.assertIn((24,0x23456780),s.ip.writes)
        self.assertIn((28,1),s.ip.writes)
        s.close()
        self.assertTrue(all(b.freed for b in s.buffers))

    def test_timeout_blocks_relaunch_and_free(self):
        s=session(False)
        with patch('ffn_host.time.perf_counter',side_effect=[0,6]):
            with self.assertRaises(TimeoutError): s._call(1)
        self.assert_blocked(s)

    def test_interrupt_during_first_read_is_protected(self):
        s=session()
        with patch.object(s.ip,'read',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): s._call(1)
        self.assert_blocked(s)

    def test_pointer_write_failure_is_protected(self):
        s=session()
        with patch.object(s.ip,'write',side_effect=OSError('MMIO failed')):
            with self.assertRaises(OSError): s._call(1)
        self.assert_blocked(s)

    def test_return_read_failure_is_protected(self):
        s=session()
        with patch.object(s.ip,'read',side_effect=[4,6,OSError('return failed')]):
            with self.assertRaises(OSError): s._call(1)
        self.assert_blocked(s)

    def test_done_can_precede_idle_and_clear_before_idle_is_seen(self):
        s=session()
        with patch.object(s.ip,'read',side_effect=[4,10,0,4,0]):
            self.assertEqual(s._call(1),0)
        self.assertFalse(s.busy)
        self.assertFalse(s.poisoned)

    def test_done_without_eventual_idle_times_out_and_preserves_buffers(self):
        s=session()
        with patch.object(s.ip,'read',side_effect=[4,10,0]):
            with patch('ffn_host.time.perf_counter',side_effect=[0,1,6]):
                with self.assertRaises(TimeoutError): s._call(1,timeout=5)
        self.assert_blocked(s)

    def test_autorestart_after_launch_is_rejected(self):
        s=session()
        with patch.object(s.ip,'read',side_effect=[4,138]):
            with self.assertRaises(RuntimeError): s._call(1)
        self.assert_blocked(s)

    def test_nonidle_and_autorestart_are_rejected_before_writes(self):
        for ctrl in (0,5,132):
            s=session()
            with patch.object(s.ip,'read',return_value=ctrl):
                with self.assertRaises(RuntimeError): s._call(1)
            self.assertEqual(s.ip.writes,[])
            self.assert_blocked(s)

    def test_early_call_does_not_access_hardware(self):
        s=session(); s.stage='programmed'
        with self.assertRaises(RuntimeError): s._call(1)
        self.assertEqual(s.ip.writes,[])

    def test_close_rechecks_idle_before_free(self):
        s=session()
        with patch.object(s.ip,'read',return_value=0):
            with self.assertRaises(RuntimeError): s.close()
        self.assert_blocked(s)

    def test_guard_operations_do_not_write_dma_pointers(self):
        s=session(); s.stage='control'
        s._call(2,guard_only=True)
        self.assertEqual(s.ip.writes,[(60,2),(0,1)])

    def test_correctness_failure_revokes_validation_and_preserves_buffers(self):
        s=session()
        with self.assertRaises(RuntimeError): s._expect(False,'mismatch')
        self.assert_blocked(s)

    def test_parameter_load_accepts_legacy_numpy_filename_api(self):
        import numpy as np
        from types import SimpleNamespace
        s=session()
        s.package=Path(__file__).resolve().parents[1]
        paths=[]
        def old_fromfile(filename, **kwargs):
            if not isinstance(filename,str):
                raise AttributeError("PosixPath has no attribute flush")
            paths.append(filename)
            return np.fromfile(filename,**kwargs)
        s.np=SimpleNamespace(fromfile=old_fromfile)
        s.params=MagicMock()
        s._call=MagicMock(return_value=0)
        s.load('random_506')
        self.assertEqual(len(paths),1)
        s.params.flush.assert_called_once()
        s._call.assert_called_once_with(0)
        self.assertTrue(s.ready)

    def test_constructor_has_no_pynq_dependency_or_programming(self):
        with tempfile.TemporaryDirectory() as tmp:
            package=Path(tmp); (package/'data').mkdir(); (package/'data/manifest.json').write_text('{}')
            manifest={'config':{},'run':'test','source_hash':'hash','sha256':{'ffn.bit':'bit'},'package_revision':'audit1'}
            with patch('ffn_host.preflight',return_value=(manifest,{})):
                s=FFNSession(package)
                self.assertEqual(s.stage,'preflight')
                self.assertEqual(s.buffers,[])
                self.assertFalse(hasattr(s,'overlay'))
                s.close()


class Ownership(unittest.TestCase):
    def test_live_owner_is_retained_and_second_session_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=str(Path(tmp)/'guard'); owner=object()
            first=SessionGuard(root,'boot1'); first.acquire(owner)
            self.assertIs(_LIVE[root],owner)
            with self.assertRaises(RuntimeError): SessionGuard(root,'boot1').acquire(object())
            first.release()
            second=SessionGuard(root,'boot1'); second.acquire(object()); second.release()

    def test_dead_process_marker_survives_kernel_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=str(Path(tmp)/'guard')
            first=SessionGuard(root,'boot1'); first.acquire(object())
            # Simulate process death: OS closes the lock, but marker remains active.
            first.file.close(); _LIVE.pop(root)
            with self.assertRaises(RuntimeError): SessionGuard(root,'boot1').acquire(object())
            # A physical reboot changes Linux's boot ID.
            rebooted=SessionGuard(root,'boot2'); rebooted.acquire(object()); rebooted.release()

    def test_corrupt_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=str(Path(tmp)/'guard'); Path(root+'.state.json').write_text('{')
            with self.assertRaises(ValueError): SessionGuard(root,'boot1').acquire(object())

    def test_failed_acquirer_cannot_clear_another_owners_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=str(Path(tmp)/'guard'); first=SessionGuard(root,'boot1'); first.acquire(object())
            second=SessionGuard(root,'boot1')
            with self.assertRaises(RuntimeError): second.acquire(object())
            before=Path(root+'.state.json').read_bytes()
            with self.assertRaises(RuntimeError): second.release()
            self.assertEqual(before,Path(root+'.state.json').read_bytes())
            first.release()

    def test_file_lock_blocks_another_process(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root=str(Path(tmp)/'guard'); first=SessionGuard(root,'boot1'); first.acquire(object())
            child='import fcntl,sys; f=open(sys.argv[1],"a+"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
            result=subprocess.run([sys.executable,'-c',child,root+'.lock'],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'BlockingIOError',result.stderr)
            first.release()


if __name__=='__main__': unittest.main()
