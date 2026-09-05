from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import os
import shutil
import sys


DEFAULTS: dict[str, str] = {
    "language": "zh-CN",
    "voice": "zh-CN-YunxiNeural",
    "edge_rate": "+65%",
    "edge_volume": "+30%",
    "local_voice": "Tingting",
    "local_rate": "1.0",
    "local_wpm": "750",
    "local_volume": "0.7",
    "hotkeys_enabled": "false",
    "hotkey": "CTRL+CMD+/",
    "master_hotkey": "CTRL+CMD+M",
    "copy_hotkey": "CTRL+SHIFT+C",
    "poll_seconds": "0.1",
    "recent_files": "16",
    "max_chars": "900",
    "low_latency": "true",
    "announce_reply_start": "false",
    "prefer_latest_reply": "true",
    "read_full": "true",
    "translate_english": "true",
    "foreground_only": "false",
    "alert_enabled": "true",
    "alert_speak": "true",
    "stuck_backstop_enabled": "false",
    "stuck_seconds": "180",
    "alert_repeat_seconds": "120",
    "announce_errors": "true",
    "extra_roots": "",
}

ALIASES = {
    "CONTROL": "CTRL",
    "COMMAND": "CMD",
    "ALT": "OPTION",
}


def _bool(value: str, default: bool) -> bool:
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _int(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return min(max(int(value), minimum), maximum)
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float, minimum: float, maximum: float) -> float:
    try:
        return min(max(float(value), minimum), maximum)
    except (TypeError, ValueError):
        return default


def normalize_hotkey(value: str, default: str) -> str:
    parts = [ALIASES.get(x.strip().upper(), x.strip().upper()) for x in value.split("+") if x.strip()]
    valid_mods = {"CTRL", "CMD", "OPTION", "SHIFT"}
    if len(parts) < 2 or any(x not in valid_mods for x in parts[:-1]):
        return default
    key = parts[-1]
    if len(key) != 1 and key not in {"SLASH"}:
        return default
    if key == "SLASH":
        key = "/"
    return "+".join(parts[:-1] + [key])


@dataclass(frozen=True)
class AppPaths:
    support: Path
    state: Path
    logs: Path
    cache: Path
    config: Path
    launch_agent: Path

    @classmethod
    def current(cls, home: Path | None = None) -> "AppPaths":
        home = home or Path.home()
        support = home / "Library/Application Support/OpenClose/GPT Monitor"
        return cls(
            support=support,
            state=support / "state",
            logs=home / "Library/Logs/OpenClose/GPT Monitor",
            cache=home / "Library/Caches/OpenClose/GPT Monitor",
            config=support / "config.txt",
            launch_agent=home / "Library/LaunchAgents/com.openclose.gptmonitor.plist",
        )

    def ensure(self, template: Path | None = None) -> None:
        for path in (self.support, self.state, self.logs, self.cache, self.launch_agent.parent):
            path.mkdir(parents=True, exist_ok=True)
        if not self.config.exists():
            if template and template.exists():
                shutil.copy2(template, self.config)
            else:
                self.config.write_text("".join(f"{k}={v}\n" for k, v in DEFAULTS.items()), encoding="utf-8")


@dataclass(frozen=True)
class Config:
    values: dict[str, str]

    @classmethod
    def load(cls, path: Path, logger: logging.Logger | None = None) -> "Config":
        values = dict(DEFAULTS)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            text = ""
        except Exception as exc:
            if logger:
                logger.warning("config_read_failed reason=%s", type(exc).__name__)
            text = ""
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if "=" not in line:
                if logger:
                    logger.warning("config_invalid_line line=%d", number)
                continue
            key, value = (x.strip() for x in line.split("=", 1))
            if key not in DEFAULTS:
                if logger:
                    logger.warning("config_unknown_key key=%s", key)
                continue
            values[key] = value

        # The fixed cloud voice settings are part of the product contract.
        fixed = {key: DEFAULTS[key] for key in ("voice", "edge_rate", "edge_volume")}
        if values["language"].lower().startswith("en"):
            fixed["voice"] = "en-US-AriaNeural"
        for key, expected in fixed.items():
            if values[key] != expected:
                if logger:
                    logger.warning("config_fixed_value_restored key=%s", key)
                values[key] = expected
        values["hotkey"] = normalize_hotkey(values["hotkey"], DEFAULTS["hotkey"])
        values["master_hotkey"] = normalize_hotkey(values["master_hotkey"], DEFAULTS["master_hotkey"])
        values["copy_hotkey"] = normalize_hotkey(values["copy_hotkey"], DEFAULTS["copy_hotkey"])
        # Language-specific defaults apply unless explicitly configured.
        configured = {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.lstrip().startswith(("#", ";"))}
        if values["language"].lower().startswith("en"):
            for key, value in {"local_voice": "Samantha", "local_wpm": "220", "voice": "en-US-AriaNeural", "translate_english": "false"}.items():
                if key not in configured:
                    values[key] = value
        return cls(values)

    def bool(self, key: str) -> bool:
        return _bool(self.values[key], _bool(DEFAULTS[key], False))

    def integer(self, key: str, minimum: int = 0, maximum: int = 100000) -> int:
        return _int(self.values[key], int(DEFAULTS[key]), minimum, maximum)

    def number(self, key: str, minimum: float = 0, maximum: float = 100000) -> float:
        return _float(self.values[key], float(DEFAULTS[key]), minimum, maximum)

    def __getitem__(self, key: str) -> str:
        return self.values[key]


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def default_config_template() -> Path:
    return resource_root() / "config.txt"


def configure_logging(paths: AppPaths, role: str) -> logging.Logger:
    paths.logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"gpt_monitor.{role}")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            paths.logs / "gpt_monitor.log", maxBytes=2_000_000, backupCount=4, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    return logger


# Imported late so the module remains cheap and easy to unit-test.
import logging.handlers
