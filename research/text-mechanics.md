# Text Mechanics

This note records the current confirmed mechanics behind ROM text lookup and in-place text editing.

It is written for practical use. Every point here is meant to help someone find game text, understand what they are looking at, and make safe edits without stumbling into avoidable corruption.

## Confirmed text banks

Two different text representations are currently confirmed in the ROM.

### Plain ASCII bank

Character names appear in plain ASCII around `0x001E0700`.

Confirmed examples:

- `Goblin` at `0x001E0784`
- `Dark Dragon` at `0x001E09AC`

This bank is easy to search with standard string tools.

### ROTDD custom-encoded bank

Spell names, item names, and at least some other menu-facing strings are stored in a custom single-byte encoding around `0x001DD7E3` and onward.

Confirmed examples:

- `Heal` at `0x001DD802`
- `Blaze` at `0x001DD875`
- `Medical Herb` at `0x001DD946`
- `Healing Seed` at `0x001DD953`

This bank is not visible through plain ASCII or UTF-16 text search.

### Class-name table

Class names are stored in the first slice of the partial ROTDD table around `0x0056F000`.

Confirmed examples include:

- `Swordsman`
- `Knight`
- `Warrior`
- `Mage`
- `Monk`

This is the class-name source, not an enemy roster list.

### Enemy-name table

Enemy names are stored in the second slice of the same partial ROTDD table around `0x0056F09C`.

Confirmed examples include:

- `Goblin`
- `Bowrider`
- `Rune Knight`
- `Silver KT`
- `Dullahan`

This is the enemy-name source, not a monster roster list. The confirmed slice currently runs through `Soul Eater` before the next text block begins, and the current export now covers 79 enemy-name rows.

### Known dialogue windows

The corpus review also points to a few reliable dialogue windows that are useful when checking speaker names and dialogue-driven rename coverage:

- Priest general dialogue: `0x001D276F` to `0x001D2E72`
- Merchant general dialogue: `0x001D2E72` to `0x001D3536`
- Merchant-related later dialogue: `0x001DC487` to `0x001DD0D5`

The first two windows meet at the same boundary. The later merchant block looks related, but it may be a separate scene bank, so we keep all three windows documented for now.

## Confirmed codec rules

The currently confirmed parts of the ROTDD text codec are enough to decode and patch many menu strings safely.

- `0x00` terminates a string
- `0x10` is a space
- uppercase letters decode as `byte + 0x16`
- lowercase letters decode as `byte + 0x19`
- visible digits also use one-byte glyphs in the surface codec; our current best mapping treats them as a contiguous run:
  - `0x11` is `0`
  - `0x12` is `1`
  - `0x13` is `2`
  - `0x14` is `3`
  - `0x15` is `4`
  - `0x16` is `5`
  - `0x17` is `6`
  - `0x18` is `7`
  - `0x19` is `8`
  - `0x1A` is `9`
- `0x23` is a period
- `0x25` is a colon
- `0x29` is a question mark
- `0x67` is a comma
- `0x69` is an apostrophe
- `0x22` is a hyphen and is exported as `-`
- `0xB3` is a double quote, exported as `<QUOTE>`
- `0x1B` is an exclamation mark

Dialogue-surface control bytes that are currently confirmed:

- `0x09` inserts the stored player name
- `0x0A` is a newline
- `0x0E` marks the next page from the same speaker
- `0x03` marks a handoff to the next speaker

Observed but not yet named dialogue bytes are preserved in the exported corpus when they appear inside otherwise readable text. Current examples include `0x02` and `0x05`, which appear to act like pauses or delays but are not yet confirmed, so they remain untranslated for now.

Examples:

- `Heal` encodes to `32 4C 48 53`
- `Blaze` encodes to `2C 53 48 61 4C`
- `Flare` encodes to `30 53 48 59 4C`

Dialogue example from the opening scene:

- `Now then, <PLAYER_NAME>,`
- `attack me any way you like.`
- `Give it all you've got!`

The dialogue window also shows a speaker prefix such as `Varios:` when the scene calls for one. The exported surface CSV records the decoded text bytes we can see in ROM, and the prefix may appear in the decoded string when it is part of that surface.

