from __future__ import annotations

import logging
import subprocess
import threading


class GlobalHotkeys:
    """A pass-through CGEventTap that observes the exact configured controls."""

    SLASH_KEYCODE = 44
    C_KEYCODE = 8
    M_KEYCODE = 46

    def __init__(
        self, on_toggle, on_skip, on_copy, on_master_toggle,
        logger: logging.Logger, double_seconds: float = 0.45,
    ):
        self.on_toggle = on_toggle
        self.on_skip = on_skip
        self.on_copy = on_copy
        self.on_master_toggle = on_master_toggle
        self.logger = logger
        self.double_seconds = double_seconds
        self.registered = False
        self.permission_granted = False
        self._thread = None
        self._timer: threading.Timer | None = None
        self._tap = None
        self._source = None
        self._run_loop = None
        self._ready = threading.Event()

    @staticmethod
    def preflight() -> bool:
        try:
            from Quartz import CGPreflightListenEventAccess
            return bool(CGPreflightListenEventAccess())
        except Exception:
            return False

    @staticmethod
    def request_access() -> bool:
        try:
            from Quartz import CGRequestListenEventAccess
            return bool(CGRequestListenEventAccess())
        except Exception:
            return False

    def start(self, request_permission: bool = True) -> bool:
        self.permission_granted = self.preflight()
        if not self.permission_granted and request_permission:
            self.permission_granted = self.request_access()
        # Preflight can lag System Settings state. Attempt the passive session tap and
        # treat the real creation result as authoritative.
        self._thread = threading.Thread(target=self._run, name="gpt-monitor-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self.registered

    def open_settings(self) -> None:
        subprocess.Popen([
            "/usr/bin/open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
        ])

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
        if self._run_loop is not None:
            try:
                from Quartz import CFRunLoopStop
                CFRunLoopStop(self._run_loop)
            except Exception:
                pass

    def _slash_press(self) -> None:
        if self._timer is not None and self._timer.is_alive():
            self._timer.cancel()
            self._timer = None
            self.on_skip()
            return
        def single() -> None:
            self._timer = None
            self.on_toggle()
        self._timer = threading.Timer(self.double_seconds, single)
        self._timer.daemon = True
        self._timer.start()

    def _run(self) -> None:
        from Quartz import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetCurrent,
            CFRunLoopRun,
            CGEventGetFlags,
            CGEventGetIntegerValueField,
            CGEventMaskBit,
            CGEventTapCreate,
            CGEventTapEnable,
            kCFRunLoopCommonModes,
            kCGEventFlagMaskCommand,
            kCGEventFlagMaskControl,
            kCGEventFlagMaskShift,
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventKeyDown,
            kCGKeyboardEventKeycode,
            kCGEventTapOptionListenOnly,
        )
        relevant = (
            kCGEventFlagMaskControl
            | kCGEventFlagMaskCommand
            | kCGEventFlagMaskShift
        )

        def callback(proxy, event_type, event, refcon):
            if event_type != kCGEventKeyDown:
                return event
            keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
            flags = int(CGEventGetFlags(event)) & relevant
            pause_flags = kCGEventFlagMaskControl | kCGEventFlagMaskCommand
            copy_flags = kCGEventFlagMaskControl | kCGEventFlagMaskShift
            if keycode == self.SLASH_KEYCODE and flags == pause_flags:
                self._slash_press()
            elif keycode == self.M_KEYCODE and flags == pause_flags:
                self.on_master_toggle()
            elif keycode == self.C_KEYCODE and flags == copy_flags:
                self.on_copy()
            return event  # Listen-only and explicitly pass through.

        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            CGEventMaskBit(kCGEventKeyDown),
            callback,
            None,
        )
        if self._tap is None:
            self.logger.error("hotkey_event_tap_create_failed")
            self.registered = False
            self.permission_granted = False
            self._ready.set()
            return
        self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._run_loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._run_loop, self._source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        self.permission_granted = True
        self.registered = True
        self._ready.set()
        self.logger.info(
            "hotkeys_registered pause=CTRL+CMD+/ master=CTRL+CMD+M copy=CTRL+SHIFT+C"
        )
        CFRunLoopRun()
        self.registered = False
