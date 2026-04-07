# Shining Force: Resurrection of the Dark Dragon Reverse Engineering

This repository is a small public knowledge base and tooling project for reverse engineering Shining Force: Resurrection of the Dark Dragon on the Game Boy Advance.

## What is public here

- structured research data in `research/raw/`
- confirmed mechanics notes in `research/`
- package-backed tooling in `src/rotdd_tools/`
- ImHex artifacts in `imhex/`
- command-line entry scripts in `scripts/`
- contribution guidance in `CONTRIBUTING.md`

## What stays out of version control

- ROMs
- saves and savestates
- live Ghidra project data
- other local-only working material

Those files live under `ignore/`.

## Current focus

The current working artifacts are the structured address data, an ImHex pattern that has tested accurate so far, and a confirmed first pass on the game's text system.

Current confirmed leads:

- enemy names exist in a plain ASCII bank
- spells and item names exist in a custom single-byte text bank
- a pointer table around `0x0056ED80` resolves spell and item names
- conservative in-place edits are already validated on copied ROMs
- a generated text map now records known pointer-table entries in a reusable CSV
- a whole-ROM dialogue-like corpus can be exported to `research/raw/text-surfaces.csv`
- a narrower contiguous dialogue/script excerpt export remains available for known ROM ranges
- mapped text rows can be browsed with `list-known-text`
- mapped text rows can be patched safely with `patch-known-text`
- arbitrary ROM offsets can be patched with `patch-text-at-offset`
- additional ROTDD-style text runs can be scanned with `scan-rotdd-runs`
- a likely story or script text bank appears around `0x001765C0`
- confirmed dialogue punctuation and control bytes now round-trip in the surface CSV
- the combined surface CSV keeps ROM offset and decoded dialogue text together for easier human review and future CSV-driven patching
- the surface CSV quotes only the `decoded_text` field so it stays readable while preserving commas and inline tags inside the text cell
- the dialogue box is currently treated as a 35-character wide, 3-row surface for automatic wrapping

Start with `research/text-mechanics.md`, `research/text-table-map.md`, `research/text-surfaces.md`, `PROGRESS.md`, and `scripts/README.md` if you want to continue the text work.

For local script setup, either pass `--rom` directly when running a tool or create `scripts/rom_path.local.txt` with a repository-relative ROM path. If that file does not exist, the script can prompt for a path and save it for later runs.

`list-known-text` is the safest way to browse patch targets before you edit anything. Use `--table`, `--category`, `--contains`, and `--show-notes` to narrow the list.

`patch-text-at-offset` is the simplest CSV-driven write path when you already know a literal ROM offset. Pass the offset and replacement text as separate positional arguments, then add `--output` for a copied ROM or `--in-place` if you intentionally want to overwrite the source ROM. Quote the replacement when it contains spaces or punctuation. The tool will wrap on whole-word boundaries into at most three rows of 35 characters, trim trailing padding spaces if needed to stay within the original byte budget, and refuse to overflow into a different surface. If a short punctuated token would be orphaned at the end of a long line, the tool nudges it to the next line instead of splitting it. Page breaks reset the three-row budget for the next page.

## License

This repository is released under the MIT License for the original content included here. That does not grant rights to the underlying game, its ROM, or other third-party intellectual property.

This repository exists for research and preservation work only. I do not endorse or support the illegal sharing or distribution of copyrighted software.

## Credits

- Explicit thanks to ElfenTaiga from Shining Force Central for sharing the ImHex pattern artifact now recorded in this repository.
