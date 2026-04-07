"""Structured data models used by the text-mapping workflow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownTextTable:
    """
    Metadata for a pointer table with a confirmed or partly confirmed purpose.

    The table coordinates are ROTDD-specific, but the shape itself is generic
    enough to reuse for other pointer-driven GBA projects later.
    """

    slug: str
    category: str
    start_offset: int
    count: int
    codec: str
    notes: str = ""


@dataclass(frozen=True)
class TextMapRow:
    """One exported row from a known text table."""

    game: str
    table_slug: str
    category: str
    local_index: int
    pointer_table_offset: int
    pointer_value: int
    text_rom_offset: int
    text_gba_address: int
    text_length: int
    codec: str
    decoded_text: str
    notes: str


@dataclass(frozen=True)
class TextSurfaceRow:
    """One exported row from a contiguous text surface such as dialogue or script text."""

    row_index: int
    source_kind: str
    rom_offset: int
    decoded_text: str


@dataclass(frozen=True)
class CharacterNameRow:
    """One exported row from the canonical character-name pointer table."""

    local_index: int
    pointer_table_offset: int
    pointer_value: int
    name_rom_offset: int
    name_length: int
    decoded_name: str


@dataclass(frozen=True)
class CharacterNameReferenceRow:
    """One exported row showing where a character name appears in the ROM."""

    row_index: int
    source_kind: str
    source_label: str
    source_index: int
    rom_offset: int
    decoded_text: str
