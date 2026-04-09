# Text Surfaces

This note is the first pass at inventorying the ROM's text-like data surfaces.

It separates confirmed evidence from likely story or script text so future work can stay precise.

## Confirmed Surfaces

### Plain ASCII name bank

Character names exist in a plain ASCII bank around `0x001E0700`.

This surface is useful for simple searches, but it is not the same thing as the story dialogue system.

### Class-name table

Class names exist in the first slice of the partial ROTDD table around `0x0056F000`.

This surface currently behaves like a table-driven name block rather than freeform dialogue, and it is now exposed through the class rename workflow.

### Enemy-name table

Enemy names exist in the second slice of the same partial ROTDD table around `0x0056F09C`.

This surface currently behaves like a table-driven name block rather than freeform dialogue, and it is now exposed through the enemy rename workflow.

The confirmed enemy slice currently runs through `Soul Eater`.

### Item-name table

Item names are also exposed through the split raw name exports and the dedicated item-name workflow.

This is not a dialogue surface, but it is part of the same general family of visible labels that we want the tooling to edit cleanly.

### ROTDD custom-encoded menu bank

Spell names, item names, and related menu labels exist in a custom single-byte bank around `0x001DD7E3`.

Confirmed examples include:

- `Soul Eater`
- `Heal`
- `Medical Herb`
- `Guardiana`

This surface is currently the best-understood ROTDD text bank and is already exposed through the known-table tooling.

### Plain ASCII debug or menu text

There is also a clearly readable plain ASCII surface around `0x00079960`.

Examples include:

- `SHINING FORCE ADVANCE`
- `SCENE SELECT`
- `MESSAGE TEST`
- `VISUAL VIEWER`

This looks like system/debug/menu text rather than in-game story dialogue.

## Candidate Story Or Script Text

The strongest new discovery so far is a long dialogue text bank around `0x001765C0`.

The currently exported opening excerpt begins at `0x001765DC`, which includes the first visible speaker prefix `Varios:`.

The text in that region is not plain ASCII in the ROM dump. It uses the same basic ROTDD letter-and-space mapping that we already know from the spell and item tables, plus the punctuation and dialogue control bytes that are currently confirmed in `research/text-mechanics.md`.

The region contains consecutive English lines that read like dialogue or script text, for example:

- `Now then`
- `What are you doing`
- `King of Guardiana`
- `A wretch like you`
- `The Gate of the Ancients`

The strings continue for many pages and include conversational exchanges, mission instructions, and location references.

The current evidence strongly suggests a story or script text surface, but the exact engine behavior still needs verification.

### Known Dialogue Windows

The current corpus review points to a few reliable dialogue windows that are useful when checking story text and NPC-speaker extraction:

- Priest general dialogue: `0x001D276F` to `0x001D2E72`
- Merchant general dialogue: `0x001D2E72` to `0x001D3536`
- Merchant-related later dialogue: `0x001DC487` to `0x001DD0D5`

The first two ranges meet at the same boundary. The later merchant block looks related, but it may be a separate scene bank, so both ranges are worth keeping for now.

### Early observations

- The bank appears to be a contiguous encoded text run rather than plain ASCII.
- The visible words decode with the confirmed ROTDD letter, punctuation, and control mapping, which is a strong sign that this is part of the game's text system.
- Direct GBA pointer searches against sample offsets in the region returned no hits, so the lookup method may be index-based, relative, or stored in a different data structure.
- The region is a better candidate for dialogue work than the menu/debug text because it contains long conversational passages.

## What Still Needs Manual Classification

Before we treat the `0x001765C0` region as fully mapped dialogue, we should confirm:

- whether it is main story dialogue, tutorial text, or another script-driven text surface
- how the game indexes or references the strings
- whether the region has scene boundaries or speaker metadata nearby
- whether the text is reused across multiple scenes

## Next Inventory Steps

1. classify a few sample strings with emulator context
2. locate the table or script structure that references the dialogue bank
3. map a small confirmed excerpt end to end
4. document the control codes or formatting rules once they are confirmed

## CSV Layout

The current `export-text-surface-corpus` command writes one combined CSV to `research/raw/text-surfaces.csv`.

Current columns:

- `source_kind`
- `rom_offset`
- `type`
- `decoded_text`

