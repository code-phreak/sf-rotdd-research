# Text Surfaces

This note is the first pass at inventorying the ROM's text-like data surfaces.

It separates confirmed evidence from likely story or script text so future work can stay precise.

## Confirmed Surfaces

### Plain ASCII name bank

Enemy and character names exist in a plain ASCII bank around `0x001E0700`.

This surface is useful for simple searches, but it is not the same thing as the story dialogue system.

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

- `row_index`
- `rom_offset`
- `decoded_text`

The file intentionally stays text-only. Unknown bytes remain visible as placeholder tokens like `<XX>` until we map them.

Only the `decoded_text` column is quoted. That keeps the file readable while still protecting commas and inline tags inside the text cell.

Current dialogue-token conventions in the export:

- `<NEWLINE>` marks an in-box line break
- `<PAGE_BREAK>` marks the next page of the same speaker
- `<SPEAKER_BREAK>` marks a speaker handoff
- `<PLAYER_NAME>` marks the stored player-name insertion point

The dialogue window shows a speaker prefix like `Varios:` when the scene calls for one. The current CSV captures the decoded ROM surface as it appears in bytes, so speaker names may appear in the decoded text when they are part of the underlying text run.

If we already know a small ROM window, `export-text-surface-map` is still available for a narrower contiguous excerpt. The whole-ROM corpus is the better starting point for discovery, while the narrow export is the better starting point for exact scene mapping.

The corpus exporter also makes a second conservative pass for word-like plain ASCII runs so names, places, items, and similar readable blocks can be sorted out later without mixing in too much binary noise.

The dialogue/script pass is intentionally stricter and keeps only rows with actual word separation, so we do not fill the corpus with marker-only or alphabet-soup fragments.

`patch-text-at-offset` is the companion write command for when you already know the literal ROM offset for a line and want to replace it while staying within the original byte budget.
Pass the address and replacement text as separate positional arguments, and quote the replacement when it contains spaces or punctuation so the shell keeps it together as one argument.
The command will automatically wrap text on whole-word boundaries to the observed 35-character line width when no explicit `<NEWLINE>` tags are provided, trim trailing padding spaces when it needs to fit the original byte budget, and refuse to expand beyond the three visible rows on a single page.
If a short punctuated token would be orphaned at the end of a long line, the command nudges it to the next line instead of splitting it.

Patch-time reminder:

- replacements still need to fit within the original byte budget for now
- shorter replacements are padded with spaces on the right so the line fills the visible width
- `<PAGE_BREAK>` resets the visible-row budget for the next page
- when the tool inserts line breaks automatically, it prints a warning and the result should be reviewed on screen
- `--in-place` exists for all write commands, but it is unsafe because it overwrites the source ROM
- longer replacements need future repointing support
- the CSV is descriptive first and editable second
