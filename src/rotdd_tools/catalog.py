"""
Known-table export helpers.

This module mixes generic pointer walking with ROTDD-specific table metadata.
The generic pointer math lives in `gba.py`; the hardcoded table coordinates live
in `rotdd.py`.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from pathlib import Path
from functools import lru_cache

from .gba import (
    GBA_ROM_BASE,
    iter_find_all,
    pointer_to_rom_offset,
    printable_ascii,
    read_terminated_string,
)
from .models import (
    EntityNameTemplateRow,
    CharacterNameRow,
    NpcNameRow,
    TextMapRow,
    TextSurfaceRow,
    TextSurfaceTemplateRow,
)
from .paths import REPO_ROOT
from .rotdd import (
    GAME_SLUG,
    ROTDD_CHARACTER_NAME_COUNT,
    ROTDD_CHARACTER_NAME_POINTER_TABLE_OFFSET,
    ROTDD_CLASS_NAME_TABLE_SLUG,
    ROTDD_ENEMY_NAME_TABLE_SLUG,
    ROTDD_ITEM_NAME_TABLE_SLUG,
    KNOWN_TEXT_TABLES,
    ROTDD_TERMINATOR,
    decode_rotdd_bytes,
    is_known_rotdd_surface_byte,
)


def strip_surface_tags(text: str) -> str:
    """Remove inline <TAG> markers when judging whether a row has visible text."""
    return re.sub(r"<[^>]+>", "", text)


def normalize_visible_name(name: str) -> str:
    """
    Normalize a visible name for cross-table comparisons.

    We keep the spelling and punctuation intact, but collapse repeated
    whitespace and case-fold the result so table comparisons are stable even
    when one export has extra padding spaces.
    """

    return re.sub(r"\s+", " ", name).strip().casefold()


NON_NPC_DIALOGUE_LABELS = {
    normalize_visible_name("Victory Conditions"),
    normalize_visible_name("Clear Bonus"),
}


TEXT_SURFACE_DROP_OFFSETS: set[int] = {
    0x0029D770,
    0x002DD448,
    0x002DD648,
    0x00305749,
    0x00305BB2,
    0x0032EBE4,
    0x0032F11C,
    0x003312A8,
    0x0033BCBA,
    0x0033FFC8,
    0x00340057,
    0x00340768,
    0x003450A1,
    0x0034BFC0,
    0x0034C3A4,
    0x00351D52,
    0x0035DAFE,
    0x0035E345,
    0x003655CC,
    0x00366B05,
    0x00366D8D,
    0x0036B573,
    0x0036EB26,
    0x0036EBBD,
    0x0037C874,
    0x00385883,
    0x00391454,
    0x00391494,
    0x00398DB9,
    0x00398E04,
    0x00398FBC,
    0x003A23F8,
    0x003AF4DA,
    0x00624524,
    0x00625324,
    0x00696194,
    0x006CD24D,
    0x006EA8B5,
    0x00788FFE,
}

TEXT_SURFACE_TYPED_OFFSET_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x001AA623, 0x001AC38C, "object_descriptor"),
    (0x001D092D, 0x001D0B5F, "opening_scene"),
    (0x001D459D, 0x001D7E5C, "item_descriptor"),
    (0x001DA9C0, 0x001DB0AC, "stage_title"),
    (0x001DB0AD, 0x001DB95A, "victory_condition"),
    (0x001DB95B, 0x001DD5B7, "battle_text"),
    (0x001DD5B8, 0x001DE69C, "name_block"),
    (0x001DE69D, 0x001DEB4D, "menu_text"),
    (0x0007AA40, 0x0007ADA8, "credits"),
)


@lru_cache(maxsize=1)
def _canonical_playable_character_names() -> set[str]:
    """
    Load the stable canonical playable-character roster from the checked-in CSV.

    This stays separate from the current ROM export so NPC extraction continues
    to recognize playable characters even after the user renames them in a test
    ROM copy.
    """

    character_csv = REPO_ROOT / "research" / "raw" / "character-names.csv"
    names: set[str] = set()
    try:
        with character_csv.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                name = (row.get("decoded_name") or "").strip()
                if name:
                    names.add(normalize_visible_name(name))
    except OSError:
        pass
    return names


def _looks_like_non_npc_dialogue_label(speaker_name: str, body_text: str) -> bool:
    """
    Return True for dialogue-looking rows that should not become NPC names.

    The NPC pass is intentionally last in precedence. These rows are the
    obvious non-NPC leftovers we still need to keep out of the NPC map even
    though they appear in colon-prefixed dialogue-like surfaces.
    """

    if normalize_visible_name(speaker_name) in NON_NPC_DIALOGUE_LABELS:
        return True
    if body_text.startswith(("Restores ", "Greatly restores ", "Fully restores ")):
        return True
    if "Use during battle" in body_text or "Range:" in body_text:
        return True
    if body_text.startswith(("Cures ", "Creates ", "Blocks ", "Reduces ")):
        return True
    return False


VOWELS = set("aeiouAEIOU")


def _surface_tokens(text: str) -> list[str]:
    """Split decoded surface text into cleaned word-like tokens."""
    visible_text = strip_surface_tags(text).strip()
    tokens: list[str] = []
    for token in visible_text.split():
        cleaned = token.strip("'.-,:;!?")
        if cleaned:
            tokens.append(cleaned)
    return tokens


def _looks_like_human_word(token: str) -> bool:
    """Return True for a token that looks like a readable English word."""
    letters = [char for char in token if char.isalpha()]
    if len(letters) < 3:
        return False
    if not any(char in VOWELS for char in letters):
        return False
    if len(set(char.lower() for char in letters)) <= 2:
        return False
    return token.isupper() or token.islower() or token.istitle()


def _looks_like_rotdd_surface(decoded_text: str, run: list[int], min_len: int) -> bool:
    """Keep dialogue-like rows while rejecting marker-heavy or alphabet-soup runs."""
    visible_text = strip_surface_tags(decoded_text).strip()
    if not visible_text:
        return False
    word_tokens = [token for token in _surface_tokens(decoded_text) if _looks_like_human_word(token)]
    if len(run) < min_len:
        return len(word_tokens) >= 2
    if len(word_tokens) < 2:
        return False
    return " " in visible_text or any(byte in {0x03, 0x09, 0x0A, 0x0E} for byte in run)


def _looks_like_ascii_surface(text: str) -> bool:
    """Keep readable ASCII labels, names, and headers while rejecting noise."""
    stripped = strip_surface_tags(text).strip()
    if not stripped:
        return False

    if stripped.isupper():
        if " " not in stripped:
            return False
        tokens = [token for token in _surface_tokens(text) if token.isalpha()]
        return len(tokens) >= 2

    tokens = [token for token in _surface_tokens(text) if token.isalpha()]
    if not tokens:
        return False

    if " " not in stripped and not (stripped.istitle() or stripped.islower()):
        return False

    if len(tokens) == 1:
        token = tokens[0]
        if len(token) < 4:
            return False
        if not any(char in VOWELS for char in token):
            return False
        return token.istitle() or token.islower()

    if not any(_looks_like_human_word(token) for token in tokens):
        return False
    return True


def _range_contains(index: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    """Return True when an index falls within any inclusive range."""

    return any(start <= index <= end for start, end in ranges)


def _classify_text_surface_row(
    rom_offset: int,
    decoded_text: str,
    enemy_names: set[str],
    item_names: set[str],
) -> tuple[str, bool]:
    """
    Assign a corpus type label and whether the row should be kept.

    The modify-file instructions label only a handful of confirmed ranges.
    Anything else defaults to `unsorted`.
    """

    if rom_offset in TEXT_SURFACE_DROP_OFFSETS:
        return "unsorted", False

    if _range_contains(
        rom_offset,
        tuple((start, end) for start, end, _label in TEXT_SURFACE_TYPED_OFFSET_RANGES),
    ):
        for start, end, label in TEXT_SURFACE_TYPED_OFFSET_RANGES:
            if start <= rom_offset <= end:
                if label != "name_block":
                    return label, True
                normalized = normalize_visible_name(strip_surface_tags(decoded_text))
                if normalized in enemy_names:
                    return "enemy_name", True
                if normalized in item_names:
                    return "item_name", True
                return "unsorted", True

    return "unsorted", True


def _expand_ascii_run(data: bytes, hit: int, needle_length: int) -> tuple[int, int]:
    """
    Expand an exact ASCII hit to the surrounding printable run.

    This is used for short roster/menu labels such as `Mae`, where the whole
    run is too short to survive the broader surface corpus filters.
    """

    start = hit
    while start > 0 and printable_ascii(data[start - 1]):
        start -= 1

    end = hit + needle_length
    limit = len(data)
    while end < limit and printable_ascii(data[end]):
        end += 1

    return start, end


def iter_exact_name_ascii_runs(data: bytes, current_name: str):
    """
    Yield ASCII runs that contain a specific character name or its plural form.

    This targets short roster or menu labels that can be missed by the broader
    surface-corpus filters, while still avoiding subword matches inside longer
    words like `Maximum`.
    """

    try:
        current_name.encode("ascii")
    except UnicodeEncodeError:
        return

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

    singular = re.escape(current_name)
    plural_name = pluralize(current_name)
    plural = re.escape(plural_name)
    if plural == singular:
        pattern = re.compile(rf"(?<![A-Za-z]){singular}(?![A-Za-z])", re.IGNORECASE)
    else:
        pattern = re.compile(rf"(?<![A-Za-z])(?:{singular}|{plural})(?![A-Za-z])", re.IGNORECASE)

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

        text = bytes(run).decode("ascii", errors="replace")
        if pattern.search(text):
            yield run_start, text


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


def export_character_name_map(data: bytes) -> list[CharacterNameRow]:
    """
    Export the canonical character-name pointer table.

    The names themselves are plain ASCII, but the live lookup structure is a
    pointer table. Keeping both the pointer and the resolved ROM offset in the
    export makes it easier to audit repointing work later.
    """

    exported: list[CharacterNameRow] = []
    for local_index in range(ROTDD_CHARACTER_NAME_COUNT):
        pointer_table_offset = ROTDD_CHARACTER_NAME_POINTER_TABLE_OFFSET + (local_index * 4)
        pointer_value = int.from_bytes(data[pointer_table_offset:pointer_table_offset + 4], "little")
        name_rom_offset = pointer_to_rom_offset(pointer_value, base=GBA_ROM_BASE)
        raw = read_terminated_string(data, name_rom_offset, terminator=0x00)
        decoded_name = raw.decode("ascii", errors="strict")
        exported.append(
            CharacterNameRow(
                local_index=local_index,
                pointer_table_offset=pointer_table_offset,
                pointer_value=pointer_value,
                name_rom_offset=name_rom_offset,
                name_length=len(raw),
                decoded_name=decoded_name,
            )
        )
    return exported


def export_class_name_map(data: bytes) -> list[TextMapRow]:
    """Export the confirmed class-name table."""

    return [row for row in export_known_text_map(data) if row.table_slug == ROTDD_CLASS_NAME_TABLE_SLUG]


def export_enemy_name_map(data: bytes) -> list[TextMapRow]:
    """Export the confirmed enemy-name table."""

    return [row for row in export_known_text_map(data) if row.table_slug == ROTDD_ENEMY_NAME_TABLE_SLUG]


def export_item_name_map(data: bytes) -> list[TextMapRow]:
    """Export the confirmed item-name table."""

    return [row for row in export_known_text_map(data) if row.table_slug == ROTDD_ITEM_NAME_TABLE_SLUG]


def collect_named_entity_name_sets(data: bytes) -> dict[str, set[str]]:
    """
    Collect the currently confirmed name sets that should take precedence over NPC extraction.

    The result is intentionally ROM-driven and conservative: it only includes
    the named entities we can already export as canonical or table-backed rows.
    """

    return {
        "character": {normalize_visible_name(row.decoded_name) for row in export_character_name_map(data)},
        "class": {normalize_visible_name(row.decoded_text) for row in export_class_name_map(data)},
        "enemy": {normalize_visible_name(row.decoded_text) for row in export_enemy_name_map(data)},
        "item": {normalize_visible_name(row.decoded_text) for row in export_item_name_map(data)},
    }


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
                }
            )


def write_character_name_csv(rows: list[CharacterNameRow], output_path: Path) -> None:
    """Write the canonical character-name map to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "local_index",
        "pointer_table_offset",
        "pointer_value",
        "name_rom_offset",
        "name_length",
        "decoded_name",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow(
                [
                    row.local_index,
                    f"0x{row.pointer_table_offset:08X}",
                    f"0x{row.pointer_value:08X}",
                    f"0x{row.name_rom_offset:08X}",
                    row.name_length,
                    row.decoded_name,
                ]
            )


