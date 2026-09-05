from __future__ import annotations

import ctypes
import logging
import threading


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("hotkey_id", ctypes.c_uint32)]


class ExactMasterHotkey:
    """Register only Control+Command+M without monitoring keyboard input."""

    M_KEYCODE = 46
    COMMAND_MODIFIER = 1 << 8
    CONTROL_MODIFIER = 1 << 12
    EVENT_CLASS_KEYBOARD = int.from_bytes(b"keyb", "big")
    EVENT_HOTKEY_PRESSED = 5
    SIGNATURE = int.from_bytes(b"GPMM", "big")

    def __init__(self, callback, logger: logging.Logger):
        self.callback = callback
        self.logger = logger
        self.registered = False
        self._carbon = None
        self._hotkey_ref = ctypes.c_void_p()

    def start(self) -> bool:
        if threading.current_thread() is not threading.main_thread():
            self.logger.error("exact_master_hotkey_failed reason=not_main_thread")
            return False
        carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.RegisterEventHotKey.restype = ctypes.c_int32
        carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        carbon.UnregisterEventHotKey.restype = ctypes.c_int32
        carbon.ReceiveNextEvent.argtypes = [
            ctypes.c_uint32, ctypes.c_void_p, ctypes.c_double,
            ctypes.c_uint8, ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.ReceiveNextEvent.restype = ctypes.c_int32
        carbon.GetEventClass.argtypes = [ctypes.c_void_p]
        carbon.GetEventClass.restype = ctypes.c_uint32
        carbon.GetEventKind.argtypes = [ctypes.c_void_p]
        carbon.GetEventKind.restype = ctypes.c_uint32
        carbon.ReleaseEvent.argtypes = [ctypes.c_void_p]

        hotkey_id = EventHotKeyID(self.SIGNATURE, 1)
        status = carbon.RegisterEventHotKey(
            self.M_KEYCODE,
            self.COMMAND_MODIFIER | self.CONTROL_MODIFIER,
            hotkey_id,
            carbon.GetApplicationEventTarget(),
            0,
            ctypes.byref(self._hotkey_ref),
        )
        self._carbon = carbon
        self.registered = status == 0 and bool(self._hotkey_ref.value)
        if self.registered:
            self.logger.info(
                "exact_master_hotkey_registered hotkey=CTRL+CMD+M input_monitoring=false thread=main"
            )
        else:
            self.logger.error("exact_master_hotkey_failed status=%d", status)
        return self.registered

    def poll(self) -> bool:
        """Deliver one pending Carbon hot-key event on the registering thread."""
        if not self.registered or self._carbon is None:
            return False
        event = ctypes.c_void_p()
        result = self._carbon.ReceiveNextEvent(0, None, 0.0, 1, ctypes.byref(event))
        if result != 0 or not event.value:
            return False
        handled = False
        try:
            if (
                self._carbon.GetEventClass(event) == self.EVENT_CLASS_KEYBOARD
                and self._carbon.GetEventKind(event) == self.EVENT_HOTKEY_PRESSED
            ):
                self.callback()
                handled = True
        finally:
            self._carbon.ReleaseEvent(event)
        return handled

    def stop(self) -> None:
        if self.registered and self._carbon is not None and self._hotkey_ref.value:
            self._carbon.UnregisterEventHotKey(self._hotkey_ref)
        self.registered = False
        self._hotkey_ref = ctypes.c_void_p()
        self._carbon = None
