"""Check that remote orchestration rejects unsafe requests before board access."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_board


class RemoteRunnerGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = patch.object(run_board, 'ROOT', Path(self.tmp.name))
        root.start()
        self.addCleanup(root.stop)
        network = patch.object(run_board.requests, 'Session')
        self.network = network.start()
        self.addCleanup(network.stop)
        self.future = datetime.now(timezone.utc) + timedelta(hours=1)

    def test_expired_reservation_never_connects(self):
        with self.assertRaisesRegex(RuntimeError, 'ended'):
            run_board.Run('B11', 2, self.future - timedelta(hours=2), 'expired')
        self.network.assert_not_called()

    def test_timezone_is_required(self):
        with self.assertRaisesRegex(ValueError, 'UTC offset'):
            run_board.Run('B11', 2, self.future.replace(tzinfo=None), 'naive')
        self.network.assert_not_called()

    def test_run_id_cannot_escape_output_directory(self):
        for run_id in ('../elsewhere', '/tmp/elsewhere', '..', '.'):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                run_board.Run('B11', 2, self.future, run_id)
        self.network.assert_not_called()

    def test_old_state_cannot_be_reused_on_another_board(self):
        out = run_board.ROOT / 'results/board_runs/existing/B11'
        out.mkdir(parents=True)
        (out / 'remote_run.json').write_text(json.dumps({
            'board': 1, 'config': 'B11', 'reservation_end': self.future.isoformat()}))
        with self.assertRaisesRegex(RuntimeError, 'different board'):
            run_board.Run('B11', 2, self.future, 'existing')
        self.network.assert_not_called()

    def test_no_implicit_password_for_noninteractive_usage(self):
        with patch.dict(run_board.os.environ, {}, clear=True), patch.object(run_board.sys.stdin, 'isatty', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'PYNQ_PASSWORD'):
                run_board.Run('B11', 2, self.future, 'missing-password')
        self.network.assert_not_called()

    def test_uncertain_stage_cannot_be_relaunched(self):
        for flag in ('failure', 'active_stage'):
            run = object.__new__(run_board.Run)
            run.state = {'completed': ['setup'], flag: 'unknown'}
            run.execute = Mock()
            with self.subTest(flag=flag), self.assertRaisesRegex(RuntimeError, 'unknown'):
                run.stage('preflight')
            run.execute.assert_not_called()

    def test_stage_cannot_start_without_time_to_save(self):
        run = object.__new__(run_board.Run)
        run.end = datetime.now(timezone.utc) + timedelta(seconds=20)
        with patch.object(run_board.websocket, 'create_connection') as connection:
            with self.assertRaisesRegex(RuntimeError, 'Insufficient'):
                run.execute('session.program()', 45)
            connection.assert_not_called()

    def test_kernel_cannot_be_stopped_before_normal_close(self):
        run = object.__new__(run_board.Run)
        run.state = {'completed': ['setup', 'program']}
        run.api = Mock()
        with self.assertRaisesRegex(RuntimeError, 'verified normal close'):
            run.finish()
        run.api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
