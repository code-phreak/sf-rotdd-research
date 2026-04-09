# Text Table Map

This note records the currently confirmed name-table slices and the most useful boundaries for browsing and patching them.

The split entity exports are the important output now:

- `character-names.csv`
- `class-names.csv`
- `enemy-names.csv`
- `item-names.csv`
- `npc-names.csv`

The broader dialogue corpus lives in `research/raw/text-surfaces.csv` and uses `type` labels such as `unsorted`, `battle_text`, and `menu_text`. That corpus is documented separately because it is a different workflow from the split name tables.

## Confirmed Name Slices

### Character names

- Plain ASCII pointer table
- Pointer table offset: `0x0056F578`
- Current confirmed row count: `33`
- Current max name length for this table: `8` ASCII characters

### Class names

- Confirmed slice of a partial ROTDD name table
- Table area: `0x0056F000`
- Confirmed rows: `39`
- Current max name length: `12` ASCII characters

### Enemy names

- Confirmed slice of the same partial ROTDD name table as the class names
- Table area: `0x0056F09C`
- Confirmed rows: `79`
- Current max name length: `12` ASCII characters
- This workflow is still experimental while the broad repoint rules are being verified

### Item names

- Confirmed ROTDD menu-name table
- Table area begins around `0x0056EE5C`
- Item names are currently browsable and patchable as a separate workflow

### NPC names

- Dialogue-speaker prefixes are extracted from the corpus, not from a fixed pointer table
- NPC names are kept separate from playable names, classes, enemies, and items
- NPC name length is limited by the dialogue box, not by a fixed 12-character cap

## Why the split matters

The split exports keep each name workflow small and readable:

- the canonical character roster stays separate from class and enemy slices
- item names can be browsed and edited without dragging dialogue data into the same CSV
- NPC names are derived from dialogue text and tracked independently
- the dialogue corpus stays focused on screen-sized text, not entity metadata

## Relationship To The Corpus

The dialogue corpus is still the best source for visible story text.

- it drives `text-surface export template`
- it feeds the broad story rewrite workflow
- it is where rename side effects show up when names appear in dialogue or menu text

For the current wrapping and codec rules, see [`research/text-mechanics.md`](./text-mechanics.md).

## Current Guidance

- use the entity CSVs for browsing and renaming named things
- use `research/raw/text-surfaces.csv` and its templates for dialogue and other surface text
- treat enemy renames as experimental until the broad repoint behavior is fully verified
- treat multi-line template rewriting as experimental until the pointer rewrite path is proven safe

