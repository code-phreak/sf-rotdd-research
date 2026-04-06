# Shining Force: Resurrection of the Dark Dragon Reverse Engineering

This repository is a small public knowledge base for reverse engineering Shining Force: Resurrection of the Dark Dragon on the Game Boy Advance.

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
- same-length in-place edits are already validated
- a generated text map now records known pointer-table entries in a reusable CSV
- mapped text rows can be browsed with `list-known-text`
- mapped text rows can be patched safely with `patch-known-text`

Start with `research/text-mechanics.md`, `research/text-table-map.md`, and `scripts/README.md` if you want to continue the text work.

For local script setup, either pass `--rom` directly when running a tool or create `scripts/rom_path.local.txt` with a repository-relative ROM path. If that file does not exist, the script can prompt for a path and save it for later runs.

## License

This repository is released under the MIT License for the original content included here. That does not grant rights to the underlying game, its ROM, or other third-party intellectual property.

## Credits

- Explicit thanks to ElfenTaiga from Shining Force Central for sharing the ImHex pattern artifact now recorded in this repository.
