from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest

import psutil
from i18n import message as localized_message

from config import AppPaths, Config, configure_logging, default_config_template, resource_root
from carbon_hotkey import ExactMasterHotkey
from launch_agent import bootstrap, bootout, loaded, write_launch_agent
from mac_audio import MacAudioEngine, SpeechJob
from mac_clipboard import copy_unicode
from mac_hotkeys import GlobalHotkeys
from monitor import SessionMonitor, latest_complete_reply
from process_guard import (
    InstanceLock,
    atomic_write_json,
    executable_path,
    process_record,
    read_json,
    validate_pid_record,
)


APP_VERSION = "0.2.0"
CONTROLLER_SOCKET = "controller.sock"
LISTENER_SOCKET = "listener.sock"


def command_prefix() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve())]


def managed_executable() -> str:
    return str(Path(sys.executable).resolve())


def send_datagram(path: Path, payload: dict, logger=None) -> bool:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > 48_000:
        if logger:
            logger.warning("ipc_message_too_large bytes=%d", len(data))
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(data, str(path))
        return True
    except OSError as exc:
        if logger:
            logger.warning("ipc_send_failed target=%s reason=%s", path.name, type(exc).__name__)
        return False
    finally:
        sock.close()


def bind_datagram(path: Path) -> socket.socket:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(str(path))
    sock.settimeout(0.5)
    return sock


def session_roots(config: Config) -> list[Path]:
    roots = [Path.home() / ".codex/sessions"]
    for raw in config["extra_roots"].split(os.pathsep):
        raw = raw.strip()
        if raw:
            roots.append(Path(raw).expanduser())
    return roots


