# Progress Log

This document tracks incremental reverse-engineering work and the state of the public tooling.

The goal is twofold:

- build useful tools that can be rerun and extended
- build durable documentation that helps humans understand the reverse-engineered framework of the game

## Current Phase

Story dialogue and broader text manipulation.

We are starting with inventory and classification, not editing.

## Confirmed Text Surfaces

- plain ASCII names in the ROM around `0x001E0700`
- a custom single-byte ROTDD text bank around `0x001DD7E3`
- confirmed pointer-table-driven text at and after `0x0056ED80`
- item display names in `research/raw/text-map.csv`
- RAM-side inventory totals in `research/raw/ram_addresses.csv` are separate from ROM text and should not be conflated with the text tables

## Known Tools

- `encode-rotdd`
- `search-term`
- `search-rotdd`
- `dump-strings`
- `dump-rotdd`
- `find-pointer`
- `dump-pointer-table`
- `export-known-text-map`
- `list-known-text`
- `patch-known-text`
- `patch-text-at-offset`
- `peek`

## Work Log

### 2026-04-06

- Added the first progress tracker for feature work.
- Began the dialogue/text inventory phase.
- Confirmed the existing public data still cleanly separates ROM text tables from RAM gameplay values.
- Identified a likely story or script text bank around `0x001765C0` and started separating it from the menu/debug text surfaces.
- Confirmed a sample from `0x08176750` decodes into dialogue-like text with the known ROTDD letter/space mapping plus additional control bytes.
- Confirmed dialogue punctuation and control mappings for comma, colon, apostrophe, period, question mark, exclamation mark, newline, player name insertion, page break, and speaker handoff.
- Confirmed `0xB3` as the dialogue double quote and represented it in exports as `<QUOTE>`.
- Confirmed the visible digit glyphs `0x11` through `0x16` as `0` through `5`.
- Confirmed `0x22` as a visible hyphen in dialogue and corpus exports.
- Noted `0x02` and `0x05` as likely pause/delay bytes, but left them untranslated for now.
- Kept the combined CSV export path for contiguous text surfaces so the opening dialogue bank can be mapped row by row before scene breakpoints are known.
- Started the character-attribute track with canonical character names: pointer table at `0x0056F578`, ASCII bank at `0x001E0688`, exported to `research/raw/character-names.csv`.
- Added a character-name reference export at `research/raw/character-name-references.csv` so global rename work can be reviewed before writing.
- Confirmed `Mawlock` is the 33rd canonical name row and widened the canonical export to include it.
- Upgraded `patch-character-name` from a pointer-table-only edit to a case-sensitive global rename across the canonical name table, matched text references, and short whole-name ROTDD surface runs such as menu labels.
- Tightened the rename repointing fallback so it uses safe free space above the ROM header and tracks reserved spans to avoid collisions during one rename pass.
- Added a duplicate-name guard so rename targets cannot collide with an existing live canonical name.
- Confirmed the dialogue window shows a speaker prefix such as `Varios:` in the opening scene.
- Corrected the opening surface anchor to include the full first visible speaker prefix at `0x001765DC`.
- Switched dialogue-surface newline handling to inline `<NEWLINE>` tags so the CSV stays single-line per row.
- Added a whole-ROM dialogue-like corpus export and regenerated the CSV so dialogue rows stay contiguous around observed control bytes.
- Added `patch-text-at-offset` for literal-offset replacement work within the original byte budget and exposed `--in-place` for deliberate unsafe writes.
- Established an observed dialogue wrapping rule of 35 visible characters per line and up to 3 visible rows per box for automatic formatting.

## Next Questions

- Where is the story dialogue stored relative to the already confirmed item/spell/system text?
- Does dialogue use the same codec, or a superset with punctuation and control codes?
- Is story text pointer-based, inline, or a mix of both?
- Which visible strings are safe to use as discovery anchors for emulator verification?

## Verification Notes

Any new claims about dialogue should be backed by at least one of:

- a ROM offset and an observed decoded string
- a pointer table entry and its resolved target
- an emulator or debugger observation
- a reproducible script command that prints the same result again
