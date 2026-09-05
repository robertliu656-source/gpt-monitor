from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import fcntl
import json
import os
import sys
import tempfile
import time

import psutil


BUNDLE_ID = "com.openclose.gptmonitor"


class InstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            return False

    def release(self) -> None:
        if self.handle:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def executable_path() -> str:
    return str(Path(sys.executable).resolve())


def process_record(role: str, extra: dict | None = None) -> dict:
    process = psutil.Process(os.getpid())
    record = {
        "pid": process.pid,
        "create_time": process.create_time(),
        "executable_path": str(Path(process.exe()).resolve()),
        "bundle_id": BUNDLE_ID,
        "role": role,
        "started_at": time.time(),
    }
    if extra:
        record.update(extra)
    return record


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def validate_pid_record(record: dict | None, role: str, expected_executable: str | None = None) -> bool:
    if not record or record.get("role") != role or record.get("bundle_id") != BUNDLE_ID:
        return False
    try:
        process = psutil.Process(int(record["pid"]))
        if abs(process.create_time() - float(record["create_time"])) > 0.2:
            return False
        recorded_exe = str(Path(record["executable_path"]).resolve())
        actual_exe = str(Path(process.exe()).resolve())
        if actual_exe != recorded_exe:
            return False
        if expected_executable and recorded_exe != str(Path(expected_executable).resolve()):
            return False
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (KeyError, ValueError, TypeError, psutil.Error, OSError):
        return False
