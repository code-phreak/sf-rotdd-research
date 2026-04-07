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
ROTDD_PUNCTUATION = {
    0x23: ".",
    0x25: ":",
    0x29: "?",
    0x67: ",",
    0x69: "'",
    0x1B: "!",
}
ROTDD_PUNCTUATION_BY_CHAR = {value: key for key, value in ROTDD_PUNCTUATION.items()}
ROTDD_SURFACE_CONTROLS = {
    0x09: "<PLAYER_NAME>",
    0x0A: "<NEWLINE>",
    0x0E: "<PAGE_BREAK>",
    0x03: "<SPEAKER_BREAK>",
}
ROTDD_SURFACE_CONTROLS_BY_TAG = {value: key for key, value in ROTDD_SURFACE_CONTROLS.items()}

# The dialogue/script surfaces we have seen also use a few bytes that are not
# fully translated yet. Keep them in the discovery alphabet so the scanner does
# not split strings at those boundaries.
ROTDD_SURFACE_UNKNOWN_CONTROLS = {
    0x02,
    0x05,
}

# Observed from the current dialogue corpus export: the widest visible line is
# 35 characters after tags are stripped. The box shows up to three stacked rows.
ROTDD_DIALOGUE_LINE_WIDTH = 35
ROTDD_DIALOGUE_VISIBLE_ROWS = 3

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


def encode_rotdd_surface_text(text: str) -> bytes:
    """
    Encode a text string that may include known inline tags.

    This is the right encoder for CSV-editable text because it preserves the
    same visible tokens that the corpus exporter emits.
    """

    encoded = bytearray()
    index = 0
    limit = len(text)
    while index < limit:
        char = text[index]
        if char == "<":
            close = text.find(">", index + 1)
            if close == -1:
                raise ValueError(f"Unterminated inline tag in text: {text!r}")
            tag = text[index : close + 1]
            if tag in ROTDD_SURFACE_CONTROLS_BY_TAG:
                encoded.append(ROTDD_SURFACE_CONTROLS_BY_TAG[tag])
                index = close + 1
                continue
            raw_hex = tag[1:-1]
            if len(raw_hex) == 2:
                try:
                    encoded.append(int(raw_hex, 16))
                    index = close + 1
                    continue
                except ValueError as exc:
                    raise ValueError(f"Unsupported inline tag in text: {tag!r}") from exc
            raise ValueError(f"Unsupported inline tag in text: {tag!r}")
        if char in ROTDD_PUNCTUATION_BY_CHAR:
            encoded.append(ROTDD_PUNCTUATION_BY_CHAR[char])
        else:
            encoded.append(encode_rotdd_char(char))
        index += 1
    return bytes(encoded)


def decode_rotdd_byte(byte: int) -> str:
    """Decode one byte from the known ROTDD table."""
    if byte == ROTDD_SPACE:
        return " "
    if byte in ROTDD_PUNCTUATION:
        return ROTDD_PUNCTUATION[byte]
    if byte in ROTDD_SURFACE_CONTROLS:
        return ROTDD_SURFACE_CONTROLS[byte]
    if ROTDD_UPPERCASE_MIN <= byte <= ROTDD_UPPERCASE_MAX:
        return chr(byte + ROTDD_UPPERCASE_SHIFT)
    if ROTDD_LOWERCASE_MIN <= byte <= ROTDD_LOWERCASE_MAX:
        return chr(byte + ROTDD_LOWERCASE_SHIFT)
    return f"<{byte:02X}>"


def is_known_rotdd_text_byte(byte: int) -> bool:
    """Return True when a byte belongs to the currently confirmed text alphabet."""
    return (
        byte == ROTDD_SPACE
        or ROTDD_UPPERCASE_MIN <= byte <= ROTDD_UPPERCASE_MAX
        or ROTDD_LOWERCASE_MIN <= byte <= ROTDD_LOWERCASE_MAX
    )


def is_known_rotdd_surface_byte(byte: int) -> bool:
    """Return True when a byte looks like part of ROTDD dialogue or script text."""
    return (
        is_known_rotdd_text_byte(byte)
        or byte in ROTDD_PUNCTUATION
        or byte in ROTDD_SURFACE_CONTROLS
        or byte in ROTDD_SURFACE_UNKNOWN_CONTROLS
    )


def decode_rotdd_bytes(chunk: bytes) -> str:
    """Decode bytes until a terminator or the end of the provided slice."""
    decoded: list[str] = []
    for byte in chunk:
        if byte == ROTDD_TERMINATOR:
            break
        decoded.append(decode_rotdd_byte(byte))
    return "".join(decoded)
