from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from .models import LockInfo

STALE_LOCK_SECONDS = 5 * 60


class LockAcquisitionError(RuntimeError):
    pass


class ActiveRunError(RuntimeError):
    def __init__(self, lock: dict):
        self.lock = lock
        super().__init__("Another GTN run is currently active")


class StaleLockError(RuntimeError):
    def __init__(self, lock: dict):
        self.lock = lock
        super().__init__("A stale GTN lock exists")



def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True



def load_lock(lock_path: Path) -> dict | None:
    if not lock_path.exists():
        return None
    return json.loads(lock_path.read_text(encoding="utf-8"))



def lock_status(lock_path: Path, now_epoch: float | None = None) -> str:
    lock = load_lock(lock_path)
    if not lock:
        return "none"
    now = now_epoch or time.time()
    pid = int(lock.get("pid", -1))
    started_at_epoch = float(lock.get("started_at_epoch", 0))
    if _pid_exists(pid):
        return "active"
    if now - started_at_epoch > STALE_LOCK_SECONDS:
        return "stale"
    return "released"


def is_lock_stale(lock: dict, now_epoch: float | None = None) -> bool:
    now = now_epoch or time.time()
    pid = int(lock.get("pid", -1))
    if _pid_exists(pid):
        return False
    started_at_epoch = float(lock.get("started_at_epoch", 0))
    if started_at_epoch <= 0:
        return True
    return now - started_at_epoch > STALE_LOCK_SECONDS



def acquire_lock(lock_path: Path, lock: LockInfo, now_epoch: float | None = None) -> None:
    existing = load_lock(lock_path)
    if existing:
        status = lock_status(lock_path, now_epoch=now_epoch)
        if status == "active":
            raise ActiveRunError(existing)
        if status == "stale":
            raise StaleLockError(existing)
        lock_path.unlink(missing_ok=True)

    payload = asdict(lock)
    payload["started_at_epoch"] = now_epoch or time.time()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(lock_path, flags, 0o644)
    try:
        os.write(fd, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)



def release_lock(lock_path: Path) -> None:
    lock_path.unlink(missing_ok=True)
