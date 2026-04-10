"""
Safe edit helpers for known ROTDD text tables.

The default editor path is intentionally conservative. It keeps replacements
within the original byte budget when possible, repoints longer values by
appending them to the end of a copied ROM, and only uses unsafe in-place
writes when the caller explicitly asks for liberal mode or direct overwrites.
"""

from __future__ import annotations

import re
from collections.abc import Callable
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
    read_text_surface_csv,
    load_text_surface_template_csv,
    normalize_visible_name,
    iter_rotdd_surface_runs,
    write_text_surface_csv,
)
from .models import (
    CharacterNameReferenceRow,
    CharacterNameRow,
    NpcNameRow,
    TextMapRow,
)
from .gba import GBA_ROM_BASE, iter_find_all, printable_ascii, read_terminated_string
from .rotdd import (
    KNOWN_TEXT_TABLES,
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


def _report_progress(
    progress_callback: Callable[[float, str], None] | None,
    percent: float,
    message: str,
) -> None:
    """Forward a normalized progress update when the caller asked for one."""

    if progress_callback is None:
        return
    progress_callback(max(0.0, min(1.0, percent)), message)


def _short_skip_reason(exc: ValueError) -> str:
    """Convert a detailed ValueError into a short one-line skip reason."""

    message = str(exc).lower()
    if "no pointer table was found" in message or "no pointer table" in message:
        return "no pointer table"
    if "unsupported character" in message:
        return "unsupported glyph"
    if "unsupported inline tag" in message:
        return "unsupported tag"
    if "unsupported patch codec" in message or "codec" in message:
        return "unsupported codec"
    if "already in use" in message or "collision" in message:
        return "name collision"
    if "too long" in message or "length" in message:
        return "too long for slot"
    if "plain ascii" in message:
        return "ASCII only"
    if "cannot be empty" in message:
        return "empty replacement"
    return "unsafe skip"


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
    """Replace a whole visible name, including its simple plural form."""

    def pluralize(name: str) -> str:
        parts = name.split()
        if not parts:
            return name
        last = parts[-1]
        if re.search(r"(s|x|z|ch|sh)$", last, re.IGNORECASE):
            plural_last = last + "es"
        elif re.search(r"[^aeiou]y$", last, re.IGNORECASE):
            plural_last = last[:-1] + "ies"
        else:
            plural_last = last + "s"
        return " ".join(parts[:-1] + [plural_last])

    try:
        current_name.encode("ascii")
        replacement_name.encode("ascii")
    except UnicodeEncodeError:
        return text, False

    singular = re.escape(current_name)
    plural_name = pluralize(current_name)
    plural = re.escape(plural_name)
    if plural == singular:
        pattern = re.compile(rf"(?<![A-Za-z]){singular}(?![A-Za-z])", re.IGNORECASE)
    else:
        pattern = re.compile(rf"(?<![A-Za-z])(?:{singular}|{plural})(?![A-Za-z])", re.IGNORECASE)

    def repl(match: re.Match[str]) -> str:
        matched = match.group(0)
        if matched.casefold() == plural_name.casefold():
            return pluralize(replacement_name)
        return replacement_name

    updated, count = pattern.subn(repl, text)
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

    The result keeps explicit tags intact, wraps on word boundaries, and
    automatically inserts page breaks so the output stays within the three
    visible rows the box can show on each page.
    """

    text = text.replace("…", "...")
    tokens = re.findall(r"<[^>]+>|\s+|[^\s<>]+", text)
    parts: list[str] = []
    current: list[str] = []
    current_width = 0
    page_rows = 0
    auto_wrapped = False

    def has_more_content(next_index: int) -> bool:
        for token in tokens[next_index:]:
            if not token.isspace():
                return True
        return False

    def emit_page_break_if_needed(next_index: int) -> bool:
        nonlocal page_rows
        if page_rows < ROTDD_DIALOGUE_VISIBLE_ROWS:
            return False
        if current:
            return False
        if not has_more_content(next_index):
            return False
        parts.append("<PAGE_BREAK>")
        page_rows = 0
        return True

    def flush_line() -> None:
        nonlocal current, current_width, page_rows
        if not current:
            return
        line = "".join(current).rstrip()
        parts.append(line)
        page_rows += 1
        current = []
        current_width = 0

    for index, token in enumerate(tokens):
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

        if re.fullmatch(r"[.,!?;:'\"-]+", token):
            current.append(token)
            current_width += len(token)
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
            page_break_emitted = False
            if page_rows >= ROTDD_DIALOGUE_VISIBLE_ROWS:
                page_break_emitted = emit_page_break_if_needed(index)
                auto_wrapped = True
            if not current and page_rows < ROTDD_DIALOGUE_VISIBLE_ROWS and not page_break_emitted:
                parts.append("<NEWLINE>")
                auto_wrapped = True
        if current and current[-1] != " ":
            current.append(" ")
            current_width += 1
        current.append(token)
        current_width += word_width

        emit_page_break_if_needed(index + 1)

    flush_line()
    emit_page_break_if_needed(len(tokens))
    normalized = "".join(parts)
    if auto_wrapped:
        normalized = re.sub(r"(<NEWLINE>|<PAGE_BREAK>|<SPEAKER_BREAK>)\s+", r"\1", normalized)
    normalized = re.sub(r"(?<!\.)\s+\.(?!\.)", ".", normalized)
    return normalized, auto_wrapped


def reflow_surface_replacement_text(text: str) -> tuple[str, bool]:
    """
    Rebuild a dialogue-like blob into fresh screen-sized pages.

    Existing hard line/page breaks are discarded so renamed names can shift the
    surrounding text naturally instead of inheriting stale wrap points.
    """

    stripped = text.replace("<NEWLINE>", " ").replace("<PAGE_BREAK>", " ")
    return normalize_surface_replacement_text(stripped)


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
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[TextMapRow, bytes, Path]:
    """
    Patch a known text entry while keeping the replacement readable and
    conservative.

    Shorter replacements stay within the original byte budget. When a row
    still needs more room and we can prove a safe pointer target, the payload
    is appended to EOF and the table entry is repointed there instead of
    guessing at internal free space.
    """

    _report_progress(progress_callback, 0.0, "Selecting known text row")
    get_known_table(table_slug)
    rows = export_known_text_map(data)
    row = select_known_text_row(rows, table_slug, local_index, match_text, occurrence)

    if row.codec != "rotdd":
        raise ValueError(f"Unsupported patch codec for table '{table_slug}': {row.codec}")

    _report_progress(progress_callback, 0.35, "Encoding replacement text")
    mutable = bytearray(data)
    start = row.text_rom_offset
    end = start + row.text_length
    try:
        _normalized_text, replacement_bytes, auto_wrapped, dropped_unknowns = fit_surface_text_to_length(
            replacement_text,
            row.text_length,
        )
        mutable[start:end] = replacement_bytes
    except ValueError:
        _normalized_text, auto_wrapped = normalize_surface_replacement_text(replacement_text)
        replacement_bytes = encode_rotdd_surface_text(_normalized_text)
        pointer_hits = _find_pointer_hits(data, row.text_rom_offset)
        if pointer_hits:
            payload = replacement_bytes + bytes([ROTDD_TERMINATOR])
            target_rom_offset = _append_repoint_payload(mutable, payload)
            _rewrite_pointer_hits(mutable, pointer_hits, target_rom_offset)
            replacement_bytes = payload
            dropped_unknowns = 0
        else:
            raise ValueError(
                "Replacement is too long for this known text row and no pointer table was found."
            )

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    _report_progress(progress_callback, 1.0, "Patch complete")
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
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[str, bytes, Path]:
    """
    Patch a ROTDD text run at a literal ROM offset while staying within the
    original byte budget when possible.

    The replacement text may include the known inline tags used by the corpus
    exporter, so the CSV can be reused as a source of truth. If the run has a
    safe pointer target and the replacement no longer fits in place, the tool
    appends the payload to EOF and repoints those pointers instead of guessing
    at free space.
    """

    _report_progress(progress_callback, 0.0, "Reading text run")
    original_bytes = read_terminated_string(data, rom_offset, terminator=ROTDD_TERMINATOR)
    _report_progress(progress_callback, 0.3, "Encoding replacement text")
    mutable = bytearray(data)
    end = rom_offset + len(original_bytes)
    try:
        normalized_text, replacement_bytes, auto_wrapped, dropped_unknowns = fit_surface_text_to_length(
            replacement_text,
            len(original_bytes),
        )
        mutable[rom_offset:end] = replacement_bytes
    except ValueError:
        normalized_text, auto_wrapped = normalize_surface_replacement_text(replacement_text)
        replacement_bytes = encode_rotdd_surface_text(normalized_text)
        pointer_hits = _find_pointer_hits(data, rom_offset)
        if pointer_hits:
            payload = replacement_bytes + bytes([ROTDD_TERMINATOR])
            target_rom_offset = _append_repoint_payload(mutable, payload)
            _rewrite_pointer_hits(mutable, pointer_hits, target_rom_offset)
            replacement_bytes = payload
            dropped_unknowns = 0
        else:
            raise ValueError("Replacement is too long for this ROTDD run and no pointer table was found.")

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    _report_progress(progress_callback, 1.0, "Patch complete")
    if dropped_unknowns:
        print(
            f"Dropped {dropped_unknowns} unmapped placeholder byte(s) to keep the replacement within the original budget."
        )
    return decode_rotdd_bytes(original_bytes), replacement_bytes, final_output_path


def patch_bytes_at_offset(
    data: bytes,
    source_path: Path,
    rom_offset: int,
    replacement_bytes: bytes,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[bytes, bytes, Path]:
    """
    Patch raw bytes at a literal ROM offset while keeping the write bounded to
    the exact replacement length.

    This command is the generic binary counterpart to patch-text-at-offset.
    It does not try to infer any codec or padding rules; it simply replaces the
    bytes at the requested offset with the exact byte sequence provided by the
    caller.
    """

    if not replacement_bytes:
        raise ValueError("Replacement byte sequence cannot be empty.")

    _report_progress(progress_callback, 0.0, "Reading target bytes")
    end = rom_offset + len(replacement_bytes)
    if end > len(data):
        raise ValueError("Replacement extends beyond the end of the ROM.")

    mutable = bytearray(data)
    original_bytes = bytes(mutable[rom_offset:end])
    _report_progress(progress_callback, 0.6, "Writing byte patch")
    mutable[rom_offset:end] = replacement_bytes

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    _report_progress(progress_callback, 1.0, "Patch complete")
    return original_bytes, replacement_bytes, final_output_path


def patch_text_surface_template_file(
    data: bytes,
    source_path: Path,
    template_path: Path,
    corpus_path: Path,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str = "strict",
    rewrite_reference_corpus: bool = False,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[int, int, list[str], list[str], Path]:
    """
    Patch every changed row in a two-column text-surface template CSV.

    The template is compared against the live ROM text at each offset. Unchanged
    rows are ignored. ROTDD rows keep the usual auto-wrap and page-break logic,
    and longer rows are repointed to EOF when a safe pointer target exists.
    """

    template_rows = load_text_surface_template_csv(template_path)
    corpus_rows = read_text_surface_csv(corpus_path)
    corpus_codec_by_offset = {row.rom_offset: row.source_kind for row in corpus_rows}
    mutable = bytearray(data)
    changed_rows = 0
    patched_rows = 0
    skipped_rows: list[str] = []
    deferred_messages: list[str] = []
    allow_unsafe_write = mode == "liberal"
    total_rows = max(1, len(template_rows))
    _report_progress(progress_callback, 0.0, f"Reading template {template_path.name}")

    for row_index, row in enumerate(template_rows):
        _report_progress(
            progress_callback,
            0.02 + (0.78 * (row_index / total_rows)),
            "Scanning template rows",
        )
        codec_kind = corpus_codec_by_offset.get(row.rom_offset)
        if codec_kind == "ascii":
            codec = "ascii"
            current_text = read_terminated_string(data, row.rom_offset, terminator=0x00).decode("ascii", errors="replace")
        elif codec_kind == "rotdd":
            codec = "rotdd"
            current_text = decode_rotdd_bytes(read_terminated_string(data, row.rom_offset, terminator=ROTDD_TERMINATOR))
        else:
            codec, current_text, _original_length = _infer_surface_codec(data, row.rom_offset)
        if current_text == row.decoded_text:
            continue

        changed_rows += 1
        try:
            if codec == "ascii":
                changed, target_rom_offset, _payload_length = _patch_ascii_surface_text(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    replacement_text=row.decoded_text,
                    allow_unsafe_write=allow_unsafe_write,
                )
                auto_wrapped = False
            else:
                changed, target_rom_offset, _payload_length, auto_wrapped = _patch_rotdd_surface_text(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    replacement_text=row.decoded_text,
                    allow_unsafe_write=allow_unsafe_write,
                )
        except ValueError as exc:
            skipped_rows.append(
                f"  rom=0x{row.rom_offset:08X} reason={_short_skip_reason(exc)}"
            )
            continue

        if not changed:
            continue

        patched_rows += 1

    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    if rewrite_reference_corpus:
        corpus_rows = export_text_surface_corpus(bytes(mutable), progress_callback=None)
        write_text_surface_csv(corpus_rows, corpus_path)
        deferred_messages.append(f"Rewrote reference corpus: {corpus_path}")
    _report_progress(progress_callback, 1.0, "Patch complete")
    return changed_rows, patched_rows, skipped_rows, deferred_messages, final_output_path


def select_character_name_row(
    rows: list[CharacterNameRow],
    name: str,
) -> CharacterNameRow:
    """Select one character-name row by its decoded ASCII name."""

    normalized_name = normalize_visible_name(name)
    matches = [row for row in rows if normalize_visible_name(row.decoded_name) == normalized_name]
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

    normalized_name = normalize_visible_name(name)
    matches = [row for row in rows if normalize_visible_name(row.speaker_name) == normalized_name]
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


def _validate_ascii_replacement_name(
    replacement_name: str,
    *,
    entity_label: str,
    max_length: int | None = None,
) -> bytes:
    """Validate a replacement name before any ROM-wide scanning starts."""

    try:
        replacement_bytes = replacement_name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{entity_label.capitalize()} names must be plain ASCII for now.") from exc

    if not replacement_bytes:
        raise ValueError(f"{entity_label.capitalize()} names cannot be empty.")
    if max_length is not None and len(replacement_bytes) > max_length:
        raise ValueError(
            f"{entity_label.capitalize()} names are currently limited to {max_length} ASCII characters."
        )
    return replacement_bytes


def _append_repoint_payload(mutable: bytearray, payload: bytes) -> int:
    """Append a replacement payload to the end of the ROM copy and return its offset."""

    target_rom_offset = len(mutable)
    mutable.extend(payload)
    return target_rom_offset


def _force_ascii_in_place_payload(replacement_name: str, original_length: int) -> bytes:
    """Build a best-effort ASCII payload when the conservative rewrite path is unavailable."""

    payload = replacement_name.encode("ascii") + bytes([0x00])
    target_length = original_length + 1
    if len(payload) >= target_length:
        return payload[: target_length - 1] + bytes([0x00])
    return payload + bytes([0x00]) * (target_length - len(payload))


def _force_rotdd_in_place_payload(normalized_text: str, original_length: int) -> bytes:
    """Build a best-effort ROTDD payload when the conservative rewrite path is unavailable."""

    encoded = encode_rotdd_surface_text(normalized_text)
    if len(encoded) >= original_length:
        return encoded[:original_length]
    return pad_rotdd_bytes(encoded, original_length)


def _infer_surface_codec(data: bytes, rom_offset: int) -> tuple[str, str, int]:
    """Infer whether a surface run is plain ASCII or ROTDD-encoded text."""

    raw = read_terminated_string(data, rom_offset, terminator=0x00)
    if raw and all(printable_ascii(byte) for byte in raw):
        return "ascii", raw.decode("ascii"), len(raw)
    return "rotdd", decode_rotdd_bytes(raw), len(raw)


def _patch_ascii_surface_text(
    mutable: bytearray,
    data: bytes,
    rom_offset: int,
    replacement_text: str,
    allow_unsafe_write: bool = False,
) -> tuple[bool, int, int]:
    """Patch one plain-ASCII surface run inside a mutable ROM buffer."""

    original_bytes = read_terminated_string(data, rom_offset, terminator=0x00)
    original_length = len(original_bytes)

    try:
        replacement_bytes = replacement_text.encode("ascii") + bytes([0x00])
    except UnicodeEncodeError as exc:
        raise ValueError("ASCII text must be plain ASCII.") from exc

    if len(replacement_bytes) <= (original_length + 1):
        mutable[rom_offset:rom_offset + len(replacement_bytes)] = replacement_bytes
        if len(replacement_bytes) < (original_length + 1):
            mutable[rom_offset + len(replacement_bytes):rom_offset + original_length + 1] = bytes([0x00]) * (
                (original_length + 1) - len(replacement_bytes)
            )
        return True, rom_offset, len(replacement_bytes)

    pointer_hits = _find_pointer_hits(data, rom_offset)
    if not pointer_hits:
        if allow_unsafe_write:
            unsafe_payload = _force_ascii_in_place_payload(replacement_text, original_length)
            mutable[rom_offset:rom_offset + original_length + 1] = unsafe_payload
            return True, rom_offset, len(unsafe_payload)
        raise ValueError("Replacement is too long for this ASCII string and no pointer table was found.")

    target_rom_offset = _append_repoint_payload(mutable, replacement_bytes)
    _rewrite_pointer_hits(mutable, pointer_hits, target_rom_offset)
    return True, target_rom_offset, len(replacement_bytes)


def _patch_rotdd_surface_text(
    mutable: bytearray,
    data: bytes,
    rom_offset: int,
    replacement_text: str,
    allow_unsafe_write: bool = False,
) -> tuple[bool, int, int, bool]:
    """Patch one ROTDD surface run inside a mutable ROM buffer."""

    original_bytes = read_terminated_string(data, rom_offset, terminator=ROTDD_TERMINATOR)
    original_length = len(original_bytes)
    reflowed_text, reflowed_auto_wrapped = reflow_surface_replacement_text(replacement_text)

    try:
        normalized_text, replacement_bytes, auto_wrapped, _dropped_unknowns = fit_surface_text_to_length(
            reflowed_text,
            original_length,
        )
        mutable[rom_offset:rom_offset + original_length] = replacement_bytes
        return True, rom_offset, len(replacement_bytes), auto_wrapped or reflowed_auto_wrapped
    except ValueError:
        replacement_bytes = encode_rotdd_surface_text(reflowed_text)
        pointer_hits = _find_pointer_hits(data, rom_offset)
        if pointer_hits:
            payload = replacement_bytes + bytes([ROTDD_TERMINATOR])
            target_rom_offset = _append_repoint_payload(mutable, payload)
            _rewrite_pointer_hits(mutable, pointer_hits, target_rom_offset)
            return True, target_rom_offset, len(payload), reflowed_auto_wrapped
        if allow_unsafe_write:
            unsafe_payload = _force_rotdd_in_place_payload(reflowed_text, original_length)
            mutable[rom_offset:rom_offset + original_length] = unsafe_payload
            return True, rom_offset, len(unsafe_payload), reflowed_auto_wrapped
        raise ValueError("Replacement is too long for this ROTDD run and no pointer table was found.")


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
    allow_unsafe_write: bool = False,
) -> tuple[bool, int, int, bool]:
    """Patch one ROTDD-encoded run inside a mutable ROM buffer."""

    original_bytes = bytes(mutable[rom_offset:rom_offset + original_length])
    original_text = decode_rotdd_bytes(original_bytes)
    updated_text, changed = replace_case_sensitive_name(original_text, current_name, replacement_name)
    if not changed:
        return False, rom_offset, original_length, False

    reflowed_text, auto_wrapped = reflow_surface_replacement_text(updated_text)
    try:
        normalized_text, replacement_bytes, _auto_wrapped, _dropped_unknowns = fit_surface_text_to_length(
            reflowed_text,
            original_length,
            allow_placeholder_drop=True,
        )
    except ValueError:
        pointer_hits = _find_pointer_hits(data, rom_offset)
        if not pointer_hits:
            if allow_unsafe_write:
                normalized_text = reflowed_text
                replacement_bytes = _force_rotdd_in_place_payload(normalized_text, original_length)
                mutable[rom_offset:rom_offset + original_length] = replacement_bytes
                return True, rom_offset, len(replacement_bytes), auto_wrapped
            raise ValueError(
                "Replacement is too long for this inline text run and no pointer table was found."
            )

        normalized_text = reflowed_text
        replacement_bytes = encode_rotdd_surface_text(normalized_text) + bytes([ROTDD_TERMINATOR])
        target_rom_offset = _append_repoint_payload(mutable, replacement_bytes)
        _rewrite_pointer_hits(mutable, pointer_hits, target_rom_offset)
        return True, target_rom_offset, len(replacement_bytes), auto_wrapped

    mutable[rom_offset:rom_offset + original_length] = replacement_bytes
    return True, rom_offset, len(replacement_bytes), auto_wrapped


def _patch_ascii_run(
    mutable: bytearray,
    data: bytes,
    rom_offset: int,
    original_length: int,
    current_name: str,
    replacement_name: str,
    reserved_ranges: list[tuple[int, int]] | None = None,
    allow_unsafe_write: bool = False,
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
        if allow_unsafe_write:
            replacement_bytes = _force_ascii_in_place_payload(replacement_name, original_length)
            mutable[rom_offset:rom_offset + original_length + 1] = replacement_bytes
            return True, rom_offset, len(replacement_bytes)
        raise ValueError("Replacement is too long for this ASCII string and no pointer table was found.")

    target_rom_offset = _append_repoint_payload(mutable, payload)
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
    mode: str = "strict",
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[CharacterNameRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """
    Patch a character name at its canonical source and in every matched text row.

    The canonical pointer table is updated first. Then the tool scans the known
    ROTDD text tables and the broader text-surface corpus for case-sensitive
    whole-name matches. Each matched row is rewritten in memory and written once
    at the end so the command stays reproducible and easy to audit.
    """

    _report_progress(progress_callback, 0.0, "Locating character row")
    name_rows = export_character_name_map(data)
    canonical_row = select_character_name_row(name_rows, current_name)
    replacement_bytes = _validate_ascii_replacement_name(
        replacement_name,
        entity_label="character",
        max_length=ROTDD_CHARACTER_NAME_MAX_LENGTH,
    )
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, "character")

    mutable = bytearray(data)
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    target_rom_offset = canonical_row.name_rom_offset
    pointer_value = canonical_row.pointer_value
    payload = replacement_bytes + bytes([0x00])
    reserved_ranges: list[tuple[int, int]] = []
    allow_unsafe_write = mode == "liberal"

    _report_progress(progress_callback, 0.1, "Writing canonical name")
    if len(payload) <= (canonical_row.name_length + 1):
        start = canonical_row.name_rom_offset
        end = start + canonical_row.name_length + 1
        mutable[start:start + len(payload)] = payload
        if len(payload) < (canonical_row.name_length + 1):
            mutable[start + len(payload):end] = bytes([0x00]) * (end - (start + len(payload)))
    else:
        target_rom_offset = _append_repoint_payload(mutable, payload)
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
    known_total = max(1, len(known_rows))
    for row_index, row in enumerate(known_rows):
        _report_progress(
            progress_callback,
            0.15 + (0.20 * (row_index / known_total)),
            "Scanning known text rows",
        )
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
                allow_unsafe_write=allow_unsafe_write,
            )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="known_text",
                    source_label=row.table_slug,
                    source_index=row.local_index,
                    rom_offset=row.text_rom_offset,
                    decoded_text=row.decoded_text,
                    skip_reason=_short_skip_reason(exc),
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

    surface_rows = export_text_surface_corpus(
        data,
        progress_callback=(lambda percent, message: _report_progress(
            progress_callback,
            0.35 + (percent * 0.40),
            message,
        )) if progress_callback is not None else None,
    )
    surface_total = max(1, len(surface_rows))
    for row_index, row in enumerate(surface_rows):
        _report_progress(
            progress_callback,
            0.75 + (0.18 * (row_index / surface_total)),
            "Scanning dialogue corpus",
        )
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
                    allow_unsafe_write=allow_unsafe_write,
                )
            except ValueError as exc:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                        skip_reason=_short_skip_reason(exc),
                    )
                )
                continue
        else:
            try:
                # ASCII surface rows can also repoint when they outgrow the
                # original slot, so they use the same EOF append path as the
                # ROTDD surface paths above.
                changed, target_rom_offset, payload_length = _patch_ascii_run(
                    mutable=mutable,
                    data=data,
                    rom_offset=row.rom_offset,
                    original_length=original_length,
                    current_name=current_name,
                    replacement_name=replacement_name,
                    reserved_ranges=reserved_ranges,
                    allow_unsafe_write=allow_unsafe_write,
                )
            except ValueError as exc:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                        skip_reason=_short_skip_reason(exc),
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

    _report_progress(progress_callback, 0.95, "Scanning exact ASCII hits")
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
                    allow_unsafe_write=allow_unsafe_write,
                )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="ascii_exact_name",
                    source_label="exact_name_hit",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=text,
                    skip_reason=_short_skip_reason(exc),
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
                    allow_unsafe_write=allow_unsafe_write,
                )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="rotdd_surface_run",
                    source_label="surface-run",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=decoded_text,
                    skip_reason=_short_skip_reason(exc),
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
                    allow_unsafe_write=allow_unsafe_write,
                )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="ascii_surface",
                    source_label="printable_ascii",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=original_text,
                    skip_reason=_short_skip_reason(exc),
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

    _report_progress(progress_callback, 0.99, "Writing patched ROM")
    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    _report_progress(progress_callback, 1.0, "Patch complete")
    return canonical_row, patched_rows, skipped_rows, final_output_path


def _patch_named_table_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str,
    table_rows: list[TextMapRow],
    table_slug: str,
    table_label: str,
    table_row_source_kind: str,
    max_length: int,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """
    Patch one visible-name table across the confirmed table slice and all
    matched visible references.

    The implementation mirrors the playable-character rename workflow, but it
    starts from the dedicated name-table slice instead of the character-name
    pointer table.
    """

    _report_progress(progress_callback, 0.0, f"Locating {table_label} row")
    normalized_current_name = normalize_visible_name(current_name)
    source_rows = [
        row for row in table_rows
        if normalize_visible_name(row.decoded_text) == normalized_current_name
    ]
    if not source_rows:
        raise ValueError(f"No {table_label}-name row found with decoded text {current_name!r}.")
    replacement_bytes = _validate_ascii_replacement_name(
        replacement_name,
        entity_label=table_label,
        max_length=max_length,
    )
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, table_label)

    mutable = bytearray(data)
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    reserved_ranges: list[tuple[int, int]] = []
    allow_unsafe_write = mode == "liberal"
    patched_rows: list[CharacterNameReferenceRow] = []
    skipped_rows: list[CharacterNameReferenceRow] = []
    patched_offsets: set[int] = set()
    patched_ranges: list[tuple[int, int]] = []

    _report_progress(progress_callback, 0.1, f"Scanning {table_label} table")
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
                allow_unsafe_write=allow_unsafe_write,
            )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind=table_row_source_kind,
                    source_label=row.table_slug,
                    source_index=row.local_index,
                    rom_offset=row.text_rom_offset,
                    decoded_text=row.decoded_text,
                    skip_reason=_short_skip_reason(exc),
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
    known_rows = export_known_text_map(data)
    known_total = max(1, len(known_rows))
    for row_index, row in enumerate(known_rows):
        _report_progress(
            progress_callback,
            0.1 + (0.25 * (row_index / known_total)),
            f"Scanning matched ROTDD text",
        )
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
                    allow_unsafe_write=allow_unsafe_write,
                )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="known_text",
                    source_label=row.table_slug,
                    source_index=row.local_index,
                    rom_offset=row.text_rom_offset,
                    decoded_text=row.decoded_text,
                    skip_reason=_short_skip_reason(exc),
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
    surface_rows = export_text_surface_corpus(
        data,
        progress_callback=(lambda percent, message: _report_progress(
            progress_callback,
            0.35 + (percent * 0.4),
            message,
        )) if progress_callback is not None else None,
    )
    surface_total = max(1, len(surface_rows))
    for row_index, row in enumerate(surface_rows):
        _report_progress(
            progress_callback,
            0.75 + (0.20 * (row_index / surface_total)),
            "Scanning dialogue corpus",
        )
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
                    allow_unsafe_write=allow_unsafe_write,
                )
            except ValueError as exc:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                        skip_reason=_short_skip_reason(exc),
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
                    allow_unsafe_write=allow_unsafe_write,
                )
            except ValueError as exc:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"text_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                        skip_reason=_short_skip_reason(exc),
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

    _report_progress(progress_callback, 0.95, "Scanning exact ASCII hits")
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
                    allow_unsafe_write=allow_unsafe_write,
                )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="ascii_exact_name",
                    source_label="exact_name_hit",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=text,
                    skip_reason=_short_skip_reason(exc),
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

    _report_progress(progress_callback, 0.99, "Writing patched ROM")
    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    _report_progress(progress_callback, 1.0, "Patch complete")
    return source_rows[0], patched_rows, skipped_rows, final_output_path


def patch_class_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str = "strict",
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """Patch a class name across the confirmed class slice and matched references."""

    _validate_ascii_replacement_name(
        replacement_name,
        entity_label="class",
        max_length=ROTDD_CLASS_NAME_MAX_LENGTH,
    )
    class_rows = export_class_name_map(data)
    return _patch_named_table_everywhere(
        data=data,
        source_path=source_path,
        current_name=current_name,
        replacement_name=replacement_name,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        mode=mode,
        table_rows=class_rows,
        table_slug=ROTDD_CLASS_NAME_TABLE_SLUG,
        table_label="class",
        table_row_source_kind="class_name_table",
        max_length=ROTDD_CLASS_NAME_MAX_LENGTH,
        progress_callback=progress_callback,
    )


def patch_enemy_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str = "strict",
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """Patch an enemy name across the confirmed enemy slice and matched references."""

    _validate_ascii_replacement_name(
        replacement_name,
        entity_label="enemy",
        max_length=ROTDD_ENEMY_NAME_MAX_LENGTH,
    )
    enemy_rows = export_enemy_name_map(data)
    return _patch_named_table_everywhere(
        data=data,
        source_path=source_path,
        current_name=current_name,
        replacement_name=replacement_name,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        mode=mode,
        table_rows=enemy_rows,
        table_slug=ROTDD_ENEMY_NAME_TABLE_SLUG,
        table_label="enemy",
        table_row_source_kind="enemy_name_table",
        max_length=ROTDD_ENEMY_NAME_MAX_LENGTH,
        progress_callback=progress_callback,
    )


def patch_item_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str = "strict",
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[TextMapRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """Patch an item name across the confirmed item slice and matched references."""

    _validate_ascii_replacement_name(
        replacement_name,
        entity_label="item",
        max_length=ROTDD_ITEM_NAME_MAX_LENGTH,
    )
    item_rows = export_item_name_map(data)
    return _patch_named_table_everywhere(
        data=data,
        source_path=source_path,
        current_name=current_name,
        replacement_name=replacement_name,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        mode=mode,
        table_rows=item_rows,
        table_slug=ROTDD_ITEM_NAME_TABLE_SLUG,
        table_label="item",
        table_row_source_kind="item_name_table",
        max_length=ROTDD_ITEM_NAME_MAX_LENGTH,
        progress_callback=progress_callback,
    )


def patch_npc_name_everywhere(
    data: bytes,
    source_path: Path,
    current_name: str,
    replacement_name: str,
    output_path: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str = "strict",
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[NpcNameRow, list[CharacterNameReferenceRow], list[CharacterNameReferenceRow], Path]:
    """
    Patch a dialogue speaker or NPC-style visible name across dialogue text.

    NPC names are not source-table driven like the playable roster, so this
    workflow focuses on the dialogue surfaces and other visible whole-name hits
    that the corpus exporter can see.
    """

    _report_progress(progress_callback, 0.0, "Locating NPC row")
    replacement_bytes = _validate_ascii_replacement_name(
        replacement_name,
        entity_label="npc",
        max_length=None,
    )
    npc_rows = export_npc_name_map(data)
    npc_row = select_npc_name_row(npc_rows, current_name)
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, "NPC")
    allow_unsafe_write = mode == "liberal"

    mutable = bytearray(data)
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    reserved_ranges: list[tuple[int, int]] = []
    patched_rows: list[CharacterNameReferenceRow] = []
    skipped_rows: list[CharacterNameReferenceRow] = []
    patched_offsets: set[int] = set()
    patched_ranges: list[tuple[int, int]] = []

    surface_rows = export_text_surface_corpus(
        data,
        progress_callback=(lambda percent, message: _report_progress(
            progress_callback,
            0.05 + (percent * 0.65),
            message,
        )) if progress_callback is not None else None,
    )
    surface_total = max(1, len(surface_rows))
    for row_index, row in enumerate(surface_rows):
        _report_progress(
            progress_callback,
            0.70 + (0.20 * (row_index / surface_total)),
            "Scanning dialogue corpus",
        )
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
                    allow_unsafe_write=allow_unsafe_write,
                )
            except ValueError as exc:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"npc_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                        skip_reason=_short_skip_reason(exc),
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
                    allow_unsafe_write=allow_unsafe_write,
                )
            except ValueError as exc:
                skipped_rows.append(
                    CharacterNameReferenceRow(
                        row_index=len(skipped_rows),
                        source_kind=f"npc_surface:{row.source_kind}",
                        source_label="surface-corpus",
                        source_index=row.row_index,
                        rom_offset=row.rom_offset,
                        decoded_text=row.decoded_text,
                        skip_reason=_short_skip_reason(exc),
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
    _report_progress(progress_callback, 0.92, "Scanning ROTDD surface runs")
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
                allow_unsafe_write=allow_unsafe_write,
            )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="npc_surface_run",
                    source_label="surface-run",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=decoded_text,
                    skip_reason=_short_skip_reason(exc),
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
    _report_progress(progress_callback, 0.97, "Scanning ASCII surface runs")
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
                    allow_unsafe_write=allow_unsafe_write,
                )
        except ValueError as exc:
            skipped_rows.append(
                CharacterNameReferenceRow(
                    row_index=len(skipped_rows),
                    source_kind="npc_ascii_surface",
                    source_label="printable_ascii",
                    source_index=run_start,
                    rom_offset=run_start,
                    decoded_text=original_text,
                    skip_reason=_short_skip_reason(exc),
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

    _report_progress(progress_callback, 0.995, "Writing patched ROM")
    final_output_path = resolve_patch_output_path(
        source_path=source_path,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(mutable)
    _report_progress(progress_callback, 1.0, "Patch complete")
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
    repointed to appended space at the end of the copied ROM so we do not guess
    at internal free space or disturb unrelated data.
    """

    rows = export_character_name_map(data)
    row = select_character_name_row(rows, current_name)
    replacement_bytes = _validate_ascii_replacement_name(
        replacement_name,
        entity_label="character",
        max_length=ROTDD_CHARACTER_NAME_MAX_LENGTH,
    )
    _ensure_replacement_name_is_unique(data, current_name, replacement_name, "character")

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
        target_rom_offset = _append_repoint_payload(mutable, payload)
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
