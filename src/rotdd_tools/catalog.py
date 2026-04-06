"""
Known-table export helpers.

This module mixes generic pointer walking with ROTDD-specific table metadata.
The generic pointer math lives in `gba.py`; the hardcoded table coordinates live
in `rotdd.py`.
"""

from __future__ import annotations

from pathlib import Path

from .gba import GBA_ROM_BASE, pointer_to_rom_offset, read_terminated_string
from .models import TextMapRow
from .rotdd import GAME_SLUG, KNOWN_TEXT_TABLES, ROTDD_TERMINATOR, decode_rotdd_bytes


import csv


def decode_known_text(data: bytes, offset: int, codec: str) -> tuple[str, int]:
    """Decode a known text entry and return both text and byte length."""
    raw = read_terminated_string(data, offset, terminator=ROTDD_TERMINATOR)
    if codec != "rotdd":
        raise ValueError(f"Unsupported known-table codec: {codec}")
    return decode_rotdd_bytes(raw), len(raw)


def export_known_text_map(data: bytes) -> list[TextMapRow]:
    """
    Export a structured text map for the currently known ROTDD tables.

    This export is intentionally ROM-focused. It records confirmed pointer-table
    structure and decoded text, without mixing in unrelated RAM inventory data.
    """
    exported: list[TextMapRow] = []

    for table in KNOWN_TEXT_TABLES:
        for local_index in range(table.count):
            pointer_table_offset = table.start_offset + (local_index * 4)
            pointer_value = int.from_bytes(data[pointer_table_offset:pointer_table_offset + 4], "little")
            text_rom_offset = pointer_to_rom_offset(pointer_value, base=GBA_ROM_BASE)
            decoded_text, text_length = decode_known_text(data, text_rom_offset, table.codec)

            notes = table.notes

            if table.category == "item":
                if decoded_text in {"Card", "Used Card"}:
                    notes = (
                        f"{notes} Display name appears more than once in the pointer table."
                    ).strip()

            exported.append(
                TextMapRow(
                    game=GAME_SLUG,
                    table_slug=table.slug,
                    category=table.category,
                    local_index=local_index,
                    pointer_table_offset=pointer_table_offset,
                    pointer_value=pointer_value,
                    text_rom_offset=text_rom_offset,
                    text_gba_address=pointer_value,
                    text_length=text_length,
                    codec=table.codec,
                    decoded_text=decoded_text,
                    notes=notes,
                )
            )
    return exported


def write_text_map_csv(rows: list[TextMapRow], output_path: Path) -> None:
    """Write the structured text map to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "game",
        "table_slug",
        "category",
        "local_index",
        "pointer_table_offset",
        "pointer_value",
        "text_rom_offset",
        "text_gba_address",
        "text_length",
        "codec",
        "decoded_text",
        "notes",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "game": row.game,
                    "table_slug": row.table_slug,
                    "category": row.category,
                    "local_index": row.local_index,
                    "pointer_table_offset": f"0x{row.pointer_table_offset:08X}",
                    "pointer_value": f"0x{row.pointer_value:08X}",
                    "text_rom_offset": f"0x{row.text_rom_offset:08X}",
                    "text_gba_address": f"0x{row.text_gba_address:08X}",
                    "text_length": row.text_length,
                    "codec": row.codec,
                    "decoded_text": row.decoded_text,
                    "notes": row.notes,
                }
            )
