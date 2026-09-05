from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator
import json
import re


MEMORY_BLOCK = re.compile(r"<oai-mem-citation>.*?</oai-mem-citation>", re.I | re.S)
MEMORY_TAIL = re.compile(r"<oai-mem-citation>.*\Z", re.I | re.S)
DIRECTIVE = re.compile(
    r"::(?:codex-file-citation|code-comment|created-thread)\{.*?\}(?:\s*\n)?", re.I | re.S
)
INTERNAL_CITE = re.compile(r"(?:cite|filecite|genui).*?", re.S)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
MARKDOWN_LINK = re.compile(r"!?\[([^\]]+)\]\((?:[^()]+|\([^)]*\))*\)")


def sanitize_visible_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\ufeff", "")
    text = MEMORY_BLOCK.sub("", text)
    text = MEMORY_TAIL.sub("", text)
    text = DIRECTIVE.sub("", text)
    text = INTERNAL_CITE.sub("", text)
    # Defensive cleanup for orphaned citation fields that should never be spoken.
    text = re.sub(r"(?ms)^\s*(?:citation_entries|rollout_ids)\s*:?.*?(?=\n\S|\Z)", "", text)
    text = MARKDOWN_LINK.sub(r"\1", text)
    text = re.sub(r"(?m)^\s*```[^\n]*$", "", text)
    text = text.replace("```", "").replace("`", "")
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = HTML_TAG.sub("", text)
    text = CONTROL.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return ""
    # Raw internal JSON is never user-facing prose.
    if text[:1] in "[{" and text[-1:] in "]}":
        try:
            json.loads(text)
            return ""
        except Exception:
            pass
    return text


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", sanitize_visible_text(text)).strip()


def split_for_speech(text: str, max_chars: int = 900) -> list[str]:
    text = sanitize_visible_text(text)
    if not text:
        return []
    max_chars = max(80, max_chars)
    parts: list[str] = []
    rest = text
    while len(rest) > max_chars:
        window = rest[: max_chars + 1]
        cuts = [window.rfind(x) for x in ("\n\n", "。", "！", "？", ". ", "\n", "，", ", ", " ")]
        cut = max(cuts)
        if cut < max_chars // 3:
            cut = max_chars
        else:
            cut += 1
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        parts.append(rest)
    return [x for x in parts if x]


@dataclass(frozen=True)
class VisibleEvent:
    session_id: str
    turn_id: str
    message_id: str
    phase: str
    text: str
    timestamp: str

    @property
    def reply_id(self) -> str:
        return f"{self.session_id}:{self.turn_id}"


def extract_visible_event(record: dict, session_id: str, current_turn: str | None = None) -> VisibleEvent | None:
    if record.get("type") != "response_item":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "message" or payload.get("role") != "assistant":
        return None
    phase = payload.get("phase")
    if phase not in {"commentary", "final_answer"}:
        return None
    metadata = payload.get("internal_chat_message_metadata_passthrough")
    metadata = metadata if isinstance(metadata, dict) else {}
    # Messages explicitly routed to an internal agent are not screen-visible root replies.
    if metadata.get("recipient") not in {None, "", "user", "all"}:
        return None
    turn_id = str(metadata.get("turn_id") or current_turn or "unknown-turn")
    texts = []
    for item in payload.get("content", []):
        if isinstance(item, dict) and item.get("type") == "output_text":
            visible = sanitize_visible_text(item.get("text", ""))
            if visible:
                texts.append(visible)
    text = "\n".join(texts).strip()
    if not text:
        return None
    return VisibleEvent(
        session_id=session_id,
        turn_id=turn_id,
        message_id=str(payload.get("id") or f"{turn_id}:{record.get('timestamp','')}:{phase}"),
        phase=phase,
        text=text,
        timestamp=str(record.get("timestamp") or ""),
    )


def explicit_attention_event(record: dict) -> bool:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return False
    event_type = str(payload.get("type") or "").lower()
    return event_type in {
        "approval_request",
        "request_user_input",
        "user_input_required",
        "elicitation_request",
        "needs_user_action",
    }


@dataclass
class TurnSpeechState:
    commentary: list[str] = field(default_factory=list)
    message_ids: set[str] = field(default_factory=set)
    final_seen: bool = False

    def accept(self, event: VisibleEvent) -> str:
        if event.message_id in self.message_ids:
            return ""
        self.message_ids.add(event.message_id)
        if event.phase == "commentary":
            self.commentary.append(event.text)
            return event.text
        if self.final_seen:
            return ""
        self.final_seen = True
        final = event.text
        final_norm = normalize_text(final)
        if not final_norm:
            return ""
        # Stable turn identity plus a real prefix match is safer than time-only dedupe.
        candidates = [x for x in self.commentary if len(normalize_text(x)) >= 180]
        combined = "\n".join(candidates)
        for spoken in sorted(candidates + ([combined] if combined else []), key=len, reverse=True):
            spoken_norm = normalize_text(spoken)
            if spoken_norm and final_norm == spoken_norm:
                return ""
            if spoken_norm and final_norm.startswith(spoken_norm):
                # Locate a conservative boundary in the original final text.
                raw_pos = len(spoken)
                if normalize_text(final[:raw_pos]) == spoken_norm:
                    return final[raw_pos:].lstrip(" \n:：-—")
        # Short progress commentary must not suppress the actual final answer.
        return final


class CompleteLineReader:
    """Incremental binary reader that never advances across an unfinished JSONL tail."""

    @staticmethod
    def read(path: Path, offset: int) -> tuple[list[bytes], int]:
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
        if not data:
            return [], offset
        last_newline = data.rfind(b"\n")
        if last_newline < 0:
            return [], offset
        complete = data[: last_newline + 1]
        return complete.splitlines(), offset + last_newline + 1


def decode_json_line(raw: bytes) -> dict | None:
    try:
        return json.loads(raw.decode("utf-8-sig").rstrip("\r"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def iter_complete_records(path: Path) -> Iterator[dict]:
    lines, _ = CompleteLineReader.read(path, 0)
    for raw in lines:
        record = decode_json_line(raw)
        if record is not None:
            yield record


def iter_complete_records_reverse(path: Path, chunk_size: int = 65536) -> Iterator[dict]:
    """Yield complete JSONL records newest-first without loading a reply file into a cache."""
    size = path.stat().st_size
    if size == 0:
        return
    with path.open("rb") as handle:
        handle.seek(0, 2)
        end = handle.tell()
        # A non-newline tail is actively being written and must be ignored.
        handle.seek(end - 1)
        ends_complete = handle.read(1) == b"\n"
        position = end
        buffer = b""
        skipped_tail = ends_complete
        while position > 0:
            take = min(chunk_size, position)
            position -= take
            handle.seek(position)
            buffer = handle.read(take) + buffer
            parts = buffer.split(b"\n")
            buffer = parts[0]
            for raw in reversed(parts[1:]):
                if not skipped_tail:
                    skipped_tail = True
                    continue
                if not raw:
                    continue
                record = decode_json_line(raw)
                if record is not None:
                    yield record
        if buffer and skipped_tail:
            record = decode_json_line(buffer)
            if record is not None:
                yield record
