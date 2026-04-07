# Shining Force: Resurrection of the Dark Dragon Reverse Engineering

This repository is a public knowledge base and tooling project for reverse engineering *Shining Force: Resurrection of the Dark Dragon* on Game Boy Advance.

It is meant to be readable by humans first and useful to tools second. The goal is to preserve confirmed evidence, keep the code maintainable, and make each step reproducible.

## Quick Start

1. Use Python to run the command-line tool from the repository root.
2. Pass `--rom` with a ROM copy, or let the script prompt for a local ROM path.
3. For arbitrary text replacement, start with `patch-text-at-offset`.

Examples:

```powershell
python scripts/rom_text_tools.py --rom path\to\your-rom.gba peek 0x00195F37 --length 0x80
python scripts/rom_text_tools.py --rom path\to\your-rom.gba patch-text-at-offset 0x00195F37 "Mae: Hyaaah!" --output ignore\rom\test.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba patch-character-name Mae Jade --output ignore\rom\test-mae-jade.gba
```

If you do not want to type `--rom` every time, create `scripts/rom_path.local.txt` with a repository-relative ROM path. That file is ignored by Git and remains local.

## What This Repo Contains

- `research/raw/` for structured exports and other raw research data
- `research/` for confirmed writeups and maintained notes
- `src/rotdd_tools/` for package-backed tooling
- `scripts/` for thin command-line entry points and usage notes
- `imhex/` for shared ImHex artifacts
- `ignore/` for ROMs, savestates, Ghidra data, and other private local material

## Useful Data And Docs

The main folders and files to know about are:

- [`research/raw/text-map.csv`](./research/raw/text-map.csv) for confirmed pointer-table text
- [`research/raw/text-surfaces.csv`](./research/raw/text-surfaces.csv) for the broad dialogue/script corpus
- [`research/raw/character-names.csv`](./research/raw/character-names.csv) for the canonical name pointer table
- [`research/raw/character-name-references.csv`](./research/raw/character-name-references.csv) for global rename review rows
- [`research/character-attributes.md`](./research/character-attributes.md) for character name and attribute notes
- [`research/text-mechanics.md`](./research/text-mechanics.md) for the current text codec and wrapping rules
- [`research/text-table-map.md`](./research/text-table-map.md) for the known table map
- [`scripts/README.md`](./scripts/README.md) for command reference and examples
- [`scripts/architecture.md`](./scripts/architecture.md) for the implementation split
- [`PROGRESS.md`](./PROGRESS.md) for the running work log

## Current Focus

The current work is centered on story dialogue, broader text manipulation, and conservative character-attribute editing.

Current confirmed leads:

- enemy names exist in a plain ASCII bank
- spell and item names exist in a custom single-byte text bank
- the canonical character-name table is a plain ASCII pointer table at `0x0056F578`
- `Mawlock` is part of the canonical character-name table and should remain tracked
- a pointer table around `0x0056ED80` resolves spell and item names
- a whole-ROM dialogue-like corpus can be exported to `research/raw/text-surfaces.csv`
- a narrower contiguous dialogue/script excerpt export remains available for known ROM ranges
- mapped text rows can be browsed with `list-known-text`
- mapped text rows can be patched safely with `patch-known-text`
- character names can be browsed with `list-character-names`
- character names can be renamed safely with `patch-character-name`
- arbitrary ROM offsets can be patched with `patch-text-at-offset`
- additional ROTDD-style text runs can be scanned with `scan-rotdd-runs`
- the dialogue codec currently supports punctuation, control tags, visible digits, and whole-name replacements in a CSV-friendly format
- the dialogue box is currently treated as a 35-character wide, 3-row surface for automatic wrapping

`patch-character-name` is the conservative attribute-editing command for names. It patches the canonical name pointer table, repoints longer names into observed safe padding when possible, and rewrites whole-name matches across known text rows, dialogue surfaces, and short ROTDD surface runs such as menu labels, join banners, and card labels. Repointed rows use safe free space above the ROM header, and the allocator tracks reserved spans so one rename does not overwrite another.

## Text Editing Basics

`patch-text-at-offset` is the simplest CSV-friendly write path when you already know a literal ROM offset.

- pass the offset and replacement text as separate positional arguments
- quote the replacement when it contains spaces or punctuation so the shell keeps it together as one argument
- use `<QUOTE>` inside the replacement when you need a double quote
- the tool auto-wraps on whole-word boundaries into at most three rows of 35 characters when you do not supply explicit `<NEWLINE>` tags
- `<PAGE_BREAK>` resets the three-row budget for the next page
- if the wrapped text would need more than three visible rows on one page, the command fails instead of overflowing into a different surface
- the tool prints a warning when it inserts line breaks for you, because the result should be reviewed on screen

Example:

```powershell
python scripts/rom_text_tools.py --rom path\to\your-rom.gba patch-text-at-offset 0x00195F37 "Mae: I'm busy.<PAGE_BREAK>Come back later.<SPEAKER_BREAK>" --output ignore\rom\test.gba
```

## Safety Notes

- `patch-known-text` only works on mapped rows from the known ROTDD tables
- `patch-text-at-offset` works from a literal ROM offset and still stays within the original byte budget
- both write commands accept `--in-place` if you intentionally want to overwrite the source ROM
- `--in-place` is unsafe and should only be used when you have a backup copy
- duplicate live names are rejected when a rename would create a collision
- the canonical character-name export now includes `Mawlock` as the 33rd named row

## License

This repository is released under the MIT License for the original content included here. That does not grant rights to the underlying game, its ROM, or other third-party intellectual property.

This repository exists for research and preservation work only. I do not endorse or support the illegal sharing or distribution of copyrighted software.

## Credits

- Explicit thanks to ElfenTaiga from Shining Force Central for sharing the ImHex pattern artifact now recorded in this repository.