class Controller:
    def __init__(self, paths: AppPaths, config: Config, no_greeting: bool = False):
        self.paths = paths
        self.config = config
        self.logger = configure_logging(paths, "controller")
        self.no_greeting = no_greeting
        self.stop_event = threading.Event()
        self.lock = InstanceLock(paths.state / "controller.lock")
        self.sock = None
        self.listener_process: subprocess.Popen | None = None
        self.audio = MacAudioEngine(
            config, paths.cache, self.logger, mute_state_path=paths.support / "muted.flag"
        )
        self.permission_announced = False
        self.hotkeys = GlobalHotkeys(
            self.audio.toggle_pause,
            self.audio.skip_current_reply,
            self.request_copy,
            self.toggle_master_mute,
            self.logger,
        )
        self.exact_master_hotkey = ExactMasterHotkey(self.toggle_master_mute, self.logger)

    def toggle_master_mute(self) -> None:
        muted = self.audio.toggle_master_mute()
        sound = "/System/Library/Sounds/Tink.aiff" if muted else "/System/Library/Sounds/Pop.aiff"
        try:
            subprocess.Popen(
                ["/usr/bin/afplay", sound],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            self.logger.warning("master_mute_cue_failed reason=%s", type(exc).__name__)

    def request_copy(self) -> None:
        send_datagram(self.paths.state / LISTENER_SOCKET, {"type": "copy"}, self.logger)

    def _start_listener(self) -> None:
        cmd = command_prefix() + ["--listener", "--no-greeting"]
        self.listener_process = subprocess.Popen(cmd, close_fds=True)
        self.logger.info("listener_started pid=%d", self.listener_process.pid)

    def _handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "speak":
            text = message.get("text")
            if isinstance(text, str) and text:
                self.audio.enqueue(SpeechJob(
                    str(message.get("reply_id") or "unknown"),
                    str(message.get("segment_id") or time.time_ns()),
                    text,
                ))
        elif kind == "copy_result":
            success = bool(message.get("success"))
            self.audio.announce_local(localized_message(self.config, "copied" if success else "copy_empty"), "copy-result")
        elif kind == "attention":
            if self.config.bool("alert_enabled"):
                if self.config.bool("alert_speak"):
                    self.audio.announce_local(localized_message(self.config, "attention"), "attention")
        elif kind == "reply_start":
            reply_id = str(message.get("reply_id") or "")
            if reply_id:
                self.audio.begin_reply(
                    reply_id,
                    announce=self.config.bool("announce_reply_start"),
                    prefer_latest=self.config.bool("prefer_latest_reply"),
                )
        elif kind == "control_start":
            self.audio.resume_if_paused()
            self.audio.announce_local(localized_message(self.config, "greeting"), "greeting")
            if (
                self.config.bool("hotkeys_enabled")
                and not self.hotkeys.permission_granted
                and not self.permission_announced
            ):
                self.permission_announced = True
                self.audio.announce_local(localized_message(self.config, "permission"), "permission")
                self.hotkeys.open_settings()
        elif kind == "control_stop":
            self.stop_event.set()

    def _receiver(self) -> None:
        while not self.stop_event.is_set():
            try:
                raw = self.sock.recv(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                message = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if isinstance(message, dict):
                self._handle(message)

    def _write_state(self) -> None:
        listener_record = read_json(self.paths.state / "listener.json")
        log_path = self.paths.logs / "gpt_monitor.log"
        extra = {
            "version": APP_VERSION,
            "hotkeys_enabled": self.config.bool("hotkeys_enabled"),
            "listener_pid": listener_record.get("pid") if listener_record else None,
            "hotkey_pause_registered": self.hotkeys.registered,
            "hotkey_copy_registered": self.hotkeys.registered,
            "hotkey_master_registered": (
                self.hotkeys.registered or self.exact_master_hotkey.registered
            ),
            "input_monitoring_permission": self.hotkeys.permission_granted,
            "paused": self.audio.paused,
            "speaking": self.audio.is_speaking,
            "playback_state": self.audio.state.value,
            "audio_worker_alive": self.audio.worker_alive,
            "audio_queue_depth": self.audio.queue_depth,
            "master_muted": self.audio.master_muted,
            "low_latency": self.config.bool("low_latency"),
            "local_voice": self.config["local_voice"],
            "local_wpm": self.config.integer("local_wpm", 120, 900),
            "local_volume": self.config.number("local_volume", 0.0, 1.0),
            "announce_reply_start": self.config.bool("announce_reply_start"),
            "prefer_latest_reply": self.config.bool("prefer_latest_reply"),
            "last_log_update": log_path.stat().st_mtime if log_path.exists() else None,
            "updated_at": time.time(),
        }
        atomic_write_json(self.paths.state / "controller.json", process_record("controller", extra))

    def run(self) -> int:
        if not self.lock.acquire():
            self.logger.info("controller_duplicate_prevented")
            return 0
        self.sock = bind_datagram(self.paths.state / CONTROLLER_SOCKET)
        self.audio.start()
        if self.config.bool("hotkeys_enabled"):
            self.hotkeys.start(request_permission=True)
            if not self.hotkeys.permission_granted:
                self.logger.warning("hotkeys_unavailable permission=input_monitoring")
        else:
            self.logger.info("hotkeys_disabled safe_mode=true")
            if not self.exact_master_hotkey.start():
                self.logger.warning("exact_master_hotkey_unavailable")
        self._start_listener()
        threading.Thread(target=self._receiver, name="gpt-monitor-controller-ipc", daemon=True).start()
        if not self.no_greeting:
            self.audio.announce_local(localized_message(self.config, "greeting"), "greeting")
        try:
            next_housekeeping = 0.0
            while not self.stop_event.is_set():
                self.exact_master_hotkey.poll()
                now = time.monotonic()
                if now >= next_housekeeping:
                    if self.listener_process and self.listener_process.poll() is not None:
                        self.logger.warning("listener_exited code=%s restart=true", self.listener_process.returncode)
                        time.sleep(1)
                        self._start_listener()
                    self._write_state()
                    next_housekeeping = now + 1.0
                self.stop_event.wait(0.05)
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        self.stop_event.set()
        self.hotkeys.stop()
        self.exact_master_hotkey.stop()
        self.audio.stop()
        if self.listener_process and self.listener_process.poll() is None:
            self.listener_process.terminate()
            try:
                self.listener_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.listener_process.kill()
        if self.sock:
            self.sock.close()
        (self.paths.state / CONTROLLER_SOCKET).unlink(missing_ok=True)
        (self.paths.state / "controller.json").unlink(missing_ok=True)
        self.lock.release()
        self.logger.info("controller_stopped")


class Listener:
    def __init__(self, paths: AppPaths, config: Config):
        self.paths = paths
        self.config = config
        self.logger = configure_logging(paths, "listener")
        self.lock = InstanceLock(paths.state / "listener.lock")
        self.stop_event = threading.Event()
        self.sock = None
        self.roots = session_roots(config)
        self.monitor = SessionMonitor(
            roots=self.roots,
            recent_files=config.integer("recent_files", 16, 256),
            max_chars=config.integer("max_chars", 80, 6000),
            on_speech=lambda m: send_datagram(paths.state / CONTROLLER_SOCKET, m, self.logger),
            on_attention=lambda: send_datagram(paths.state / CONTROLLER_SOCKET, {"type": "attention"}, self.logger),
            logger=self.logger,
            start_at_end=True,
            on_reply_start=lambda reply_id: send_datagram(
                paths.state / CONTROLLER_SOCKET,
                {"type": "reply_start", "reply_id": reply_id},
                self.logger,
            ),
        )

    def _commands(self) -> None:
        while not self.stop_event.is_set():
            try:
                raw = self.sock.recv(8192)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                message = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if message.get("type") != "copy":
                continue
            started = time.time()
            success = False
            chars = 0
            try:
                reply = latest_complete_reply(self.roots, self.config.integer("recent_files", 16, 256))
                if reply:
                    chars = copy_unicode(reply)
                    success = True
                reply = None  # Release the only complete-body variable immediately.
            except Exception as exc:
                self.logger.warning("copy_failed reason=%s", type(exc).__name__)
            self.logger.info("copy_result success=%s chars=%d duration_ms=%d", success, chars, int((time.time()-started)*1000))
            send_datagram(
                self.paths.state / CONTROLLER_SOCKET,
                {"type": "copy_result", "success": success, "chars": chars},
                self.logger,
            )

    def run(self) -> int:
        if not self.lock.acquire():
            self.logger.info("listener_duplicate_prevented")
            return 0
        self.sock = bind_datagram(self.paths.state / LISTENER_SOCKET)
        threading.Thread(target=self._commands, name="gpt-monitor-listener-ipc", daemon=True).start()
        try:
            while not self.stop_event.is_set():
                self.monitor.scan_once()
                atomic_write_json(
                    self.paths.state / "listener.json",
                    process_record("listener", {"updated_at": time.time(), "watched_files": len(self.monitor.files)}),
                )
                self.stop_event.wait(self.config.number("poll_seconds", 0.1, 10.0))
        finally:
            self.monitor.stop()
            if self.sock:
                self.sock.close()
            (self.paths.state / LISTENER_SOCKET).unlink(missing_ok=True)
            (self.paths.state / "listener.json").unlink(missing_ok=True)
            self.lock.release()
        return 0


def current_status(paths: AppPaths) -> tuple[dict, bool]:
    controller = read_json(paths.state / "controller.json")
    listener = read_json(paths.state / "listener.json")
    controller_ok = validate_pid_record(controller, "controller")
    listener_ok = validate_pid_record(listener, "listener")
    status = {
        "version": APP_VERSION,
        "hotkeys_enabled": bool(controller and controller.get("hotkeys_enabled")),
        "controller_running": controller_ok,
        "listener_running": listener_ok,
        "controller_pid": controller.get("pid") if controller_ok else None,
        "listener_pid": listener.get("pid") if listener_ok else None,
        "controller_create_time": controller.get("create_time") if controller_ok else None,
        "listener_create_time": listener.get("create_time") if listener_ok else None,
        "executable_path": controller.get("executable_path") if controller_ok else None,
        "launch_agent_loaded": loaded(),
        "hotkey_pause_registered": bool(controller and controller.get("hotkey_pause_registered")),
        "hotkey_copy_registered": bool(controller and controller.get("hotkey_copy_registered")),
        "hotkey_master_registered": bool(controller and controller.get("hotkey_master_registered")),
        "input_monitoring_permission": bool(controller and controller.get("input_monitoring_permission")),
        "paused": bool(controller and controller.get("paused")),
        "speaking": bool(controller and controller.get("speaking")),
        "audio_worker_alive": bool(controller and controller.get("audio_worker_alive")),
        "audio_queue_depth": controller.get("audio_queue_depth") if controller else None,
        "master_muted": bool(controller and controller.get("master_muted")),
        "low_latency": bool(controller and controller.get("low_latency")),
        "local_voice": controller.get("local_voice") if controller else None,
        "local_wpm": controller.get("local_wpm") if controller else None,
        "local_volume": controller.get("local_volume") if controller else None,
        "announce_reply_start": bool(controller and controller.get("announce_reply_start")),
        "prefer_latest_reply": bool(controller and controller.get("prefer_latest_reply")),
        "last_log_update": controller.get("last_log_update") if controller else None,
    }
    return status, controller_ok and listener_ok


def wait_for_socket(path: Path, seconds: float = 12) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.2)
    return False


def start_service(paths: AppPaths) -> int:
    status, running = current_status(paths)
    if not running:
        if not getattr(sys, "frozen", False):
            print("--start must be run from the packaged GPT Monitor.app", file=sys.stderr)
            return 2
        write_launch_agent(paths.launch_agent, managed_executable())
        bootstrap(paths.launch_agent)
        if not wait_for_socket(paths.state / CONTROLLER_SOCKET):
            print("GPT Monitor controller did not become ready", file=sys.stderr)
            return 1
    if not send_datagram(paths.state / CONTROLLER_SOCKET, {"type": "control_start"}):
        return 1
    return 0


def stop_service(paths: AppPaths) -> int:
    # Unload KeepAlive before asking the process to exit.
    bootout(paths.launch_agent)
    send_datagram(paths.state / CONTROLLER_SOCKET, {"type": "control_stop"})
    return 0


def run_selftest() -> int:
    tests = resource_root() / "tests" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent / "tests"
    suite = unittest.defaultTestLoader.discover(str(tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def run_local_voice_test(paths: AppPaths, config: Config) -> int:
    logger = configure_logging(paths, "local_voice_test")
    engine = MacAudioEngine(config, paths.cache, logger)
    engine.start()
    engine.announce_local(localized_message(config, "voice_test"), "local-voice-selftest")
    deadline = time.time() + 15
    started = False
    while time.time() < deadline:
        started = started or engine.is_speaking
        if started and not engine.is_speaking:
            engine.stop()
            print("local_voice_test=passed")
            return 0
        time.sleep(0.05)
    engine.stop()
    print("local_voice_test=failed", file=sys.stderr)
    return 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="GPT Monitor")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--start", action="store_true")
    actions.add_argument("--stop", action="store_true")
    actions.add_argument("--restart", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--selftest", action="store_true")
    actions.add_argument("--local-voice-test", action="store_true", help=argparse.SUPPRESS)
    actions.add_argument("--daemon", action="store_true")
    actions.add_argument("--listener", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-greeting", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    paths = AppPaths.current()
    paths.ensure(default_config_template())
    config = Config.load(paths.config)
    if args.selftest:
        return run_selftest()
    if args.local_voice_test:
        return run_local_voice_test(paths, config)
    if args.status:
        status, healthy = current_status(paths)
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if healthy else 1
    if args.stop:
        return stop_service(paths)
    if args.restart:
        stop_service(paths)
        time.sleep(1)
        return start_service(paths)
    if args.daemon:
        controller = Controller(paths, config, args.no_greeting)
        def stop_handler(signum, frame):
            controller.stop_event.set()
        signal.signal(signal.SIGTERM, stop_handler)
        signal.signal(signal.SIGINT, stop_handler)
        return controller.run()
    if args.listener:
        listener = Listener(paths, config)
        def listener_stop(signum, frame):
            listener.stop_event.set()
        signal.signal(signal.SIGTERM, listener_stop)
        signal.signal(signal.SIGINT, listener_stop)
        return listener.run()
    return start_service(paths)  # Double-click default.


if __name__ == "__main__":
    raise SystemExit(main())