The dialogue-surface export uses inline tags instead of raw newlines:

- `0x0A` becomes `<NEWLINE>`
- `0x0E` becomes `<PAGE_BREAK>`
- `0x03` becomes `<SPEAKER_BREAK>`

Characters outside the currently confirmed letter-and-space set should still be treated carefully until they are mapped explicitly.

## Pointer tables

The custom-encoded bank is referenced through pointer tables rather than by embedding every string directly in code.

The clearest confirmed table so far begins around `0x0056ED80`.

Confirmed entries:

- `0x0056ED90 -> 0x001DD802 -> Heal`
- `0x0056EDE0 -> 0x001DD875 -> Blaze`
- `0x0056EE5C -> 0x001DD946 -> Medical Herb`

 The current structured exports for these tables live in the split raw name CSVs under `research/raw/`, one file per entity type.

This means the working lookup path is at least:

1. an ID or index
2. a pointer table entry
3. a custom-encoded string in ROM
4. rendered menu text

## Safe editing rules

The first successful validation pass used in-place editing of an item name and confirmed that this approach works when the replacement stays within the original string budget.

### What is safe right now

- replacement that stays within the original byte budget
- testing on a copy of the ROM

The repository tooling now supports this same workflow directly through `patch-known-text`, `patch-text-at-offset`, and the entity rename commands. Entity rename commands default to the conservative path: longer replacements repoint by appending to the end of the copied ROM when possible, and only truly unpointable hits are skipped. `liberal` remains intentionally unsafe and may fall back to direct in-place writes when the conservative path would skip a reference. The broader pointer-rewrite path is still unstable and should be treated as an evolving mechanism until we finish verifying which references are safe to rewrite.

When a named-table replacement needs more room, the current tools append the new payload to the end of the copied ROM and repoint the relevant table entry there instead of guessing at internal free space. For bulk story rewrites, that repoint strategy is still considered unstable until we finish narrowing the rewrite targets to verified pointer references.
That is a good fit for emulator testing and copied-ROM workflows, but if we eventually target physical hardware or a flashcart we should verify that the enlarged image is still accepted.

The dialogue normalizer also auto-inserts `<PAGE_BREAK>` between groups of three visible rows when a replacement needs more room on screen. That keeps long dialogue rewrites readable without asking the caller to manually manage page breaks.

### What is not safe yet

- longer replacement without a repointed destination
- changing table structure without understanding the consuming code
- assuming every visible string uses the same bank or same lookup path

## Successful manual workflow

This is the current best practice for validating a text edit.

1. Identify the target string offset.
2. Encode the replacement string with `scripts/rom_text_tools.py`.
3. Patch only the string bytes in ImHex.
4. Keep the existing `0x00` terminator.
5. Save a test ROM copy.
6. Verify the result in mGBA.

This workflow already worked for an inventory item name and is a reliable first pass before broader automatic repointing work.

The script currently only supports replacement text that fits the known ROTDD letter-and-space codec and the current dialogue-box budget when it is doing literal in-place patching.

## Suggested breakpoint strategy

When tracing how the game resolves IDs into menu text, use both the string and its pointer-table entry.

Examples:

- `Medical Herb` string at `0x081DD946`
- `Medical Herb` pointer entry at `0x0856EE5C`
- `Blaze` string at `0x081DD875`
- `Blaze` pointer entry at `0x0856EDE0`

Useful capture fields when a breakpoint hits:

- PC
- LR
- R0 through R3
- whether the hit was on the pointer read or on the string read

## Lessons learned

- Blind RAM string searches were the wrong first tool for this text path.
- The ROM contains more than one text representation.
- Once a small piece of the custom codec was confirmed, the spell and item banks became easy to identify.
- The combination of ROM offset, pointer table, and emulator breakpoint is much more productive than trial-and-error text guessing.

## Open questions

- full punctuation and control-code coverage for the ROTDD codec
- exact boundaries of each text bank
- exact spell ID and item ID numbering used by the lookup tables
- the code path that resolves table entries into final rendered output
