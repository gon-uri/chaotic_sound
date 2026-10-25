# chaotic_sound: v1 specification

- Status: **draft v0.1**, awaiting the owner's review (see `REVIEW.md`).
- Scope: the behavior of every box in the first version. Any engine (the Python reference in
  `lab/`, the future browser engine) must follow this document, and cross-engine tests check
  that they do.
- Rationale: the "why" behind the choices lives in `decisions/` (ADRs) and `math/tuning.md`.

## 1. What v1 contains

| Box | Produces | Purpose |
|---|---|---|
| **Modulator** | control signal in [0, 1] | Slow periodic or one-shot movement (LFO / envelope) |
| **Dynamical** | audio (stereo) | Integrates a chaotic ODE tuned to a note |
| **Sum** | audio (stereo) | Adds audio signals |
| **Output** | speakers / WAV | Final volume, play/stop, WAV export |

Five systems: **Lorenz, Rössler, Chua, Thomas, Duffing (forced)**.

Not in v1 (on the roadmap): pitch input, chaotic modulators, modulator properties (duty, min/max,
phase), the route to chaos (periodic regimes), noise, filters, effects, feedback loops, MIDI,
and languages other than English.

## 2. Glossary

| Term | Meaning |
|---|---|
| **Patch** | The whole graph: boxes plus cables. |
| **Block / box** | A processing unit. Code says *block*; the UI says *box*. |
| **Port** | A named input or output of a block, typed `audio` or `control`. |
| **Cable** | A directed connection from an output port to an input port of the same type. |
| **Knob** | A user setting in [0, 1]. Some knobs have an input port with the same name that can override them. |
| **Setting** | A non-modulatable choice (system, note, shape, mode, …). |
| **System time τ** | The ODE's own time variable, in whatever units the equations use. |
| **Real time t** | Seconds of audio. |
| **Time scale k** | System time per second of audio: τ = k·t. |
| **Characteristic period P** | The period of the most prominent spectral peak of the heard variable, in system time (see `math/tuning.md`). |
| **Observable** | The state variable (x, y, z, …) that becomes the audio. |
| **Normalized parameter u** | The [0, 1] knob that maps linearly onto the system parameter's chaotic range [p_min, p_max]. |
| **Pitch lock** | Adjusting k as the parameter moves so that the note stays fixed and only the timbre changes. |
| **Catalog** | Generated JSON (`catalog/`) holding, per system, ranges, tuning tables and normalization tables. |

## 3. Signal conventions

- **Sample rate** `fs`: engines must work at any rate. The browser uses the device rate
  (usually 44.1 or 48 kHz). Offline renders default to 48 000 Hz.
- **Audio signals** are stereo with a nominal range of [-1, 1]. Each dynamical box with amp = 1
  is normalized to an RMS of **0.25** (about -12 dBFS), so different systems sound roughly
  equally loud.
- **Control signals** are mono and strictly in [0, 1]. Engines clip them.
- **Fan-out**: any output can feed any number of inputs.
- **Fan-in**:
  - The Sum box's `in` accepts any number of audio cables and adds them.
  - Each control input accepts any number of cables; they are summed, then clipped to [0, 1].
  - Output's `in` accepts exactly one cable.
- **Override rule**: when at least one cable is connected to a knob's input port, the cable
  value replaces the knob value.
- **Declicking**: every control value a dynamical box uses (knob or cable) passes through a
  one-pole low-pass filter with a 5 ms time constant.
- **Graph**: it must be acyclic (no feedback in v1), and there is exactly one Output box.

## 4. Boxes

### 4.1 Modulator

| Name | Kind | Values | Default |
|---|---|---|---|
| `shape` | setting | `sine`, `triangle`, `square`, `ramp_up`, `ramp_down` | `sine` |
| `period_s` | setting | seconds, > 0 | 4.0 |
| `mode` | setting | `loop`, `once` | `loop` |
| `out` | output | control | |

Let T = `period_s`. The phase is φ(t) = (t / T) mod 1 in loop mode, and φ(t) = min(t / T, 1) in
once mode. The output is shape(φ):

| Shape | shape(φ) | Value at φ = 0 | Value held at the end of `once` |
|---|---|---|---|
| sine | (1 − cos 2πφ) / 2 | 0 | 0 |
| triangle | 1 − \|2φ − 1\| | 0 | 0 |
| square | 1 if φ < ½, else 0 | 1 | 0 |
| ramp_up | φ | 0 | 1 |
| ramp_down | 1 − φ | 1 | 0 |

- t = 0 is the start of playback or of the render.
- In `once` mode, `period_s` is the length of the envelope in seconds. The value holds at
  shape(1) afterwards.

### 4.2 Dynamical

| Name | Kind | Values | Default |
|---|---|---|---|
| `system` | setting | `lorenz`, `rossler`, `chua`, `thomas`, `duffing` | `rossler` |
| `note` | setting | scientific pitch name, e.g. `A3`, `C#4`, `Bb2` | `A3` (220 Hz) |
| `cents` | setting | −100 … +100 | 0 |
| `observable` | setting | state variable name | per system (catalog) |
| `observable_right` | setting | state variable name or none | none (mono) |
| `pitch_lock` | setting | true / false | true |
| `seed` | setting | integer | stable hash of the block id |
| `param` | knob + control input | [0, 1] | u of the dysts default value |
| `amp` | knob + control input | [0, 1] | 1.0 |
| `out` | output | audio | |

