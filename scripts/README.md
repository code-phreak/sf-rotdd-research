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
- `scan-rotdd-runs` finds contiguous runs that use only the confirmed ROTDD text alphabet.
- `find-pointer` searches for GBA little-endian ROM pointers to a target offset.
- `dump-pointer-table` decodes a pointer table into strings.
- `export-known-text-map` writes the current known ROTDD text tables to `research/raw/text-map.csv`.
- `export-text-surface-corpus` scans the whole ROM for dialogue-like ROTDD text runs and writes them to `research/raw/text-surfaces.csv`.
- `export-text-surface-map` writes a contiguous text surface to `research/raw/text-surfaces.csv`.
- `list-known-text` lists mapped rows from the known ROTDD text tables.
- `patch-known-text` patches one mapped text entry in a copied ROM while keeping the encoded text within the original byte budget.
- `patch-text-at-offset` patches one text run at a literal ROM offset while keeping the encoded text within the original byte budget.
- `peek` prints a quick hex and ASCII view of a ROM region.

Examples:

```bash
python scripts/rom_text_tools.py encode-rotdd Flare
python scripts/rom_text_tools.py --rom path/to/your-rom.gba search-term Goblin
python scripts/rom_text_tools.py --rom path/to/your-rom.gba search-term Heal --encoding ascii utf-16le
python scripts/rom_text_tools.py --rom path/to/your-rom.gba search-rotdd "Dark Dragon"
python scripts/rom_text_tools.py --rom path/to/your-rom.gba dump-strings --start 0x1E0700 --end 0x1E0A40
python scripts/rom_text_tools.py --rom path/to/your-rom.gba dump-rotdd --start 0x1DD5B0 --end 0x1DD650
python scripts/rom_text_tools.py --rom path/to/your-rom.gba scan-rotdd-runs --start 0x1DD7E3 --end 0x1DE100
python scripts/rom_text_tools.py --rom path/to/your-rom.gba find-pointer 0x1E0784
python scripts/rom_text_tools.py --rom path/to/your-rom.gba dump-pointer-table 0x56ED80 --count 16 --codec rotdd
python scripts/rom_text_tools.py --rom path/to/your-rom.gba export-known-text-map
python scripts/rom_text_tools.py --rom path/to/your-rom.gba export-text-surface-corpus --min-len 24
python scripts/rom_text_tools.py --rom path/to/your-rom.gba export-text-surface-map --start 0x1765E3 --end 0x177B80
python scripts/rom_text_tools.py --rom path/to/your-rom.gba list-known-text --table item_names --contains Ring
python scripts/rom_text_tools.py --rom path/to/your-rom.gba list-known-text --category item --show-notes
python scripts/rom_text_tools.py --rom path/to/your-rom.gba patch-known-text --table item_names --index 0 --output path/to/test-rom.gba "Magic   Herb"
python scripts/rom_text_tools.py --rom path/to/your-rom.gba patch-text-at-offset 0x001766AA "Max: Hyaaah!" --output path/to/test-rom.gba
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
- it writes to a copied ROM unless you add `--in-place`
- it keeps the existing `0x00` terminator in place by only replacing the encoded text bytes
- if `--output` is omitted, it writes a sibling ROM ending in `.patched.gba`
- duplicate decoded names require an explicit `--occurrence`
- shorter replacements are padded with ROTDD spaces on the right
- longer replacements still fail until we have repointing support

Prefer `--index` when possible. It is the safest selector when a table contains duplicate visible names.

`patch-text-at-offset` uses the same conservative byte-budget rule, but it works from a literal ROM offset instead of a mapped table row.
- pass the offset and replacement as separate positional arguments
- quote the replacement when it contains spaces or punctuation so the shell keeps it together as one argument
- the tool will auto-wrap text on whole-word boundaries to the observed 35-character dialogue width when you do not supply explicit `<NEWLINE>` tags
- if a short punctuated token would be orphaned at the end of a long line, the tool nudges it onto the next line instead of splitting it
- `<PAGE_BREAK>` resets the three-row budget for the next page
- it prints a warning when it inserts line breaks for you, because the result should be reviewed on screen
- it keeps wrapped lines tight and only pads the final encoded payload when needed to preserve the byte budget
- if the wrapped text would need more than three visible rows on one page, the command fails instead of trying to overflow into other memory

Both write commands accept `--in-place` if you intentionally want to overwrite the source ROM. That is unsafe and should only be used when you have a backup copy.

The current confirmed surface encoder supports uppercase letters, lowercase letters, spaces, known punctuation, and the inline tags used in the corpus export. Keep that limit in mind when choosing replacement text.

## Browsing mapped text

`list-known-text` is the easiest way to browse patch targets from the terminal before you edit anything.

- use `--table` to narrow to one known table such as `item_names`
- use `--category` to narrow to one confirmed table category such as `item`
- use `--contains` to find rows by visible text
- use `--show-notes` when you want duplicate or partial-table warnings inline

`scan-rotdd-runs` is useful when you want to discover additional text-like regions before you know how they terminate.

`export-text-surface-corpus` is the broad first pass for whole-ROM dialogue discovery.

- the output is written to `research/raw/text-surfaces.csv`
- the CSV includes the ROM offset for each row
- only the `decoded_text` column is quoted, so the file stays easy to read while still preserving commas and inline tags
- the CSV intentionally contains only human-readable text rows, not hex dumps
- the dialogue/script pass keeps only rows with real word separation; the plain-ASCII pass catches readable names and title blocks
- the extra ASCII pass is intentionally conservative and prefers word-like strings over raw printable noise
- the dialogue box currently behaves like a 35-character wide, 3-row surface for wrapping decisions
- unknown bytes remain visible as placeholder tokens like `<XX>` until we map them
- confirmed punctuation and control bytes are rendered in the decoded text so the CSV reads closer to the on-screen dialogue
- speaker names and dialogue handoffs are documented as explicit control or text tokens when they appear in the ROM surface
- `<NEWLINE>`, `<PAGE_BREAK>`, and `<SPEAKER_BREAK>` stay inline so each CSV row remains a single line on disk
- the file shape is intended to stay friendly for future CSV-driven patching

`export-text-surface-map` remains available for a contiguous excerpt when you already know a specific ROM range.

The actual patcher still needs to stay within the original byte budget for now, so any future CSV-driven replacement step must preserve or trim within that budget unless we add repointing support.

This is the recommended first step before `patch-known-text`.

## Technical direction

The tooling is being written as if it will eventually support a richer API and UI layer.

- generic code should stay reusable for other GBA ROM projects
- ROTDD-specific facts should stay isolated and easy to audit
- generated mapping artifacts should be stable enough for downstream tools to consume
