from __future__ import annotations

from pathlib import Path
import os
import shutil
import time
import re


def _assert_release_child(path: Path, dist: Path) -> None:
    resolved = path.resolve()
    parent = dist.resolve()
    if resolved.parent != parent or not re.fullmatch(r"GPTMonitor_Mac_\d+\.\d+\.\d+(?:-en)?(?:\.staging|\.backup\.\d+)?", resolved.name):
        raise ValueError(f"unsafe release path: {resolved}")


def atomic_promote(staging: Path, final: Path) -> None:
    dist = final.parent
    _assert_release_child(staging, dist)
    _assert_release_child(final, dist)
    if not staging.is_dir() or not (staging / "GPT Monitor.app").is_dir():
        raise ValueError("staging candidate is incomplete")
    backup = dist / f"{final.name}.backup.{int(time.time())}"
    if final.exists():
        final.rename(backup)
    try:
        staging.rename(final)
    except Exception:
        if backup.exists() and not final.exists():
            backup.rename(final)
        raise
    if backup.exists():
        _assert_release_child(backup, dist)
        shutil.rmtree(backup)


def clear_generated(path: Path, allowed_parent: Path) -> None:
    resolved = path.resolve()
    parent = allowed_parent.resolve()
    allowed = resolved.name in {"pyinstaller", "pyinstaller-work"} or re.fullmatch(r"GPTMonitor_Mac_\d+\.\d+\.\d+(?:-en)?\.staging", resolved.name)
    if resolved.parent != parent or not allowed:
        raise ValueError(f"unsafe generated path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
