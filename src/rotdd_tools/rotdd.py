"""
ROTDD-specific codec rules and known pointer-table coordinates.

These values should be treated as game-specific evidence, not generic GBA
assumptions. The comments are meant to make that boundary obvious.
"""

from __future__ import annotations

from .models import KnownTextTable


GAME_SLUG = "sf-rotdd"
GAME_TITLE = "Shining Force: Resurrection of the Dark Dragon"

# The currently confirmed custom codec for the spell, item, and related menu
# string bank in ROTDD.
ROTDD_TERMINATOR = 0x00
ROTDD_SPACE = 0x10
ROTDD_UPPERCASE_SHIFT = 0x16
ROTDD_LOWERCASE_SHIFT = 0x19
ROTDD_UPPERCASE_MIN = 0x2B
ROTDD_UPPERCASE_MAX = 0x44
ROTDD_LOWERCASE_MIN = 0x48
ROTDD_LOWERCASE_MAX = 0x63

KNOWN_TEXT_TABLES = [
    KnownTextTable(
        slug="system_terms",
        category="system",
        start_offset=0x0056ED80,
        count=4,
        codec="rotdd",
        notes="Small pre-spell table containing system or special-purpose labels.",
    ),
    KnownTextTable(
        slug="spell_names",
        category="spell",
        start_offset=0x0056ED90,
        count=51,
        codec="rotdd",
        notes="Confirmed spell and spell-adjacent menu labels.",
    ),
    KnownTextTable(
        slug="item_names",
        category="item",
        start_offset=0x0056EE5C,
        count=105,
        codec="rotdd",
        notes="Confirmed item display-name table.",
    ),
    KnownTextTable(
        slug="class_enemy_type_names_partial",
        category="class_or_enemy_type",
        start_offset=0x0056F000,
        count=64,
        codec="rotdd",
        notes="Confirmed contiguous table after item names. Current export is partial and should not be treated as complete.",
    ),
]


def encode_rotdd_char(char: str) -> int:
    """Encode one character with the currently known ROTDD table."""
    if char == " ":
        return ROTDD_SPACE
    if "A" <= char <= "Z":
        return ord(char) - ROTDD_UPPERCASE_SHIFT
    if "a" <= char <= "z":
        return ord(char) - ROTDD_LOWERCASE_SHIFT
    raise ValueError(f"Unsupported character for current ROTDD codec: {char!r}")


def encode_rotdd_text(text: str) -> bytes:
    """Encode a text string without appending a terminator byte."""
    return bytes(encode_rotdd_char(char) for char in text)


def decode_rotdd_byte(byte: int) -> str:
    """Decode one byte from the known ROTDD table."""
    if byte == ROTDD_SPACE:
        return " "
    if ROTDD_UPPERCASE_MIN <= byte <= ROTDD_UPPERCASE_MAX:
        return chr(byte + ROTDD_UPPERCASE_SHIFT)
    if ROTDD_LOWERCASE_MIN <= byte <= ROTDD_LOWERCASE_MAX:
        return chr(byte + ROTDD_LOWERCASE_SHIFT)
    return f"<{byte:02X}>"


def decode_rotdd_bytes(chunk: bytes) -> str:
    """Decode bytes until a terminator or the end of the provided slice."""
    decoded: list[str] = []
    for byte in chunk:
        if byte == ROTDD_TERMINATOR:
            break
        decoded.append(decode_rotdd_byte(byte))
    return "".join(decoded)
