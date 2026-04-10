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
The rename commands default to the conservative path for these entity workflows. That keeps the EOF-repoint path as the normal behavior, while `liberal` remains an unsafe fallback for cases where a reference would otherwise be skipped. The broader bulk repoint path is still unstable until we verify which pointer hits are safe to rewrite.
Each entity workflow also supports a bulk CSV template:

- `character export template` / `character patch file`
- `class export template` / `class patch file`
- `enemy export template` / `enemy patch file`
- `item export template` / `item patch file`
- `npc export template` / `npc patch file`

### Why this matters

The table-driven layout means we can repoint an individual name without disturbing the surrounding names.

For the canonical name table itself, longer replacements now append their payload to the end of the copied ROM instead of guessing at free space inside the original image. That keeps the source ROM untouched and avoids accidental overlap with unrelated data.
Because the replacement payload is appended, the resulting ROM image can be larger than the source file; emulator verification is fine, but hardware or flashcart testing should confirm that the target accepts the larger image.

The rename workflow now also searches the known ROTDD text tables, the broader text-surface corpus, and short whole-name ROTDD surface runs such as menu labels so visible dialogue and similar references stay aligned with the canonical name table.
If a matched row cannot fit the longer replacement yet, the tool reports that row and repoints the payload into appended space instead of forcing a bad write. That is currently fine for the named-table workflows, but the same strategy is still under review for bulk story patching.
The rename tools also reject a replacement that would collide with an existing live canonical name.
Playable character names are currently limited to 8 ASCII characters so menu spacing stays readable. The conservative repointing path for the other entity tables still uses a 12-character cap.
Whole-name matching prevents substring rewrites and also handles simple singular/plural dialogue forms, so a rename like `Max -> Jeff` will not touch `Maximum` and `Goblin -> Big Loser` can also affect `goblins`.
When you verify a rename visually, prefer a fresh boot or a freshly reloaded save so cached in-memory UI does not obscure a correct ROM patch.

The dialogue normalizer can automatically page long dialogue rewrites, so a single replacement can span multiple 3-row pages without the caller manually inserting every page break.

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

- `character export map` writes the canonical CSV export
- `character list names` prints a browseable terminal view
- `character patch name <current> <replacement>` renames one character everywhere we can confidently see the old name, including short menu labels and other whole-name ROTDD runs.

### Example

To change Mae to Jade, the current workflow appends the replacement into space at the end of the copied ROM, updates the pointer-table entry that references her name, and rewrites every matched text reference it can confidently see.

That keeps the edit small, visible, and easy to verify in both the CSV and the ROM, while also keeping the visible dialogue, menu labels, and related text in sync.

## Future attribute work

When we move beyond names, this note can grow sections for class data, stats, growth, portrait references, battle flags, and other attributes with their own canonical sources.

### Community-confirmed stat and spell notes

A public GameFAQs stats topic for ROTDD gives us reliable gameplay rules, but not a verified persistent memory layout yet. It is useful for behavior and balance notes, not yet enough by itself to map a safe stat editor.

Confirmed from that post:

- the stats being tracked are HP, MP, Attack, Defense, and Speed
- weapon choice affects Attack only in the poster's collected data
- character-level samples were gathered at pre-promotion levels 5, 10, 15, and 20, plus post-promotion levels 1, 10, 15, 20, and 25
- Gong learns `Heal2` at level 8, `Heal3` at 16, `Heal4` at `20/24`, and `Aura1` at `20/30`
- Ken starts with `Spear`
- Mae's base weapon is `Bronze Lance`
- archers start from `Wooden Arrow`
- `Steel Arrow`, `Elven Arrow`, `Armour Arrow`, and `Sniper` progress the archer line
- `Handaxe`, `Middle Axe`, `Heat Axe`, and `Great Axe` are confirmed axe progression points for fighters like Gort and Luke

The post also notes that Diana joins at level 6 and is close enough to Hans for a swap point, but that is a gameplay observation rather than a memory map.

At the moment, this still does not identify a stable in-memory or save-file struct for character stats. We still need a verified persistent layout before we can safely build `character patch stat`.

### Observed live-RAM stat layout

The repo also contains a live-RAM stat map in `research/raw/ram_addresses.csv`. That map is more concrete than the legacy notes, but it still describes runtime memory rather than a verified persistent save layout.

The current pattern looks like this:

- each party member has a block of live RAM stat fields
- matching stat fields are separated by a regular stride of `0x148` bytes between characters
- the observed fields include:
  - current HP
  - max HP
  - current MP
  - max MP
  - EX
  - attack
  - defend
  - agility
  - movement
  - magic resistance

For the first four party members, the current validation set is:

Important correction:

- the early starting-stat values we observed are not reliable fixed values
- the game appears to assign or derive some of these values at first load, so recorded numbers should be treated as samples, not as anticipated constants
- do not build future stat-edit assumptions on the exact boot-time numbers we happened to observe

- `Max`
  - Level 1
  - Max HP 12
  - Max MP 10
  - EX 0
  - Magic Resistance 6%
  - Attack 11
  - Defend 6
  - Agility 4
  - Movement 6
  - Spells: `Egress`
  - Equipped: `Short Sword`, `Steel Ring`
  - Items: `None`
  - Growth charts:
    - HP = Type B
    - MP = Type A
    - Mag Res = Type C
    - Attack = Type C
    - Defend = Type C
    - Agility = Type C
