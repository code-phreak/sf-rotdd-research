"""Command-line interface for the current ROTDD research utilities."""

from __future__ import annotations

import argparse
import csv
import random
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile

from .catalog import (
    load_entity_name_template_csv,
    export_character_name_map,
    export_class_name_map,
    export_enemy_name_map,
    export_known_text_map,
    export_item_name_map,
    export_npc_name_map,
    export_text_surface_template_rows,
    export_text_surface_corpus,
    export_text_surface_map,
    read_text_surface_csv,
    write_class_name_csv,
    write_enemy_name_csv,
    write_item_name_csv,
    write_character_name_csv,
    write_npc_name_csv,
    write_entity_name_template_csv,
    write_text_surface_template_csv,
    write_text_surface_csv,
)
from .models import EntityNameTemplateRow
from .editing import (
    patch_character_name_everywhere,
    patch_class_name_everywhere,
    patch_enemy_name_everywhere,
    patch_item_name_everywhere,
    patch_known_text,
    patch_npc_name_everywhere,
    patch_text_at_offset,
    patch_text_surface_template_file,
    resolve_patch_output_path,
)
from .gba import GBA_ROM_BASE, format_ascii, iter_find_all, printable_ascii, read_terminated_string
from .paths import REPO_ROOT, resolve_rom_path
from .rotdd import (
    KNOWN_TEXT_TABLES,
    decode_rotdd_bytes,
    encode_rotdd_surface_text,
    encode_rotdd_text,
    is_known_rotdd_text_byte,
)


def parse_int(value: str) -> int:
    """Accept plain decimal or Python-style base-prefixed integers."""
    return int(value, 0)


def load_rom(path: Path) -> bytes:
    """Load the requested ROM into memory."""
    if not path.exists():
        raise FileNotFoundError(f"ROM not found: {path}")
    return path.read_bytes()


def search_term(data: bytes, term: str, encodings: list[str]) -> int:
    """Search for a term using standard Python codecs."""
    total_hits = 0
    for encoding in encodings:
        needle = term.encode(encoding)
        hits = list(iter_find_all(data, needle))
        total_hits += len(hits)
        print(f"[{encoding}] {len(hits)} hit(s)")
        for hit in hits:
            print(f"  {hit:#010x}")
    return total_hits


def print_rotdd_encoding(text: str) -> None:
    """Print the encoded bytes for manual ROM patching."""
    encoded = encode_rotdd_surface_text(text)
    print(text)
    print(" ".join(f"{byte:02X}" for byte in encoded))


class ProgressBar:
    """Small stderr progress bar for long-running CLI commands."""

    def __init__(self, label: str = "Working", width: int = 28) -> None:
        self.label = label
        self.width = width
        self.enabled = sys.stderr.isatty()
        self._last_render = ""
        self._last_render_len = 0
        self._message = label
        self._progress = 0.0
        self._stop_event = threading.Event()
        self._real_progress_seen = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._thread = threading.Thread(target=self._idle_loop, daemon=True)
            self._thread.start()

    def update(self, percent: float, message: str) -> None:
        if not self.enabled:
            return
        percent = max(0.0, min(1.0, percent))
        with self._lock:
            self._message = message
            if percent > 0.0:
                self._real_progress_seen.set()
                self._progress = max(self._progress, percent)
            else:
                percent = max(percent, self._progress)
            self._render_locked(percent, message)

    def finish(self, message: str = "Done") -> None:
        if not self.enabled:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        with self._lock:
            self._render_locked(1.0, message)
        sys.stderr.write("\n")
        sys.stderr.flush()

    def _idle_loop(self) -> None:
        """Keep the bar gently moving until real progress starts."""

        while not self._stop_event.is_set() and not self._real_progress_seen.is_set():
            if self._stop_event.wait(random.uniform(1.0, 2.0)):
                return
            with self._lock:
                if self._real_progress_seen.is_set():
                    return
                self._progress = min(0.085, self._progress + random.uniform(0.001, 0.003))
                self._render_locked(self._progress, self._message)

    def _render_locked(self, percent: float, message: str) -> None:
        """Render one progress line while clearing any leftover characters."""

        percent = max(0.0, min(1.0, percent))
        filled = int(round(self.width * percent))
        bar = "#" * filled + "-" * (self.width - filled)
        line = f"[{bar}] {percent * 100:6.1f}% {message}"
        if line == self._last_render:
            return
        self._last_render = line
        self._progress = max(self._progress, percent)
        padded = line.ljust(max(self._last_render_len, len(line)))
        self._last_render_len = max(self._last_render_len, len(line))
        sys.stderr.write("\r" + padded)
        sys.stderr.flush()


def fresh_boot_notice() -> str:
    """Return the emulator fresh-boot reminder used after write commands."""

    return (
        "If this patch is being tested in an emulator, prefer a fresh boot or a freshly reloaded save so cached UI "
        "state does not hide the result of the ROM patch."
    )


def refs_mode_path() -> Path:
    """Return the local preference file used for text-surface ref handling."""

    return REPO_ROOT / "scripts" / "text_surface_refs.local.txt"


def load_refs_mode_preference() -> str | None:
    """Load the saved text-surface ref preference if it exists."""

    path = refs_mode_path()
    try:
        value = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return value if value in {"rewrite", "keep"} else None


def save_refs_mode_preference(mode: str) -> None:
    """Persist the chosen text-surface ref preference locally."""

    path = refs_mode_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{mode}\n", encoding="utf-8")


def clear_refs_mode_preference() -> None:
    """Remove the saved text-surface ref preference if it exists."""

    path = refs_mode_path()
    try:
        path.unlink()
    except OSError:
        pass


def choose_refs_mode(explicit_mode: str | None) -> str:
    """
    Resolve the ref-file handling mode.

    If the caller supplied a mode, use it. Otherwise fall back to a saved local
    preference or prompt once and optionally remember the answer.
    """

    if explicit_mode is not None:
        return explicit_mode

    saved = load_refs_mode_preference()
    if saved is not None:
        return saved

    if not sys.stdin.isatty():
        return "keep"

    print("The ref-file option controls whether the corpus CSV is regenerated after patching.")
    print("rewrite: patch the ROM and regenerate the reference corpus CSV from the patched ROM.")
    print("keep: patch the ROM and leave the reference CSV unchanged.")
    while True:
        choice = input("Choose ref-file mode [keep/rewrite]: ").strip().lower() or "keep"
        if choice in {"keep", "rewrite"}:
            break
        print("Please enter 'keep' or 'rewrite'.")
    remember = input("Save this preference for future runs? [y/N]: ").strip().lower() in {"y", "yes"}
    if remember:
        save_refs_mode_preference(choice)
    return choice