def write_name_table_csv(rows: list[TextMapRow], output_path: Path) -> None:
    """Write a name-table export using the compact canonical-name column layout."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "local_index",
        "pointer_table_offset",
        "pointer_value",
        "name_rom_offset",
        "name_length",
        "decoded_name",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow(
                [
                    row.local_index,
                    f"0x{row.pointer_table_offset:08X}",
                    f"0x{row.pointer_value:08X}",
                    f"0x{row.text_rom_offset:08X}",
                    row.text_length,
                    row.decoded_text,
                ]
            )


def write_class_name_csv(rows: list[TextMapRow], output_path: Path) -> None:
    """Write the confirmed class-name table to disk."""
    write_name_table_csv(rows, output_path)


def write_enemy_name_csv(rows: list[TextMapRow], output_path: Path) -> None:
    """Write the confirmed enemy-name table to disk."""
    write_name_table_csv(rows, output_path)


def write_item_name_csv(rows: list[TextMapRow], output_path: Path) -> None:
    """Write the confirmed item-name table to disk."""
    write_name_table_csv(rows, output_path)


def export_text_surface_map(
    data: bytes,
    start: int,
    end: int,
) -> list[TextSurfaceRow]:
    """
    Export a contiguous text surface as CSV-friendly rows.

    This is meant for dialogue, script text, and other terminator-delimited
    surfaces that are not already represented by a pointer table export.
    """
    from .rotdd import ROTDD_TERMINATOR, decode_rotdd_bytes

    exported: list[TextSurfaceRow] = []
    index = start
    limit = min(end, len(data))
    row_index = 0

    while index < limit:
        terminator = data.find(bytes([ROTDD_TERMINATOR]), index, limit)
        if terminator == -1:
            break
        raw = data[index:terminator]
        if raw:
            decoded_text = decode_rotdd_bytes(raw)
            exported.append(
                TextSurfaceRow(
                    row_index=row_index,
                    source_kind="rotdd",
                    rom_offset=index,
                    surface_type="unsorted",
                    decoded_text=decoded_text,
                )
            )
            row_index += 1
        index = terminator + 1

    return exported


def export_text_surface_corpus(
    data: bytes,
    min_len: int = 24,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[TextSurfaceRow]:
    """
    Export a whole-ROM dialogue-like corpus.

    This is intentionally broader than the narrow contiguous surface export.
    It scans for runs of bytes that look like ROTDD dialogue or script text and
    keeps the result human-readable so the rows can be split and translated
    later.
    """
    exported: list[TextSurfaceRow] = []
    index = 0
    row_index = 0
    limit = len(data)
    last_reported = -1.0
    named_entities = collect_named_entity_name_sets(data)
    enemy_name_set = named_entities["enemy"]
    item_name_set = named_entities["item"]

    def report_progress(percent: float, message: str) -> None:
        nonlocal last_reported
        if progress_callback is None:
            return
        percent = max(0.0, min(1.0, percent))
        if percent - last_reported < 0.01 and percent < 1.0:
            return
        last_reported = percent
        progress_callback(percent, message)

    report_progress(0.0, "Scanning ROTDD text surfaces")
    while index < limit:
        if not is_known_rotdd_surface_byte(data[index]):
            index += 1
            report_progress((index / limit) * 0.5 if limit else 0.5, "Scanning ROTDD text surfaces")
            continue

        run_start = index
        run: list[int] = []
        while index < limit and is_known_rotdd_surface_byte(data[index]):
            run.append(data[index])
            index += 1
            report_progress((index / limit) * 0.5 if limit else 0.5, "Scanning ROTDD text surfaces")

        decoded_text = decode_rotdd_bytes(bytes(run))
        if not _looks_like_rotdd_surface(decoded_text, run, min_len):
            continue
        surface_type, keep_row = _classify_text_surface_row(
            run_start,
            decoded_text,
            enemy_name_set,
            item_name_set,
        )
        if not keep_row:
            row_index += 1
            continue

        exported.append(
            TextSurfaceRow(
                row_index=row_index,
                source_kind="rotdd",
                rom_offset=run_start,
                surface_type=surface_type,
                decoded_text=decoded_text,
            )
        )
        row_index += 1

    ascii_min_len = max(4, min_len // 2)
    ascii_allowed_punctuation = set(" '-.,!:;?")
    index = 0
    report_progress(0.5, "Scanning ASCII text surfaces")
    while index < limit:
        if not printable_ascii(data[index]):
            index += 1
            report_progress(0.5 + ((index / limit) * 0.5 if limit else 0.5), "Scanning ASCII text surfaces")
            continue

        run_start = index
        run: list[int] = []
        while index < limit and printable_ascii(data[index]):
            run.append(data[index])
            index += 1
            report_progress(0.5 + ((index / limit) * 0.5 if limit else 0.5), "Scanning ASCII text surfaces")

        if len(run) < ascii_min_len:
            continue

        text = bytes(run).decode("ascii", errors="replace")
        if len(text.strip()) < ascii_min_len:
            continue
        if any(not char.isalpha() and char not in ascii_allowed_punctuation for char in text.strip()):
            continue
        if not _looks_like_ascii_surface(text):
            continue
        surface_type, keep_row = _classify_text_surface_row(
            run_start,
            text,
            enemy_name_set,
            item_name_set,
        )
        if not keep_row:
            row_index += 1
            continue

        exported.append(
            TextSurfaceRow(
                row_index=row_index,
                source_kind="ascii",
                rom_offset=run_start,
                surface_type=surface_type,
                decoded_text=text,
            )
        )
        row_index += 1

    report_progress(1.0, "Text surface scan complete")
    return exported


def write_text_surface_csv(rows: list[TextSurfaceRow], output_path: Path) -> None:
    """Write contiguous text-surface rows to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source_kind", "rom_offset", "type", "decoded_text"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        handle.write(",".join(fieldnames) + "\n")
        for row in rows:
            decoded_text = row.decoded_text.replace('"', '""')
            handle.write(
                f"{row.source_kind},0x{row.rom_offset:08X},{row.surface_type},\"{decoded_text}\"\n"
            )


