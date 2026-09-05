from __future__ import annotations

def copy_unicode(text: str) -> int:
    """Place original visible UTF-8 text on the macOS pasteboard without a reply file."""
    from AppKit import NSPasteboard, NSPasteboardTypeString
    board = NSPasteboard.generalPasteboard()
    board.clearContents()
    if not board.setString_forType_(text, NSPasteboardTypeString):
        raise RuntimeError("pasteboard_write_failed")
    written = board.stringForType_(NSPasteboardTypeString)
    if written is None or str(written) != text:
        raise RuntimeError("pasteboard_verify_failed")
    return len(text)


def read_unicode() -> str:
    from AppKit import NSPasteboard, NSPasteboardTypeString
    value = NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)
    return "" if value is None else str(value)
