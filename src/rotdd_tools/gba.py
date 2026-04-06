"""
Helpers that are useful for any GBA ROM project.

Nothing in this module is specific to Shining Force. The goal is to keep the
generic pieces here so the ROTDD-specific logic stays isolated and obvious.
"""

from __future__ import annotations

from typing import Iterable


GBA_ROM_BASE = 0x08000000


def iter_find_all(data: bytes, needle: bytes) -> Iterable[int]:
    """Yield every match offset for a byte sequence."""
    start = 0
    while True:
        index = data.find(needle, start)
        if index == -1:
            return
        yield index
        start = index + 1


def rom_offset_to_pointer(offset: int, base: int = GBA_ROM_BASE) -> int:
    """Convert a ROM offset into the usual GBA pointer value."""
    return base + offset


def pointer_to_rom_offset(pointer: int, base: int = GBA_ROM_BASE) -> int:
    """Convert a GBA pointer value back into a ROM offset."""
    return pointer - base


def read_terminated_string(data: bytes, start: int, terminator: int = 0x00) -> bytes:
    """Read a terminated byte string from a ROM offset."""
    end = data.find(bytes([terminator]), start)
    if end == -1:
        end = len(data)
    return data[start:end]


def printable_ascii(byte_value: int) -> bool:
    """Return True when a byte falls in the printable ASCII range."""
    return 32 <= byte_value < 127


def format_ascii(chunk: bytes) -> str:
    """Format a byte slice as ASCII with dots for non-printable bytes."""
    return "".join(chr(byte) if printable_ascii(byte) else "." for byte in chunk)
