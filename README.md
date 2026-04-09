# Shining Force: Resurrection of the Dark Dragon Reverse Engineering

This repository is a public knowledge base and tooling project for reverse engineering *Shining Force: Resurrection of the Dark Dragon* on Game Boy Advance.


## Quick Start

1. Use Python to run the command-line tool from the repository root.
2. Pass `--rom` with a ROM copy, or let the script prompt for a local ROM path.
3. For arbitrary text replacement, start with `patch-text-at-offset`.
4. For larger text edits, export a two-column template from `research/raw/text-surfaces.csv` and patch it back with `text-surface export template` and `text-surface patch file`. If you do not pass `--refs rewrite` or `--refs keep`, the tool will explain the choice the first time, ask once, and remember your preference locally unless you clear it. Dialogue-like patches now reflow screen breaks from the updated text so renamed names can shift the surrounding lines naturally. `unsorted` rows have been reliable so far when the replacement stays the same length or shorter; multi-line template rewriting is still experimental, and the current broad EOF repoint behavior is still considered unstable until the pointer rewrite rules are fully verified.

Examples:

```powershell
python scripts/rom_text_tools.py --rom path\to\your-rom.gba peek 0x00195F37 --length 0x80
python scripts/rom_text_tools.py --rom path\to\your-rom.gba patch-text-at-offset 0x00195F37 "Mae: Hyaaah!" --output ignore\rom\test.gba
python scripts/rom_text_tools.py text-surface export template --type unsorted
python scripts/rom_text_tools.py --rom path\to\your-rom.gba text-surface patch file --input ignore\temp\text-surfaces.unsorted.csv --corpus research\raw\text-surfaces.csv --output ignore\rom\test-surfaces.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba text-surface patch file --input ignore\temp\text-surfaces.unsorted.csv --corpus research\raw\text-surfaces.csv --refs rewrite --output ignore\rom\test-surfaces.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba character patch name Mae Jade --output ignore\rom\test-mae-jade.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba class patch name Knight Baron --output ignore\rom\test-knight-baron.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba enemy patch name Goblin Ogre --output ignore\rom\test-goblin-ogre.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba item patch name Healing Seed Remedy --output ignore\rom\test-healing-seed-remedy.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba npc patch name Priest Oracle --output ignore\rom\test-priest-oracle.gba
```

If you do not want to type `--rom` every time, create `scripts/rom_path.local.txt` with a repository-relative ROM path. That file is ignored by Git and remains local.

## What This Repo Contains

- `research/raw/` for structured exports and other raw research data
- `research/` for confirmed writeups and maintained notes
- `src/rotdd_tools/` for package-backed tooling
- `scripts/` for thin command-line entry points and usage notes
- `imhex/` for shared ImHex artifacts
- `ignore/` for ROMs, savestates, Ghidra data, and other private local material

`research/raw/` is reserved for canonical exports that we expect to keep and diff over time. Temporary review artifacts, scratch ROMs, and other one-off outputs belong in `ignore/`.

The name-table CSVs are intentionally compact. `character-names.csv`, `class-names.csv`, `enemy-names.csv`, and `item-names.csv` all use the same six-column layout, while `npc-names.csv` keeps the NPC name in the rightmost column, omits the full dialogue line, and no longer stores `row_index`. `text-surfaces.csv` uses `source_kind,rom_offset,type,decoded_text`, `decoded_text` is always quoted so commas and inline tags stay readable, and generated text-surface templates quote `decoded_text` as well.

## Useful Data And Docs

The main folders and files to know about are:

