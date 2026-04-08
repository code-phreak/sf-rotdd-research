# Roadmap

This document is the living progress log and near-term roadmap for the project.
It tracks what is already confirmed, what is currently implemented, and what we
plan to tackle next.

## Current Focus

- story dialogue and broader text manipulation
- conservative character-attribute editing
- a more API-like command structure for future game edits

## What Is Confirmed

- class names exist in the first slice of a confirmed ROTDD text table after the item names
- enemy names exist in the second slice of that same table and currently run through `Soul Eater`; the confirmed export now covers 79 enemy rows
- item names can now be browsed with `list-item-names`
- item names can be renamed safely with `patch-item-name`
- the newer `item <name> rename <replacement>` command shape is the preferred API-style entry point, with `patch-item-name` kept as a compatibility alias
- dialogue-speaker names can now be browsed with `list-npc-names`
- dialogue-speaker names can be renamed safely with `patch-npc-name`
- the newer `npc <name> rename <replacement>` command shape is the preferred API-style entry point, with `patch-npc-name` kept as a compatibility alias
- NPC extraction treats playable names, enemies, classes, and items as higher-priority categories and excludes them from the NPC map
- spell and item names exist in a custom single-byte text bank
- the canonical character-name table is a plain ASCII pointer table at `0x0056F578`
- a pointer table around `0x0056ED80` resolves spell and item names
- a whole-ROM dialogue-like corpus can be exported to `research/raw/text-surfaces.csv`
- a narrower contiguous dialogue/script excerpt export remains available for known ROM ranges
- mapped text rows can be browsed with `list-known-text`
- mapped text rows can be patched safely with `patch-known-text`
- character names can be browsed with `list-character-names`
- character names can be renamed safely with `patch-character-name`
- the newer `character <name> rename <replacement>` command shape is the preferred API-style entry point, with `patch-character-name` kept as a compatibility alias
- class names can now be browsed with `list-class-names`
- class names can be renamed safely with `patch-class-name`
- the newer `class <name> rename <replacement>` command shape is the preferred API-style entry point, with `patch-class-name` kept as a compatibility alias
- enemy names can now be browsed with `list-enemy-names`
- enemy names can be renamed safely with `patch-enemy-name`
- the newer `enemy <name> rename <replacement>` command shape is the preferred API-style entry point, with `patch-enemy-name` kept as a compatibility alias
- item names can now be browsed with `list-item-names`
- item names can be renamed safely with `patch-item-name`
- the newer `item <name> rename <replacement>` command shape is the preferred API-style entry point, with `patch-item-name` kept as a compatibility alias
- dialogue-speaker names can now be browsed with `list-npc-names`
- dialogue-speaker names can be renamed safely with `patch-npc-name`
- the newer `npc <name> rename <replacement>` command shape is the preferred API-style entry point, with `patch-npc-name` kept as a compatibility alias
- arbitrary ROM offsets can be patched with `patch-text-at-offset`
- additional ROTDD-style text runs can be scanned with `scan-rotdd-runs`
- the dialogue codec currently supports punctuation, control tags, visible digits, and whole-name replacements in a CSV-friendly format
- the dialogue box is currently treated as a 35-character wide, 3-row surface for automatic wrapping

## Near-Term Roadmap

### 1. Character rename API polish

- keep `character <name> rename <replacement>` as the main forward-looking command shape
- keep `patch-character-name` as a stable alias for existing scripts and muscle memory
- add more character actions later without breaking the rename workflow

### 2. Raw save-file patching

- add support for patching the game's raw battery save format, not emulator savestates
- document that savestates are emulator snapshots and are not a stable format to target generically
- keep save patching separate from ROM patching so both workflows stay understandable

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
