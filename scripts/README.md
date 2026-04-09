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

### General ROM And Text Utilities

- `search-term` searches the ROM for a term in one or more encodings.
- `search-rotdd` searches using the currently known ROTDD custom text codec.
- `encode-rotdd` prints the current custom-encoded bytes for a text string.
- `dump-strings` extracts printable ASCII strings and their ROM offsets.
- `dump-rotdd` decodes null-terminated strings with the current ROTDD custom codec.
- `scan-rotdd-runs` finds contiguous runs that use only the confirmed ROTDD text alphabet.
- `find-pointer` searches for GBA little-endian ROM pointers to a target offset.
- `dump-pointer-table` decodes a pointer table into strings.
- `peek` prints a quick hex and ASCII view of a ROM region.
- `patch-text-at-offset` patches one text run at a literal ROM offset, keeping the encoded text within the original byte budget when possible and repointing to EOF when a safe pointer target exists.
- `list-known-text` lists mapped rows from the known ROTDD text tables.
- `patch-known-text` patches one mapped text entry in a copied ROM, keeping the encoded text within the original byte budget when possible and repointing to EOF when a safe pointer target exists.

All entity rename commands default to the conservative path. Longer replacements still use EOF repointing when a safer write needs more room. `liberal` is intentionally unsafe and may fall back to direct in-place writes when a reference would otherwise be skipped. The current broad pointer-rewrite path is still unstable and should not be treated as a finished guarantee for full-story rewrites.

### Character Name API

- `character export map` writes the canonical character-name pointer table to `research/raw/character-names.csv`.
- `character list names` lists the canonical character names from the pointer table.
- `character patch name <current> <replacement>` performs a case-sensitive global rename across the canonical name table, known mapped text rows, matching text-surface rows, and other whole-name ROTDD surface runs such as short menu labels.
- Playable character names are conservatively capped at 8 ASCII characters, which is enough for the repointed-safe path we have evidence for right now.
- When a replacement needs more room, the tool appends the new payload to the end of the copied ROM and rewrites the relevant pointer(s). That can grow the ROM image, so hardware or flashcart validation should confirm the target accepts the larger file.
- When a reference is skipped, the CLI prints every skipped row with a short one-line reason such as `too long for slot`, `no pointer table`, or `name collision`.

Skipped-row reasons:

- `no pointer table` means the tool found visible text but could not prove a safe repoint target.
- `too long for slot` means the text still did not fit after wrapping, trimming, and other conservative fitting steps.
- `name collision` means the replacement already exists somewhere else in the live entity tables.
- `unsupported codec` means the tool found a row it can see, but not one it can safely rewrite yet.
- `ASCII only` means the replacement needs characters the current surface codec does not know how to encode.
- `empty replacement` means the requested replacement was blank.
- `unsafe skip` means the row failed for a reason that does not fit the shorter buckets above.

### Class Name API

- `class export map` writes the confirmed class-name slice to `research/raw/class-names.csv`.
- `class list names` lists the confirmed class names from the current slice.
- `class patch name <current> <replacement>` performs the matching case-sensitive global rename across the confirmed class-name slice, known mapped text rows, matching text-surface rows, and other whole-name ROTDD surface runs.

### Enemy Name API

- `enemy export map` writes the confirmed enemy-name slice to `research/raw/enemy-names.csv`.
- `enemy list names` lists the confirmed enemy names from the current table.
- `enemy patch name <current> <replacement>` performs the matching case-sensitive global rename across the confirmed enemy-name slice, known mapped text rows, matching text-surface rows, and other whole-name ROTDD surface runs.
- Enemy rename is in active testing, especially around bulk template patching and the broad EOF repoint path.

### Item Name API

- `item export map` writes the confirmed item-name table to `research/raw/item-names.csv`.
- `item list names` lists the confirmed item names from the current table.
- `item patch name <current> <replacement>` performs the matching case-sensitive global rename across the confirmed item-name table, known mapped text rows, matching text-surface rows, and other whole-name ROTDD surface runs.
- Named-table selectors use normalized visible names, so trailing padding spaces in the exported rows do not block a rename target from being found.

### NPC Name API

