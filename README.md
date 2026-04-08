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
python scripts/rom_text_tools.py --rom path\to\your-rom.gba character Mae rename Jade --output ignore\rom\test-mae-jade.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba class Knight rename Baron --output ignore\rom\test-knight-baron.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba enemy Goblin rename Ogre --output ignore\rom\test-goblin-ogre.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba item Healing Seed rename Remedy --output ignore\rom\test-healing-seed-remedy.gba
python scripts/rom_text_tools.py --rom path\to\your-rom.gba npc Priest rename Oracle --output ignore\rom\test-priest-oracle.gba
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

The name-table CSVs are intentionally compact. `character-names.csv`, `class-names.csv`, `enemy-names.csv`, and `item-names.csv` all use the same six-column layout, while `npc-names.csv` keeps the NPC name in the rightmost column and omits the full dialogue line.

## Useful Data And Docs

The main folders and files to know about are:

- [`research/raw/character-names.csv`](./research/raw/character-names.csv) for the canonical playable-name table
- [`research/raw/class-names.csv`](./research/raw/class-names.csv) for the confirmed class-name slice
- [`research/raw/enemy-names.csv`](./research/raw/enemy-names.csv) for the confirmed enemy-name slice
- [`research/raw/item-names.csv`](./research/raw/item-names.csv) for the confirmed item-name table
- [`research/raw/npc-names.csv`](./research/raw/npc-names.csv) for dialogue-speaker prefixes extracted from the corpus
- [`research/raw/text-surfaces.csv`](./research/raw/text-surfaces.csv) for the broad dialogue/script corpus
- [`research/character-attributes.md`](./research/character-attributes.md) for character name and attribute notes
- [`research/text-mechanics.md`](./research/text-mechanics.md) for the current text codec and wrapping rules
- [`research/text-table-map.md`](./research/text-table-map.md) for the known table map
- [`scripts/README.md`](./scripts/README.md) for command reference and examples
- [`scripts/architecture.md`](./scripts/architecture.md) for the implementation split
- [`ROADMAP.md`](./ROADMAP.md) for the living roadmap and progress log

## Current Focus

The current work is centered on story dialogue, broader text manipulation, and conservative character-attribute editing.

Current confirmed leads:

- character names exist in a plain ASCII bank
- the confirmed class-name slice and enemy-name slice are partial ROTDD text tables that can be browsed and renamed with the same API-style command shape
- the canonical character-name table is a plain ASCII pointer table at `0x0056F578`
- a pointer table around `0x0056ED80` resolves spell and item names
- a whole-ROM dialogue-like corpus can be exported to `research/raw/text-surfaces.csv`
- a narrower contiguous dialogue/script excerpt export remains available for known ROM ranges
- character names can be browsed with `list-character-names`
- character names can be renamed safely with `patch-character-name`
- class names can be browsed with `list-class-names`
- class names can be renamed safely with `patch-class-name`
- enemy names can be browsed with `list-enemy-names`
- enemy names can be renamed safely with `patch-enemy-name`
- item names can be browsed with `list-item-names`
- item names can be renamed safely with `patch-item-name`
- NPC-speaker names can be browsed with `list-npc-names`
- NPC-speaker names can be renamed safely with `patch-npc-name`
- arbitrary ROM offsets can be patched with `patch-text-at-offset`
- additional ROTDD-style text runs can be scanned with `scan-rotdd-runs`
- the dialogue codec currently supports punctuation, control tags, visible digits, and whole-name replacements in a CSV-friendly format
- the dialogue box is currently treated as a 35-character wide, 3-row surface for automatic wrapping

`patch-character-name` is the conservative attribute-editing command for names. It patches the canonical name pointer table, repoints longer names into observed safe padding when possible, and rewrites whole-name matches across known text rows, dialogue surfaces, and short ROTDD surface runs such as menu labels, join banners, and card labels. Repointed rows use safe free space above the ROM header, and the allocator tracks reserved spans so one rename does not overwrite another. The preferred API-style entry point is now `character <name> rename <replacement>`, with `patch-character-name` kept as a compatibility alias.

`patch-class-name` is the matching command for the confirmed class-name slice. It uses the same conservative rename rules, 12-character cap, and whole-name matching behavior, but it starts from the class slice instead of the playable-character pointer table. The preferred API-style entry point is `class <name> rename <replacement>`, with `patch-class-name` kept as a compatibility alias.

`patch-enemy-name` is the matching command for the confirmed enemy-name slice. It uses the same conservative rename rules, 12-character cap, and whole-name matching behavior, but it starts from the enemy slice instead of the playable-character pointer table. The preferred API-style entry point is `enemy <name> rename <replacement>`, with `patch-enemy-name` kept as a compatibility alias.

`patch-item-name` is the matching command for the confirmed item-name table. It uses the same conservative rename rules, 12-character cap, and whole-name matching behavior, but it starts from the item table. The preferred API-style entry point is `item <name> rename <replacement>`, with `patch-item-name` kept as a compatibility alias.

`patch-npc-name` is the matching command for dialogue-speaker prefixes extracted from the corpus. It uses the same conservative rename rules and whole-name matching behavior, but it starts from dialogue text instead of a pointer table. The preferred API-style entry point is `npc <name> rename <replacement>`, with `patch-npc-name` kept as a compatibility alias.

## Text Editing Basics

`patch-text-at-offset` is the simplest CSV-friendly write path when you already know a literal ROM offset.

- pass the offset and replacement text as separate positional arguments
- quote the replacement when it contains spaces or punctuation so the shell keeps it together as one argument
- use `<QUOTE>` inside the replacement when you need a double quote
- the tool auto-wraps on whole-word boundaries into at most three rows of 35 characters when you do not supply explicit `<NEWLINE>` tags
- `<PAGE_BREAK>` resets the three-row budget for the next page
- if the wrapped text would need more than three visible rows on one page, the command fails instead of overflowing into a different surface
- the tool prints a warning when it inserts line breaks for you, because the result should be reviewed on screen

If you already know the mapped row rather than the literal offset, `patch-known-text` can patch the selected row directly.

Example:

```powershell
python scripts/rom_text_tools.py --rom path\to\your-rom.gba patch-text-at-offset 0x00195F37 "Mae: I'm busy.<PAGE_BREAK>Come back later.<SPEAKER_BREAK>" --output ignore\rom\test.gba
```

## Safety Notes

- `patch-text-at-offset` works from a literal ROM offset and still stays within the original byte budget
- both write commands accept `--in-place` if you intentionally want to overwrite the source ROM
- `--in-place` is unsafe and should only be used when you have a backup copy
- duplicate live names are rejected when a rename would create a collision
- character-name replacements are currently capped at 12 ASCII characters, which is enough for the repointed-safe path we have evidence for right now
- whole-name matching avoids substring rewrites, so `Max` will not turn `Maximum` into `Jeffimum`
- the canonical character-name export now includes `Mawlock` as the 33rd named row
- when you verify a rename in the emulator, prefer a fresh boot or a freshly reloaded save over an old savestate because stale in-memory UI can hide a correct ROM patch
- savestates are emulator snapshots; if you need to patch save data, the roadmap calls for raw battery-save support instead of trying to support arbitrary savestate formats

## License

This repository is released under the MIT License for the original content included here. That does not grant rights to the underlying game, its ROM, or other third-party intellectual property.

This repository exists for research and preservation work only. I do not endorse or support the illegal sharing or distribution of copyrighted software.

## Credits

- Thanks to ElfenTaiga from Shining Force Central for sharing the ImHex pattern artifact now recorded in this repository.
