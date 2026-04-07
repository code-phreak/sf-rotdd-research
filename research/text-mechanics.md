# Text Mechanics

This note records the current confirmed mechanics behind ROM text lookup and in-place text editing.

It is written for practical use. Every point here is meant to help someone find game text, understand what they are looking at, and make safe edits without stumbling into avoidable corruption.

## Confirmed text banks

Two different text representations are currently confirmed in the ROM.

### Plain ASCII bank

Enemy and character names appear in plain ASCII around `0x001E0700`.

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

## Confirmed codec rules

The currently confirmed parts of the ROTDD text codec are enough to decode and patch many menu strings safely.

- `0x00` terminates a string
- `0x10` is a space
- uppercase letters decode as `byte + 0x16`
- lowercase letters decode as `byte + 0x19`
- `0x23` is a period
- `0x25` is a colon
- `0x29` is a question mark
- `0x67` is a comma
- `0x69` is an apostrophe
- `0x1B` is an exclamation mark

Dialogue-surface control bytes that are currently confirmed:

- `0x09` inserts the stored player name
- `0x0A` is a newline
- `0x0E` marks the next page from the same speaker
- `0x03` marks a handoff to the next speaker

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

The current structured export of these tables lives in `research/raw/text-map.csv`.

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

The repository tooling now supports this same conservative workflow directly through `patch-known-text` and `patch-text-at-offset`, but it still keeps replacements within the original byte budget unless you deliberately opt into `--in-place`.

### What is not safe yet

- longer replacement without repointing
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

This workflow already worked for an inventory item name and is a reliable first pass before deeper repointing work.

The script currently only supports replacement text that fits the known ROTDD letter-and-space codec and the current dialogue-box budget.

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