- `npc export map` writes dialogue-speaker prefixes to `research/raw/npc-names.csv`.
- The NPC CSV keeps the speaker name in the rightmost column and does not store `row_index`.
- `npc list names` lists dialogue-speaker prefixes extracted from the corpus.
- `npc patch name <current> <replacement>` performs the matching case-sensitive global rename across dialogue-speaker prefixes and matching text-surface rows.
- NPC names are limited by dialogue line wrapping rather than the 8-character cap used for playable characters and the 12-character cap used for classes, enemies, and items.
- NPC extraction always excludes the canonical playable roster from the checked-in character-name export, so renamed playable characters stay out of the NPC list.
- The dialogue normalizer auto-wraps whole words and auto-inserts page breaks so pages cycle cleanly every three visible rows when the text needs more room.

### Text Corpus Discovery

- `export-text-surface-corpus` scans the whole ROM for dialogue-like ROTDD text runs and writes them to `research/raw/text-surfaces.csv` with `source_kind,rom_offset,type,decoded_text`.
- `export-text-surface-map` writes a contiguous text surface to `research/raw/text-surfaces.csv` with the same layout.
- `type` values are driven by the current corpus review notes. Rows not called out there default to `unsorted`.
- `decoded_text` is always quoted in these exports so commas and inline tags stay easy to read, and generated templates quote `decoded_text` too.
- `text-surface export template` filters `research/raw/text-surfaces.csv` down to a single type label and writes a two-column editable template to `ignore/temp/`.
- `text-surface patch file` compares a two-column template against the current corpus, patches only the modified rows, and repoints changed text to EOF when a safe pointer target exists.
- `unsorted` rows have been reliable so far when the replacement stays the same length or shorter, but multi-line template rewriting is still experimental and should be treated as a work-in-progress.
- the patch command uses `research/raw/text-surfaces.csv` as its default codec/source reference so the template file can stay compact
- editable CSV text may use `…` as a shorthand for `...`; the tool normalizes it to the period bytes used by the ROM
- `--refs rewrite` regenerates the corpus CSV after patching; `--refs keep` leaves it unchanged
- if `--refs` is omitted, the CLI explains the choice once, prompts for a preference, and can remember it in `scripts/text_surface_refs.local.txt`
- `--clear-refs-preference` removes the saved local preference
- the broad EOF repoint path is still unstable and should be treated as a work-in-progress mechanism until the pointer rewrite rules are fully verified

### Reserved Future Actions

