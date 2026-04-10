# Reverse Engineering Log

This document tracks the reverse-engineering trail for ROTDD stat handling and related initialization logic.
It is meant to be a living human reference, not a historical notebook dump.

## Goal

We want a ROM-side way to patch arbitrary character stats before first load, and later enemy stats with the same general workflow.
The current evidence points to a table-driven growth and load path, but we still do not have a verified editable stat table yet.

## What Is Confirmed

### Live stat fields in RAM

The following live RAM fields have been confirmed with watchpoints.

- `0x020002C4` = Max HP for Max
- `0x02000274` = Max Attack for Max
- `0x02001228` = Current MP for Tao

The observed live-unit block for Max includes stat bytes that align with the expected fields:

- `0x02000260`
- `0x02000268`

The current layout strongly suggests a structured unit block in RAM, not random state.

### Persistent behavior

Some live fields persist across save and restart.

Confirmed persistent fields:

- Max current HP
- Max max HP
- Max current MP
- Max max MP
- Max EX

This proves that at least part of the live-unit block is written into the game save and restored on load.

## Current Load / Init Chain

The current best-known chain for the Max stat load path is:

1. `0x0802B200`
2. `0x0802B1D4`
3. `0x08029F28`
4. `0x0802A090`
5. `0x08036B14`
6. `0x08036B94`
7. `0x08079754`
8. `0x081E88E0`

The source-builder branch also appears to pass through the slot dispatcher around `0x08029A60`, the slot-copy routine at `0x08029898`, and a stat-type switch at `0x08029598`. The `0x08029598` area currently looks like the most likely place where the code chooses which stat or growth slot is being assembled, but that still needs one more targeted inspection to confirm.

The latest disassembly confirms that `0x08029598` is a wide stat/growth switch table with many cases. The later cases at `0x080297D8` and the helper calls around `0x08029984` / `0x08029898` appear to be handling slot population and stat-specific copy logic, which is a strong sign that we have finally reached the stat-selection layer rather than just generic loader glue.

### Meaning of each layer

- `0x0802B200` and nearby code
  - final load and clamp wrapper
  - copies values into live RAM
  - clamps fields to legal bounds

- `0x08029F28`
  - builds a source structure in RAM
  - fills bytes that later feed the live stat block

- `0x0802A090`
  - source builder for the growth / stat seed path
  - uses helper lookups and table-style comparisons

- `0x08036B14`
  - selector routine
  - chooses one of several growth cases

- `0x08036B94`
  - growth math routine
  - uses the selector result and per-case parameters

- `0x08079754`
  - interpolation helper
  - reads from the ROM growth table

- `0x081E88E0`
  - ROM growth-data region
  - begins with function-pointer-like entries and then data blocks

## Important Addresses

### RAM

- `0x02000260` - Max live unit block region
- `0x02000268` - Max stat block region
- `0x02000274` - Max Attack live field
- `0x020002C4` - Max HP live field
- `0x03007934` - runtime source block seen in load traces

### ROM / code

- `0x0802B23C` - final Max HP clamp/store site
- `0x0802BF10` - final Max Attack clamp/store site
- `0x0802B1D4` - call site that feeds the loader chain
- `0x08029F28` - source-block construction routine
- `0x0802A090` - growth source builder
- `0x08036B14` - growth selector
- `0x08036B94` - growth math
- `0x08079754` - interpolation / table lookup helper
- `0x081E88E0` - ROM growth table region

## Growth / Stat Observations

### Max HP variation at boot

Max HP was observed to start at both `12` and `13` in different fresh-boot traces.
This does not look random.

The likely explanation is that the load/init chain is selecting different source-state moments or source fields, rather than choosing a random HP value.

### Max Attack trace

Max Attack final write was observed at `0x0802BF10`.
That write clamps the result to `99` and stores it into the live block.

### Selector and growth routine behavior

`0x08036B14` and `0x08036B94` show a table-driven growth system.
The code paths select among small case indices, then run interpolation math on ROM data.

`0x08079754` reads from `0x081E88E0` and performs interpolation between table points.

### Max level-up sample: level 2 -> 3

We now have one concrete growth sample for Max from level 2 to 3 on the same run.

Observed stat gains:

- Attack +1
- Defense +1
- Speed +2
- Max HP +2
- Max MP +1

The breakpoint still lands at `0x08036B94`, and the growth context object at `0x03007B20` is the source we want to keep tracking.
The live registers at the breakpoint are stable enough to keep using as a reference point:

- `r0 = 0x03007B20`
- `r1 = 0x00000009`
- `r4 = 0x0200036C`
- `r6 = 0x02022954`
- `r7 = 0x02000260`
- `r9 = 0x02022830`
- `r15 = 0x08036B96`

This gives us a controlled growth trajectory sample without needing a full-ROM dump or broad playtest sweep.

### Broader source-block capture

A broader RAM slice around the loader path was captured from `0x030078A0` through `0x03007ABF`.
That region is dominated by a long run of `0x99` padding / sentinel-like bytes at the front, then resolves into the same structured loader object we have already been tracking around `0x03007934`.

The important part of the capture is that the source object is not isolated in RAM on its own; it sits inside a larger live working area that contains repeated padding, pointer-like values, and the same growth/init metadata we saw in the smaller dumps.
That makes `0x03007934` a useful anchor, but not a complete standalone table.

### Equipment side effect from ROM stat patching

When the ROM-side stat bytes around `0x081E0A30` and `0x081E0A44` were patched for proof testing, Max's default equipment also changed.

Observed effect:

