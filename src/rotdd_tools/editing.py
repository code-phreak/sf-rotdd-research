"""
Safe edit helpers for known ROTDD text tables.

The current editor is intentionally conservative. It keeps replacements within
the original byte budget for already mapped tables and always writes to a
copied ROM unless the caller explicitly opts into unsafe in-place writes.
"""

from __future__ import annotations

import re
from pathlib import Path

from .catalog import export_known_text_map
from .models import TextMapRow
from .gba import read_terminated_string
from .rotdd import (
    KNOWN_TEXT_TABLES,
    ROTDD_DIALOGUE_LINE_WIDTH,
    ROTDD_DIALOGUE_VISIBLE_ROWS,
    ROTDD_SPACE,
    ROTDD_TERMINATOR,
    decode_rotdd_bytes,
    encode_rotdd_surface_text,
)


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


def resolve_patch_output_path(
    source_path: Path,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> Path:
    """Resolve the final write target for a patch operation."""
    if in_place:
        if output_path is not None and source_path.resolve() != output_path.resolve():
            raise ValueError("Cannot combine --in-place with a separate output path.")
        return source_path

    final_output_path = output_path or derive_patched_output_path(source_path)
    if source_path.resolve() == final_output_path.resolve():
        raise ValueError("Refusing to overwrite the source ROM without --in-place.")
    if final_output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {final_output_path}")
    return final_output_path


def pad_rotdd_bytes(encoded: bytes, target_length: int) -> bytes:
    """Pad a replacement with ROTDD spaces on the right."""
    if len(encoded) > target_length:
        raise ValueError(
            f"Replacement is too long by {len(encoded) - target_length} encoded byte(s)."
        )
    if len(encoded) == target_length:
        return encoded
    return encoded + bytes([ROTDD_SPACE]) * (target_length - len(encoded))


def _visible_width(text: str) -> int:
    """Count visible characters after stripping inline tags."""
    return len(re.sub(r"<[^>]+>", "", text))


def _pad_visible_line(text: str) -> str:
    """Validate one text line against the observed dialogue width."""
    visible = _visible_width(text)
    if visible > ROTDD_DIALOGUE_LINE_WIDTH:
        raise ValueError(
            f"One explicit text line is {visible} characters wide; "
            f"the dialogue box only allows {ROTDD_DIALOGUE_LINE_WIDTH}."
        )
    return text.rstrip()


def _nudge_trailing_short_token(page_text: str) -> str:
    """
    Move a short trailing punctuation token onto its own line when it would
    otherwise be orphaned at the end of a wide line.
    """

    lines = page_text.split("<NEWLINE>")
    last_line = lines[-1].rstrip()
    if not last_line:
        return page_text

    visible = _visible_width(last_line)
    if visible < 24:
        return page_text

    match = re.match(r"^(.*\S)\s+(\S+)$", last_line)
    if not match:
        return page_text

    prefix, token = match.groups()
    token_visible = _visible_width(token)
    if token_visible > 4:
        return page_text
    if token.isalpha():
        return page_text
    if not any(char in token for char in "?!.,:;'\""):
        return page_text
    if not prefix.strip():
        return page_text

    lines[-1] = _pad_visible_line(prefix)
    lines.append(_pad_visible_line(token))
    if len(lines) > ROTDD_DIALOGUE_VISIBLE_ROWS:
        return page_text
    return "<NEWLINE>".join(lines)


def fit_surface_text_to_length(text: str, target_length: int) -> tuple[str, bytes, bool]:
    """
    Normalize surface text, then trim trailing padding spaces if needed so the
    encoded result still fits the original byte budget.
    """

    normalized, auto_wrapped = normalize_surface_replacement_text(text)
    encoded = encode_rotdd_surface_text(normalized)
    if len(encoded) <= target_length:
        return normalized, pad_rotdd_bytes(encoded, target_length), auto_wrapped

    parts = re.split(r"(<NEWLINE>|<PAGE_BREAK>|<SPEAKER_BREAK>)", normalized)
    trailing_indexes = [
        index
        for index, part in enumerate(parts)
        if part not in {"<NEWLINE>", "<PAGE_BREAK>", "<SPEAKER_BREAK>"}
    ]
    while len(encoded) > target_length:
        changed = False
        for index in reversed(trailing_indexes):
            part = parts[index]
            if part.endswith(" "):
                parts[index] = part.rstrip()
                changed = True
                candidate = "".join(parts)
                encoded = encode_rotdd_surface_text(candidate)
                if len(encoded) <= target_length:
                    normalized = candidate
                    return normalized, pad_rotdd_bytes(encoded, target_length), auto_wrapped
                break
        if not changed:
            break

    if len(encoded) > target_length:
        raise ValueError(
            f"Replacement is too long by {len(encoded) - target_length} encoded byte(s). "
            "Try shorter text or add another page break."
        )

    normalized = "".join(parts)
    return normalized, pad_rotdd_bytes(encoded, target_length), auto_wrapped


def normalize_surface_replacement_text(text: str) -> tuple[str, bool]:
    """
    Insert inline line breaks for dialogue-like text.

    The result keeps explicit tags intact, wraps on word boundaries, and limits
    the output to the three visible rows the box can show on each page.
    """

    tagged_text = re.sub(r"(<[^>]+>)", r" \1 ", text)
    tokens = re.findall(r"<[^>]+>|\S+|\s+", tagged_text)
    parts: list[str] = []
    current: list[str] = []
    current_width = 0
    page_rows = 0
    auto_wrapped = False

    def flush_line() -> None:
        nonlocal current, current_width, page_rows
        if not current:
            return
        line = "".join(current).rstrip()
        visible = _visible_width(line)
        page_rows += 1
        if page_rows > ROTDD_DIALOGUE_VISIBLE_ROWS:
            raise ValueError(
                f"Replacement would expand a page to {page_rows} visible line(s); "
                f"the dialogue box only has {ROTDD_DIALOGUE_VISIBLE_ROWS} rows per page."
            )
        parts.append(line)
        current = []
        current_width = 0

    for token in tokens:
        if token.isspace():
            if current and current[-1] != " ":
                current.append(" ")
                current_width += 1
            continue

        if token == "<PAGE_BREAK>":
            flush_line()
            parts.append(token)
            page_rows = 0
            continue

        if token in {"<NEWLINE>", "<SPEAKER_BREAK>"}:
            flush_line()
            parts.append(token)
            continue

        if token.startswith("<") and token.endswith(">"):
            current.append(token)
            continue

        word_width = len(token)
        if word_width > ROTDD_DIALOGUE_LINE_WIDTH:
            raise ValueError(
                f"Word {token!r} is {word_width} characters wide; "
                f"the dialogue box only allows {ROTDD_DIALOGUE_LINE_WIDTH}."
            )
        next_width = current_width + (1 if current and current[-1] != " " else 0) + word_width
        if current and next_width > ROTDD_DIALOGUE_LINE_WIDTH:
            flush_line()
            parts.append("<NEWLINE>")
            auto_wrapped = True
        if current and current[-1] != " ":
            current.append(" ")
            current_width += 1
        current.append(token)
        current_width += word_width

    flush_line()
    normalized = "".join(parts)
    if auto_wrapped:
        normalized = re.sub(r"(<NEWLINE>|<PAGE_BREAK>|<SPEAKER_BREAK>)\s+", r"\1", normalized)

    segments = re.split(r"(<PAGE_BREAK>|<SPEAKER_BREAK>)", normalized)
    rebuilt: list[str] = []
    for segment in segments:
        if segment in {"<PAGE_BREAK>", "<SPEAKER_BREAK>"}:
            rebuilt.append(segment)
            continue
        if not segment:
            continue
        rebuilt.append(_nudge_trailing_short_token(segment))
    normalized = "".join(rebuilt)
    return normalized, auto_wrapped


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
    in_place: bool,
) -> tuple[TextMapRow, bytes, Path]:
    """
    Patch a known text entry while keeping the encoded bytes within the
    original byte budget.

    This function only patches the encoded bytes for the selected text entry.
    The existing terminator byte remains untouched.
    """

    get_known_table(table_slug)
    rows = export_known_text_map(data)
    row = select_known_text_row(rows, table_slug, local_index, match_text, occurrence)

    if row.codec != "rotdd":
        raise ValueError(f"Unsupported patch codec for table '{table_slug}': {row.codec}")

    _normalized_text, replacement_bytes, auto_wrapped = fit_surface_text_to_length(
        replacement_text,
        row.text_length,
    )

    mutable = bytearray(data)
    start = row.text_rom_offset
    end = start + row.text_length
    mutable[start:end] = replacement_bytes

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    if auto_wrapped:
        print(
            f"Auto-wrapped replacement text to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of "
            f"{ROTDD_DIALOGUE_LINE_WIDTH} characters. Please review the result on screen."
        )
    return row, replacement_bytes, final_output_path


def patch_text_at_offset(
    data: bytes,
    source_path: Path,
    rom_offset: int,
    replacement_text: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> tuple[str, bytes, Path]:
    """
    Patch a ROTDD text run at a literal ROM offset while staying within the
    original byte budget.

    The replacement text may include the known inline tags used by the corpus
    exporter, so the CSV can be reused as a source of truth.
    """

    original_bytes = read_terminated_string(data, rom_offset, terminator=ROTDD_TERMINATOR)
    normalized_text, replacement_bytes, auto_wrapped = fit_surface_text_to_length(
        replacement_text,
        len(original_bytes),
    )

    mutable = bytearray(data)
    end = rom_offset + len(original_bytes)
    mutable[rom_offset:end] = replacement_bytes

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    if auto_wrapped:
        print(
            f"Auto-wrapped replacement text to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of "
            f"{ROTDD_DIALOGUE_LINE_WIDTH} characters. Please review the result on screen."
        )
    return decode_rotdd_bytes(original_bytes), replacement_bytes, final_output_path
