"""
Safe edit helpers for known ROTDD text tables.

The current editor is intentionally conservative. It only supports same-length
replacements in already mapped tables, and it always writes to a copied ROM.
"""

from __future__ import annotations

from pathlib import Path

from .catalog import export_known_text_map
from .models import TextMapRow
from .rotdd import KNOWN_TEXT_TABLES, encode_rotdd_text


def get_known_table(table_slug: str):
    """Return table metadata for a known table slug."""
    for table in KNOWN_TEXT_TABLES:
        if table.slug == table_slug:
            return table
    raise ValueError(f"Unknown table slug: {table_slug}")


def select_known_text_row(
    rows: list[TextMapRow],
    table_slug: str,
    local_index: int | None,
    match_text: str | None,
    occurrence: int | None,
) -> TextMapRow:
    """
    Select a single known text row by index or decoded text.

    Index selection is the safest option because some visible strings appear
    more than once inside the same table.
    """

    table_rows = [row for row in rows if row.table_slug == table_slug]
    if local_index is not None:
        for row in table_rows:
            if row.local_index == local_index:
                return row
        raise ValueError(f"No row found for table '{table_slug}' at local index {local_index}.")

    assert match_text is not None
    matches = [row for row in table_rows if row.decoded_text == match_text]
    if not matches:
        raise ValueError(f"No row found for table '{table_slug}' with decoded text {match_text!r}.")
    if len(matches) == 1:
        return matches[0]
    if occurrence is None:
        available = ", ".join(str(row.local_index) for row in matches)
        raise ValueError(
            f"Decoded text {match_text!r} appears {len(matches)} times in table '{table_slug}'. "
            f"Pass --occurrence with a value from 0 to {len(matches) - 1}. "
            f"Matching local indices: {available}."
        )
    if occurrence < 0 or occurrence >= len(matches):
        available = ", ".join(str(row.local_index) for row in matches)
        raise ValueError(
            f"Occurrence {occurrence} is out of range for decoded text {match_text!r} in table '{table_slug}'. "
            f"Pass --occurrence with a value from 0 to {len(matches) - 1}. "
            f"Matching local indices: {available}."
        )
    return matches[occurrence]


def derive_patched_output_path(source_path: Path) -> Path:
    """Build a default output path that never points at the original ROM."""
    suffix = source_path.suffix or ".gba"
    return source_path.with_name(f"{source_path.stem}.patched{suffix}")


def ensure_safe_output_path(source_path: Path, output_path: Path, overwrite: bool) -> None:
    """Refuse risky output choices before writing a patched ROM."""
    if source_path.resolve() == output_path.resolve():
        raise ValueError("Refusing to overwrite the source ROM. Choose a different output path.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")


def patch_known_text(
    data: bytes,
    source_path: Path,
    table_slug: str,
    local_index: int | None,
    match_text: str | None,
    occurrence: int | None,
    replacement_text: str,
    output_path: Path | None,
    overwrite: bool,
) -> tuple[TextMapRow, bytes, Path]:
    """
    Patch a known text entry with a same-length replacement.

    This function only patches the encoded bytes for the selected text entry.
    The existing terminator byte remains untouched.
    """

    get_known_table(table_slug)
    rows = export_known_text_map(data)
    row = select_known_text_row(rows, table_slug, local_index, match_text, occurrence)

    if row.codec != "rotdd":
        raise ValueError(f"Unsupported patch codec for table '{table_slug}': {row.codec}")

    replacement_bytes = encode_rotdd_text(replacement_text)
    if len(replacement_bytes) != row.text_length:
        raise ValueError(
            f"Replacement length mismatch for {row.decoded_text!r}: "
            f"expected {row.text_length} encoded bytes, got {len(replacement_bytes)}."
        )

    mutable = bytearray(data)
    start = row.text_rom_offset
    end = start + row.text_length
    mutable[start:end] = replacement_bytes

    final_output_path = output_path or derive_patched_output_path(source_path)
    ensure_safe_output_path(source_path, final_output_path, overwrite=overwrite)
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    return row, replacement_bytes, final_output_path
