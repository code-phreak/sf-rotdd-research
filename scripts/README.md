# Script Notes

`rom_text_tools.py` is the first reusable probe for ROM text work in this repository.

The script exists to replace throwaway terminal experiments with repeatable commands that other researchers can read, rerun, and extend.

## ROM path setup

The script no longer assumes a specific local ROM location.

Use one of these approaches:

- pass `--rom` on the command line
- edit `scripts/rom_path.local.txt` with a relative path from the repository root

The repository currently includes `scripts/rom_path.local.txt` with a generic placeholder value.

If that file is empty, unreadable, or points to a ROM path that does not exist, the script will prompt for a path and ask whether it should save the updated value for future runs.

## Commands

- `search-term` searches the ROM for a term in one or more encodings.
- `encode-rotdd` prints the current custom-encoded bytes for a text string.
- `search-rotdd` searches using the currently known ROTDD custom text codec.
- `dump-strings` extracts printable ASCII strings and their ROM offsets.
- `dump-rotdd` decodes null-terminated strings with the current ROTDD custom codec.
- `find-pointer` searches for GBA little-endian ROM pointers to a target offset.
- `dump-pointer-table` decodes a pointer table into strings.
- `peek` prints a quick hex and ASCII view of a ROM region.

Examples:

```bash
python scripts/rom_text_tools.py encode-rotdd Flare
python scripts/rom_text_tools.py --rom path/to/your-rom.gba search-term Goblin
python scripts/rom_text_tools.py --rom path/to/your-rom.gba search-term Heal --encoding ascii utf-16le
python scripts/rom_text_tools.py --rom path/to/your-rom.gba search-rotdd "Dark Dragon"
python scripts/rom_text_tools.py --rom path/to/your-rom.gba dump-strings --start 0x1E0700 --end 0x1E0A40
python scripts/rom_text_tools.py --rom path/to/your-rom.gba dump-rotdd --start 0x1DD5B0 --end 0x1DD650
python scripts/rom_text_tools.py --rom path/to/your-rom.gba find-pointer 0x1E0784
python scripts/rom_text_tools.py --rom path/to/your-rom.gba dump-pointer-table 0x56ED80 --count 16 --codec rotdd
python scripts/rom_text_tools.py --rom path/to/your-rom.gba peek 0x1DD5B0 --length 0x80
```

## Current confirmed text observations

- `0x00` terminates a string
- `0x10` decodes as a space
- uppercase letters currently decode as byte `+ 0x16`
- lowercase letters currently decode as byte `+ 0x19`

That mapping is strong enough to decode the spell and item bank around `0x1DD7E3` and the related pointer table around `0x56ED80`.

## Maintenance standard

Keep new utilities easy to read.

- prefer small focused commands over one script that tries to do everything
- document command purpose and examples in this file
- preserve explicit offsets in output so results can be verified in external tools
