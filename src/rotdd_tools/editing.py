"""
Safe edit helpers for known ROTDD text tables.

The current editor is intentionally conservative. It keeps replacements within
the original byte budget for already mapped tables and always writes to a
copied ROM unless the caller explicitly opts into unsafe in-place writes.
"""

from __future__ import annotations

import re
from pathlib import Path

from .catalog import (
    collect_named_entity_name_sets,
    export_character_name_map,
    export_item_name_map,
    iter_exact_name_ascii_runs,
    export_class_name_map,
    export_enemy_name_map,
    export_npc_name_map,
    export_known_text_map,
    export_text_surface_corpus,
    normalize_visible_name,
    iter_rotdd_surface_runs,
)
from .models import CharacterNameReferenceRow, CharacterNameRow, NpcNameRow, TextMapRow
from .gba import GBA_ROM_BASE, iter_find_all, printable_ascii, read_terminated_string
from .rotdd import (
    KNOWN_TEXT_TABLES,
    ROTDD_CHARACTER_NAME_REPOINT_END,
    ROTDD_CHARACTER_NAME_REPOINT_START,
    ROTDD_CHARACTER_NAME_MAX_LENGTH,
    ROTDD_CLASS_NAME_MAX_LENGTH,
    ROTDD_CLASS_NAME_TABLE_SLUG,
    ROTDD_ENEMY_NAME_MAX_LENGTH,
    ROTDD_ENEMY_NAME_TABLE_SLUG,
    ROTDD_ITEM_NAME_MAX_LENGTH,
    ROTDD_ITEM_NAME_TABLE_SLUG,
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


def pad_ascii_bytes(encoded: bytes, target_length: int) -> bytes:
    """Pad an ASCII string with spaces on the right."""
    if len(encoded) > target_length:
        raise ValueError(
            f"Replacement is too long by {len(encoded) - target_length} encoded byte(s)."
        )
    if len(encoded) == target_length:
        return encoded
    return encoded + b" " * (target_length - len(encoded))


def _visible_width(text: str) -> int:
    """Count visible characters after stripping inline tags."""
    return len(re.sub(r"<[^>]+>", "", text))


def replace_case_sensitive_name(text: str, current_name: str, replacement_name: str) -> tuple[str, bool]:
    """Replace a whole-name occurrence without touching longer words."""
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    updated, count = pattern.subn(replacement_name, text)
    return updated, count > 0


def _pad_visible_line(text: str) -> str:
    """Validate one text line against the observed dialogue width."""
    visible = _visible_width(text)
    if visible > ROTDD_DIALOGUE_LINE_WIDTH:
        raise ValueError(
            f"One explicit text line is {visible} characters wide; "
            f"the dialogue box only allows {ROTDD_DIALOGUE_LINE_WIDTH}."
        )
    return text.rstrip()


def _strip_unmapped_placeholders(text: str) -> tuple[str, int]:
    """
    Remove raw hex placeholders that we have not assigned meaning to yet.

    Confirmed timing bytes such as <02> and <05> are intentionally preserved.
    This fallback is only used when we need a tiny amount of extra room for a
    rename and the row contains bytes whose meaning is still unknown.
    """

    matches = [
        match
        for match in re.finditer(r"<([0-9A-F]{2})>", text)
        if match.group(1) not in {"02", "05"}
    ]
    if not matches:
        return text, 0

    stripped = text
    removed = 0
    for match in reversed(matches):
        stripped = stripped[:match.start()] + stripped[match.end():]
        removed += 1

    stripped = re.sub(r" {2,}", " ", stripped)
    return stripped, removed


def _nudge_trailing_short_token(page_text: str) -> str:
    """
    Move a short trailing punctuation token onto its own line when it would
    otherwise be orphaned at the end of a wide line.

    This also catches short punctuation-plus-quote tails such as `ME?!<QUOTE>`
    so quote runs stay attached to the word they belong to.
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
    if token_visible > 8:
        return page_text
    if token.isalpha():
        return page_text
    if not any(char in token for char in "?!.,:;'\"") and "<QUOTE>" not in token:
        return page_text
    if not prefix.strip():
        return page_text

    lines[-1] = _pad_visible_line(prefix)
    lines.append(_pad_visible_line(token))
    if len(lines) > ROTDD_DIALOGUE_VISIBLE_ROWS:
        return page_text
    return "<NEWLINE>".join(lines)


def _nudge_trailing_quote_cluster(page_text: str) -> str:
    """
    Move a short word plus trailing quote run onto its own line when the
    current line is already near the visible limit.
    """

    lines = page_text.split("<NEWLINE>")
    last_line = lines[-1].rstrip()
    if "<QUOTE>" not in last_line:
        return page_text

    parts = last_line.split()
    if len(parts) < 2:
        return page_text

    quote_count = 0
    index = len(parts) - 1
    while index >= 0 and parts[index] == "<QUOTE>":
        quote_count += 1
        index -= 1

    if quote_count == 0 or index < 0:
        return page_text

    tail_word = parts[index]
    tail_visible = _visible_width(tail_word)
    if tail_visible > 8:
        return page_text
    if not any(char in tail_word for char in "?!.,:;'\""):
        return page_text

    prefix = " ".join(parts[:index]).rstrip()
    if not prefix.strip():
        return page_text

    tail = " ".join(parts[index:]).rstrip()
    lines[-1] = _pad_visible_line(prefix)
    lines.append(_pad_visible_line(tail))
    if len(lines) > ROTDD_DIALOGUE_VISIBLE_ROWS:
        return page_text
    return "<NEWLINE>".join(lines)


def fit_surface_text_to_length(
    text: str,
    target_length: int,
    allow_placeholder_drop: bool = False,
) -> tuple[str, bytes, bool, int]:
    """
    Normalize surface text, then trim trailing padding spaces if needed so the
    encoded result still fits the original byte budget.
    """

    normalized, auto_wrapped = normalize_surface_replacement_text(text)
    encoded = encode_rotdd_surface_text(normalized)
    if len(encoded) <= target_length:
        return normalized, pad_rotdd_bytes(encoded, target_length), auto_wrapped, 0

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
                    return normalized, pad_rotdd_bytes(encoded, target_length), auto_wrapped, 0
                break
        if not changed:
            break

    if len(encoded) > target_length:
        if allow_placeholder_drop:
            stripped_text, dropped = _strip_unmapped_placeholders(normalized)
            if dropped:
                encoded = encode_rotdd_surface_text(stripped_text)
                if len(encoded) <= target_length:
                    return stripped_text, pad_rotdd_bytes(encoded, target_length), auto_wrapped, dropped
                normalized = stripped_text

        raise ValueError(
            f"Replacement is too long by {len(encoded) - target_length} encoded byte(s). "
            "Try shorter text or add another page break."
        )

    normalized = "".join(parts)
    return normalized, pad_rotdd_bytes(encoded, target_length), auto_wrapped, 0


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
        segment = _nudge_trailing_quote_cluster(segment)
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

    _normalized_text, replacement_bytes, auto_wrapped, dropped_unknowns = fit_surface_text_to_length(
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
    if dropped_unknowns:
        print(
            f"Dropped {dropped_unknowns} unmapped placeholder byte(s) to keep the replacement within the original budget."
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
    normalized_text, replacement_bytes, auto_wrapped, dropped_unknowns = fit_surface_text_to_length(
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
    if dropped_unknowns:
        print(
            f"Dropped {dropped_unknowns} unmapped placeholder byte(s) to keep the replacement within the original budget."
        )
    return decode_rotdd_bytes(original_bytes), replacement_bytes, final_output_path


def select_character_name_row(
    rows: list[CharacterNameRow],
    name: str,
) -> CharacterNameRow:
    """Select one character-name row by its decoded ASCII name."""

    matches = [row for row in rows if row.decoded_name == name]
    if not matches:
        raise ValueError(f"No character-name row found with decoded name {name!r}.")
    if len(matches) > 1:
        available = ", ".join(str(row.local_index) for row in matches)
        raise ValueError(
            f"Character name {name!r} appears {len(matches)} times. "
            f"Matching local indices: {available}."
        )
    return matches[0]


def select_npc_name_row(rows: list[NpcNameRow], name: str) -> NpcNameRow:
    """Select one NPC/speaker name row by its decoded speaker label."""

    matches = [row for row in rows if row.speaker_name == name]
    if not matches:
        raise ValueError(f"No NPC-name row found with decoded name {name!r}.")
    if len(matches) > 1:
        available = ", ".join(str(row.row_index) for row in matches)
        raise ValueError(
            f"NPC name {name!r} appears {len(matches)} times. "
            f"Matching row indices: {available}."
        )
    return matches[0]


def _collect_taken_entity_names(data: bytes) -> dict[str, set[str]]:
    """Collect the current ROM-visible names that should not be duplicated."""

    taken = collect_named_entity_name_sets(data)
    taken["npc"] = {normalize_visible_name(row.speaker_name) for row in export_npc_name_map(data)}
    return taken


def _ensure_replacement_name_is_unique(
    data: bytes,
    current_name: str,
    replacement_name: str,
    entity_label: str,
) -> None:
    """Reject renames that would create a duplicate name anywhere we track names."""

    normalized_current = normalize_visible_name(current_name)
    normalized_replacement = normalize_visible_name(replacement_name)

    if normalized_replacement == normalized_current:
        return

    conflict_sources = [
        label
        for label, names in _collect_taken_entity_names(data).items()
        if normalized_replacement in names
    ]
    if conflict_sources:
        sources = ", ".join(conflict_sources)
        raise ValueError(
            f"Replacement name {replacement_name!r} is already in use by {sources}. "
            f"Choose a unique replacement name before renaming the {entity_label}."
        )


def _find_zero_run(data: bytes, start: int, end: int, length: int) -> int:
    """Find a zero-filled region that can hold a repointed name."""

    needle = bytes([0x00]) * length
    index = data.find(needle, start, end)
    if index == -1:
        raise ValueError(
            "No free space was found for the longer character name. "
            "The current repointing rule only uses the observed padding before the name bank."
    )
    return index


def _find_global_zero_run(
    data: bytes,
    length: int,
    min_offset: int = 0x8000,
    reserved_ranges: list[tuple[int, int]] | None = None,
) -> int:
    """
    Find a zero-filled region in the ROM copy that is safely beyond the header.

    The minimum offset is intentionally conservative so we never repoint into the
    cartridge header or other early boot data just because it happens to contain
    zeros.
    """

    needle = bytes([0x00]) * length
    index = min_offset
    reserved_ranges = reserved_ranges or []
    while True:
        index = data.find(needle, index)
        if index == -1:
            raise ValueError("No free space was found for the longer replacement.")

        end = index + length
        if any(index < reserved_end and end > reserved_start for reserved_start, reserved_end in reserved_ranges):
            index += 1
            continue
        return index


def _find_pointer_hits(data: bytes, rom_offset: int) -> list[int]:
    """Return every pointer-table location that references a ROM offset."""

    pointer_value = (GBA_ROM_BASE + rom_offset).to_bytes(4, "little")
    return list(iter_find_all(data, pointer_value))


def _rewrite_pointer_hits(mutable: bytearray, pointer_hits: list[int], target_rom_offset: int) -> None:
    """Point every known pointer at the newly written replacement string."""

    pointer_value = (GBA_ROM_BASE + target_rom_offset).to_bytes(4, "little")
    for hit in pointer_hits:
        mutable[hit:hit + 4] = pointer_value


def _patch_rotdd_run(
    mutable: bytearray,
    data: bytes,
    rom_offset: int,
    original_length: int,
    current_name: str,
    replacement_name: str,
    reserved_ranges: list[tuple[int, int]] | None = None,
) -> tuple[bool, int, int, bool]:
    """Patch one ROTDD-encoded run inside a mutable ROM buffer."""

    original_bytes = bytes(mutable[rom_offset:rom_offset + original_length])
    original_text = decode_rotdd_bytes(original_bytes)
    updated_text, changed = replace_case_sensitive_name(original_text, current_name, replacement_name)
    if not changed:
        return False, rom_offset, original_length, False

    try:
        normalized_text, replacement_bytes, _auto_wrapped, _dropped_unknowns = fit_surface_text_to_length(
            updated_text,
            original_length,
            allow_placeholder_drop=True,
        )
    except ValueError:
        pointer_hits = _find_pointer_hits(data, rom_offset)
        if not pointer_hits:
            raise ValueError(
                "Replacement is too long for this inline text run and no pointer table was found."
            )

        normalized_text, _auto_wrapped = normalize_surface_replacement_text(updated_text)
        replacement_bytes = encode_rotdd_surface_text(normalized_text) + bytes([ROTDD_TERMINATOR])
        target_rom_offset = _find_global_zero_run(
            data,
            len(replacement_bytes),
            reserved_ranges=reserved_ranges,
        )
        mutable[target_rom_offset:target_rom_offset + len(replacement_bytes)] = replacement_bytes
        _rewrite_pointer_hits(mutable, pointer_hits, target_rom_offset)
        return True, target_rom_offset, len(replacement_bytes), _auto_wrapped

    mutable[rom_offset:rom_offset + original_length] = replacement_bytes
    return True, rom_offset, len(replacement_bytes), False


def _patch_ascii_run(
    mutable: bytearray,
    data: bytes,
    rom_offset: int,
    original_length: int,
    current_name: str,
    replacement_name: str,
    reserved_ranges: list[tuple[int, int]] | None = None,
) -> tuple[bool, int, int]:
    """Patch one plain-ASCII run inside a mutable ROM buffer."""

    original_bytes = bytes(mutable[rom_offset:rom_offset + original_length])
    original_text = original_bytes.decode("ascii", errors="strict")
    updated_text, changed = replace_case_sensitive_name(original_text, current_name, replacement_name)
    if not changed:
        return False, rom_offset, original_length

    payload = updated_text.encode("ascii") + bytes([0x00])
    if len(payload) <= (original_length + 1):
        mutable[rom_offset:rom_offset + len(payload)] = payload
        if len(payload) < (original_length + 1):
            mutable[rom_offset + len(payload):rom_offset + original_length + 1] = bytes([0x00]) * (
                (original_length + 1) - len(payload)
            )
        return True, rom_offset, len(payload)

    pointer_hits = _find_pointer_hits(data, rom_offset)
    if not pointer_hits:
        raise ValueError("Replacement is too long for this ASCII string and no pointer table was found.")

    target_rom_offset = _find_global_zero_run(
        data,
        len(payload),
        reserved_ranges=reserved_ranges,
    )
    mutable[target_rom_offset:target_rom_offset + len(payload)] = payload
    _rewrite_pointer_hits(mutable, pointer_hits, target_rom_offset)
    return True, target_rom_offset, len(payload)


def patch_character_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> tuple[CharacterNameRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """
    Patch a character name at its canonical source and in every matched text row.

    The canonical pointer table is updated first. Then the tool scans the known
    ROTDD text tables and the broader text-surface corpus for case-sensitive
    whole-name matches. Each matched row is rewritten in memory and written once
    at the end so the command stays reproducible and easy to audit.
    """

    name_rows = export_character_name_map(data)
    canonical_row = select_character_name_row(name_rows, current_name)
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, "character")

    try:
        replacement_bytes = replacement_name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Character names must be plain ASCII for now.") from exc

    if not replacement_bytes:
        raise ValueError("Character names cannot be empty.")
    if len(replacement_bytes) > ROTDD_CHARACTER_NAME_MAX_LENGTH:
        raise ValueError(
            f"Character names are currently limited to {ROTDD_CHARACTER_NAME_MAX_LENGTH} ASCII characters."
        )

    mutable = bytearray(data)
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    target_rom_offset = canonical_row.name_rom_offset
    pointer_value = canonical_row.pointer_value
    payload = replacement_bytes + bytes([0x00])
    reserved_ranges: list[tuple[int, int]] = []

    if len(payload) <= (canonical_row.name_length + 1):
        start = canonical_row.name_rom_offset
        end = start + canonical_row.name_length + 1
        mutable[start:start + len(payload)] = payload
        if len(payload) < (canonical_row.name_length + 1):
            mutable[start + len(payload):end] = bytes([0x00]) * (end - (start + len(payload)))
    else:
        target_rom_offset = _find_zero_run(
            data=bytes(mutable),
            start=ROTDD_CHARACTER_NAME_REPOINT_START,
            end=ROTDD_CHARACTER_NAME_REPOINT_END,
            length=len(payload),
        )
        mutable[target_rom_offset:target_rom_offset + len(payload)] = payload
        pointer_value = GBA_ROM_BASE + target_rom_offset
        mutable[canonical_row.pointer_table_offset:canonical_row.pointer_table_offset + 4] = (
            pointer_value.to_bytes(4, "little")
        )
        reserved_ranges.append((target_rom_offset, target_rom_offset + len(payload)))

    patched_rows: list[CharacterNameReferenceRow] = [
        CharacterNameReferenceRow(
            row_index=0,
            source_kind="canonical_name",
            source_label="character-name-table",
            source_index=canonical_row.local_index,
            rom_offset=target_rom_offset,
            decoded_text=replacement_name,
        )
    ]
    skipped_rows: list[CharacterNameReferenceRow] = []
    patched_offsets: set[int] = {canonical_row.name_rom_offset}
    canonical_source_end = canonical_row.name_rom_offset + canonical_row.name_length + 1
    patched_ranges: list[tuple[int, int]] = [
        (canonical_row.name_rom_offset, canonical_source_end),
        (target_rom_offset, target_rom_offset + len(payload)),
    ]

    known_rows = export_known_text_map(data)
    for row in known_rows:
        if not pattern.search(row.decoded_text):
            continue
        if any(start <= row.text_rom_offset < end for start, end in patched_ranges):
            continue
        if row.codec != "rotdd":
            raise ValueError(f"Unsupported patch codec for table '{row.table_slug}': {row.codec}")

        try:
            changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                mutable=mutable,
                data=data,
                rom_offset=row.text_rom_offset,
                original_length=row.text_length,
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="known_text",
                    source_label=row.table_slug,
                    source_index=row.local_index,
                    rom_offset=row.text_rom_offset,
                    decoded_text=row.decoded_text,
                )
            )
            continue
        if not changed:
            continue

        patched_offsets.add(row.text_rom_offset)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="known_text",
                source_label=row.table_slug,
                source_index=row.local_index,
                rom_offset=target_rom_offset,
                decoded_text=row.decoded_text,
            )
        )
        if auto_wrapped:
            print(
                f"Auto-wrapped replacement text for {row.table_slug}[{row.local_index}] "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    surface_rows = export_text_surface_corpus(data)
    for row in surface_rows:
        if not pattern.search(row.decoded_text):
            continue
        if row.rom_offset in patched_offsets:
            continue
        if any(start <= row.rom_offset < end for start, end in patched_ranges):
            continue

        original_length = len(read_terminated_string(data, row.rom_offset, terminator=ROTDD_TERMINATOR))
        if row.source_kind == "rotdd":
            try:
                changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    original_length=original_length,
                    current_name=current_name,
                    replacement_name=replacement_name,
                )
            except ValueError:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                    )
                )
                continue
        else:
            try:
                # ASCII surface rows can also repoint when they outgrow the
                # original slot, so they must participate in the same reserved
                # free-space pool as the ROTDD surface paths above.
                changed, target_rom_offset, payload_length = _patch_ascii_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    original_length=original_length,
                    current_name=current_name,
                    replacement_name=replacement_name,
                    reserved_ranges=reserved_ranges,
                )
            except ValueError:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                    )
                )
                continue

        if not changed:
            continue

        patched_offsets.add(row.rom_offset)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind=f"text_surface:{row.source_kind}",
                source_label="surface-corpus",
                source_index=row.row_index,
                rom_offset=target_rom_offset,
                decoded_text=row.decoded_text,
            )
        )
        if row.source_kind == "rotdd" and auto_wrapped:
            print(
                f"Auto-wrapped replacement text for surface row {row.row_index} "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    for run_start, text in iter_exact_name_ascii_runs(data, current_name):
        if run_start in patched_offsets:
            continue
        if any(start <= run_start < end for start, end in patched_ranges):
            continue

        try:
            changed, target_rom_offset, payload_length = _patch_ascii_run(
                mutable=mutable,
                data=data,
                rom_offset=run_start,
                original_length=len(text),
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="ascii_exact_name",
                    source_label="exact_name_hit",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=text,
                )
            )
            continue

        if not changed:
            continue

        patched_offsets.add(run_start)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="ascii_exact_name",
                source_label="exact_name_hit",
                source_index=run_start,
                rom_offset=target_rom_offset,
                decoded_text=text,
            )
        )

    for run_start, run_bytes, decoded_text in iter_rotdd_surface_runs(data):
        if run_start in patched_offsets:
            continue
        if any(start <= run_start < end for start, end in patched_ranges):
            continue
        if not pattern.search(decoded_text):
            continue

        original_length = len(read_terminated_string(data, run_start, terminator=ROTDD_TERMINATOR))
        try:
            changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                mutable=mutable,
                data=data,
                rom_offset=run_start,
                original_length=original_length,
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="rotdd_surface_run",
                    source_label="surface-run",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=decoded_text,
                )
            )
            continue

        if not changed:
            continue

        patched_offsets.add(run_start)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="rotdd_surface_run",
                source_label="surface-run",
                source_index=run_start,
                rom_offset=target_rom_offset,
                decoded_text=decoded_text,
            )
        )
        if auto_wrapped:
            print(
                f"Auto-wrapped replacement text for surface run at 0x{run_start:08X} "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    ascii_index = 0
    limit = len(data)
    while ascii_index < limit:
        if not printable_ascii(data[ascii_index]):
            ascii_index += 1
            continue

        run_start = ascii_index
        run: list[int] = []
        while ascii_index < limit and printable_ascii(data[ascii_index]):
            run.append(data[ascii_index])
            ascii_index += 1

        original_text = bytes(run).decode("ascii", errors="replace")
        if not pattern.search(original_text):
            continue
        if any(start <= run_start < end for start, end in patched_ranges):
            continue

        try:
                changed, target_rom_offset, payload_length = _patch_ascii_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=run_start,
                    original_length=len(run),
                    current_name=current_name,
                    replacement_name=replacement_name,
                    reserved_ranges=reserved_ranges,
                )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="ascii_surface",
                    source_label="printable_ascii",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=original_text,
                )
            )
            continue

        if not changed:
            continue

        patched_offsets.add(run_start)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="ascii_surface",
                source_label="printable_ascii",
                source_index=run_start,
                rom_offset=target_rom_offset,
                decoded_text=original_text,
            )
        )

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    return canonical_row, patched_rows, skipped_rows, final_output_path


def _patch_named_table_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    table_rows: list[TextMapRow],
    table_slug: str,
    table_label: str,
    table_row_source_kind: str,
    max_length: int,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """
    Patch one visible-name table across the confirmed table slice and all
    matched visible references.

    The implementation mirrors the playable-character rename workflow, but it
    starts from the dedicated name-table slice instead of the character-name
    pointer table.
    """

    source_rows = [row for row in table_rows if row.decoded_text == current_name]
    if not source_rows:
        raise ValueError(f"No {table_label}-name row found with decoded text {current_name!r}.")
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, table_label)

    try:
        replacement_bytes = replacement_name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{table_label.capitalize()} names must be plain ASCII for now.") from exc

    if not replacement_bytes:
        raise ValueError(f"{table_label.capitalize()} names cannot be empty.")
    if len(replacement_bytes) > max_length:
        raise ValueError(
            f"{table_label.capitalize()} names are currently limited to {max_length} ASCII characters."
        )

    mutable = bytearray(data)
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    reserved_ranges: list[tuple[int, int]] = []
    patched_rows: list[CharacterNameReferenceRow] = []
    skipped_rows: list[CharacterNameReferenceRow] = []
    patched_offsets: set[int] = set()
    patched_ranges: list[tuple[int, int]] = []

    for row in source_rows:
        try:
            changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                mutable=mutable,
                data=data,
                rom_offset=row.text_rom_offset,
                original_length=row.text_length,
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind=table_row_source_kind,
                    source_label=row.table_slug,
                    source_index=row.local_index,
                    rom_offset=row.text_rom_offset,
                    decoded_text=row.decoded_text,
                )
            )
            continue
        if not changed:
            continue

        patched_offsets.add(row.text_rom_offset)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind=table_row_source_kind,
                source_label=row.table_slug,
                source_index=row.local_index,
                rom_offset=target_rom_offset,
                decoded_text=row.decoded_text,
            )
        )
        if auto_wrapped:
            print(
                f"Auto-wrapped replacement text for {row.table_slug}[{row.local_index}] "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    known_rows = export_known_text_map(data)
    for row in known_rows:
        if row.table_slug == table_slug:
            continue
        if not pattern.search(row.decoded_text):
            continue
        if row.text_rom_offset in patched_offsets:
            continue
        if any(start <= row.text_rom_offset < end for start, end in patched_ranges):
            continue
        if row.codec != "rotdd":
            raise ValueError(f"Unsupported patch codec for table '{row.table_slug}': {row.codec}")

        try:
            changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                mutable=mutable,
                data=data,
                rom_offset=row.text_rom_offset,
                original_length=row.text_length,
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="known_text",
                    source_label=row.table_slug,
                    source_index=row.local_index,
                    rom_offset=row.text_rom_offset,
                    decoded_text=row.decoded_text,
                )
            )
            continue
        if not changed:
            continue

        patched_offsets.add(row.text_rom_offset)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="known_text",
                source_label=row.table_slug,
                source_index=row.local_index,
                rom_offset=target_rom_offset,
                decoded_text=row.decoded_text,
            )
        )
        if auto_wrapped:
            print(
                f"Auto-wrapped replacement text for {row.table_slug}[{row.local_index}] "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    surface_rows = export_text_surface_corpus(data)
    for row in surface_rows:
        if not pattern.search(row.decoded_text):
            continue
        if row.rom_offset in patched_offsets:
            continue
        if any(start <= row.rom_offset < end for start, end in patched_ranges):
            continue

        original_length = len(read_terminated_string(data, row.rom_offset, terminator=ROTDD_TERMINATOR))
        if row.source_kind == "rotdd":
            try:
                changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    original_length=original_length,
                    current_name=current_name,
                    replacement_name=replacement_name,
                )
            except ValueError:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                    )
                )
                continue
        else:
            try:
                changed, target_rom_offset, payload_length = _patch_ascii_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    original_length=original_length,
                    current_name=current_name,
                    replacement_name=replacement_name,
                    reserved_ranges=reserved_ranges,
                )
            except ValueError:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                    )
                )
                continue

        if not changed:
            continue

        patched_offsets.add(row.rom_offset)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind=f"text_surface:{row.source_kind}",
                source_label="surface-corpus",
                source_index=row.row_index,
                rom_offset=target_rom_offset,
                decoded_text=row.decoded_text,
            )
        )
        if row.source_kind == "rotdd" and auto_wrapped:
            print(
                f"Auto-wrapped replacement text for surface row {row.row_index} "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    for run_start, text in iter_exact_name_ascii_runs(data, current_name):
        if run_start in patched_offsets:
            continue
        if any(start <= run_start < end for start, end in patched_ranges):
            continue

        try:
            changed, target_rom_offset, payload_length = _patch_ascii_run(
                mutable=mutable,
                data=data,
                rom_offset=run_start,
                original_length=len(text),
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="ascii_exact_name",
                    source_label="exact_name_hit",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=text,
                )
            )
            continue

        if not changed:
            continue

        patched_offsets.add(run_start)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="ascii_exact_name",
                source_label="exact_name_hit",
                source_index=run_start,
                rom_offset=target_rom_offset,
                decoded_text=text,
            )
        )

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    return source_rows[0], patched_rows, skipped_rows, final_output_path


def patch_class_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """Patch a class name across the confirmed class slice and matched references."""

    class_rows = export_class_name_map(data)
    return _patch_named_table_everywhere(
        data=data,
        source_path=source_path,
        current_name=current_name,
        replacement_name=replacement_name,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        table_rows=class_rows,
        table_slug=ROTDD_CLASS_NAME_TABLE_SLUG,
        table_label="class",
        table_row_source_kind="class_name_table",
        max_length=ROTDD_CLASS_NAME_MAX_LENGTH,
    )


def patch_enemy_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """Patch an enemy name across the confirmed enemy slice and matched references."""

    enemy_rows = export_enemy_name_map(data)
    return _patch_named_table_everywhere(
        data=data,
        source_path=source_path,
        current_name=current_name,
        replacement_name=replacement_name,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        table_rows=enemy_rows,
        table_slug=ROTDD_ENEMY_NAME_TABLE_SLUG,
        table_label="enemy",
        table_row_source_kind="enemy_name_table",
        max_length=ROTDD_ENEMY_NAME_MAX_LENGTH,
    )


def patch_item_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """Patch an item name across the confirmed item slice and matched references."""

    item_rows = export_item_name_map(data)
    return _patch_named_table_everywhere(
        data=data,
        source_path=source_path,
        current_name=current_name,
        replacement_name=replacement_name,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        table_rows=item_rows,
        table_slug=ROTDD_ITEM_NAME_TABLE_SLUG,
        table_label="item",
        table_row_source_kind="item_name_table",
        max_length=ROTDD_ITEM_NAME_MAX_LENGTH,
    )


def patch_npc_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> tuple[NpcNameRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """
    Patch a dialogue speaker or NPC-style visible name across dialogue text.

    NPC names are not source-table driven like the playable roster, so this
    workflow focuses on the dialogue surfaces and other visible whole-name hits
    that the corpus exporter can see.
    """

    npc_rows = export_npc_name_map(data)
    npc_row = select_npc_name_row(npc_rows, current_name)
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, "NPC")

    try:
        replacement_bytes = replacement_name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("NPC names must be plain ASCII for now.") from exc

    if not replacement_bytes:
        raise ValueError("NPC names cannot be empty.")

    mutable = bytearray(data)
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    reserved_ranges: list[tuple[int, int]] = []
    patched_rows: list[CharacterNameReferenceRow] = []
    skipped_rows: list[CharacterNameReferenceRow] = []
    patched_offsets: set[int] = set()
    patched_ranges: list[tuple[int, int]] = []

    surface_rows = export_text_surface_corpus(data)
    for row in surface_rows:
        if not pattern.search(row.decoded_text):
            continue
        if row.rom_offset in patched_offsets:
            continue
        if any(start <= row.rom_offset < end for start, end in patched_ranges):
            continue

        original_length = len(read_terminated_string(data, row.rom_offset, terminator=ROTDD_TERMINATOR))
        if row.source_kind == "rotdd":
            try:
                changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    original_length=original_length,
                    current_name=current_name,
                    replacement_name=replacement_name,
                    reserved_ranges=reserved_ranges,
                )
            except ValueError:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"npc_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                    )
                )
                continue
        else:
            try:
                changed, target_rom_offset, payload_length = _patch_ascii_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    original_length=original_length,
                    current_name=current_name,
                    replacement_name=replacement_name,
                    reserved_ranges=reserved_ranges,
                )
            except ValueError:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"npc_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                    )
                )
                continue

        if not changed:
            continue

        patched_offsets.add(row.rom_offset)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        if row.source_kind == "rotdd":
            reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind=f"npc_surface:{row.source_kind}",
                source_label="surface-corpus",
                source_index=row.row_index,
                rom_offset=target_rom_offset,
                decoded_text=row.decoded_text,
            )
        )
        if row.source_kind == "rotdd" and auto_wrapped:
            print(
                f"Auto-wrapped replacement text for NPC surface row {row.row_index} "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    for run_start, run_bytes, decoded_text in iter_rotdd_surface_runs(data):
        if run_start in patched_offsets:
            continue
        if any(start <= run_start < end for start, end in patched_ranges):
            continue
        if not pattern.search(decoded_text):
            continue

        original_length = len(read_terminated_string(data, run_start, terminator=ROTDD_TERMINATOR))
        try:
            changed, target_rom_offset, payload_length, auto_wrapped = _patch_rotdd_run(
                mutable=mutable,
                data=data,
                rom_offset=run_start,
                original_length=original_length,
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="npc_surface_run",
                    source_label="surface-run",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=decoded_text,
                )
            )
            continue

        if not changed:
            continue

        patched_offsets.add(run_start)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="npc_surface_run",
                source_label="surface-run",
                source_index=run_start,
                rom_offset=target_rom_offset,
                decoded_text=decoded_text,
            )
        )
        if auto_wrapped:
            print(
                f"Auto-wrapped replacement text for NPC surface run at 0x{run_start:08X} "
                f"to fit {ROTDD_DIALOGUE_VISIBLE_ROWS} rows of {ROTDD_DIALOGUE_LINE_WIDTH} characters."
            )

    ascii_index = 0
    limit = len(data)
    while ascii_index < limit:
        if not printable_ascii(data[ascii_index]):
            ascii_index += 1
            continue

        run_start = ascii_index
        run: list[int] = []
        while ascii_index < limit and printable_ascii(data[ascii_index]):
            run.append(data[ascii_index])
            ascii_index += 1

        original_text = bytes(run).decode("ascii", errors="replace")
        if not pattern.search(original_text):
            continue
        if any(start <= run_start < end for start, end in patched_ranges):
            continue

        try:
            changed, target_rom_offset, payload_length = _patch_ascii_run(
                mutable=mutable,
                data=data,
                rom_offset=run_start,
                original_length=len(run),
                current_name=current_name,
                replacement_name=replacement_name,
                reserved_ranges=reserved_ranges,
            )
        except ValueError:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="npc_ascii_surface",
                    source_label="printable_ascii",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=original_text,
                )
            )
            continue

        if not changed:
            continue

        patched_offsets.add(run_start)
        patched_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        reserved_ranges.append((target_rom_offset, target_rom_offset + payload_length))
        patched_rows.append(
            CharacterNameReferenceRow(
                row_index=len(patched_rows),
                source_kind="npc_ascii_surface",
                source_label="printable_ascii",
                source_index=run_start,
                rom_offset=target_rom_offset,
                decoded_text=original_text,
            )
        )

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    return npc_row, patched_rows, skipped_rows, final_output_path


def patch_character_name(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
) -> tuple[CharacterNameRow, int, int, Path]:
    """
    Patch a character name in the canonical pointer table.

    Shorter or equal-length replacements stay in place. Longer replacements are
    repointed into the observed zero padding before the name bank so we do not
    disturb the existing table order.
    """

    rows = export_character_name_map(data)
    row = select_character_name_row(rows, current_name)
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, "character")

    try:
        replacement_bytes = replacement_name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Character names must be plain ASCII for now.") from exc

    if not replacement_bytes:
        raise ValueError("Character names cannot be empty.")
    if len(replacement_bytes) > ROTDD_CHARACTER_NAME_MAX_LENGTH:
        raise ValueError(
            f"Character names are currently limited to {ROTDD_CHARACTER_NAME_MAX_LENGTH} ASCII characters."
        )

    mutable = bytearray(data)
    target_rom_offset = row.name_rom_offset
    pointer_value = row.pointer_value
    payload = replacement_bytes + bytes([0x00])

    if len(payload) <= (row.name_length + 1):
        start = row.name_rom_offset
        end = start + row.name_length + 1
        mutable[start:start + len(payload)] = payload
        if len(payload) < (row.name_length + 1):
            mutable[start + len(payload):end] = bytes([0x00]) * (end - (start + len(payload)))
    else:
        target_rom_offset = _find_zero_run(
            data=bytes(mutable),
            start=ROTDD_CHARACTER_NAME_REPOINT_START,
            end=ROTDD_CHARACTER_NAME_REPOINT_END,
            length=len(payload),
        )
        mutable[target_rom_offset:target_rom_offset + len(payload)] = payload
        pointer_value = GBA_ROM_BASE + target_rom_offset
        mutable[row.pointer_table_offset:row.pointer_table_offset + 4] = pointer_value.to_bytes(4, "little")

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)

    return row, target_rom_offset, pointer_value, final_output_path
