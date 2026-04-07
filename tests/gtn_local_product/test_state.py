import time
import unittest

from runtime.gtn_local_product.locks import STALE_LOCK_SECONDS, is_lock_stale


class StateTests(unittest.TestCase):
    def test_lock_not_stale_with_recent_missing_pid(self) -> None:
        now = time.time()
        lock = {"pid": 99999999, "started_at_epoch": now - 120}
        self.assertFalse(is_lock_stale(lock, now_epoch=now))

    def test_lock_stale_when_pid_missing_and_old(self) -> None:
        now = time.time()
        lock = {"pid": 99999999, "started_at_epoch": now - (STALE_LOCK_SECONDS + 1)}
        self.assertTrue(is_lock_stale(lock, now_epoch=now))


if __name__ == "__main__":
    unittest.main()
