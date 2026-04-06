# Script Notes

`rom_text_tools.py` is the first reusable probe for ROM text work in this repository.

The script exists to replace throwaway terminal experiments with repeatable commands that other researchers can read, rerun, and extend.

The command-line wrapper now delegates to a package-backed implementation in `src/rotdd_tools/`.

- `src/rotdd_tools/gba.py` holds generic GBA helpers
- `src/rotdd_tools/rotdd.py` holds ROTDD-specific codec rules and known table coordinates
- `src/rotdd_tools/catalog.py` turns known tables into structured exported data
- `scripts/rom_text_tools.py` stays as the stable entry point

## ROM path setup

The script no longer assumes a specific local ROM location.

Use one of these approaches:

- pass `--rom` on the command line
- create `scripts/rom_path.local.txt` with a relative path from the repository root

The local path file is intentionally gitignored.

If the file does not exist, is empty, is unreadable, or points to a ROM path that does not exist, the script will prompt for a path and ask whether it should save the updated value for future runs.

## Commands

- `search-term` searches the ROM for a term in one or more encodings.
- `encode-rotdd` prints the current custom-encoded bytes for a text string.
- `search-rotdd` searches using the currently known ROTDD custom text codec.
- `dump-strings` extracts printable ASCII strings and their ROM offsets.
- `dump-rotdd` decodes null-terminated strings with the current ROTDD custom codec.
- `find-pointer` searches for GBA little-endian ROM pointers to a target offset.
- `dump-pointer-table` decodes a pointer table into strings.
- `export-known-text-map` writes the current known ROTDD text tables to `research/raw/text-map.csv`.
- `list-known-text` lists mapped rows from the known ROTDD text tables.
- `patch-known-text` patches one mapped text entry in a copied ROM with a same-length replacement.
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
python scripts/rom_text_tools.py --rom path/to/your-rom.gba export-known-text-map
python scripts/rom_text_tools.py --rom path/to/your-rom.gba list-known-text --table item_names --contains Ring
python scripts/rom_text_tools.py --rom path/to/your-rom.gba patch-known-text --table item_names --index 0 --output path/to/test-rom.gba "Magic   Herb"
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

## Safe patching

`patch-known-text` is intentionally conservative.

- it only works on mapped rows from the known ROTDD tables
- it only accepts replacements that encode to exactly the same byte length as the original
- it writes to a copied ROM, never the source ROM
- it leaves the existing `0x00` terminator in place by only replacing the encoded text bytes
- if `--output` is omitted, it writes a sibling ROM ending in `.patched.gba`
- duplicate decoded names require an explicit `--occurrence`

Prefer `--index` when possible. It is the safest selector when a table contains duplicate visible names.

The current confirmed codec only supports uppercase letters, lowercase letters, and spaces. Keep that limit in mind when choosing replacement text.

## Browsing mapped text

`list-known-text` is the easiest way to browse patch targets from the terminal before you edit anything.

- use `--table` to narrow to one known table such as `item_names`
- use `--contains` to find rows by visible text
- use `--show-notes` when you want duplicate or partial-table warnings inline

This is the recommended first step before `patch-known-text`.

## Technical direction

The tooling is being written as if it will eventually support a richer API and UI layer.

- generic code should stay reusable for other GBA ROM projects
- ROTDD-specific facts should stay isolated and easy to audit
- generated mapping artifacts should be stable enough for downstream tools to consume