- `Ken`
  - Level 1
  - Max HP 8
  - Max MP 0
  - EX 0
  - Magic Resistance 0%
  - Attack 14
  - Defend 6
  - Agility 5
  - Movement 8
  - Spells: `None`
  - Equipped: `Spear`
  - Items: `None`
  - Growth charts:
    - HP = Type D
    - MP = Type ?
    - Mag Res = Type ?
    - Attack = Type B
    - Defend = Type A
    - Agility = Type B
- `Tao`
  - Level 1
  - Max HP 10
  - Max MP 7
  - EX 0
  - Magic Resistance 25%
  - Attack 8
  - Defend 4
  - Agility 6
  - Movement 5
  - Spells: `Blaze`
  - Equipped: `Wooden Staff`
  - Items: `None`
  - Growth charts:
    - HP = Type B
    - MP = Type C
    - Mag Res = Type C
    - Attack = Type B
    - Defend = Type B
    - Agility = Type B
- `Hans`
  - Level 1
  - Max HP 12
  - Max MP 0
  - EX 0
  - Magic Resistance 0%
  - Attack 14
  - Defend 4
  - Agility 6
  - Movement 5
  - Spells: `None`
  - Equipped: `Wooden Arrow`
  - Items: `None`
  - Growth charts:
    - HP = Type A
    - MP = Type ?
    - Mag Res = Type ?
    - Attack = Type A
    - Defend = Type A
    - Agility = Type C

This gives us a good validation target for live stat reads and future save mapping, but it still is not enough on its own to build a persistent stat patcher.

### Growth math and chart types

The growth system still needs its own dedicated reverse-engineering pass.

Current evidence says we have:

- a table-driven growth path
- a level-up increment path that is separate from the initial load path
- growth chart types that influence how stat gains are rolled and applied

What still needs to happen:

- reverse engineer the level/increment growth math operations in a clean, reproducible way
- identify the chart types used by the game
- determine whether those chart types are directly editable from ROM
- if they are editable, expose them through a conservative tool command rather than raw offsets

The current Max level-up work already showed visible increments for HP, MP, Attack, Defense, and Speed, so the next phase should focus on labeling the growth chart mechanics rather than re-proving that growth exists.

## Class Names

The currently confirmed class-name source is the first slice of the partial ROTDD text table around `0x0056F000`.

That slice is exposed through the same conservative rename workflow as the playable roster:

- `class export map`
- `class list names`
- `class patch name <current> <replacement>`

## Enemy Names

The currently confirmed enemy-name source is the second slice of the same partial ROTDD text table, starting around `0x0056F09C`.

The current confirmed slice runs through `Soul Eater`, so the enemy-name export is now the full confirmed enemy block we have evidence for.

That slice is exposed through the same conservative rename workflow as the playable roster:

- `enemy export map`
- `enemy list names`
- `enemy patch name <current> <replacement>`

The same 12 ASCII character cap applies to both slices for now, and whole-name matching still prevents substring rewrites such as `Max` inside `Maximum` while also handling simple plural mentions.

## Item Names

The confirmed item-name source is the item-name table already present in the split raw name exports.

That table is exposed through the same conservative rename workflow:

- `item export map`
- `item list names`
- `item patch name <current> <replacement>`

The same 12 ASCII character cap applies here too, and whole-name matching still prevents substring rewrites while also handling simple plural mentions.

## NPC Names

Dialogue-speaker prefixes are extracted from the dialogue corpus and tracked as an NPC-style name map.

NPC extraction is intentionally last in the precedence chain. If a dialogue speaker name already belongs to the playable roster, an enemy, a class, or an item, it is not treated as an NPC. That keeps names like `Ken`, `Mage`, `Dark Mage`, and `Medical Herb` out of the NPC list.
The NPC extractor also uses the canonical checked-in playable roster as a stable exclusion list, so a renamed test ROM does not accidentally reclassify a playable character like `Tao` as an NPC.

The NPC extractor also normalizes whitespace and case before comparison, so padded labels from the ROM do not create duplicate entries. It also skips obvious system-style labels and description-style item text such as `Victory Conditions`, `Clear Bonus`, or `Medical Herb`.

The NPC CSV records the first mention of each unique NPC name from the corpus, so the file acts as a compact browseable index rather than a dump of every dialogue row.

The NPC raw CSV keeps the NPC name in the rightmost column and does not store the full dialogue example line anymore.

This is the best current starting point for visible NPC labels:

- `npc export map`
- `npc list names`
- `npc patch name <current> <replacement>`

The same conservative rename rules apply, and the corpus-based extraction keeps the workflow aligned with the actual dialogue text rather than guessing at a separate NPC table. NPC replacements are not capped at 12 characters the way character, class, enemy, and item names are; instead, they are limited by the dialogue-box line wrapping rules and appended repointing when the text grows too long for its original slot.

This is the right place to note future evidence about class names, enemy names, NPC names, item names, and other visible labels that do not belong in the playable-character section above.
