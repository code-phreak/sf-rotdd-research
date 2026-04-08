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
Replacement names are currently limited by the dialogue-box line wrapping rules for NPCs, while the conservative repointing path for the other entity tables still uses a 12-character cap.
Whole-name matching prevents substring rewrites, so a rename like `Max -> Jeff` will not touch `Maximum`.
When you verify a rename visually, prefer a fresh boot or a freshly reloaded save over an old savestate so stale in-memory UI does not obscure a correct ROM patch.

### Current CSV

The canonical name export is written to `research/raw/character-names.csv`.

The tool searches the ROM directly when applying a rename, so there is no separate reference-export artifact in the normal workflow.

Current columns:

- `local_index`
- `pointer_table_offset`
- `pointer_value`
- `name_rom_offset`
- `name_length`
- `decoded_name`

The class, enemy, and item CSVs use the same compact name-table columns, so the raw files stay easy to scan side by side.

### Current tooling

- `export-character-name-map` writes the canonical CSV export
- `list-character-names` prints a browseable terminal view
- `patch-character-name` renames one character everywhere we can confidently see the old name, including short menu labels and other whole-name ROTDD runs

### Example

To change Mae to Jade, the current workflow repoints Mae into the observed zero padding before the name bank, updates the pointer-table entry that references her name, and rewrites every matched text reference it can confidently see.

That keeps the edit small, visible, and easy to verify in both the CSV and the ROM, while also keeping the visible dialogue, menu labels, and related text in sync.

## Future attribute work

When we move beyond names, this note can grow sections for class data, stats, growth, portrait references, battle flags, and other attributes with their own canonical sources.

## Class Names

The currently confirmed class-name source is the first slice of the partial ROTDD text table around `0x0056F000`.

That slice is exposed through the same conservative rename workflow as the playable roster:

- `export-class-name-map`
- `list-class-names`
- `patch-class-name`
- `class <name> rename <replacement>`

## Enemy Names

The currently confirmed enemy-name source is the second slice of the same partial ROTDD text table, starting around `0x0056F09C`.

The current confirmed slice runs through `Soul Eater`, so the enemy-name export is now the full confirmed enemy block we have evidence for.

That slice is exposed through the same conservative rename workflow as the playable roster:

- `export-enemy-name-map`
- `list-enemy-names`
- `patch-enemy-name`
- `enemy <name> rename <replacement>`

The same 12 ASCII character cap applies to both slices for now, and whole-name matching still prevents substring rewrites such as `Max` inside `Maximum`.

## Item Names

The confirmed item-name source is the item-name table already present in the structured text map.

That table is exposed through the same conservative rename workflow:

- `export-item-name-map`
- `list-item-names`
- `patch-item-name`
- `item <name> rename <replacement>`

The same 12 ASCII character cap applies here too, and whole-name matching still prevents substring rewrites.

## NPC Names

Dialogue-speaker prefixes are extracted from the dialogue corpus and tracked as an NPC-style name map.

NPC extraction is intentionally last in the precedence chain. If a dialogue speaker name already belongs to the playable roster, an enemy, a class, or an item, it is not treated as an NPC. That keeps names like `Ken`, `Mage`, `Dark Mage`, and `Medical Herb` out of the NPC list.

The NPC extractor also normalizes whitespace and case before comparison, so padded labels from the ROM do not create duplicate entries. It also skips obvious system-style labels and description-style item text such as `Victory Conditions`, `Clear Bonus`, or `Medical Herb`.

The NPC CSV records the first mention of each unique NPC name from the corpus, so the file acts as a compact browseable index rather than a dump of every dialogue row.

The NPC raw CSV keeps the NPC name in the rightmost column and does not store the full dialogue example line anymore.

This is the best current starting point for visible NPC labels:

- `export-npc-name-map`
- `list-npc-names`
- `patch-npc-name`
- `npc <name> rename <replacement>`

The same conservative rename rules apply, and the corpus-based extraction keeps the workflow aligned with the actual dialogue text rather than guessing at a separate NPC table. NPC replacements are not capped at 12 characters the way character, class, enemy, and item names are; instead, they are limited by the dialogue-box line wrapping rules and whatever repointing the patcher can safely perform.

This is the right place to note future evidence about class names, enemy names, NPC names, item names, and other visible labels that do not belong in the playable-character section above.