def _format_skipped_reference(ref) -> str:
    """Render a compact one-line summary for a skipped rename reference."""

    kind_map = {
        "canonical_name": "canonical",
        "known_text": "known",
        "rotdd_surface_run": "surface-run",
        "ascii_exact_name": "ascii-name",
        "ascii_surface": "ascii-surface",
        "text_surface:rotdd": "surface",
        "text_surface:ascii": "ascii-surface",
        "npc_surface:rotdd": "npc-surface",
        "npc_surface:ascii": "npc-ascii",
        "npc_surface_run": "npc-run",
        "npc_ascii_surface": "npc-ascii",
        "character_name_table": "character",
        "class_name_table": "class",
        "enemy_name_table": "enemy",
        "item_name_table": "item",
    }
    suffix = f" reason={ref.skip_reason}" if getattr(ref, "skip_reason", "") else ""
    kind = kind_map.get(ref.source_kind, ref.source_kind)
    return (
        f"  kind={kind} "
        f"rom=0x{ref.rom_offset:08X} "
        f"src={ref.source_label}[{ref.source_index}]" + suffix
    )


def _emit_messages(messages: list[str]) -> None:
    """Print deferred user-facing lines after long-running work finishes."""

    for message in messages:
        print(message)


def _add_write_args(parser: argparse.ArgumentParser) -> None:
    """Add the standard output/write flags used by patch commands."""

    parser.add_argument(
        "--output",
        type=Path,
        help="Patched ROM path. Defaults to a sibling file ending in .patched.gba.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow the output file to be overwritten if it already exists.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write directly into the source ROM. Unsafe.",
    )


def _add_entity_tree_parser(
    parser: argparse.ArgumentParser,
    *,
    display_name: str,
    export_output: Path,
    list_help: str,
    export_help: str,
    patch_help: str,
    allow_stat: bool,
    patch_help_suffix: str,
) -> None:
    """Add the tree-style entity command surface."""

    entity_subparsers = parser.add_subparsers(dest="action", required=True)

    export_parser = entity_subparsers.add_parser("export", help=export_help)
    export_subparsers = export_parser.add_subparsers(dest="target", required=True)
    export_map_parser = export_subparsers.add_parser(
        "map",
        help=f"Export the confirmed {display_name} slice to a CSV artifact.",
    )
    export_map_parser.add_argument(
        "--output",
        type=Path,
        default=export_output,
        help="Output CSV path, relative to the repository root by default.",
    )

    export_template_parser = export_subparsers.add_parser(
        "template",
        help=f"Export an editable template for the current {display_name} names.",
    )
    export_template_parser.add_argument(
        "--output",
        type=Path,
        default=_entity_template_default_path(display_name),
        help="Output CSV path, relative to the repository root by default.",
    )

    list_parser = entity_subparsers.add_parser("list", help=list_help)
    list_subparsers = list_parser.add_subparsers(dest="target", required=True)
    list_names_parser = list_subparsers.add_parser(
        "names",
        help=f"List the confirmed {display_name} names from the current table.",
    )
    list_names_parser.add_argument(
        "--contains",
        help="Only list names whose decoded text contains this substring.",
    )
    list_names_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of rows to print.",
    )

    patch_parser = entity_subparsers.add_parser("patch", help=patch_help)
    patch_subparsers = patch_parser.add_subparsers(dest="target", required=True)
    patch_name_parser = patch_subparsers.add_parser(
        "name",
        help=patch_help_suffix,
    )
    patch_name_parser.add_argument("current_name", help=f"Existing {display_name} name to replace.")
    patch_name_parser.add_argument("replacement", help=f"New {display_name} name.")
    patch_name_parser.add_argument(
        "--mode",
        choices=["strict", "liberal"],
        default="strict",
        help="Strict is the default conservative mode. Liberal may rewrite unsafe references in place.",
    )
    _add_write_args(patch_name_parser)

    patch_file_parser = patch_subparsers.add_parser(
        "file",
        help=f"Patch many {display_name} renames from an editable template CSV.",
    )
    patch_file_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input CSV path with current_name and replacement_name columns.",
    )
    patch_file_parser.add_argument(
        "--mode",
        choices=["strict", "liberal"],
        default="strict",
        help="Strict is the default conservative mode. Liberal may rewrite unsafe references in place.",
    )
    _add_write_args(patch_file_parser)

    if allow_stat:
        patch_stat_parser = patch_subparsers.add_parser(
            "stat",
            help=f"Reserved future stat-edit command for {display_name} entities.",
        )
        patch_stat_parser.add_argument("stat_name", help="Stat name to edit.")
        patch_stat_parser.add_argument("target_name", help=f"Existing {display_name} name to modify.")
        patch_stat_parser.add_argument("value", help="Replacement numeric value or text value.")
        _add_write_args(patch_stat_parser)


def _entity_patch_is_progress_command(args: argparse.Namespace) -> bool:
    """Return True when an entity command should display progress."""

    return (
        args.command in {"character", "class", "enemy", "item", "npc"}
        and getattr(args, "action", None) == "patch"
        and getattr(args, "target", None) in {"name", "file"}
    )


def _run_entity_name_patch(
    *,
    entity: str,
    data: bytes,
    rom_path: Path,
    args: argparse.Namespace,
    progress_callback: Callable[[float, str], None] | None,
) -> list[str]:
    """Dispatch a tree-style entity rename command."""

    patchers = {
        "character": run_patch_character_name,
        "class": run_patch_class_name,
        "enemy": run_patch_enemy_name,
        "item": run_patch_item_name,
        "npc": run_patch_npc_name,
    }
    return patchers[entity](
        data=data,
        rom_path=rom_path,
        current_name=args.current_name,
        replacement_name=args.replacement,
        mode=args.mode,
        output=args.output,
        overwrite=args.overwrite,
        in_place=args.in_place,
        progress_callback=progress_callback,
    )


def _run_entity_name_list(
    *,
    entity: str,
    data: bytes,
    args: argparse.Namespace,
) -> int:
    """Dispatch a tree-style entity list command."""

    listers = {
        "character": run_list_character_names,
        "class": run_list_class_names,
        "enemy": run_list_enemy_names,
        "item": run_list_item_names,
        "npc": run_list_npc_names,
    }
    return 0 if listers[entity](data, args.contains, args.limit) else 1


def _run_entity_name_export(
    *,
    entity: str,
    data: bytes,
    args: argparse.Namespace,
) -> None:
    """Dispatch a tree-style entity export command."""

    exporters = {
        "character": run_export_character_name_map,
        "class": run_export_class_name_map,
        "enemy": run_export_enemy_name_map,
        "item": run_export_item_name_map,
        "npc": run_export_npc_name_map,
    }
    exporters[entity](data, args.output)


def _run_entity_name_template_export(
    *,
    entity: str,
    data: bytes,
    args: argparse.Namespace,
) -> None:
    """Dispatch a tree-style entity template export command."""

    run_export_entity_name_template(data, entity, args.output)


def _run_entity_name_patch_file(
    *,
    entity: str,
    data: bytes,
    rom_path: Path,
    args: argparse.Namespace,
    progress_callback: Callable[[float, str], None] | None,
) -> list[str]:
    """Dispatch a tree-style entity bulk-patch command."""

    return run_patch_entity_name_template_file(
        entity=entity,
        data=data,
        rom_path=rom_path,
        input_path=args.input,
        output=args.output,
        overwrite=args.overwrite,
        in_place=args.in_place,
        mode=args.mode,
        progress_callback=progress_callback,
    )