def read_text_surface_csv(input_path: Path) -> list[TextSurfaceRow]:
    """Load an existing text-surface CSV from disk."""

    rows: list[TextSurfaceRow] = []
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader):
            rows.append(
                TextSurfaceRow(
                    row_index=row_index,
                    source_kind=(row.get("source_kind") or "").strip(),
                    rom_offset=int((row.get("rom_offset") or "0"), 0),
                    surface_type=(row.get("type") or "").strip(),
                    decoded_text=(row.get("decoded_text") or ""),
                )
            )
    return rows


def export_text_surface_template_rows(
    rows: list[TextSurfaceRow],
    surface_type: str,
) -> list[TextSurfaceTemplateRow]:
    """Build a two-column template from a filtered text-surface slice."""

    return [
        TextSurfaceTemplateRow(rom_offset=row.rom_offset, decoded_text=row.decoded_text)
        for row in rows
        if row.surface_type == surface_type
    ]


def write_text_surface_template_csv(
    rows: list[TextSurfaceTemplateRow],
    output_path: Path,
) -> None:
    """Write a two-column editable text-surface template to disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rom_offset", "decoded_text"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        handle.write(",".join(fieldnames) + "\n")
        for row in rows:
            decoded_text = row.decoded_text.replace('"', '""')
            handle.write(f"0x{row.rom_offset:08X},\"{decoded_text}\"\n")


def write_entity_name_template_csv(
    rows: list[EntityNameTemplateRow],
    output_path: Path,
) -> None:
    """Write an editable entity-name template CSV to disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["current_name", "replacement_name"])
        for row in rows:
            writer.writerow([row.current_name, row.replacement_name])


