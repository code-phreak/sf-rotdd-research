#!/usr/bin/env python3
"""
ROM text utilities for Shining Force: Resurrection of the Dark Dragon.

This script is meant to support repeatable text research, not one-off shell work.
It currently covers three practical needs:

1. Find raw strings in common encodings.
2. Decode the currently known ROTDD text codec.
3. Inspect pointer tables that resolve ROM text entries.

Examples:
  python scripts/rom_text_tools.py encode-rotdd Flare
  python scripts/rom_text_tools.py search-term Goblin
  python scripts/rom_text_tools.py search-term Heal --encoding ascii utf-16le
  python scripts/rom_text_tools.py search-rotdd "Dark Dragon"
  python scripts/rom_text_tools.py dump-strings --start 0x1E0700 --end 0x1E0A40
  python scripts/rom_text_tools.py dump-rotdd --start 0x1DD7E0 --end 0x1DDA40
  python scripts/rom_text_tools.py find-pointer 0x1DD946
  python scripts/rom_text_tools.py dump-pointer-table 0x56ED80 --count 16 --codec rotdd
  python scripts/rom_text_tools.py peek 0x1DD946 --length 0x40
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable


GBA_ROM_BASE = 0x08000000

ROTDD_TERMINATOR = 0x00
ROTDD_SPACE = 0x10
ROTDD_UPPERCASE_SHIFT = 0x16
ROTDD_LOWERCASE_SHIFT = 0x19
ROTDD_UPPERCASE_MIN = 0x2B
ROTDD_UPPERCASE_MAX = 0x44
ROTDD_LOWERCASE_MIN = 0x48
ROTDD_LOWERCASE_MAX = 0x63

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
LOCAL_ROM_REF = SCRIPT_DIR / "rom_path.local.txt"


def parse_int(value: str) -> int:
    """Accept plain decimal or Python-style base-prefixed integers."""
    return int(value, 0)


def load_rom(path: Path) -> bytes:
    """Load the requested ROM into memory."""
    if not path.exists():
        raise FileNotFoundError(f"ROM not found: {path}")
    return path.read_bytes()


def normalize_user_path(user_value: str) -> Path:
    """Resolve user input relative to the repository root when appropriate."""
    candidate = Path(user_value.strip())
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve()


def save_local_rom_reference(path: Path) -> None:
    """Persist a ROM path for future runs in a gitignored local file."""
    try:
        relative = path.resolve().relative_to(REPO_ROOT.resolve())
        text = relative.as_posix()
    except ValueError:
        text = str(path.resolve())
    LOCAL_ROM_REF.write_text(text + "\n", encoding="utf-8")


def load_local_rom_reference() -> Path | None:
    """Load the saved ROM path if the user has configured one locally."""
    if not LOCAL_ROM_REF.exists():
        return None
    saved = LOCAL_ROM_REF.read_text(encoding="utf-8").strip()
    if not saved:
        return None
    return normalize_user_path(saved)


def prompt_for_rom_path() -> Path:
    """Prompt the user for a ROM path and optionally save it for later runs."""
    print("No ROM path is configured.")
    print("Enter the relative path to your ROM from the repository root.")
    user_value = input("ROM path: ").strip()
    if not user_value:
        raise FileNotFoundError("No ROM path was provided.")

    path = normalize_user_path(user_value)
    if not path.exists():
        raise FileNotFoundError(f"ROM not found: {path}")

    save_choice = input("Save this path in scripts/rom_path.local.txt for future runs? [y/N]: ").strip().lower()
    if save_choice in {"y", "yes"}:
        save_local_rom_reference(path)
        print("Saved local ROM path.")
    return path


def resolve_rom_path(cli_path: Path | None) -> Path:
    """Choose the ROM path from the CLI, local config, or an interactive prompt."""
    if cli_path is not None:
        path = normalize_user_path(str(cli_path))
        if not path.exists():
            raise FileNotFoundError(f"ROM not found: {path}")
        return path

    try:
        saved_path = load_local_rom_reference()
    except OSError as error:
        print(f"Could not read scripts/rom_path.local.txt: {error}", file=sys.stderr)
        saved_path = None

    if saved_path is not None and saved_path.exists():
        return saved_path
    if saved_path is not None and not saved_path.exists():
        print(f"Configured ROM path is missing: {saved_path}", file=sys.stderr)

    if not sys.stdin.isatty():
        raise FileNotFoundError(
            "No ROM path is configured. Pass --rom or create scripts/rom_path.local.txt with a relative path."
        )
    return prompt_for_rom_path()


def printable_ascii(byte_value: int) -> bool:
    """Return True when a byte falls in the printable ASCII range."""
    return 32 <= byte_value < 127


def format_ascii(chunk: bytes) -> str:
    """Format a byte slice as ASCII with dots for non-printable bytes."""
    return "".join(chr(byte) if printable_ascii(byte) else "." for byte in chunk)


def iter_find_all(data: bytes, needle: bytes) -> Iterable[int]:
    """Yield every match offset for a byte sequence."""
    start = 0
    while True:
        index = data.find(needle, start)
        if index == -1:
            return
        yield index
        start = index + 1


def encode_rotdd_char(char: str) -> int:
    """Encode one character with the currently known ROTDD table."""
    if char == " ":
        return ROTDD_SPACE
    if "A" <= char <= "Z":
        return ord(char) - ROTDD_UPPERCASE_SHIFT
    if "a" <= char <= "z":
        return ord(char) - ROTDD_LOWERCASE_SHIFT
    raise ValueError(f"Unsupported character for current ROTDD codec: {char!r}")


def encode_rotdd_text(text: str) -> bytes:
    """Encode a text string without appending a terminator byte."""
    return bytes(encode_rotdd_char(char) for char in text)


def decode_rotdd_byte(byte: int) -> str:
    """Decode one byte from the known ROTDD table."""
    if byte == ROTDD_SPACE:
        return " "
    if ROTDD_UPPERCASE_MIN <= byte <= ROTDD_UPPERCASE_MAX:
        return chr(byte + ROTDD_UPPERCASE_SHIFT)
    if ROTDD_LOWERCASE_MIN <= byte <= ROTDD_LOWERCASE_MAX:
        return chr(byte + ROTDD_LOWERCASE_SHIFT)
    return f"<{byte:02X}>"


def decode_rotdd_bytes(chunk: bytes) -> str:
    """Decode bytes until a terminator or the end of the provided slice."""
    decoded: list[str] = []
    for byte in chunk:
        if byte == ROTDD_TERMINATOR:
            break
        decoded.append(decode_rotdd_byte(byte))
    return "".join(decoded)


def read_terminated_string(data: bytes, start: int) -> bytes:
    """Read a null-terminated byte string from a ROM offset."""
    end = data.find(bytes([ROTDD_TERMINATOR]), start)
    if end == -1:
        end = len(data)
    return data[start:end]


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
    encoded = encode_rotdd_text(text)
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
        terminator = data.find(bytes([ROTDD_TERMINATOR]), index, limit)
        if terminator == -1:
            break
        if terminator > index:
            text = decode_rotdd_bytes(data[index:terminator])
            # Spaces are part of the format, but they should not make a short control-like
            # entry look like a real string.
            printable_len = len(text.replace(" ", ""))
            if printable_len >= min_len and (contains is None or contains in text):
                print(f"{index:#010x} {text}")
                count += 1
        index = terminator + 1
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

    peek_parser = subparsers.add_parser("peek", help="Hex and ASCII preview of a ROM region.")
    peek_parser.add_argument("offset", type=parse_int, help="ROM offset to preview.")
    peek_parser.add_argument("--length", type=parse_int, default=0x80, help="Number of bytes to print.")

    return parser


def main() -> int:
    """Dispatch the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args()
    rom_path = resolve_rom_path(args.rom)
    data = load_rom(rom_path)

    if args.command == "encode-rotdd":
        print_rotdd_encoding(args.term)
        return 0
    if args.command == "search-term":
        return 0 if search_term(data, args.term, args.encoding) else 1
    if args.command == "search-rotdd":
        return 0 if search_rotdd(data, args.term) else 1
    if args.command == "dump-strings":
        return 0 if dump_strings(data, args.start, args.end, args.min_len, args.contains) else 1
    if args.command == "dump-rotdd":
        return 0 if dump_rotdd(data, args.start, args.end, args.min_len, args.contains) else 1
    if args.command == "find-pointer":
        return 0 if find_pointer(data, args.offset, args.base) else 1
    if args.command == "dump-pointer-table":
        dump_pointer_table(data, args.offset, args.count, args.base, args.codec)
        return 0
    if args.command == "peek":
        peek(data, args.offset, args.length)
        return 0

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