- [`research/raw/character-names.csv`](./research/raw/character-names.csv) for the canonical playable-name table
- [`research/raw/class-names.csv`](./research/raw/class-names.csv) for the confirmed class-name slice
- [`research/raw/enemy-names.csv`](./research/raw/enemy-names.csv) for the confirmed enemy-name slice
- [`research/raw/item-names.csv`](./research/raw/item-names.csv) for the confirmed item-name table
- [`research/raw/npc-names.csv`](./research/raw/npc-names.csv) for dialogue-speaker prefixes extracted from the corpus
- [`research/raw/text-surfaces.csv`](./research/raw/text-surfaces.csv) for the broad dialogue/script corpus, with a `type` column that defaults to `unsorted` unless the current corpus review labels the row
- [`ignore/temp/text-surfaces.unsorted.csv`](./ignore/temp/text-surfaces.unsorted.csv) for the editable two-column template exported from the current `unsorted` corpus rows
- [`research/character-attributes.md`](./research/character-attributes.md) for character name and attribute notes
- [`research/text-mechanics.md`](./research/text-mechanics.md) for the current text codec and wrapping rules
- [`research/text-table-map.md`](./research/text-table-map.md) for the known table map
- [`scripts/README.md`](./scripts/README.md) for command reference and examples
- [`scripts/architecture.md`](./scripts/architecture.md) for the implementation split
- [`ROADMAP.md`](./ROADMAP.md) for the living roadmap

## Current Focus

The current work is centered on story dialogue, broader text manipulation, conservative character-attribute editing, and laying the groundwork for spell editing.

Current confirmed leads:

- character names exist in a plain ASCII bank
- the confirmed class-name slice and enemy-name slice are partial ROTDD text tables that can be browsed and renamed with the same API-style command shape
- the canonical character-name table is a plain ASCII pointer table at `0x0056F578`
- a pointer table around `0x0056ED80` resolves spell and item names
- a whole-ROM dialogue-like corpus can be exported to `research/raw/text-surfaces.csv`
- a two-column text-surface template can be exported from any one corpus type and patched back with EOF repointing when needed
- a narrower contiguous dialogue/script excerpt export remains available for known ROM ranges
- the broad dialogue corpus includes explicit type labels for the rows called out in the current corpus review, while everything else defaults to `unsorted`
- character names can be browsed with `character list names`
- character names can be renamed safely with `character patch name <current> <replacement>`
- class names can be browsed with `class list names`
- class names can be renamed safely with `class patch name <current> <replacement>`
- enemy names can be browsed with `enemy list names`
- enemy names can be renamed safely with `enemy patch name <current> <replacement>`
- enemy renames are experimental and still in active testing while we verify the broad repoint path
- item names can be browsed with `item list names`
- item names can be renamed safely with `item patch name <current> <replacement>`
- NPC-speaker names can be browsed with `npc list names`
- NPC-speaker names can be renamed safely with `npc patch name <current> <replacement>`
- arbitrary ROM offsets can be patched with `patch-text-at-offset`
- additional ROTDD-style text runs can be scanned with `scan-rotdd-runs`
- the dialogue codec currently supports punctuation, control tags, visible digits, and whole-name replacements in a CSV-friendly format
- the dialogue box is currently treated as a 32-character wide, 3-row surface for automatic wrapping

`character patch name <current> <replacement>` is the conservative attribute-editing command for names. It patches the canonical name pointer table, repoints longer names by appending the replacement to the end of the copied ROM, and rewrites whole-name matches across known text rows, dialogue surfaces, and short ROTDD surface runs such as menu labels, join banners, and card labels. This keeps the original ROM data untouched and avoids guessing at in-ROM free space.

`class patch name <current> <replacement>` is the matching command for the confirmed class-name slice. It uses the same conservative rename rules, 12-character cap, and whole-name matching behavior, but it starts from the class slice instead of the playable-character pointer table.

`enemy patch name <current> <replacement>` is the matching command for the confirmed enemy-name slice. It uses the same conservative rename rules, 12-character cap, and whole-name matching behavior, but it starts from the enemy slice instead of the playable-character pointer table. Enemy renames are experimental and still in active testing while we verify the broad repoint path.

`item patch name <current> <replacement>` is the matching command for the confirmed item-name table. It uses the same conservative rename rules, 12-character cap, and whole-name matching behavior, but it starts from the item table.

`npc patch name <current> <replacement>` is the matching command for dialogue-speaker prefixes extracted from the corpus. It uses the same conservative rename rules and whole-name matching behavior, but it starts from dialogue text instead of a pointer table.

Each entity workflow also supports `export template` and `patch file` for bulk edits from a CSV template. The template file uses `current_name,replacement_name`, and the fixed-length entity commands reject oversized names before they start scanning for matches.