def search_rotdd(data: bytes, term: str) -> int:
    """Search for a term after encoding it with the known ROTDD codec."""
    needle = encode_rotdd_text(term)
    hits = list(iter_find_all(data, needle))
    print(f"[rotdd] {len(hits)} hit(s)")
    print(f"  encoded bytes: {' '.join(f'{byte:02X}' for byte in needle)}")
    for hit in hits:
        print(f"  {hit:#010x}")
    return len(hits)


def dump_strings(data: bytes, start: int, end: int, min_len: int, contains: str | None) -> int:
    """Dump printable ASCII strings inside a ROM range."""
    count = 0
    current: list[int] = []
    string_start = start
    for index in range(start, min(end, len(data))):
        byte = data[index]
        if printable_ascii(byte):
            if not current:
                string_start = index
            current.append(byte)
            continue
        if len(current) >= min_len:
            text = bytes(current).decode("ascii")
            if contains is None or contains in text:
                print(f"{string_start:#010x} {text}")
                count += 1
        current = []
    if len(current) >= min_len:
        text = bytes(current).decode("ascii")
        if contains is None or contains in text:
            print(f"{string_start:#010x} {text}")
            count += 1
    return count


def dump_rotdd(data: bytes, start: int, end: int, min_len: int, contains: str | None) -> int:
    """Dump null-terminated strings using the current ROTDD decoder."""
    count = 0
    index = start
    limit = min(end, len(data))
    while index < limit:
        terminator = data.find(bytes([0x00]), index, limit)
        if terminator == -1:
            break
        if terminator > index:
            text = decode_rotdd_bytes(data[index:terminator])
            printable_len = len(text.replace(" ", ""))
            if printable_len >= min_len and (contains is None or contains in text):
                print(f"{index:#010x} {text}")
                count += 1
        index = terminator + 1
    return count


def scan_rotdd_candidates(data: bytes, start: int, end: int, min_len: int) -> int:
    """Scan for contiguous runs that use only the confirmed ROTDD text alphabet."""
    count = 0
    index = start
    limit = min(end, len(data))
    while index < limit:
        if not is_known_rotdd_text_byte(data[index]):
            index += 1
            continue

        run_start = index
        run: list[int] = []
        while index < limit and is_known_rotdd_text_byte(data[index]):
            run.append(data[index])
            index += 1

        if len(run) >= min_len:
            text = decode_rotdd_bytes(bytes(run))
            print(f"{run_start:#010x} len={len(run):>3} {text}")
            count += 1

    return count


def decode_at_offset(data: bytes, offset: int, codec: str) -> str:
    """Decode a null-terminated string from a ROM offset using the requested codec."""
    raw = read_terminated_string(data, offset)
    if codec == "rotdd":
        return decode_rotdd_bytes(raw)
    if codec == "ascii":
        return raw.decode("ascii", errors="replace")
    if codec == "hex":
        return " ".join(f"{byte:02X}" for byte in raw)
    raise ValueError(f"Unsupported codec: {codec}")


def dump_pointer_table(data: bytes, start: int, count: int, gba_base: int, codec: str) -> None:
    """Decode a 32-bit pointer table into ROM offsets and text entries."""
    for index in range(count):
        table_offset = start + (index * 4)
        entry = int.from_bytes(data[table_offset:table_offset + 4], "little")
        if entry < gba_base:
            print(f"{index:03d} {table_offset:#010x} INVALID {entry:#010x}")
            continue
        rom_offset = entry - gba_base
        if rom_offset >= len(data):
            print(f"{index:03d} {table_offset:#010x} OUT_OF_RANGE {entry:#010x}")
            continue
        text = decode_at_offset(data, rom_offset, codec)
        print(f"{index:03d} {table_offset:#010x} -> {rom_offset:#010x} {text}")


def find_pointer(data: bytes, rom_offset: int, gba_base: int) -> int:
    """Search for little-endian GBA pointers to a ROM offset."""
    pointer_value = (gba_base + rom_offset).to_bytes(4, "little")
    hits = list(iter_find_all(data, pointer_value))
    print(f"pointer {gba_base + rom_offset:#010x} -> {len(hits)} hit(s)")
    for hit in hits:
        print(f"  {hit:#010x}")
    return len(hits)


def peek(data: bytes, start: int, length: int) -> None:
    """Print a hex and ASCII view of a ROM region."""
    end = min(start + length, len(data))
    for row_start in range(start, end, 16):
        row = data[row_start:min(row_start + 16, end)]
        hex_bytes = " ".join(f"{byte:02X}" for byte in row)
        print(f"{row_start:#010x}  {hex_bytes:<47}  {format_ascii(row)}")


def run_export_character_name_map(data: bytes, output: Path) -> None:
    """Export the canonical character-name pointer table to CSV."""
    rows = export_character_name_map(data)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_character_name_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def run_export_enemy_name_map(data: bytes, output: Path) -> None:
    """Export the confirmed enemy-type name table to CSV."""
    rows = export_enemy_name_map(data)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_enemy_name_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def run_export_class_name_map(data: bytes, output: Path) -> None:
    """Export the confirmed class-name table to CSV."""
    rows = export_class_name_map(data)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_class_name_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def run_export_item_name_map(data: bytes, output: Path) -> None:
    """Export the confirmed item-name table to CSV."""
    rows = export_item_name_map(data)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_item_name_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def run_export_npc_name_map(data: bytes, output: Path) -> None:
    """Export dialogue-speaker prefixes as an NPC-style browseable CSV."""
    rows = export_npc_name_map(data)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_npc_name_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def _entity_name_rows(data: bytes, entity: str) -> list[str]:
    """Return the visible names that should seed an entity template export."""

    if entity == "character":
        return [row.decoded_name for row in export_character_name_map(data)]
    if entity == "class":
        return [row.decoded_text for row in export_class_name_map(data)]
    if entity == "enemy":
        return [row.decoded_text for row in export_enemy_name_map(data)]
    if entity == "item":
        return [row.decoded_text for row in export_item_name_map(data)]
    if entity == "npc":
        return [row.speaker_name for row in export_npc_name_map(data)]
    raise ValueError(f"Unsupported entity: {entity}")


def _entity_name_max_length(entity: str) -> int | None:
    """Return the current soft cap for a rename target, if any."""

    return {
        "character": 8,
        "class": 12,
        "enemy": 12,
        "item": 12,
        "npc": None,
    }[entity]


