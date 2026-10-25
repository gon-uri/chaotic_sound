# 0008. v1 modulators: a separate entity, five shapes, loop or once

- Status: Accepted (from the owner's answers, 2026-10-25)
- Date: 2026-10-25

## Context

The owner wants simple modulators first, with richer options later.

## Decision

- Modulators and dynamical boxes are **separate entities**. Dynamical boxes cannot be used as
  modulators in v1, because they work in a different frequency range.
- Output is always in [0, 1].
- Shapes: sine, triangle, square (duty ½), ramp up, ramp down. Exact definitions are in
  spec §4.1.
- A `mode` toggle chooses `loop` or `once`. One duration setting, `period_s` (seconds), is both
  the loop period and the length of the once-envelope.

## Consequences / future (on the roadmap)

- Later modulator properties: duty cycle, min/max, phase offset, retrigger, tempo sync.
- Later chaotic modulators: a slow chaotic system as an LFO.
- Later pitch input on dynamical boxes.