All entity rename commands default to the conservative path. Longer replacements append to the end of the copied ROM and repoint the relevant table entry when possible. `liberal` is intentionally unsafe and may fall back to direct in-place writes when a reference would otherwise be skipped.

`text-surface export template` filters `research/raw/text-surfaces.csv` down to a single type label and writes a two-column editable CSV to `ignore/temp/`. `text-surface patch file` compares that template against the current corpus, patches only the modified rows, and uses EOF repointing when a changed row needs more room. Dialogue-like patches reflow screen breaks from the updated text so name changes can shift the surrounding lines naturally. `unsorted` rows have been reliable so far when the replacement stays the same length or shorter, but multi-line template rewriting is still experimental and the bulk repoint path is still unstable until we finish verifying which pointer references are safe to rewrite.

`text-surface patch file` also supports a ref-file preference tag:

- `--refs rewrite` regenerates the reference corpus CSV after patching
- `--refs keep` leaves the reference corpus CSV unchanged
- if neither is supplied, the first run explains the choice, prompts once, and can remember the answer in `scripts/text_surface_refs.local.txt`
- `--clear-refs-preference` deletes the saved local preference

## Text Editing Basics

`patch-text-at-offset` is the simplest CSV-friendly write path when you already know a literal ROM offset.

- pass the offset and replacement text as separate positional arguments
- quote the replacement when it contains spaces or punctuation so the shell keeps it together as one argument
- use `<QUOTE>` inside the replacement when you need a double quote
- the tool auto-wraps on whole-word boundaries into at most three rows of 33 characters when you do not supply explicit `<NEWLINE>` tags
- `<PAGE_BREAK>` resets the three-row budget for the next page
- the normalizer can also insert `<PAGE_BREAK>` automatically when a dialogue block needs to continue past three visible rows
- if the wrapped text would need more than three visible rows on one page, the command fails instead of overflowing into a different surface
- the tool prints a warning when it inserts line breaks for you, because the result should be reviewed on screen

If you already know the mapped row rather than the literal offset, `patch-known-text` can patch the selected row directly.

Example:

```powershell
python scripts/rom_text_tools.py --rom path\to\your-rom.gba patch-text-at-offset 0x00195F37 "Mae: I'm busy.<PAGE_BREAK>Come back later.<SPEAKER_BREAK>" --output ignore\rom\test.gba
```

## Safety Notes

- `patch-text-at-offset` works from a literal ROM offset and repoints to EOF when a safe pointer target exists; otherwise it stays within the original byte budget or fails cleanly
- broad template repointing is still unstable until we finish verifying which pointer references are safe to rewrite
- both write commands accept `--in-place` if you intentionally want to overwrite the source ROM
- `--in-place` is unsafe and should only be used when you have a backup copy
- duplicate live names are rejected when a rename would create a collision
- playable character-name replacements are currently capped at 8 ASCII characters, which is enough for the current rename workflow and appended repoint path
- the skip output lists every skipped row with short reason labels such as `too long for slot`, `no pointer table`, and `name collision`
- `strict` is the default conservative rename behavior for every entity workflow; `liberal` is an unsafe best-effort fallback
- whole-name matching avoids substring rewrites and also handles simple singular/plural dialogue forms, so `Max` will not turn `Maximum` into `Jeffimum` and `Goblin` can become `Big Loser` in both singular and plural mentions
- the canonical character-name export now includes `Mawlock` as the 33rd named row
- appended repoints can grow the ROM image, so emulator testing is fine but physical hardware or flashcart testing should verify that the target accepts the larger file
- when you verify a rename in the emulator, prefer a fresh boot or a freshly reloaded save so cached in-memory UI does not hide a correct ROM patch
- savestates are emulator snapshots; if you need to patch save data, the roadmap calls for raw battery-save support instead of trying to support arbitrary savestate formats

## License

This repository is released under the MIT License for the original content included here. That does not grant rights to the underlying game, its ROM, or other third-party intellectual property.

This repository exists for research and preservation work only. I do not endorse or support the illegal sharing or distribution of copyrighted software.

## Credits

- Thanks to ElfenTaiga from Shining Force Central for sharing the ImHex pattern artifact now recorded in this repository.
