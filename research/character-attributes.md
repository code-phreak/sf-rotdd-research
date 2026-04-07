# Character Attributes

This note starts with character names, because that is the smallest safe step toward editable character attributes.

The goal is to keep attribute-editing work evidence-based and reproducible:

- identify the canonical ROM source for the attribute
- export a readable CSV map for human review
- patch through a conservative tool path that preserves the rest of the ROM
- document the limitations before expanding the feature set

## Character Names

The canonical character-name source is a plain ASCII pointer table at `0x0056F578`.

The table currently maps the first 33 named characters used by the game. The strings they point to are in a plain ASCII bank beginning at `0x001E0688`.

Confirmed early rows include:

- `Max`
- `Mae`
- `Pelle`
- `Ken`
- `Vankar`
- `Mawlock`

The same bank continues with the rest of the named characters.

### Why this matters

The table-driven layout means we can repoint an individual name without disturbing the surrounding names.

For the canonical name table itself, the tool uses the observed zero padding immediately before the name bank as conservative free space for longer replacements. That is enough for the current Mae test case, but it is intentionally narrow until we map more of the surrounding ROM.

The rename workflow now also searches the known ROTDD text tables, the broader text-surface corpus, and short whole-name ROTDD surface runs such as menu labels so visible dialogue and similar references stay aligned with the canonical name table.
If a matched row cannot fit the longer replacement yet, the tool reports that row and leaves it for later repointing work instead of forcing a bad write.
Repointed rows are allocated from safe free space above the ROM header, and each reserved span is tracked so one rename does not overwrite another.
The rename tools also reject a replacement that would collide with an existing live canonical name.

### Current CSV

The canonical name export is written to `research/raw/character-names.csv`.

A companion reference export is written to `research/raw/character-name-references.csv` when we want to review every matched occurrence of one name before applying a global rename.

Current columns:

- `local_index`
- `pointer_table_offset`
- `pointer_value`
- `name_rom_offset`
- `name_length`
- `decoded_name`

Reference export columns:

- `row_index`
- `source_kind`
- `source_label`
- `source_index`
- `rom_offset`
- `decoded_text`

### Current tooling

- `export-character-name-map` writes the canonical CSV export
- `export-character-name-references` writes a review CSV for one current name
- `list-character-names` prints a browseable terminal view
- `patch-character-name` renames one character everywhere we can confidently see the old name, including short menu labels and other whole-name ROTDD runs

### Example

To change Mae to Jade, the current workflow repoints Mae into the observed zero padding before the name bank, updates the pointer-table entry that references her name, and rewrites every matched text reference it can confidently see.

That keeps the edit small, visible, and easy to verify in both the CSV and the ROM, while also keeping the visible dialogue, menu labels, and related text in sync.

## Future attribute work

When we move beyond names, this note can grow sections for class data, stats, growth, portrait references, battle flags, and other attributes with their own canonical sources.