- `character patch stat <stat> <target> <value>` is reserved for future character stat editing.
- `class patch stat <stat> <target> <value>` is reserved for future class stat editing.
- `enemy patch stat <stat> <target> <value>` is reserved for future enemy stat editing.
- `item patch stat <stat> <target> <value>` is reserved for future item stat editing.
- These commands currently parse and then report that stat editing is not implemented yet.

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
python scripts/rom_text_tools.py --rom path/to/your-rom.gba character export map
python scripts/rom_text_tools.py --rom path/to/your-rom.gba class export map
python scripts/rom_text_tools.py --rom path/to/your-rom.gba enemy export map
python scripts/rom_text_tools.py --rom path/to/your-rom.gba item export map
python scripts/rom_text_tools.py --rom path/to/your-rom.gba npc export map
python scripts/rom_text_tools.py --rom path/to/your-rom.gba export-text-surface-corpus --min-len 24
python scripts/rom_text_tools.py --rom path/to/your-rom.gba export-text-surface-map --start 0x1765E3 --end 0x177B80
python scripts/rom_text_tools.py --rom path/to/your-rom.gba character list names --contains Mae
python scripts/rom_text_tools.py --rom path/to/your-rom.gba class list names --contains Knight
python scripts/rom_text_tools.py --rom path/to/your-rom.gba enemy list names --contains Goblin
python scripts/rom_text_tools.py --rom path/to/your-rom.gba item list names --contains Ring
python scripts/rom_text_tools.py --rom path/to/your-rom.gba npc list names --contains Priest
python scripts/rom_text_tools.py --rom path/to/your-rom.gba list-known-text --table item_names --contains Ring
python scripts/rom_text_tools.py --rom path/to/your-rom.gba list-known-text --category item --show-notes
python scripts/rom_text_tools.py --rom path/to/your-rom.gba patch-known-text --table item_names --index 0 --output path/to/test-rom.gba "Medical Herb"
python scripts/rom_text_tools.py --rom path/to/your-rom.gba character patch name Mae Jade --output path/to/test-rom.gba
python scripts/rom_text_tools.py --rom path/to/your-rom.gba class patch name Knight Baron --output path/to/test-rom.gba
python scripts/rom_text_tools.py --rom path/to/your-rom.gba enemy patch name Goblin Ogre --output path/to/test-rom.gba
python scripts/rom_text_tools.py --rom path/to/your-rom.gba item patch name Healing Seed Remedy --output path/to/test-rom.gba
python scripts/rom_text_tools.py --rom path/to/your-rom.gba npc patch name Priest Oracle --output path/to/test-rom.gba
python scripts/rom_text_tools.py text-surface export template --type unsorted
python scripts/rom_text_tools.py --rom path/to/your-rom.gba text-surface patch file --input ignore/temp/text-surfaces.unsorted.csv --corpus research/raw/text-surfaces.csv --output path/to/test-rom.gba
python scripts/rom_text_tools.py --rom path/to/your-rom.gba text-surface patch file --input ignore/temp/text-surfaces.unsorted.csv --corpus research/raw/text-surfaces.csv --refs rewrite --output path/to/test-rom.gba
python scripts/rom_text_tools.py --rom path/to/your-rom.gba patch-text-at-offset 0x001766AA "Max: Hyaaah!" --output path/to/test-rom.gba
python scripts/rom_text_tools.py --rom path/to/your-rom.gba peek 0x1DD5B0 --length 0x80
```

## Current confirmed text observations

- `0x00` terminates a string
- `0x10` decodes as a space
- uppercase letters currently decode as byte `+ 0x16`
- lowercase letters currently decode as byte `+ 0x19`
- visible digits `0` through `9` are decoded from the surface codec instead of left as placeholders
- `0x22` is decoded as a hyphen, which keeps compound words intact during export and patching

Character-name work currently starts from the plain ASCII pointer table at `0x0056F578` and the ASCII name bank at `0x001E0688`.
The global rename command also scans the known ROTDD text tables, the broader text-surface corpus, and targeted exact-name ASCII hits for short roster/menu labels so visible references stay in sync.

That mapping is strong enough to decode the spell and item bank around `0x1DD7E3` and the related pointer table around `0x56ED80`.

## Maintenance standard

Keep new utilities easy to read.

- prefer small focused commands over one script that tries to do everything
- document command purpose and examples in this file
- preserve explicit offsets in output so results can be verified in external tools
- long-running exports and rename scans print a terminal progress bar when stderr is interactive

## Safe patching

`patch-known-text` is intentionally conservative.

- it only works on mapped rows from the known ROTDD tables
- it writes to a copied ROM unless you add `--in-place`
- it keeps the existing `0x00` terminator in place by only replacing the encoded text bytes
- if `--output` is omitted, it writes a sibling ROM ending in `.patched.gba`
- duplicate decoded names require an explicit `--occurrence`
- shorter replacements are padded with ROTDD spaces on the right
- longer replacements repoint to appended space at the end of the copied ROM when the target table needs extra room
- if the replacement adds more bytes, the image can grow; check hardware or flashcart compatibility separately if that matters for your workflow
- if a mapped row still does not fit after conservative fitting, the safe path appends the replacement to EOF and repoints the table when pointers exist

Prefer `--index` when possible. It is the safest selector when a table contains duplicate visible names.

`patch-text-at-offset` uses the same conservative byte-budget rule, but it works from a literal ROM offset instead of a mapped table row.
- pass the offset and replacement as separate positional arguments
- quote the replacement when it contains spaces or punctuation so the shell keeps it together as one argument
- use `<QUOTE>` inside the replacement when you need a double quote
- the tool will auto-wrap text on whole-word boundaries to the observed 33-character dialogue width when you do not supply explicit `<NEWLINE>` tags
- if a short punctuated token would be orphaned at the end of a long line, the tool nudges it onto the next line instead of splitting it
- `<PAGE_BREAK>` resets the three-row budget for the next page
- the normalizer can also insert `<PAGE_BREAK>` automatically when a dialogue block needs to continue past three visible rows
- it prints a warning when it inserts line breaks for you, because the result should be reviewed on screen
- it keeps wrapped lines tight and only pads the final encoded payload when needed to preserve the byte budget
- if the wrapped text would need more than three visible rows on one page, the command fails instead of trying to overflow into other memory

Both write commands accept `--in-place` if you intentionally want to overwrite the source ROM. That is unsafe and should only be used when you have a backup copy.
Use `<QUOTE>` inside replacement text when you need a double quote.

`character patch name <current> <replacement>` is different from the dialogue patchers:

- it reads from the canonical name-pointer table instead of a dialogue row
- it keeps short or equal-length replacements in place
- if the replacement is longer, it appends the new payload to the end of the copied ROM and repoints the table entry there
- it also rewrites matching dialogue, menu labels, and other whole-name references that contain the old name
- if a matched reference still does not fit, the tool reports it and leaves it for later repointing instead of forcing a bad write
- duplicate live names are rejected so renames do not create collisions
- playable character names are currently limited to 8 ASCII characters for the character workflow; class, enemy, and item workflows still use a 12-character cap for now, and NPC names are limited by the dialogue box line length instead
- whole-name matching prevents substring rewrites and also handles simple singular/plural dialogue forms, so `Max` does not become `Jeffimum` and `Goblin` can become `Big Loser` in both singular and plural mentions
- repointed rows are appended to the copied ROM, and the corresponding pointers are rewritten to the new payload
- it still supports `--output` for a copied ROM and `--in-place` for an unsafe direct write

`class patch name <current> <replacement>` follows the same shape and the same safety rules, but it starts from the confirmed class-name slice instead of the playable-character pointer table.

`enemy patch name <current> <replacement>` follows the same shape and the same safety rules, but it starts from the confirmed enemy-name slice instead of the playable-character pointer table.

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
- `decoded_text` is always quoted, so the file stays easy to read while still preserving commas and inline tags
- the CSV intentionally contains only human-readable text rows, not hex dumps
- the dialogue/script pass keeps only rows with real word separation; the plain-ASCII pass catches readable names and title blocks
- the extra ASCII pass is intentionally conservative and prefers word-like strings over raw printable noise
- rows that are not explicitly called out in the current corpus review default to `unsorted`
- the dialogue box currently behaves like a 32-character wide, 3-row surface for wrapping decisions
- unknown bytes remain visible as placeholder tokens like `<XX>` until we map them
- confirmed punctuation and control bytes are rendered in the decoded text so the CSV reads closer to the on-screen dialogue
- speaker names and dialogue handoffs are documented as explicit control or text tokens when they appear in the ROM surface
- `<NEWLINE>`, `<PAGE_BREAK>`, and `<SPEAKER_BREAK>` stay inline so each CSV row remains a single line on disk
- the file shape is intended to stay friendly for future CSV-driven patching

`export-text-surface-map` remains available for a contiguous excerpt when you already know a specific ROM range.

`text-surface export template` and `text-surface patch file` are the CSV-driven workflow for larger edits.

- the export command takes a type label and writes `rom_offset,decoded_text` rows to `ignore/temp/`
- the patch command reads a template CSV, compares each row to the current corpus, and only rewrites rows whose text changed
- ROTDD rows auto-wrap and auto-insert `<PAGE_BREAK>` tags when needed
- changed rows repoint to EOF when a safe pointer target exists
- `--refs rewrite` tells the command to regenerate the corpus CSV after patching; `--refs keep` leaves the corpus CSV alone
- if neither ref mode is provided, the command explains the choice, prompts once, and can remember the answer locally
- `--mode liberal` is the unsafe fallback when you intentionally want best-effort in-place writes
- the current bulk EOF repoint path is still unstable until we finish verifying which pointer references are safe to rewrite

The actual patcher still needs to stay within the original byte budget when no safe pointer target exists, but the new CSV-driven template workflow already repoints changed rows to EOF when that is possible and falls back to the conservative path otherwise.

This is the recommended first step before `patch-known-text`.

## Technical direction

The tooling is being written as if it will eventually support a richer API and UI layer.

- generic code should stay reusable for other GBA ROM projects
- ROTDD-specific facts should stay isolated and easy to audit
- generated mapping artifacts should be stable enough for downstream tools to consume