Each sample is computed as follows:

1. **Controls.** Take u(t) and a(t) from the cable if one is connected, otherwise from the knob,
   then apply the declicking filter.
2. **Parameter.** p(t) = p_min + u(t)·(p_max − p_min), using the system's chaotic range from the
   catalog.
3. **Pitch.** f₀ = 440 · 2^((m − 69)/12) · 2^(cents/1200), where m is the MIDI note number
   (A4 = 69, 12-tone equal temperament).
4. **Time scale.** With pitch lock, k(t) = P(u(t))·f₀. Without it, k = P(u_default)·f₀, so the
   note is exact only at the default parameter. P(u) is the catalog table, interpolated
   linearly in u.
5. **Integration.** Advance dx/dτ = F(x; p(t)) by Δτ = k(t)/fs using n = ⌈Δτ / h_max⌉ equal
   classical RK4 sub-steps. The parameter is held constant within one sample. h_max is set by
   the catalog's `steps_per_period` N: h_max = P(u_default)/N.
6. **Audio.** y = a(t) · 0.25 · (x_obs − μ(u)) / σ(u), where μ(u) and σ(u) are the catalog's
   mean and standard deviation of the observable. A DC blocker follows (first-order high-pass,
   5 Hz). Mono puts y on both channels. Stereo puts `observable` on the left and
   `observable_right` on the right.
7. **Phase variables.** The drive phase of forced systems (Duffing's z) is wrapped modulo 2π
   after every sample.
8. **Safety.** If the state becomes non-finite or leaves the catalog's bounding box, it is reset
   to the initial condition, and the engine counts the event. The output is muted for that
   sample.
9. **Initial condition.** The catalog's initial condition, which lies on the attractor, plus a
   seeded perturbation of 10⁻⁶·σ per variable. Two boxes with the same system and note
   therefore drift apart instead of sounding identical, while renders stay reproducible.

### 4.3 Sum

| Name | Kind | Values | Default |
|---|---|---|---|
| `in` | input (many cables) | audio | |
| `gain` | knob | [0, 1] | 1.0 |
| `out` | output | audio | |

out = gain · Σ inputs. With nothing connected, out = 0.

### 4.4 Output

| Name | Kind | Values | Default |
|---|---|---|---|
| `in` | input (one cable) | audio | |
| `volume` | knob | [0, 1] | 0.8 |

- The output is y = softclip(volume · in).
- softclip is the identity for |x| ≤ 0.9. Above that, the excess is squashed with tanh into
  (0.9, 1): sign(x)·(0.9 + 0.1·tanh((|x| − 0.9)/0.1)).
- **WAV export**: an offline render of a chosen length (default 10 s) at 48 kHz, stereo. The
  default format is 16-bit PCM; 32-bit float is available.

## 5. Patch format (JSON, version 0)

```json
{
  "format": "chaotic-sound-patch",
  "version": 0,
  "blocks": [
    {"id": "lfo", "type": "modulator", "params": {"shape": "sine", "period_s": 8.0, "mode": "loop"}},
    {"id": "ross", "type": "dynamical", "params": {"system": "rossler", "note": "A3", "param": 0.5}},
    {"id": "mix", "type": "sum", "params": {"gain": 1.0}},
    {"id": "out", "type": "output", "params": {"volume": 0.8}}
  ],
  "cables": [
    {"from": "lfo.out", "to": "ross.param"},
    {"from": "ross.out", "to": "mix.in"},
    {"from": "mix.out", "to": "out.in"}
  ]
}
```

- Omitted params take their defaults.
- Unknown params are an error, which catches typos.
- An optional `"ui"` object per block (position, collapsed, …) is reserved for the web app and
  ignored by engines.

## 6. Processing model

- Blocks are processed in topological order, a block of samples at a time.
- **Output must not depend on the block size.** Rendering with blocks of 128 or of 4096
  samples gives identical samples. This is a required test.
- All blocks start at t = 0 when playback or a render starts.
- **Determinism**: the same patch, sample rate and length give bit-identical output within one
  engine. Across engines, outputs must agree statistically (same spectra and levels). Sample by
  sample they agree only for a short time, because chaos amplifies round-off.

## 7. Systems in v1

The concrete numbers (ranges, P(u), μ(u), σ(u), default observable, steps per period) are
generated by `lab/scripts/build_catalog.py` into `catalog/systems.json`. The table in
`math/tuning.md` summarizes them. Base values come from dysts.

| System | State | Modulated parameter | dysts default |
|---|---|---|---|
| Lorenz | x, y, z | ρ | 28 |
| Rössler | x, y, z | c | 5.7 |
| Chua | x, y, z | α | 15.6 |
| Thomas | x, y, z | a (damping; classical β = a/b) | 1.85 |
| Duffing (forced) | x, y, z = drive phase | γ (drive amplitude) | 0.35 |
