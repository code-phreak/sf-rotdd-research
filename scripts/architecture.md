# Tooling Architecture

This repository now treats the Python tooling as the beginning of a maintainable application surface, not a pile of one-off utilities.

## Current layout

- `scripts/rom_text_tools.py`
  Thin command-line wrapper that keeps the public workflow stable.
- `src/rotdd_tools/gba.py`
  Generic helpers for GBA pointer math, byte scanning, and byte-view formatting.
- `src/rotdd_tools/paths.py`
  Repository path conventions, including the local ROM reference file used by this project.
- `src/rotdd_tools/rotdd.py`
  Game-specific codec rules, confirmed pointer-table coordinates, and other hardcoded ROTDD evidence.
- `src/rotdd_tools/catalog.py`
  Export logic that turns known pointer tables into structured research artifacts.
- `src/rotdd_tools/editing.py`
  Conservative patch helpers for same-length edits in known text tables.
- `src/rotdd_tools/models.py`
  Named data structures for table metadata and exported rows.

## Design rule

Keep the boundary between reusable code and game-specific evidence visible.

### Good candidates for generic reuse

- GBA pointer math
- byte-pattern search
- generic terminated-string readers
- table-walking utilities
- CSV or JSON export helpers

### ROTDD-specific by definition

- custom text codec rules
- known table offsets like `0x0056ED80`
- table counts that were derived from this ROM
- assumptions about spell, item, or class naming
- local repository conventions such as `scripts/rom_path.local.txt`

## Why this matters

If the project later grows into a desktop UI, web service, or a broader GBA research toolkit, the low-level reusable pieces should already be separated from the ROTDD-specific facts they operate on.

That lets us extend the code without rewriting everything and without blurring confirmed game evidence into generic library behavior.
