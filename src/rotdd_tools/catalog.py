"""
Known-table export helpers.

This module mixes generic pointer walking with ROTDD-specific table metadata.
The generic pointer math lives in `gba.py`; the hardcoded table coordinates live
in `rotdd.py`.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .gba import (
    GBA_ROM_BASE,
    iter_find_all,
    pointer_to_rom_offset,
    printable_ascii,
    read_terminated_string,
)
from .models import CharacterNameRow, NpcNameRow, TextMapRow, TextSurfaceRow
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
    Yield exact ASCII runs that contain a specific character name.

    This targets short roster or menu labels that can be missed by the broader
    surface-corpus filters, while still avoiding subword matches inside longer
    words like `Maximum`.
    """

    try:
        needle = current_name.encode("ascii")
    except UnicodeEncodeError:
        return

    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(current_name)}(?![A-Za-z])")
    for hit in iter_find_all(data, needle):
        run_start, run_end = _expand_ascii_run(data, hit, len(needle))
        text = data[run_start:run_end].decode("ascii", errors="replace")
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
            exported.append(
                TextSurfaceRow(
                    row_index=row_index,
                    source_kind="rotdd",
                    rom_offset=index,
                    decoded_text=decode_rotdd_bytes(raw),
                )
            )
            row_index += 1
        index = terminator + 1

    return exported


def export_text_surface_corpus(
    data: bytes,
    min_len: int = 24,
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

    while index < limit:
        if not is_known_rotdd_surface_byte(data[index]):
            index += 1
            continue

        run_start = index
        run: list[int] = []
        while index < limit and is_known_rotdd_surface_byte(data[index]):
            run.append(data[index])
            index += 1

        decoded_text = decode_rotdd_bytes(bytes(run))
        if not _looks_like_rotdd_surface(decoded_text, run, min_len):
            continue

        exported.append(
            TextSurfaceRow(
                row_index=row_index,
                source_kind="rotdd",
                rom_offset=run_start,
                decoded_text=decoded_text,
            )
        )
        row_index += 1

    ascii_min_len = max(4, min_len // 2)
    ascii_allowed_punctuation = set(" '-.,!:;?")
    index = 0
    while index < limit:
        if not printable_ascii(data[index]):
            index += 1
            continue

        run_start = index
        run: list[int] = []
        while index < limit and printable_ascii(data[index]):
            run.append(data[index])
            index += 1

        if len(run) < ascii_min_len:
            continue

        text = bytes(run).decode("ascii", errors="replace")
        if len(text.strip()) < ascii_min_len:
            continue
        if any(not char.isalpha() and char not in ascii_allowed_punctuation for char in text.strip()):
            continue
        if not _looks_like_ascii_surface(text):
            continue

        exported.append(
            TextSurfaceRow(
                row_index=row_index,
                source_kind="ascii",
                rom_offset=run_start,
                decoded_text=text,
            )
        )
        row_index += 1

    return exported


def write_text_surface_csv(rows: list[TextSurfaceRow], output_path: Path) -> None:
    """Write contiguous text-surface rows to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["row_index", "source_kind", "rom_offset", "decoded_text"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow(
                [
                    row.row_index,
                    row.source_kind,
                    f"0x{row.rom_offset:08X}",
                    row.decoded_text,
                ]
            )


def write_npc_name_csv(rows: list[NpcNameRow], output_path: Path) -> None:
    """Write the dialogue-speaker name map to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_index",
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
                    row.row_index,
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
