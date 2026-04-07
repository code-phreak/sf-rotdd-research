"""Command-line interface for the current ROTDD research utilities."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .catalog import (
    export_known_text_map,
    export_text_surface_corpus,
    export_text_surface_map,
    write_text_map_csv,
    write_text_surface_csv,
)
from .editing import patch_known_text, patch_text_at_offset
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


def run_export_known_text_map(data: bytes, output: Path) -> None:
    """Export the current known text tables to a structured CSV artifact."""
    rows = export_known_text_map(data)
    output_path = output if output.is_absolute() else (REPO_ROOT / output)
    write_text_map_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


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
) -> None:
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
    )

    print(f"Patched table: {row.table_slug}")
    print(f"Local index: {row.local_index}")
    print(f"Original text: {row.decoded_text}")
    print(f"Replacement: {replacement_text}")
    print(f"ROM offset: 0x{row.text_rom_offset:08X}")
    print(f"Pointer-table offset: 0x{row.pointer_table_offset:08X}")
    print(f"Encoded bytes: {' '.join(f'{byte:02X}' for byte in replacement_bytes)}")
    if in_place:
        print(f"Patched source ROM in place: {final_output_path}")
    else:
        print(f"Wrote patched ROM: {final_output_path}")


def run_patch_text_at_offset(
    data: bytes,
    rom_path: Path,
    rom_offset: int,
    replacement_text: str,
    output: Path | None,
    overwrite: bool,
    in_place: bool,
) -> None:
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
    )

    print(f"ROM offset: 0x{rom_offset:08X}")
    print(f"Original text: {original_text}")
    print(f"Replacement: {replacement_text}")
    print(f"Encoded bytes: {' '.join(f'{byte:02X}' for byte in replacement_bytes)}")
    if in_place:
        print(f"Patched source ROM in place: {final_output_path}")
    else:
        print(f"Wrote patched ROM: {final_output_path}")


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

    export_parser = subparsers.add_parser(
        "export-known-text-map",
        help="Export the currently known ROTDD text tables to a CSV artifact.",
    )
    export_parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/raw/text-map.csv"),
        help="Output CSV path, relative to the repository root by default.",
    )

    surface_export_parser = subparsers.add_parser(
        "export-text-surface-map",
        help="Export a contiguous text surface to a CSV artifact.",
    )
    surface_export_parser.add_argument("--start", type=parse_int, required=True, help="Start ROM offset.")
    surface_export_parser.add_argument("--end", type=parse_int, required=True, help="End ROM offset.")
    surface_export_parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/raw/text-surfaces.csv"),
        help="Output CSV path, relative to the repository root by default.",
    )

    surface_corpus_parser = subparsers.add_parser(
        "export-text-surface-corpus",
        help="Export a whole-ROM corpus of dialogue-like ROTDD text runs.",
    )
    surface_corpus_parser.add_argument(
        "--min-len",
        type=int,
        default=24,
        help="Minimum run length in bytes before a candidate is kept.",
    )
    surface_corpus_parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/raw/text-surfaces.csv"),
        help="Output CSV path, relative to the repository root by default.",
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
        help="Replacement text. It must encode to exactly the same byte length as the original.",
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
        help="Replacement text. Quote it when it contains spaces or punctuation.",
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
    args = parser.parse_args()

    if args.command == "encode-rotdd":
        print_rotdd_encoding(args.term)
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
    if args.command == "export-known-text-map":
        run_export_known_text_map(data, args.output)
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
        rows = export_text_surface_corpus(data=data, min_len=args.min_len)
        output_path = args.output if args.output.is_absolute() else (REPO_ROOT / args.output)
        write_text_surface_csv(rows, output_path)
        print(f"Wrote {len(rows)} rows to {output_path}")
        return 0
    if args.command == "list-known-text":
        return 0 if run_list_known_text(data, args.table, args.category, args.contains, args.limit, args.show_notes) else 1
    if args.command == "patch-known-text":
        run_patch_known_text(
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
        )
        return 0
    if args.command == "patch-text-at-offset":
        run_patch_text_at_offset(
            data=data,
            rom_path=rom_path,
            rom_offset=args.offset,
            replacement_text=args.replacement,
            output=args.output,
            overwrite=args.overwrite,
            in_place=args.in_place,
        )
        return 0
    if args.command == "peek":
        peek(data, args.offset, args.length)
        return 0

    parser.error(f"Unhandled command: {args.command}")
    return 2


def run() -> int:
    """Run the CLI with user-facing error handling."""
    try:
        return main()
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
