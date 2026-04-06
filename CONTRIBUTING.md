# Contributing

Keep this repository useful to others.

## Rules

- Do not commit ROMs, saves, savestates, or live Ghidra project data.
- Keep local-only material under `ignore/`.
- Put structured public data in `research/raw/`.
- Put confirmed writeups and mechanics notes in `research/`.
- Put reusable package code in `src/rotdd_tools/`.
- Keep lightweight public entry scripts in `scripts/`.
- Prefer evidence over guesswork.
- Keep changes small and easy to review.
- Write for a human reader who may not share your current context.

## Notes

- Use explicit addresses, offsets, and reproduction details when available.
- Separate confirmed findings from open questions.
- If a claim depends on a tool export or emulator observation, say so.
- When adding or revising scripts, prefer clear function boundaries, direct naming, and comments that explain intent rather than narrating every line.
- Keep generic GBA helpers separate from ROTDD-specific offsets, table counts, and codec rules.
- If a generated table is partial, label that clearly in both code and docs.
- When adding browse or patch commands, make the safe path the default and require explicit selectors for ambiguous rows.
