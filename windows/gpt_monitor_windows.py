"""GPT Monitor for Windows: local SAPI speech and registered global hotkeys."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import queue
import sys
import threading
import time

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app_files"))
from monitor import SessionMonitor

VERSION = "0.2.0"
PROMPTS = {
    "en": {"start": "GPT Monitor is listening", "attention": "Your attention is needed"},
    "zh": {"start": "GPT Monitor 开始监听", "attention": "需要你处理"},
}


def load_config(path):
    data = {"language": "en-US", "voice_name": "", "rate": "0", "volume": "70"}
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in raw and not raw.lstrip().startswith("#"):
                key, value = raw.split("=", 1)
                if key.strip() in data:
                    data[key.strip()] = value.strip()
    if not data["language"].lower().startswith(("en", "zh")):
        raise ValueError("language must be en-US or zh-CN")
    data["rate"] = max(-10, min(10, int(data["rate"])))
    data["volume"] = max(0, min(100, int(data["volume"])))
    return data


def voice_matches(language, lcid):
    # SAPI language attributes are hexadecimal Windows language IDs.
    wanted = 0x09 if language.lower().startswith("en") else 0x04
    for item in lcid.split(";"):
        try:
            if int(item, 16) & 0x3ff == wanted:
                return True
        except ValueError:
            pass
    return False


def run(root, config, smoke=False):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = None
    registered = []
    voice = None
    output_stream = None
    stop = threading.Event()
    status_path = root / "status.json"
    log = logging.getLogger("gpt-monitor-windows")
    log.setLevel(logging.INFO)
    handler = RotatingFileHandler(root / "monitor.log", maxBytes=1_000_000, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    try:
        mutex = kernel32.CreateMutexW(None, False, "Local\\OpenClose.GPTMonitor.Windows")
        if not mutex:
            raise OSError("Could not create single-instance lock")
        if kernel32.GetLastError() == 183:
            return 0
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voices = voice.GetVoices()
        chosen = None
        for index in range(voices.Count):
            candidate = voices.Item(index)
            name = candidate.GetDescription()
            if config["voice_name"]:
                match = config["voice_name"].casefold() in name.casefold()
            else:
                match = voice_matches(config["language"], candidate.GetAttribute("Language"))
            if match:
                chosen = candidate
                break
        if chosen is None:
            raise RuntimeError("No matching SAPI voice. Install a compatible Windows speech voice or set voice_name in config.txt. / 未找到对应的 Windows SAPI 语音，请安装语音或配置 voice_name。")
        voice.Voice = chosen
        voice.Rate = config["rate"]
        voice.Volume = config["volume"]
        if smoke:
            output_stream = win32com.client.Dispatch("SAPI.SpFileStream")
            output_stream.Open(str(root / "smoke-test.wav"), 3)
            voice.AudioOutputStream = output_stream
        lang = "en" if config["language"].startswith("en") else "zh"
        # MOD_NOREPEAT | MOD_CONTROL | MOD_ALT; OEM_2 is slash on a US keyboard.
        for ident, key in ((1, 0xBF), (2, ord("Q"))):
            if not user32.RegisterHotKey(None, ident, 0x4003, key):
                raise RuntimeError("Global shortcut is already in use. / 快捷键已被其他程序占用。")
            registered.append(ident)
        paused = False
        pending = queue.Queue(maxsize=128)

        def enqueue(event):
            try:
                pending.put_nowait(event)
            except queue.Full:
                log.warning("speech_queue_full message_dropped=true")

        monitor = SessionMonitor([Path.home() / ".codex" / "sessions"], 16, 900,
                                 enqueue, lambda: enqueue({"text": PROMPTS[lang]["attention"]}), log)

        def listen():
            while not stop.is_set():
                try:
                    monitor.scan_once()
                except Exception as exc:
                    log.warning("scan_failed reason=%s", type(exc).__name__)
                stop.wait(0.2)

        if not smoke:
            threading.Thread(target=listen, daemon=True).start()
        voice.Speak(PROMPTS[lang]["start"], 1 | 16)
        next_status = 0
        deadline = time.monotonic() + 3 if smoke else float("inf")
        msg = wintypes.MSG()
        while not stop.is_set() and time.monotonic() < deadline:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x312:
                    if msg.wParam == 2:
                        stop.set()
                    elif msg.wParam == 1:
                        if paused:
                            voice.Resume()
                        else:
                            voice.Pause()
                        paused = not paused
                        log.info("paused=%s", paused)
            # Drop new replies while paused; retain the current utterance only.
            if paused:
                while True:
                    try:
                        pending.get_nowait()
                    except queue.Empty:
                        break
            elif voice.Status.RunningState != 2:
                try:
                    event = pending.get_nowait()
                except queue.Empty:
                    event = None
                if event and event.get("text"):
                    voice.Speak(event["text"], 1 | 16)
            now = time.monotonic()
            if now >= next_status:
                state = {"version": VERSION, "pid": os.getpid(), "running": True,
                         "updated_at": time.time(), "language": config["language"],
                         "voice": chosen.GetDescription(), "rate": config["rate"],
                         "volume": config["volume"], "paused": paused,
                         "pause_hotkey": "Ctrl+Alt+/", "quit_hotkey": "Ctrl+Alt+Q"}
                temporary = status_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temporary, status_path)
                next_status = now + 1
            pythoncom.PumpWaitingMessages()
            time.sleep(0.03)
        return 0
    finally:
        stop.set()
        for ident in registered:
            user32.UnregisterHotKey(None, ident)
        if voice is not None:
            voice.Speak("", 2)
        if output_stream is not None:
            output_stream.Close()
        if registered:
            status_path.write_text(json.dumps({"version": VERSION, "running": False, "updated_at": time.time()}), encoding="utf-8")
        if mutex:
            kernel32.CloseHandle(mutex)
        pythoncom.CoUninitialize()
        handler.close()
        log.removeHandler(handler)


def main():
    args = argparse.ArgumentParser(description="GPT Monitor for Windows")
    args.add_argument("--smoke-test", action="store_true", help="Check SAPI and hotkey registration, then exit")
    options = args.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This entrypoint requires Windows")
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpenClose" / "GPT Monitor"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.txt"
    if not path.exists():
        bundled = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        template = bundled / "config.txt"
        path.write_text(template.read_text(encoding="utf-8-sig") if template.exists() else "language=en-US\nrate=0\nvolume=70\n", encoding="utf-8")
    try:
        return run(root, load_config(path), smoke=options.smoke_test)
    except Exception as exc:
        # No text from monitored replies is put into this dialog.
        if not options.smoke_test:
            ctypes.windll.user32.MessageBoxW(None, str(exc), "GPT Monitor", 0x10)
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
