from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import hashlib
import json
import logging
import os
import time

from parser import (
    CompleteLineReader,
    TurnSpeechState,
    decode_json_line,
    explicit_attention_event,
    extract_visible_event,
    iter_complete_records,
    iter_complete_records_reverse,
    sanitize_visible_text,
    split_for_speech,
)


@dataclass
class FileState:
    offset: int
    current_turn: str | None = None


class SessionMonitor:
    def __init__(
        self,
        roots: list[Path],
        recent_files: int,
        max_chars: int,
        on_speech: Callable[[dict], None],
        on_attention: Callable[[], None],
        logger: logging.Logger,
        start_at_end: bool = True,
        on_reply_start: Callable[[str], None] | None = None,
    ) -> None:
        self.roots = roots
        self.recent_files = max(16, recent_files)
        self.max_chars = max_chars
        self.on_speech = on_speech
        self.on_attention = on_attention
        self.logger = logger
        self.start_at_end = start_at_end
        self.on_reply_start = on_reply_start or (lambda reply_id: None)
        self.started_at = time.time()
        self.files: dict[Path, FileState] = {}
        self.turns: dict[str, TurnSpeechState] = {}
        self.announced_turns: set[str] = set()
        self._running = True

    def discover(self) -> list[Path]:
        candidates: list[Path] = []
        for root in self.roots:
            if root.is_file() and root.suffix == ".jsonl":
                candidates.append(root)
            elif root.exists():
                candidates.extend(root.rglob("*.jsonl"))
        candidates = sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[: self.recent_files]

    def _session_id(self, path: Path) -> str:
        stem = path.stem
        if "-" in stem:
            return stem.rsplit("-", 5)[-5] + ":" + hashlib.sha1(str(path).encode()).hexdigest()[:8]
        return hashlib.sha1(str(path).encode()).hexdigest()[:16]

    def scan_once(self) -> int:
        count = 0
        for path in self.discover():
            if path not in self.files:
                # Existing files are baselined at EOF; files created after startup start at zero.
                is_new = path.stat().st_mtime >= self.started_at - 0.05
                offset = 0 if (is_new or not self.start_at_end) else path.stat().st_size
                self.files[path] = FileState(offset=offset)
                self.logger.info("session_added file=%s offset=%d", path.name, offset)
            state = self.files[path]
            try:
                lines, new_offset = CompleteLineReader.read(path, state.offset)
            except (FileNotFoundError, PermissionError, OSError) as exc:
                self.logger.warning("session_read_failed file=%s reason=%s", path.name, type(exc).__name__)
                continue
            for raw in lines:
                record = decode_json_line(raw)
                if record is None:
                    self.logger.warning("jsonl_line_skipped file=%s bytes=%d", path.name, len(raw))
                    continue
                payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
                if record.get("type") == "event_msg" and payload.get("type") == "task_started":
                    state.current_turn = str(payload.get("turn_id") or "") or None
                    if state.current_turn:
                        reply_id = f"{self._session_id(path)}:{state.current_turn}"
                        if reply_id not in self.announced_turns:
                            self.announced_turns.add(reply_id)
                            self.on_reply_start(reply_id)
                            self.logger.info("reply_started file=%s", path.name)
                if explicit_attention_event(record):
                    self.on_attention()
                event = extract_visible_event(record, self._session_id(path), state.current_turn)
                if not event:
                    continue
                turn = self.turns.setdefault(event.reply_id, TurnSpeechState())
                unread = turn.accept(event)
                if not unread:
                    self.logger.info("reply_dedup phase=%s file=%s chars=%d", event.phase, path.name, len(event.text))
                    continue
                segments = split_for_speech(unread, self.max_chars)
                for index, text in enumerate(segments):
                    self.on_speech({
                        "type": "speak",
                        "reply_id": event.reply_id,
                        "segment_id": f"{event.message_id}:{index}",
                        "text": text,
                        "phase": event.phase,
                    })
                    count += 1
                self.logger.info(
                    "visible_reply file=%s phase=%s chars=%d segments=%d",
                    path.name, event.phase, len(unread), len(segments),
                )
            state.offset = new_offset
        return count

    def run(self, poll_seconds: float) -> None:
        while self._running:
            self.scan_once()
            time.sleep(poll_seconds)

    def stop(self) -> None:
        self._running = False


def latest_complete_reply(roots: list[Path], recent_files: int = 16) -> str | None:
    """Demand-only reverse selection. Nothing is written or cached persistently."""
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".jsonl":
            files.append(root)
        elif root.exists():
            files.extend(root.rglob("*.jsonl"))
    files = sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)[: max(16, recent_files)]
    finals: list[tuple[str, str]] = []
    fallbacks: list[tuple[str, str]] = []
    for path in files:
        completed_turns: set[str] = set()
        # The newest files and newest complete lines are inspected first.
        for record in iter_complete_records_reverse(path):
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            if record.get("type") == "event_msg" and payload.get("type") == "task_complete":
                finished = str(payload.get("turn_id") or "")
                if finished:
                    completed_turns.add(finished)
                continue
            event = extract_visible_event(record, path.name, None)
            if not event:
                continue
            item = (event.timestamp, event.text)
            if event.phase == "final_answer":
                finals.append(item)
            elif event.turn_id in completed_turns:
                fallbacks.append(item)
    chosen = max(finals or fallbacks, key=lambda x: x[0], default=None)
    if not chosen:
        return None
    return sanitize_visible_text(chosen[1]) or None
