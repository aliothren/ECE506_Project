"""Staged PYNQ runner. Constructing a session only checks local package files."""
import csv
import json
import os
from pathlib import Path
import platform
import time

from preflight import preflight
from session_guard import SessionGuard


def now_ns():
    return int(time.perf_counter()*1e9)


class FFNSession:
    def __init__(self, package):
        import numpy as np
        self.np = np
        self.package = Path(package).resolve()
        self.manifest, self.interface = preflight(self.package)
        self.busy = self.poisoned = self.closed = self.ready = False
        self.stage = 'preflight'
        self.validation = None
        self.buffers = []
        self.guard = None
        self.metadata = {'config': self.manifest['config'], 'run': self.manifest['run'],
                         'source_hash': self.manifest['source_hash'],
                         'bit_sha256': self.manifest['sha256']['ffn.bit'],
                         'package_revision': self.manifest['package_revision'],
                         'system': platform.uname()._asdict(), 'python': platform.python_version(),
                         'data_manifest': json.loads((self.package/'data/manifest.json').read_text())}
        self._log('preflight_pass')

    def _log(self, event):
        with (self.package/'load_stages.jsonl').open('a') as f:
            f.write(json.dumps({'time': time.time(), 'event': event, 'stage': self.stage,
                                'run': self.manifest['run'], 'pid': os.getpid()})+'\n')
            f.flush()
            os.fsync(f.fileno())

    def _available(self, stage=None):
        if self.busy or self.poisoned or self.closed:
            raise RuntimeError('Session unavailable. Preserve buffers and stop; do not reprogram or restart the kernel')
        if stage is not None and self.stage != stage:
            raise RuntimeError('Expected stage '+stage+'; current stage '+self.stage)

    def _poison(self):
        self.poisoned = True
        self.ready = False
        self.validation = None
        # Leave the crash marker active and retain the owning session/buffers.
        try:
            self._log('session_poisoned')
        except Exception:
            pass

    def program(self):
        self._available('preflight')
        # Repeat hashes just before programming in case files changed after construction.
        preflight(self.package)
        if platform.machine() not in ('armv7l', 'armv7'):
            raise RuntimeError('This package requires the ARMv7 PYNQ-Z2 board')
        board = os.environ.get('BOARD', '').lower().replace('_', '-').replace(' ', '')
        if board and board not in ('pynq-z2', 'pynqz2'):
            raise RuntimeError('Unexpected BOARD environment: '+board)
        manager = Path('/sys/class/fpga_manager/fpga0/state')
        if manager.exists() and 'error' in manager.read_text().lower():
            raise RuntimeError('FPGA manager reports an error. Stop and arrange board recovery')
        import pynq
        from pynq import Overlay, Clocks
        self.metadata['pynq_version'] = getattr(pynq, '__version__', 'unknown')
        model = Path('/proc/device-tree/model')
        self.metadata['board_model'] = model.read_text().strip('\x00') if model.exists() else 'unknown'
        guard = SessionGuard()
        guard.acquire(self)
        self.guard = guard
        try:
            self._log('metadata_parse_begin')
            self.overlay = Overlay(str(self.package/'ffn.bit'), download=False)
            desc = self.overlay.ip_dict['ffn_0']
            if int(desc['phys_addr']) != self.interface['control_base'] or int(desc['addr_range']) != 65536:
                raise ValueError('PYNQ parsed an unexpected control address')
            self._log('download_begin')
            self.overlay.download()
            self.clock_mhz = float(Clocks.fclk0_mhz)
            if abs(self.clock_mhz-100) > 0.1:
                raise ValueError('Unexpected PL clock: '+str(self.clock_mhz))
            if manager.exists() and manager.read_text().strip() != 'operating':
                raise RuntimeError('FPGA manager did not reach operating state')
            self.metadata['pl_clock_mhz'] = self.clock_mhz
            self.stage = 'programmed'
            self._log('download_pass_no_PL_reads_yet')
        except BaseException:
            self._poison()
            raise
        return {'stage': self.stage, 'clock_mhz': self.clock_mhz}

    @staticmethod
    def _idle(ctrl):
        if not (ctrl & 4) or ctrl & 0x81:
            raise RuntimeError('IP is not idle, or start/auto_restart is set: 0x%x' % ctrl)

    def check_control(self):
        self._available('programmed')
        from pynq import MMIO
        try:
            self._log('first_PL_read_begin')
            # Raw MMIO avoids binding a driver that might implicitly read registers.
            self.ip = MMIO(self.interface['control_base'], 65536)
            self._idle(self.ip.read(0))
            for offsets in (self.interface['offsets'][n] for n in ('parameters', 'input', 'output')):
                for offset in offsets:
                    if self.ip.read(offset) != 0:
                        raise RuntimeError('Pointer register did not reset to zero')
            if self.ip.read(self.interface['offsets']['operation']) != 0:
                raise RuntimeError('Operation register did not reset')
            self.stage = 'control'
            # Both guards must finish without issuing any DDR request. Proven by local RTL tests.
            if self._call(2, guard_only=True) != 2 or self._call(1, guard_only=True) != 1:
                raise RuntimeError('Invalid-operation or unloaded-state guard failed')
            self._log('control_and_unloaded_guards_pass')
        except BaseException:
            self._poison()
            raise
        return {'stage': self.stage, 'guards': 'pass'}

    def allocate_buffers(self):
        self._available('control')
        from pynq import allocate
        try:
            for name, size in (('params', 4144), ('input', 16), ('output', 16)):
                b = allocate(shape=(size,), dtype=self.np.uint64)
                self.buffers.append(b)  # Retain immediately, including on partial failure.
                setattr(self, name, b)
                addr = int(b.device_address)
                if addr % 64 or not 0 < addr < addr+b.nbytes <= self.interface['ddr_bytes']:
                    raise ValueError('Buffer is unaligned or outside mapped DDR')
                b[:] = 0
                b.flush()  # Clean output CPU cache lines before the first FPGA write too.
            spans = sorted((int(b.device_address), int(b.device_address)+b.nbytes) for b in self.buffers)
            if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
                raise ValueError('Overlapping buffers')
            self.stage = 'allocated'
            self._log('buffers_pass')
        except BaseException:
            # Hardware was idle and no DMA pointers were installed. Explicit close is safe.
            self.stage = 'allocation_failed'
            raise
        return {'stage': self.stage, 'addresses': [hex(int(b.device_address)) for b in self.buffers]}

    def _pointer(self, name, buffer):
        for i, offset in enumerate(self.interface['offsets'][name]):
            self.ip.write(offset, (int(buffer.device_address) >> (32*i)) & 0xffffffff)

    def _call(self, operation, timeout=5.0, guard_only=False):
        self._available('control' if guard_only else 'allocated')
        if timeout <= 0 or (guard_only and operation not in (1, 2)) or operation not in (0, 1, 2):
            raise ValueError('Invalid call')
        self.busy = True  # Protect ALL register accesses, including pointer setup and return status.
        try:
            self._idle(self.ip.read(0))  # Also clears a previous completion flag.
            if not guard_only:
                self._pointer('parameters', self.params)
                self._pointer('input', self.input)
                self._pointer('output', self.output)
            self.ip.write(self.interface['offsets']['operation'], operation)
            start = time.perf_counter()
            self.ip.write(0, 1)
            done_seen = False
            while True:
                ctrl = self.ip.read(0)
                # ap_done is sticky/clear-on-read; ap_idle is a separately
                # registered signal and may become visible on a later read.
                done_seen = done_seen or bool(ctrl & 2)
                if ctrl & 0x80:
                    raise RuntimeError('Unexpected auto_restart during operation')
                if done_seen and ctrl & 4 and not ctrl & 1:
                    self._idle(ctrl)
                    break
                if time.perf_counter()-start > timeout:
                    raise TimeoutError('No ap_done. Preserve buffers; stop board work')
            status = self.ip.read(self.interface['offsets']['return'])
            self.busy = False
            return status
        except BaseException:
            self._poison()
            raise

    def _expect(self, condition, message):
        if not condition:
            self._poison()
            raise RuntimeError(message)

    def load(self, name):
        self._available('allocated')
        allowed = {line.split()[0] for line in (self.package/'data/index.txt').read_text().splitlines()}
        if name not in allowed:
            raise ValueError('Unknown fixture')
        words = self.np.fromfile(str(self.package/'data'/name/'params.bin'), dtype='<u8')
        if words.size != 4144:
            raise ValueError('Bad parameters')
        self.ready = False
        start = now_ns()
        self.params[:] = words
        self.params.flush()
        status = self._call(0)
        elapsed = now_ns()-start
        self._expect(status == 0, 'LOAD returned '+str(status))
        self.ready = True
        return elapsed

    def infer(self, raw_input):
        self._available('allocated')
        if not self.ready:
            raise RuntimeError('LOAD required')
        x = self.np.asarray(raw_input)
        if x.shape != (64,) or x.dtype.kind not in 'iu' or self.np.any(x < -32768) or self.np.any(x > 32767):
            raise ValueError('Expected 64 signed 16-bit raw integer values')
        x = self.np.asarray(x, dtype='<i2')
        start = now_ns()
        self.input[:] = x.view('<u8')
        self.input.flush()
        status = self._call(1)
        self._expect(status == 0, 'RUN returned '+str(status))
        self.output.invalidate()
        result = self.output.view(self.np.int16).copy()
        return result, now_ns()-start

    def smoke(self):
        self._available('allocated')
        self._log('smoke_begin')
        self.load('random_506')
        x = self.np.fromfile(str(self.package/'data/random_506/input.bin'), dtype='<i2').reshape(64, 64)
        gold = self.np.fromfile(str(self.package/'data/random_506/output.bin'), dtype='<i2').reshape(64, 64)
        result, ns = self.infer(x[0])
        self._expect(self.np.array_equal(result, gold[0]), 'Smoke mismatch')
        self._log('smoke_pass')
        return {'correct': True, 'elapsed_ns': ns}

    def validate(self):
        self._available('allocated')
        self.validation = None
        results = []
        self._log('validation_begin')
        for line in (self.package/'data/index.txt').read_text().splitlines():
            name, count = line.split()
            count = int(count)
            load_ns = self.load(name)
            x = self.np.fromfile(str(self.package/'data'/name/'input.bin'), dtype='<i2').reshape(count, 64)
            gold = self.np.fromfile(str(self.package/'data'/name/'output.bin'), dtype='<i2').reshape(count, 64)
            for i in range(count):
                result, _ = self.infer(x[i])
                self._expect(self.np.array_equal(result, gold[i]), 'Mismatch: '+name+' input '+str(i))
            results.append({'case': name, 'inferences': count, 'load_ns': load_ns, 'correct': True})
        self.validation = results
        (self.package/'board_validation.json').write_text(json.dumps(
            {'metadata': self.metadata, 'results': results}, indent=2)+'\n')
        self._log('validation_pass')
        return results

    def benchmark(self):
        self._available('allocated')
        if not self.validation:
            raise RuntimeError('Call validate() successfully first')
        load_ns = self.load('random_506')
        x = self.np.fromfile(str(self.package/'data/random_506/input.bin'), dtype='<i2').reshape(64, 64)
        gold = self.np.fromfile(str(self.package/'data/random_506/output.bin'), dtype='<i2').reshape(64, 64)
        for i in range(20):
            result, _ = self.infer(x[i % 64])
            self._expect(self.np.array_equal(result, gold[i % 64]), 'Warm-up mismatch')
        samples = []
        self._log('benchmark_begin')
        with (self.package/'board_raw.csv').open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['round', 'iteration', 'input_index', 'elapsed_ns', 'correct'])
            for r in range(3):
                for i in range(1000):
                    idx = i % 64
                    result, ns = self.infer(x[idx])
                    ok = bool(self.np.array_equal(result, gold[idx]))
                    writer.writerow([r, i, idx, ns, int(ok)])
                    self._expect(ok, 'Benchmark mismatch')
                    samples.append(ns)
                f.flush()
        summary = {'metadata': self.metadata, 'metric': 'Python host end-to-end single-input inference',
                   'boundary': 'input copy/flush, control MMIO/poll, output invalidate/copy; no validation or CSV I/O',
                   'load_ns': load_ns, 'warmup_calls': 20, 'calls': len(samples),
                   'median_ns': float(self.np.median(samples)), 'p95_ns': float(self.np.percentile(samples, 95)),
                   'correct': True}
        (self.package/'board_results.json').write_text(json.dumps(summary, indent=2)+'\n')
        self._log('benchmark_pass')
        return summary

    def close(self):
        self._available()
        if self.stage == 'programmed':
            raise RuntimeError('Run check_control() before closing a programmed session')
        if self.stage != 'preflight':
            try:
                self._idle(self.ip.read(0))
            except BaseException:
                self._poison()
                raise
        for b in self.buffers:
            b.freebuffer()
        self.closed = True
        self.stage = 'closed'
        self._log('closed_buffers_released')
        if self.guard is not None:
            self.guard.release()