def _validate_entity_template_row(entity: str, current_name: str, replacement_name: str) -> None:
    """Fail fast on obviously invalid entity template rows."""

    max_length = _entity_name_max_length(entity)
    if max_length is None:
        # NPC names are line-length constrained instead of capped here.
        replacement_name.encode("ascii")
        if not replacement_name.strip():
            raise ValueError("NPC names cannot be empty.")
        return
    replacement_bytes = replacement_name.encode("ascii")
    if not replacement_bytes:
        raise ValueError(f"{entity.capitalize()} names cannot be empty.")
    if len(replacement_bytes) > max_length:
        raise ValueError(f"{entity.capitalize()} names are currently limited to {max_length} ASCII characters.")


def _entity_template_default_path(entity: str) -> Path:
    """Return the default repository-relative output for an entity template export."""

    return Path(f"ignore/temp/{entity}-names.template.csv")


def run_export_entity_name_template(data: bytes, entity: str, output: Path) -> None:
    """Export a two-column editable template for an entity-name workflow."""

    rows = [EntityNameTemplateRow(current_name=name, replacement_name="") for name in _entity_name_rows(data, entity)]
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_entity_name_template_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def run_patch_entity_name_template_file(
    *,
    entity: str,
    data: bytes,
    rom_path: Path,
    input_path: Path,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch multiple entity renames from a two-column template CSV."""

    template_path = input_path if input_path.is_absolute() else (REPO_ROOT / input_path)
    template_rows = load_entity_name_template_csv(template_path)
    patchers = {
        "character": run_patch_character_name,
        "class": run_patch_class_name,
        "enemy": run_patch_enemy_name,
        "item": run_patch_item_name,
        "npc": run_patch_npc_name,
    }
    patcher = patchers[entity]
    final_output_path = resolve_patch_output_path(
        source_path=rom_path,
        output_path=(output if output is None else (output if output.is_absolute() else (REPO_ROOT / output))),
        overwrite=overwrite,
        in_place=in_place,
    )

    work_dir = REPO_ROOT / "ignore" / "temp"
    work_dir.mkdir(parents=True, exist_ok=True)
    work_file = NamedTemporaryFile(delete=False, suffix=".gba", dir=work_dir)
    work_path = Path(work_file.name)
    work_file.close()

    current_data = bytes(data)
    patched_rows = 0
    skipped_rows: list[str] = []
    total_rows = max(1, len(template_rows))
    try:
        for row_index, row in enumerate(template_rows):
            _report_progress(
                progress_callback,
                0.02 + (0.96 * (row_index / total_rows)),
                f"Patching {entity} template rows",
            )
            if not row.current_name:
                continue
            if not row.replacement_name:
                continue
            if row.current_name == row.replacement_name:
                continue
            try:
                _validate_entity_template_row(entity, row.current_name, row.replacement_name)
            except ValueError as exc:
                skipped_rows.append(f"  current={row.current_name!r} reason={str(exc)}")
                continue
            try:
                messages = patcher(
                    data=current_data,
                    rom_path=rom_path,
                    current_name=row.current_name,
                    replacement_name=row.replacement_name,
                    mode=mode,
                    output=work_path,
                    overwrite=True,
                    in_place=False,
                    progress_callback=None,
                )
            except ValueError as exc:
                skipped_rows.append(f"  current={row.current_name!r} reason={str(exc)}")
                continue
            current_data = work_path.read_bytes()
            patched_rows += 1
            if messages:
                # Keep the command quiet; the batch summary is the useful part.
                pass
        final_output_path.parent.mkdir(parents=True, exist_ok=True)
        final_output_path.write_bytes(current_data)
    finally:
        try:
            work_path.unlink()
        except OSError:
            pass

    messages = [
        f"Template file: {template_path}",
        f"Patched rows: {patched_rows}",
        f"Skipped rows: {len(skipped_rows)}",
    ]
    if skipped_rows:
        messages.append("Skipped rows:")
        messages.extend(skipped_rows)
    messages.append(f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}")
    return messages


def run_export_text_surface_map(
    data: bytes,
    start: int,
    end: int,
    output: Path,
) -> None:
    """Export a contiguous text surface to a research CSV artifact."""
    rows = export_text_surface_map(data=data, start=start, end=end)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_text_surface_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def run_export_text_surface_corpus(
    data: bytes,
    min_len: int,
    output: Path,
    progress_callback: Callable[[float, str], None] | None = None,
) -> None:
    """Export the broad dialogue-like surface corpus to CSV."""

    rows = export_text_surface_corpus(data=data, min_len=min_len, progress_callback=progress_callback)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_text_surface_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


def run_export_text_surface_template(
    input_path: Path,
    surface_type: str,
    output: Path,
) -> None:
    """Export a two-column text-surface template filtered by type."""

    source_path = input_path if input_path.is_absolute() else (REPO_ROOT / input_path)
    rows = read_text_surface_csv(source_path)
    template_rows = export_text_surface_template_rows(rows, surface_type)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_text_surface_template_csv(template_rows, output_path)
    print(f"Wrote {len(template_rows)} rows to {output_path}")


def run_list_character_names(data: bytes, contains: str | None, limit: int | None) -> int:
    """List canonical character names in a compact terminal-friendly format."""
    rows = export_character_name_map(data)
    if contains is not None:
        needle = contains.lower()
        rows = [row for row in rows if needle in row.decoded_name.lower()]
    if limit is not None:
        rows = rows[:limit]

    for row in rows:
        print(
            f"{row.local_index:>3} "
            f"ptr=0x{row.pointer_table_offset:08X} "
            f"rom=0x{row.name_rom_offset:08X} "
            f"name={row.decoded_name}"
        )

    return len(rows)


def run_patch_text_surface_template(
    data: bytes,
    rom_path: Path,
    input_path: Path,
    corpus_path: Path,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    mode: str,
    refs_mode: str | None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch every changed row in a two-column text-surface template CSV."""

    template_path = input_path if input_path.is_absolute() else (REPO_ROOT / input_path)
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    changed_rows, patched_rows, skipped_rows, deferred_messages, final_output_path = patch_text_surface_template_file(
        data=data,
        source_path=rom_path,
        template_path=template_path,
        corpus_path=corpus_path if corpus_path.is_absolute() else (REPO_ROOT / corpus_path),
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        mode=mode,
        rewrite_reference_corpus=refs_mode == "rewrite",
        progress_callback=progress_callback,
    )

    messages = [
        f"Template file: {template_path}",
        f"Template diffs: {changed_rows}",
        f"ROM writes: {patched_rows}",
        f"Skipped rows: {len(skipped_rows)}",
    ]
    if skipped_rows:
        messages.append("Skipped rows:")
        messages.extend(skipped_rows)
    messages.extend(deferred_messages)
    messages.append(f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}")
    return messages


def run_list_enemy_names(data: bytes, contains: str | None, limit: int | None) -> int:
    """List confirmed enemy-type names in a compact terminal-friendly format."""
    rows = export_enemy_name_map(data)
    if contains is not None:
        needle = contains.lower()
        rows = [row for row in rows if needle in row.decoded_text.lower()]
    if limit is not None:
        rows = rows[:limit]

    for row in rows:
        print(
            f"{row.local_index:>3} "
            f"ptr=0x{row.pointer_table_offset:08X} "
            f"rom=0x{row.text_rom_offset:08X} "
            f"name={row.decoded_text}"
        )

    return len(rows)


def run_list_class_names(data: bytes, contains: str | None, limit: int | None) -> int:
    """List confirmed class names in a compact terminal-friendly format."""
    rows = export_class_name_map(data)
    if contains is not None:
        needle = contains.lower()
        rows = [row for row in rows if needle in row.decoded_text.lower()]
    if limit is not None:
        rows = rows[:limit]

    for row in rows:
        print(
            f"{row.local_index:>3} "
            f"ptr=0x{row.pointer_table_offset:08X} "
            f"rom=0x{row.text_rom_offset:08X} "
            f"name={row.decoded_text}"
        )

    return len(rows)


def run_list_item_names(data: bytes, contains: str | None, limit: int | None) -> int:
    """List confirmed item names in a compact terminal-friendly format."""
    rows = export_item_name_map(data)
    if contains is not None:
        needle = contains.lower()
        rows = [row for row in rows if needle in row.decoded_text.lower()]
    if limit is not None:
        rows = rows[:limit]

    for row in rows:
        print(
            f"{row.local_index:>3} "
            f"ptr=0x{row.pointer_table_offset:08X} "
            f"rom=0x{row.text_rom_offset:08X} "
            f"name={row.decoded_text}"
        )

    return len(rows)


def run_list_npc_names(data: bytes, contains: str | None, limit: int | None) -> int:
    """List dialogue-speaker prefixes in a compact terminal-friendly format."""
    rows = export_npc_name_map(data)
    if contains is not None:
        needle = contains.lower()
        rows = [row for row in rows if needle in row.speaker_name.lower()]
    if limit is not None:
        rows = rows[:limit]

    for row in rows:
        print(
            f"{row.row_index:>3} "
            f"count={row.occurrence_count:>3} "
            f"rom=0x{row.first_rom_offset:08X} "
            f"name={row.speaker_name}"
        )

    return len(rows)


def run_list_known_text(
    data: bytes,
    table_slug: str | None,
    category: str | None,
    contains: str | None,
    limit: int | None,
    show_notes: bool,
) -> int:
    """List mapped text rows in a compact terminal-friendly format."""
    rows = export_known_text_map(data)

    if table_slug is not None:
        rows = [row for row in rows if row.table_slug == table_slug]
    if category is not None:
        rows = [row for row in rows if row.category == category]
    if contains is not None:
        needle = contains.lower()
        rows = [row for row in rows if needle in row.decoded_text.lower()]
    if limit is not None:
        rows = rows[:limit]

    for row in rows:
        line = (
            f"{row.table_slug:<28} "
            f"{row.category:<20} "
            f"{row.local_index:>3} "
            f"ptr=0x{row.pointer_table_offset:08X} "
            f"rom=0x{row.text_rom_offset:08X} "
            f"text={row.decoded_text}"
        )
        if show_notes and row.notes:
            line = f"{line} | {row.notes}"
        print(line)

    return len(rows)


def run_patch_known_text(
    data: bytes,
    rom_path: Path,
    table_slug: str,
    local_index: int | None,
    match_text: str | None,
    occurrence: int | None,
    replacement_text: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch a known text entry and report what changed."""
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    row, replacement_bytes, final_output_path = patch_known_text(
        data=data,
        source_path=rom_path,
        table_slug=table_slug,
        local_index=local_index,
        match_text=match_text,
        occurrence=occurrence,
        replacement_text=replacement_text,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        progress_callback=progress_callback,
    )

    messages = [
        f"Patched table: {row.table_slug}",
        f"Local index: {row.local_index}",
        f"Original text: {row.decoded_text}",
        f"Replacement: {replacement_text}",
        f"ROM offset: 0x{row.text_rom_offset:08X}",
        f"Pointer-table offset: 0x{row.pointer_table_offset:08X}",
        f"Encoded bytes: {' '.join(f'{byte:02X}' for byte in replacement_bytes)}",
        f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}",
    ]
    return messages


def run_patch_character_name(
    data: bytes,
    rom_path: Path,
    current_name: str,
    replacement_name: str,
    mode: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch a character name everywhere we can confidently see it."""
    _validate_entity_template_row("character", current_name, replacement_name)
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    row, patched_rows, skipped_rows, final_output_path = patch_character_name_everywhere(
        data=data,
        source_path=rom_path,
        current_name=current_name,
        replacement_name=replacement_name,
        mode=mode,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        progress_callback=progress_callback,
    )

    messages = [
        f"Character name: {row.decoded_name}",
        f"Replacement: {replacement_name}",
        f"Pointer-table offset: 0x{row.pointer_table_offset:08X}",
        f"Original ROM offset: 0x{row.name_rom_offset:08X}",
        f"Patched references: {len(patched_rows)}",
        f"Skipped references: {len(skipped_rows)}",
    ]
    if any(ref.source_kind == "canonical_name" for ref in patched_rows):
        messages.append("Canonical pointer table updated.")
    if skipped_rows:
        messages.append("Skipped rows:")
        messages.extend(_format_skipped_reference(ref) for ref in skipped_rows)
    messages.append(f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}")
    return messages


def run_patch_enemy_name(
    data: bytes,
    rom_path: Path,
    current_name: str,
    replacement_name: str,
    mode: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch an enemy-type name everywhere we can confidently see it."""
    _validate_entity_template_row("enemy", current_name, replacement_name)
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    row, patched_rows, skipped_rows, final_output_path = patch_enemy_name_everywhere(
        data=data,
        source_path=rom_path,
        current_name=current_name,
        replacement_name=replacement_name,
        mode=mode,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        progress_callback=progress_callback,
    )

    messages = [
        f"Enemy name: {row.decoded_text}",
        f"Replacement: {replacement_name}",
        f"Patched references: {len(patched_rows)}",
        f"Skipped references: {len(skipped_rows)}",
    ]
    if skipped_rows:
        messages.append("Skipped rows:")
        messages.extend(_format_skipped_reference(ref) for ref in skipped_rows)
    messages.append(f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}")
    return messages


def run_patch_item_name(
    data: bytes,
    rom_path: Path,
    current_name: str,
    replacement_name: str,
    mode: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch an item name everywhere we can confidently see it."""
    _validate_entity_template_row("item", current_name, replacement_name)
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    row, patched_rows, skipped_rows, final_output_path = patch_item_name_everywhere(
        data=data,
        source_path=rom_path,
        current_name=current_name,
        replacement_name=replacement_name,
        mode=mode,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        progress_callback=progress_callback,
    )

    messages = [
        f"Item name: {row.decoded_text}",
        f"Replacement: {replacement_name}",
        f"Patched references: {len(patched_rows)}",
        f"Skipped references: {len(skipped_rows)}",
    ]
    if skipped_rows:
        messages.append("Skipped rows:")
        messages.extend(_format_skipped_reference(ref) for ref in skipped_rows)
    messages.append(f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}")
    return messages


def run_patch_npc_name(
    data: bytes,
    rom_path: Path,
    current_name: str,
    replacement_name: str,
    mode: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch a dialogue-speaker or NPC-style name across dialogue surfaces."""
    _validate_entity_template_row("npc", current_name, replacement_name)
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    row, patched_rows, skipped_rows, final_output_path = patch_npc_name_everywhere(
        data=data,
        source_path=rom_path,
        current_name=current_name,
        replacement_name=replacement_name,
        mode=mode,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        progress_callback=progress_callback,
    )

    messages = [
        f"NPC name: {row.speaker_name}",
        f"Replacement: {replacement_name}",
        f"Patched references: {len(patched_rows)}",
        f"Skipped references: {len(skipped_rows)}",
    ]
    if skipped_rows:
        messages.append("Skipped rows:")
        messages.extend(_format_skipped_reference(ref) for ref in skipped_rows)
    messages.append(f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}")
    return messages


def run_patch_class_name(
    data: bytes,
    rom_path: Path,
    current_name: str,
    replacement_name: str,
    mode: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch a class name everywhere we can confidently see it."""
    _validate_entity_template_row("class", current_name, replacement_name)
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    row, patched_rows, skipped_rows, final_output_path = patch_class_name_everywhere(
        data=data,
        source_path=rom_path,
        current_name=current_name,
        replacement_name=replacement_name,
        mode=mode,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        progress_callback=progress_callback,
    )

    messages = [
        f"Class name: {row.decoded_text}",
        f"Replacement: {replacement_name}",
        f"Patched references: {len(patched_rows)}",
        f"Skipped references: {len(skipped_rows)}",
    ]
    if skipped_rows:
        messages.append("Skipped rows:")
        messages.extend(_format_skipped_reference(ref) for ref in skipped_rows)
    messages.append(f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}")
    return messages


def run_patch_text_at_offset(
    data: bytes,
    rom_path: Path,
    rom_offset: int,
    replacement_text: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
    progress_callback: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Patch an arbitrary ROM offset using a simple address + text form."""
    output_path = None
    if output is not None:
        output_path = output if output.is_absolute() else (REPO_ROOT / output)

    original_text, replacement_bytes, final_output_path = patch_text_at_offset(
        data=data,
        source_path=rom_path,
        rom_offset=rom_offset,
        replacement_text=replacement_text,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
        progress_callback=progress_callback,
    )

    return [
        f"ROM offset: 0x{rom_offset:08X}",
        f"Original text: {original_text}",
        f"Replacement: {replacement_text}",
        f"Encoded bytes: {' '.join(f'{byte:02X}' for byte in replacement_bytes)}",
        f"Patched source ROM in place: {final_output_path}" if in_place else f"Wrote patched ROM: {final_output_path}",
    ]


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description="Probe ROM text and pointer structures.")
    parser.add_argument(
        "--rom",
        type=Path,
        help="Path to the ROM file. If omitted, the script checks scripts/rom_path.local.txt or prompts for one.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser(
        "encode-rotdd",
        help="Encode text with the current ROTDD custom text codec.",
    )
    encode_parser.add_argument("term", help="Text to encode.")

    search_parser = subparsers.add_parser(
        "search-term",
        help="Search for a term in one or more standard encodings.",
    )
    search_parser.add_argument("term", help="Text to search for.")
    search_parser.add_argument(
        "--encoding",
        nargs="+",
        default=["ascii", "utf-16le"],
        help="Python codec names to try. Default: ascii utf-16le",
    )

    rotdd_search_parser = subparsers.add_parser(
        "search-rotdd",
        help="Search using the currently known ROTDD custom text codec.",
    )
    rotdd_search_parser.add_argument("term", help="Text to encode and search for.")

    strings_parser = subparsers.add_parser(
        "dump-strings",
        help="Dump printable ASCII strings with ROM offsets.",
    )
    strings_parser.add_argument("--start", type=parse_int, default=0, help="Start ROM offset.")
    strings_parser.add_argument("--end", type=parse_int, default=0x800000, help="End ROM offset.")
    strings_parser.add_argument("--min-len", type=int, default=4, help="Minimum string length.")
    strings_parser.add_argument("--contains", help="Only print strings containing this substring.")

    rotdd_dump_parser = subparsers.add_parser(
        "dump-rotdd",
        help="Dump null-terminated strings using the current ROTDD custom codec.",
    )
    rotdd_dump_parser.add_argument("--start", type=parse_int, default=0, help="Start ROM offset.")
    rotdd_dump_parser.add_argument("--end", type=parse_int, default=0x800000, help="End ROM offset.")
    rotdd_dump_parser.add_argument(
        "--min-len",
        type=int,
        default=4,
        help="Minimum decoded string length, excluding spaces.",
    )
    rotdd_dump_parser.add_argument("--contains", help="Only print decoded strings containing this substring.")

    rotdd_scan_parser = subparsers.add_parser(
        "scan-rotdd-runs",
        help="Scan for contiguous runs that use only the confirmed ROTDD text alphabet.",
    )
    rotdd_scan_parser.add_argument("--start", type=parse_int, default=0, help="Start ROM offset.")
    rotdd_scan_parser.add_argument("--end", type=parse_int, default=0x800000, help="End ROM offset.")
    rotdd_scan_parser.add_argument(
        "--min-len",
        type=int,
        default=4,
        help="Minimum run length in bytes.",
    )

    pointer_parser = subparsers.add_parser(
        "find-pointer",
        help="Search for a GBA ROM pointer to a target offset.",
    )
    pointer_parser.add_argument("offset", type=parse_int, help="ROM offset to search pointers for.")
    pointer_parser.add_argument("--base", type=parse_int, default=GBA_ROM_BASE, help="GBA ROM base address.")

    table_parser = subparsers.add_parser(
        "dump-pointer-table",
        help="Decode a 32-bit pointer table into strings.",
    )
    table_parser.add_argument("offset", type=parse_int, help="ROM offset of the pointer table.")
    table_parser.add_argument("--count", type=int, required=True, help="Number of 4-byte entries to dump.")
    table_parser.add_argument("--base", type=parse_int, default=GBA_ROM_BASE, help="GBA ROM base address.")
    table_parser.add_argument(
        "--codec",
        choices=["rotdd", "ascii", "hex"],
        default="rotdd",
        help="How to decode the pointed data. Default: rotdd",
    )

    list_parser = subparsers.add_parser(
        "list-known-text",
        help="List mapped rows from the current known ROTDD text tables.",
    )
    list_parser.add_argument(
        "--table",
        choices=[table.slug for table in KNOWN_TEXT_TABLES],
        help="Only list rows from one known table.",
    )
    list_parser.add_argument(
        "--category",
        choices=sorted({table.category for table in KNOWN_TEXT_TABLES}),
        help="Only list rows from one table category.",
    )
    list_parser.add_argument(
        "--contains",
        help="Only list rows whose decoded text contains this substring.",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of rows to print.",
    )
    list_parser.add_argument(
        "--show-notes",
        action="store_true",
        help="Include notes in the printed output.",
    )

    patch_parser = subparsers.add_parser(
        "patch-known-text",
        help="Patch one mapped ROTDD text entry in a copied ROM.",
    )
    patch_parser.add_argument(
        "--table",
        required=True,
        choices=[table.slug for table in KNOWN_TEXT_TABLES],
        help="Known table slug to patch.",
    )
    selector_group = patch_parser.add_mutually_exclusive_group(required=True)
    selector_group.add_argument(
        "--index",
        type=int,
        help="Local table index to patch. Safest selector when duplicate names exist.",
    )
    selector_group.add_argument(
        "--match-text",
        help="Decoded text to patch within the selected table.",
    )
    patch_parser.add_argument(
        "--occurrence",
        type=int,
        help="Occurrence index when --match-text matches more than one row.",
    )
    patch_parser.add_argument(
        "replacement",
        help="Replacement text. It must fit the original byte budget; use <QUOTE> for a double quote.",
    )
    patch_parser.add_argument(
        "--output",
        type=Path,
        help="Patched ROM path. Defaults to a sibling file ending in .patched.gba.",
    )
    patch_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow the output file to be overwritten if it already exists.",
    )
    patch_parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write directly into the source ROM. Unsafe.",
    )

    surface_corpus_parser = subparsers.add_parser(
        "export-text-surface-corpus",
        help="Export the broad dialogue-like surface corpus to CSV.",
    )
    surface_corpus_parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/raw/text-surfaces.csv"),
        help="Output CSV path, relative to the repository root by default.",
    )
    surface_corpus_parser.add_argument(
        "--min-len",
        type=int,
        default=24,
        help="Minimum decoded text length before a row is kept in the corpus.",
    )

    surface_map_parser = subparsers.add_parser(
        "export-text-surface-map",
        help="Export a contiguous text surface to CSV.",
    )
    surface_map_parser.add_argument(
        "--start",
        type=parse_int,
        required=True,
        help="Start ROM offset for the excerpt.",
    )
    surface_map_parser.add_argument(
        "--end",
        type=parse_int,
        required=True,
        help="End ROM offset for the excerpt.",
    )
    surface_map_parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/raw/text-surfaces.csv"),
        help="Output CSV path, relative to the repository root by default.",
    )

    text_surface_parser = subparsers.add_parser(
        "text-surface",
        help="Text-surface template exports and bulk patching actions.",
    )
    text_surface_subparsers = text_surface_parser.add_subparsers(dest="action", required=True)

    text_surface_export_parser = text_surface_subparsers.add_parser(
        "export",
        help="Export text-surface templates from the current corpus CSV.",
    )
    text_surface_export_subparsers = text_surface_export_parser.add_subparsers(dest="target", required=True)
    text_surface_template_export_parser = text_surface_export_subparsers.add_parser(
        "template",
        help="Export one surface type as a two-column template CSV.",
    )
    text_surface_template_export_parser.add_argument(
        "--input",
        type=Path,
        default=Path("research/raw/text-surfaces.csv"),
        help="Source text-surfaces CSV path, relative to the repository root by default.",
    )
    text_surface_template_export_parser.add_argument(
        "--type",
        required=True,
        help="Surface type label to export.",
    )
    text_surface_template_export_parser.add_argument(
        "--output",
        type=Path,
        help="Output CSV path. Defaults to ignore/temp/text-surfaces.<type>.csv.",
    )

    text_surface_patch_parser = text_surface_subparsers.add_parser(
        "patch",
        help="Patch text-surface template rows back into a copied ROM.",
    )
    text_surface_patch_subparsers = text_surface_patch_parser.add_subparsers(dest="target", required=True)
    text_surface_patch_file_parser = text_surface_patch_subparsers.add_parser(
        "file",
        help="Patch a two-column text-surface template CSV.",
    )
    text_surface_patch_file_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Template CSV path with rom_offset and decoded_text columns.",
    )
    text_surface_patch_file_parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("research/raw/text-surfaces.csv"),
        help="Current text-surfaces CSV used to infer the source codec for each offset.",
    )
    text_surface_patch_file_parser.add_argument(
        "--refs",
        choices=["rewrite", "keep"],
        help="Rewrite the reference corpus CSV after patching, or keep it unchanged.",
    )
    text_surface_patch_file_parser.add_argument(
        "--clear-refs-preference",
        action="store_true",
        help="Delete the saved local ref-file preference before running.",
    )
    text_surface_patch_file_parser.add_argument(
        "--mode",
        choices=["strict", "liberal"],
        default="strict",
        help="Strict is the default conservative mode. Liberal may rewrite unsafe references in place.",
    )
    _add_write_args(text_surface_patch_file_parser)

    character_parser = subparsers.add_parser(
        "character",
        help="Character-focused actions using a name + action command shape.",
    )
    _add_entity_tree_parser(
        character_parser,
        display_name="character",
        export_output=Path("research/raw/character-names.csv"),
        list_help="List canonical character names and their pointer-table rows.",
        export_help="Export the canonical character-name pointer table to a CSV artifact.",
        patch_help="Character name actions.",
        patch_help_suffix="Rename one character everywhere we can confidently see the old name.",
        allow_stat=True,
    )

    class_parser = subparsers.add_parser(
        "class",
        help="Class-focused actions using a name + action command shape.",
    )
    _add_entity_tree_parser(
        class_parser,
        display_name="class",
        export_output=Path("research/raw/class-names.csv"),
        list_help="List confirmed class names from the current slice.",
        export_help="Export the confirmed class-name slice to a CSV artifact.",
        patch_help="Class name actions.",
        patch_help_suffix="Rename one class label everywhere we can confidently see the old name.",
        allow_stat=True,
    )

    enemy_parser = subparsers.add_parser(
        "enemy",
        help="Enemy-focused actions using a name + action command shape.",
    )
    _add_entity_tree_parser(
        enemy_parser,
        display_name="enemy",
        export_output=Path("research/raw/enemy-names.csv"),
        list_help="List confirmed enemy names from the current slice.",
        export_help="Export the confirmed enemy-name slice to a CSV artifact.",
        patch_help="Enemy name actions.",
        patch_help_suffix="Rename one enemy label everywhere we can confidently see the old name.",
        allow_stat=True,
    )

    item_parser = subparsers.add_parser(
        "item",
        help="Item-focused actions using a name + action command shape.",
    )
    _add_entity_tree_parser(
        item_parser,
        display_name="item",
        export_output=Path("research/raw/item-names.csv"),
        list_help="List confirmed item names from the current table.",
        export_help="Export the confirmed item-name table to a CSV artifact.",
        patch_help="Item name actions.",
        patch_help_suffix="Rename one item label everywhere we can confidently see the old name.",
        allow_stat=True,
    )

    npc_parser = subparsers.add_parser(
        "npc",
        help="NPC/dialogue-speaker actions using a name + action command shape.",
    )
    _add_entity_tree_parser(
        npc_parser,
        display_name="npc",
        export_output=Path("research/raw/npc-names.csv"),
        list_help="List dialogue-speaker prefixes extracted from the corpus.",
        export_help="Export dialogue speaker prefixes as a browseable NPC-style CSV.",
        patch_help="NPC name actions.",
        patch_help_suffix="Rename one NPC or speaker name across dialogue surfaces.",
        allow_stat=False,
    )

    patch_offset_parser = subparsers.add_parser(
        "patch-text-at-offset",
        help="Patch a same-length ROTDD text run at a literal ROM offset.",
    )
    patch_offset_parser.add_argument(
        "offset",
        type=parse_int,
        help="Literal ROM offset to patch.",
    )
    patch_offset_parser.add_argument(
        "replacement",
        help="Replacement text. Quote it when it contains spaces or punctuation; use <QUOTE> for a double quote.",
    )
    patch_offset_parser.add_argument(
        "--output",
        type=Path,
        help="Patched ROM path. Defaults to a sibling file ending in .patched.gba.",
    )
    patch_offset_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow the output file to be overwritten if it already exists.",
    )
    patch_offset_parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write directly into the source ROM. Unsafe.",
    )

    peek_parser = subparsers.add_parser("peek", help="Hex and ASCII preview of a ROM region.")
    peek_parser.add_argument("offset", type=parse_int, help="ROM offset to preview.")
    peek_parser.add_argument("--length", type=parse_int, default=0x80, help="Number of bytes to print.")

    return parser


def main() -> int:
    """Dispatch the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])

    progress_commands = {
        "export-text-surface-corpus",
        "patch-known-text",
        "patch-text-at-offset",
    }
    progress_bar = ProgressBar() if args.command in progress_commands or _entity_patch_is_progress_command(args) or (args.command == "text-surface" and getattr(args, "action", None) == "patch" and getattr(args, "target", None) == "file") else None
    progress_callback = progress_bar.update if progress_bar is not None else None
    post_messages: list[str] = []

    try:
        if args.command == "encode-rotdd":
            print_rotdd_encoding(args.term)
            return 0
        if args.command == "text-surface" and args.action == "export" and args.target == "template":
            output = args.output or Path(f"ignore/temp/text-surfaces.{args.type}.csv")
            run_export_text_surface_template(
                input_path=args.input,
                surface_type=args.type,
                output=output,
            )
            return 0

        rom_path = resolve_rom_path(args.rom)
        data = load_rom(rom_path)

        if args.command == "search-term":
            return 0 if search_term(data, args.term, args.encoding) else 1
        if args.command == "search-rotdd":
            return 0 if search_rotdd(data, args.term) else 1
        if args.command == "dump-strings":
            return 0 if dump_strings(data, args.start, args.end, args.min_len, args.contains) else 1
        if args.command == "dump-rotdd":
            return 0 if dump_rotdd(data, args.start, args.end, args.min_len, args.contains) else 1
        if args.command == "scan-rotdd-runs":
            return 0 if scan_rotdd_candidates(data, args.start, args.end, args.min_len) else 1
        if args.command == "find-pointer":
            return 0 if find_pointer(data, args.offset, args.base) else 1
        if args.command == "dump-pointer-table":
            dump_pointer_table(data, args.offset, args.count, args.base, args.codec)
            return 0
        if args.command == "export-text-surface-map":
            run_export_text_surface_map(
                data=data,
                start=args.start,
                end=args.end,
                output=args.output,
            )
            return 0
        if args.command == "export-text-surface-corpus":
            run_export_text_surface_corpus(data, args.min_len, args.output, progress_callback)
            return 0
        if args.command == "text-surface":
            if args.action == "patch" and args.target == "file":
                if args.clear_refs_preference:
                    clear_refs_mode_preference()
                refs_mode = choose_refs_mode(args.refs)
                post_messages.extend(run_patch_text_surface_template(
                    data=data,
                    rom_path=rom_path,
                    input_path=args.input,
                    corpus_path=args.corpus,
                    output=args.output,
                    overwrite=args.overwrite,
                    in_place=args.in_place,
                    mode=args.mode,
                    refs_mode=refs_mode,
                    progress_callback=progress_callback,
                ))
                post_messages.append(fresh_boot_notice())
                return 0
            parser.error(f"Unhandled text-surface action: {args.action}/{getattr(args, 'target', None)}")
        if args.command == "list-known-text":
            return 0 if run_list_known_text(data, args.table, args.category, args.contains, args.limit, args.show_notes) else 1
        if args.command == "patch-known-text":
            post_messages.extend(run_patch_known_text(
                data=data,
                rom_path=rom_path,
                table_slug=args.table,
                local_index=args.index,
                match_text=args.match_text,
                occurrence=args.occurrence,
                replacement_text=args.replacement,
                output=args.output,
                overwrite=args.overwrite,
                in_place=args.in_place,
                progress_callback=progress_callback,
            ))
            post_messages.append(fresh_boot_notice())
            return 0
        if args.command in {"character", "class", "enemy", "item", "npc"}:
            if args.action == "export" and args.target == "map":
                _run_entity_name_export(entity=args.command, data=data, args=args)
                return 0
            if args.action == "export" and args.target == "template":
                _run_entity_name_template_export(entity=args.command, data=data, args=args)
                return 0
            if args.action == "list" and args.target == "names":
                return _run_entity_name_list(entity=args.command, data=data, args=args)
            if args.action == "patch" and args.target == "name":
                post_messages.extend(_run_entity_name_patch(
                    entity=args.command,
                    data=data,
                    rom_path=rom_path,
                    args=args,
                    progress_callback=progress_callback,
                ))
                post_messages.append(fresh_boot_notice())
                return 0
            if args.action == "patch" and args.target == "file":
                post_messages.extend(_run_entity_name_patch_file(
                    entity=args.command,
                    data=data,
                    rom_path=rom_path,
                    args=args,
                    progress_callback=progress_callback,
                ))
                post_messages.append(fresh_boot_notice())
                return 0
            if args.action == "patch" and args.target == "stat":
                parser.error("Stat editing is not implemented yet.")
            parser.error(f"Unhandled {args.command} action: {args.action}/{getattr(args, 'target', None)}")
        if args.command == "patch-text-at-offset":
            post_messages.extend(run_patch_text_at_offset(
                data=data,
                rom_path=rom_path,
                rom_offset=args.offset,
                replacement_text=args.replacement,
                output=args.output,
                overwrite=args.overwrite,
                in_place=args.in_place,
                progress_callback=progress_callback,
            ))
            post_messages.append(fresh_boot_notice())
            return 0
        if args.command == "peek":
            peek(data, args.offset, args.length)
            return 0

        parser.error(f"Unhandled command: {args.command}")
        return 2
    finally:
        if progress_bar is not None:
            progress_bar.finish()
        _emit_messages(post_messages)


def run() -> int:
    """Run the CLI with user-facing error handling."""
    try:
        return main()
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
