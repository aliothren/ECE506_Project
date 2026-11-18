"""Cooperative board-wide lock and crash marker. Never unlink the lock inode."""
import fcntl
import json
import os
from pathlib import Path

_LIVE = {}  # Strong references retain buffers even if the notebook variable is overwritten.


class SessionGuard:
    def __init__(self, root='/tmp/ece506_ffn', boot_id=None):
        self.root = str(root)
        self.boot_id = boot_id or Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.file = None
        self.state = Path(self.root+'.state.json')

    def acquire(self, owner):
        if self.root in _LIVE:
            raise RuntimeError('An FFN session already owns this board; reuse it or close it normally')
        f = open(self.root+'.lock', 'a+')
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.state.exists():
                previous = json.loads(self.state.read_text())
                if previous['boot_id'] == self.boot_id and previous['state'] != 'closed':
                    raise RuntimeError('An earlier session did not close safely. Stop; arrange board recovery. Restarting Jupyter is insufficient')
            self.file = f
            self.mark('active')  # Persist before any programming or MMIO.
            _LIVE[self.root] = owner
        except BaseException:
            self.file = None
            f.close()
            raise

    def mark(self, state):
        with self.state.open('w') as f:
            json.dump({'boot_id': self.boot_id, 'state': state, 'pid': os.getpid()}, f)
            f.flush()
            os.fsync(f.fileno())

    def release(self):
        if self.file is None or self.root not in _LIVE:
            raise RuntimeError('Cannot release a guard this session does not own')
        self.mark('closed')
        self.file.close()
        self.file = None
        _LIVE.pop(self.root, None)
