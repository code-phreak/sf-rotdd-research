# Roadmap

This document is the living roadmap for the project.
It tracks what is already confirmed, what is currently implemented, and what we
plan to tackle next.

## Current Focus

- story dialogue and broader text manipulation
- conservative character-attribute editing
- a more API-like command structure for future game edits
- enemy rename is in active testing while broad repoint behavior is still being verified

## What Is Confirmed

- class names exist in the first slice of a confirmed ROTDD text table after the item names
- enemy names exist in the second slice of that same table and currently run through `Soul Eater`; the confirmed export now covers 79 enemy rows
- item names can now be browsed with `item list names`
- item names can be renamed safely with `item patch name <current> <replacement>`
- dialogue-speaker names can now be browsed with `npc list names`
- dialogue-speaker names can be renamed safely with `npc patch name <current> <replacement>`
- NPC extraction treats playable names, enemies, classes, and items as higher-priority categories and excludes them from the NPC map
- spell and item names exist in a custom single-byte text bank
- the canonical character-name table is a plain ASCII pointer table at `0x0056F578`
- a pointer table around `0x0056ED80` resolves spell and item names
- a whole-ROM dialogue-like corpus can be exported to `research/raw/text-surfaces.csv`
- a narrower contiguous dialogue/script excerpt export remains available for known ROM ranges
- mapped text rows can be browsed with `list-known-text`
- mapped text rows can be patched safely with `patch-known-text`
- character names can be browsed with `character list names`
- character names can be renamed safely with `character patch name <current> <replacement>`
- class names can now be browsed with `class list names`
- class names can be renamed safely with `class patch name <current> <replacement>`
- enemy names can now be browsed with `enemy list names`
- enemy names can be renamed safely with `enemy patch name <current> <replacement>`
- item names can now be browsed with `item list names`
- item names can be renamed safely with `item patch name <current> <replacement>`
- dialogue-speaker names can now be browsed with `npc list names`
- dialogue-speaker names can be renamed safely with `npc patch name <current> <replacement>`
- arbitrary ROM offsets can be patched with `patch-text-at-offset`
- additional ROTDD-style text runs can be scanned with `scan-rotdd-runs`
- the dialogue codec currently supports punctuation, control tags, visible digits, and whole-name replacements in a CSV-friendly format
- the dialogue box is currently treated as a 35-character wide, 3-row surface for automatic wrapping

## Near-Term Roadmap

### 0. Pointer repoint safety for large bulk edits

- decide how the tool should identify verified pointer references before rewriting them
- stop treating raw byte matches as proof of a real text pointer when broad template patching repoints to EOF
- keep the current broad repoint path marked as unstable until we can prove it is safe for full-story rewrites
- prefer a verified-pointer list or an explicit map over whole-ROM pointer scans when we revisit this

### 1. Character rename API polish

- keep `character patch name <current> <replacement>` as the main forward-looking command shape
- add more character actions later without breaking the rename workflow

### 2. Raw save-file patching

- add support for patching the game's raw battery save format, not emulator savestates
- document that savestates are emulator snapshots and are not a stable format to target generically
- keep save patching separate from ROM patching so both workflows stay understandable
- note that appended repoints can enlarge a ROM image, so hardware and flashcart validation may need a separate compatibility check

### 3. Class and enemy names and other visible names

- extend the name tools to class and enemy labels after the playable roster is stable
- keep the same whole-name matching rules so substring rewrites do not happen
- continue using conservative repointing for longer replacements

### 4. Item names and NPC names

- extend the name tools to item names using the same command shape as the roster workflows
- extract NPC/speaker names directly from dialogue text and keep them browsable as a separate map
- keep the same whole-name matching rules so substring rewrites do not happen
- continue using conservative repointing for longer replacements

### 5. Character attributes and stats

- add broader item and NPC editing if the command surface proves stable
- add stat editing
- add other attribute groups once their canonical sources are mapped

## Verification Notes

When testing patched ROMs in the emulator:

- prefer a fresh boot or a freshly reloaded in-game save
- do not rely on an old savestate when checking visible UI
- if a result looks stale, confirm whether the emulator restored cached memory instead of reading the patched ROM
