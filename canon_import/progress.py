from __future__ import annotations

import sys
import time
from typing import Optional

TTY_INTERVAL = 0.1
PLAIN_INTERVAL = 5.0
PLAIN_EVERY = 250


def _mb(n: float) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


def _fmt_time(seconds: float) -> str:
    s = int(max(seconds, 0))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


class Progress:
    """Small stderr progress bar: \\r updates on a TTY, sparse plain lines otherwise."""

    def __init__(self, label, total_items=None, total_bytes=None, enabled=True,
                 plain_every=PLAIN_EVERY, plain_interval=PLAIN_INTERVAL, width=24):
        self.label = label
        self.total_items = total_items
        self.total_bytes = total_bytes
        self.enabled = enabled
        self.plain_every = plain_every
        self.plain_interval = plain_interval
        self.width = width
        self.items = 0
        self.bytes = 0
        self.note = ""
        self.start = time.monotonic()
        self._last_draw = 0.0
        self._last_items = 0
        self._dirty_line = False
        self._finished = False

    def _stream(self):
        return sys.stderr

    def _tty(self) -> bool:
        try:
            return bool(self._stream().isatty())
        except Exception:
            return False

    def add_total(self, items: int = 0, nbytes: int = 0) -> None:
        if items:
            self.total_items = (self.total_items or 0) + items
        if nbytes:
            self.total_bytes = (self.total_bytes or 0) + nbytes

    def set_note(self, note: str) -> None:
        self.note = note
        self._maybe_draw(force=False)

    def update(self, items: int = 0, nbytes: int = 0, note: Optional[str] = None) -> None:
        self.items += items
        self.bytes += nbytes
        if note is not None:
            self.note = note
        self._maybe_draw()

    def line(self) -> str:
        elapsed = max(time.monotonic() - self.start, 1e-9)
        parts = [self.label]
        frac = None
        if self.total_bytes:
            frac = min(self.bytes / self.total_bytes, 1.0)
        elif self.total_items:
            frac = min(self.items / self.total_items, 1.0)
        if frac is not None:
            filled = int(frac * self.width)
            parts.append("[" + "#" * filled + "-" * (self.width - filled) + f"] {frac * 100:5.1f}%")
        if self.total_items is not None:
            parts.append(f"{self.items}/{self.total_items} files")
        else:
            parts.append(f"{self.items} files")
        if self.total_bytes is not None:
            parts.append(f"{_mb(self.bytes)}/{_mb(self.total_bytes)}")
        elif self.bytes:
            parts.append(_mb(self.bytes))
        if self.bytes:
            rate = self.bytes / elapsed
            parts.append(f"{rate / (1024 * 1024):.1f} MB/s")
        if frac is not None and frac > 0 and frac < 1.0:
            parts.append("ETA " + _fmt_time(elapsed * (1 - frac) / frac))
        if self.note:
            parts.append(self.note)
        return " ".join(parts)

    def _maybe_draw(self, force: bool = False) -> None:
        if not self.enabled or self._finished:
            return
        now = time.monotonic()
        if self._tty():
            if force or now - self._last_draw >= TTY_INTERVAL:
                self._last_draw = now
                self._write("\r" + self.line() + "\x1b[K")
                self._dirty_line = True
        else:
            if force or now - self._last_draw >= self.plain_interval or \
                    (self.items - self._last_items) >= self.plain_every:
                self._last_draw = now
                self._last_items = self.items
                self._write(self.line() + "\n")

    def _write(self, text: str) -> None:
        try:
            s = self._stream()
            s.write(text)
            s.flush()
        except Exception:
            pass

    def clear(self) -> None:
        """Erase the bar line so other output (prompts, logs) is not garbled."""
        if self.enabled and self._dirty_line:
            self._write("\r\x1b[K")
            self._dirty_line = False

    def finish(self) -> None:
        if not self.enabled or self._finished:
            return
        if self._tty():
            self._write("\r" + self.line() + "\x1b[K\n")
        else:
            self._write(self.line() + "\n")
        self._dirty_line = False
        self._finished = True