`source_kind` distinguishes confirmed ROTDD-script rows from plain ASCII surface rows so future rename and patch workflows can make the right encoder choice.
`type` comes from the current corpus review notes, and rows that are not called out there default to `unsorted`.

The file intentionally stays text-only. Unknown bytes remain visible as placeholder tokens like `<XX>` until we map them.

The `decoded_text` column is always quoted. That keeps the file readable while still protecting commas and inline tags inside the text cells.

For larger edit passes, `text-surface export template` can filter one `type` value from `research/raw/text-surfaces.csv` and write a two-column template to `ignore/temp/`. The template writer quotes `decoded_text` the same way the corpus export does. `text-surface patch file` compares that template against the current corpus and only rewrites the rows whose text actually changed, using EOF repointing when a safe pointer target exists. `unsorted` rows have been reliable so far when the replacement stays the same length or shorter, but multi-line template rewriting is still experimental.

`text-surface patch file` can also regenerate the reference corpus CSV after patching when you pass `--refs rewrite`. If you pass `--refs keep`, the corpus file is left alone. If you omit the tag, the tool explains the choice once, prompts for it, and can remember the answer locally.

Current dialogue-token conventions in the export:

- `<NEWLINE>` marks an in-box line break
- `<PAGE_BREAK>` marks the next page of the same speaker
- `<SPEAKER_BREAK>` marks a speaker handoff
- `<PLAYER_NAME>` marks the stored player-name insertion point
- `<QUOTE>` marks a double quote
- `…` is accepted in editable CSVs as shorthand for `...` and is normalized to the period bytes the ROM uses
- visible digits `0` through `5` are decoded from the surface codec rather than left as placeholders
- observed-but-unnamed in-dialogue bytes are preserved as placeholder tags when they occur inside readable rows, so the corpus stays contiguous without claiming a meaning we have not confirmed yet
- the current read on `0x02` and `0x05` is that they behave like pauses or delays, but that is still unconfirmed, so they remain untranslated in the corpus for now
- `0x22` is a hyphen and now decodes as `-`
- the wrapper treats short punctuation-plus-quote tails as a unit so quote runs stay attached to the word they belong to during automatic wrapping
- the class-name table around `0x0056F000` is treated as a separate visible-name source, not as a monster roster list
- the enemy-name table around `0x0056F09C` is treated as a separate visible-name source, not as a monster roster list
- the dialogue corpus also doubles as the extraction source for visible NPC/speaker names, which we now browse separately from the playable roster; NPC extraction is precedence-based, so playable names, enemies, classes, and items are filtered out first and the CSV keeps only the first mention of each remaining NPC name

The dialogue window shows a speaker prefix like `Varios:` when the scene calls for one. The current CSV captures the decoded ROM surface as it appears in bytes, so speaker names may appear in the decoded text when they are part of the underlying text run.

If we already know a small ROM window, `export-text-surface-map` is still available for a narrower contiguous excerpt. The whole-ROM corpus is the better starting point for discovery, while the narrow export is the better starting point for exact scene mapping.

The corpus exporter also makes a second conservative pass for word-like plain ASCII runs so names, places, items, and similar readable blocks can be sorted out later without mixing in too much binary noise.

The dialogue/script pass is intentionally stricter and keeps only rows with actual word separation, so we do not fill the corpus with marker-only or alphabet-soup fragments.

`patch-text-at-offset` is the companion write command for when you already know the literal ROM offset for a line and want to replace it while staying within the original byte budget.
Pass the address and replacement text as separate positional arguments, and quote the replacement when it contains spaces or punctuation so the shell keeps it together as one argument.
The command will automatically wrap text on whole-word boundaries to the observed 32-character line width when no explicit `<NEWLINE>` tags are provided, trim trailing padding spaces when it needs to fit the original byte budget, and refuse to expand beyond the three visible rows on a single page.
If a short punctuated token would be orphaned at the end of a long line, the command nudges it to the next line instead of splitting it.

Patch-time reminder:

- replacements still need to fit within the original byte budget for now
- shorter replacements are padded with spaces on the right so the line fills the visible width
- `<PAGE_BREAK>` resets the visible-row budget for the next page
- when the tool inserts line breaks automatically, it prints a warning and the result should be reviewed on screen
- `--in-place` exists for all write commands, but it is unsafe because it overwrites the source ROM
- longer replacements need future repointing support
- the CSV is descriptive first and editable second
