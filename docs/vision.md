# Vision

## One sentence

A visual, playful sound-making tool in the browser, built from chaotic dynamical systems, that
gets mathematicians making music and musicians learning mathematics.

## Goals (in priority order)

1. **Education.** Spark interest in dynamical systems theory and its history. Every system has
   a "Learn more" page: a 3D view of the attractor, its equations, the parameter you are
   moving, its properties, who discovered it, when and why.
2. **Creativity.** Make it easy and fun to get interesting sounds by patching boxes together.
3. **Bridge two audiences.**
   - People coming from math, physics or engineering: an invitation to music and creativity.
   - People coming from music: an invitation to math, chaos and its history.

## Principles

- **Hear the math.** Map mathematical ideas onto audible ones. Time rescaling sets the pitch;
  moving a parameter is forcing, which changes the timbre; sensitivity to initial conditions
  makes two identical boxes drift apart.
- **Normalized and forgiving.** Every knob runs from 0 to 1, and no setting should blow up or
  hurt your ears. That is why parameter ranges are curated and the output has safety limits.
- **Scientifically honest.** Numbers come from reproducible analysis (`lab/`), facts on the
  learning pages are sourced, and simplifications are labeled as such.
- **Modular code.** New box types, systems and engines can be added without rewriting what
  exists.
- **Simple stack.** State of the art, but no more machinery than needed.

## Non-goals (for now)

- Competing with professional synthesizers or DAWs.
- Accounts, cloud storage or social features (possible later as optional services).
- Native desktop or mobile apps.

## Audience sketches

- *Ana, physics student*: knows Lorenz from a course and has never made music. She drops in a
  Lorenz box, hears it, and sweeps ρ to discover how the sound reacts.
- *Tomás, electronic musician*: knows LFOs and mixers. He patches an LFO into a Chua box, likes
  the growl, clicks "Learn more" and reads about the circuit Leon Chua designed in 1983.