def load_text_surface_template_csv(input_path: Path) -> list[TextSurfaceTemplateRow]:
    """Load a two-column text-surface template CSV from disk."""

    rows: list[TextSurfaceTemplateRow] = []
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                TextSurfaceTemplateRow(
                    rom_offset=int((row.get("rom_offset") or "0"), 0),
                    decoded_text=(row.get("decoded_text") or ""),
                )
            )
    return rows


def load_entity_name_template_csv(input_path: Path) -> list[EntityNameTemplateRow]:
    """Load an entity-name template CSV from disk."""

    rows: list[EntityNameTemplateRow] = []
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                EntityNameTemplateRow(
                    current_name=(row.get("current_name") or "").strip(),
                    replacement_name=(row.get("replacement_name") or "").strip(),
                )
            )
    return rows


def write_npc_name_csv(rows: list[NpcNameRow], output_path: Path) -> None:
    """Write the dialogue-speaker name map to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "first_source_index",
        "first_rom_offset",
        "occurrence_count",
        "npc_name",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow(
                [
                    row.first_source_index,
                    f"0x{row.first_rom_offset:08X}",
                    row.occurrence_count,
                    row.speaker_name,
                ]
            )


def export_npc_name_map(data: bytes) -> list[NpcNameRow]:
    """
    Export visible dialogue-speaker prefixes as a browseable NPC-name map.

    This is intentionally conservative. It only includes dialogue-like ROTDD
    rows that start with a plain speaker label followed by a colon, and it
    skips names that already belong to the playable roster, classes, enemies,
    or items.
    """

    taken_names = collect_named_entity_name_sets(data)
    taken_names["character"].update(_canonical_playable_character_names())
    taken_name_set = set().union(*taken_names.values())
    speaker_pattern = re.compile(r"^(?P<speaker>[A-Za-z][A-Za-z .'\-]{0,31}):(?:\s|$)")
    totals: dict[str, dict[str, object]] = {}

    for row in export_text_surface_corpus(data):
        if row.source_kind != "rotdd":
            continue
        match = speaker_pattern.match(row.decoded_text)
        if not match:
            continue

        speaker_name = match.group("speaker").strip()
        if not speaker_name:
            continue
        normalized_name = normalize_visible_name(speaker_name)
        if normalized_name in taken_name_set:
            continue
        if len(speaker_name.split()) > 3:
            continue

        body_text = row.decoded_text[match.end():].strip()
        if _looks_like_non_npc_dialogue_label(speaker_name, body_text):
            continue

        entry = totals.get(normalized_name)
        if entry is None:
            totals[normalized_name] = {
                "speaker_name": speaker_name,
                "count": 1,
                "first_source_index": row.row_index,
                "first_rom_offset": row.rom_offset,
                "example_text": row.decoded_text,
            }
            continue

        entry["count"] = int(entry["count"]) + 1

    exported: list[NpcNameRow] = []
    for row_index, entry in enumerate(totals.values()):
        exported.append(
            NpcNameRow(
                row_index=row_index,
                speaker_name=str(entry["speaker_name"]),
                occurrence_count=int(entry["count"]),
                first_source_index=int(entry["first_source_index"]),
                first_rom_offset=int(entry["first_rom_offset"]),
                example_text=str(entry["example_text"]),
            )
        )

    return exported


def iter_rotdd_surface_runs(data: bytes):
    """
    Yield every contiguous run that uses only the confirmed ROTDD surface alphabet.

    This is broader than the curated corpus export because it intentionally keeps
    short labels and menu entries that do not meet the dialogue-like length
    threshold. It is useful when a global rename needs to touch every visible
    surface, not just story dialogue.
    """

    index = 0
    limit = len(data)

    while index < limit:
        if not is_known_rotdd_surface_byte(data[index]):
            index += 1
            continue

        run_start = index
        run: list[int] = []
        while index < limit and is_known_rotdd_surface_byte(data[index]):
            run.append(data[index])
            index += 1

        if run:
            yield run_start, bytes(run), decode_rotdd_bytes(bytes(run))