- Max's starting weapon became the `Miracle Mace`
- he was expected to start with the `Short Sword`

This is important because it suggests the edited ROM row may be influencing a broader unit-init bundle than just the visible stat line. We should keep this in mind when we separate stat bytes from equipment bytes later.

### Byte-to-stat proof map for the editable row

The following one-byte probes have now been confirmed on the editable row that begins at `0x081E0A30`:

- `0x001E0A34` -> Attack
- `0x001E0A35` -> Defense
- `0x001E0A36` -> Agility
- `0x001E0A37` -> Movement
- `0x001E0A38` does not appear to change a visible stat on its own in the current test set
- `0x001E0A39` -> Magic Resistance
- `0x001E0A3A` -> Max HP
- `0x001E0A3B` -> Max MP

Working note:

- EX appears to be initialized differently, or not reflected through the simple visible-stat probes at game start
- Level is safe to ignore for the current goal and does not need to be mapped before we finish the stat patch workflow

Current tool surface:

- `character patch stat <stat> Max <value>` now targets the confirmed proof row directly
- supported Max stats are `Attack`, `Defense`, `Agility`, `Movement`, `Magic Resistance`, `Max HP`, and `Max MP`
- the row still appears to contain equipment-related init data further to the right, so we should keep the later bytes separate from the core stat bytes when we generalize the workflow

The earlier multi-byte proof patch at `0x001E0A3C` also changed HP, MP, EX, Magic Resistance, and default equipment, which means the later part of the row still contains additional live-init fields beyond the basic battle stats.

### Raw ROM table regions

Two ROM regions now look like the real table-backed source data feeding the accessor chain:

- `0x081E0A30`
- `0x081E0CC8`

Both regions contain tightly packed byte/word data that the tiny helper accessors in `0x08036A10` / `0x08036AFC` are clearly reading from.
They do not yet look like simple human-readable stat records, but they do look like the real ROM-side data blocks behind the growth/source-object assembly path.

At this point, the most likely interpretation is:

- `0x081E0A30` is one table family used by the stat/source builder
- `0x081E0CC8` is a second table family or parameter block used by the same builder

We still need one more targeted mapping step before we can assign exact meanings to the rows.

### Source-builder slot progression

The source-builder path at `0x0802A2B0` was observed stepping through Max's live block with a clear `0x148` stride between slots:

- `r1 = 0` with `r0 = 0x02000260`
- `r1 = 1` with `r0 = 0x020003A8`
- `r1 = 2` with `r0 = 0x020004F0`
- `r1 = 3` with `r0 = 0x02000638`

That strongly suggests the builder is iterating through four structured slots in the live unit block, which lines up with the earlier assumptions about a fixed per-character stride and a slot-based source assembly process.

The same run also confirmed that the source-builder hit occurs immediately after the Max HP watchpoint writes `0x020002C4`, so the slot-0 builder state is directly tied to the Max HP initialization path we care about for ROM-side stat editing.

The ROM lookup helper hit at `0x080369FC` now gives us the first concrete ROM table anchor for that slot-0 path:

- `r1 = 0` resolves to ROM base `0x081E0A30`
- the helper uses a `20-byte` stride per row (`0x14` bytes)

That means slot 0 is not just a live RAM concept; it is backed by a specific row in the ROM table family beginning at `0x081E0A30`.

Two adjacent ROM rows have now been captured from that family:

- `0x081E0A30`: `000000010605040603050C082F200500E40F1E08`
- `0x081E0A44`: `010103020505070803000B0044000000F80F1E08`

These rows are both exactly `20` bytes long and strongly look like structured records rather than flat stat bytes. The fact that adjacent rows differ in the leading fields but share the trailing `F80F1E08` pattern is another sign that we are looking at a ROM-side table family with repeated record layout, not an ad hoc scratch buffer.

### Attack case body

The Attack watchpoint at `0x02000274` resolves into a case body beginning at `0x0802BF04`.
That body increments a live field at `[r4, #12]`, which means the attack-related path is definitely table- and struct-driven rather than a hardcoded literal write.
The same case family also includes capped increments for nearby fields at offsets `16`, `20`, `24`, `28`, `32`, `36`, `40`, `44`, `48`, and `52`.
The tail of the same switch block is no longer the core stat increment family:

- `0x0802BFCA` to `0x0802BFE8` manipulates flag bytes at `+73` and `+74`
- `0x0802BFEA` to `0x0802C1D6` is a separate selector/validation path that branches through other helper routines

So the clean label for this area is:

- `0x0802BF04` through `0x0802BFB8` = stat increment cases
- `0x0802BFCA` onward = non-core flag / validation logic

## What We Still Do Not Have

- a verified editable ROM table for starting stats
- a direct mapping from a character record to a specific editable ROM stat slot
- a confirmed enemy stat table implementation
- a confirmed spell editing table

## Best Next Steps

The most useful next steps are:

1. map one known character all the way from source table to live stat field
2. identify which data entry in `0x081E88E0` feeds that character
3. confirm whether modifying that entry changes the loaded stat before first gameplay
4. repeat for one more stat field, such as Attack

## Useful Testing Notes

- use mGBA watchpoints on the final live stat fields
- capture the final write site `r15`
- disassemble the caller chain above the final store
- keep the tests small and focused on one stat at a time

## Working Hypothesis

The game uses a ROM-based growth system with selector routines, interpolation helpers, and a runtime source block that is copied into the live unit struct on load.
If we can map that source block back to a specific table entry, we should be able to build ROM-side stat editing safely.
