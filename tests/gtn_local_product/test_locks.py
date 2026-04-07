from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.gtn_local_product.locks import STALE_LOCK_SECONDS, acquire_lock, lock_status, release_lock
from runtime.gtn_local_product.models import LockInfo


class LockTests(unittest.TestCase):
    def test_stale_lock_when_pid_missing_and_old(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "lock.json"
            lock = LockInfo(pid=999999, run_id="run-1", runtime_repo_path="/tmp/repo", started_at="2026-04-07T00:00:00+08:00", trigger="manual")
            acquire_lock(lock_path, lock, now_epoch=100.0)
            self.assertEqual(lock_status(lock_path, now_epoch=100.0 + STALE_LOCK_SECONDS + 1), "stale")
            release_lock(lock_path)
            self.assertEqual(lock_status(lock_path), "none")


if __name__ == "__main__":
    unittest.main()
