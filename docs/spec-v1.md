# chaotic_sound: v1 specification

- Status: **v0.3** (2026-10-26). Updated after the owner's review, the Phase 1 studies and the
  code review.
- Scope: the behavior of every box in the first version. Every engine (the Python reference
  in `lab/`, the TypeScript engine, a possible future C++ core) must follow this document.
  Golden tests check that they do (ADR 0011).
- Rationale: the "why" behind each choice is in `decisions/` (ADRs) and `math/tuning.md`.

Formulas are exact and are meant to be implemented literally in IEEE-754 float64.
"Implementation-defined" marks the few places where engines may differ.

## 1. What v1 contains

| Box | `type` | Produces | Purpose |
|---|---|---|---|
| **Modulator** | `modulator` | control in [0, 1] | Slow periodic or one-shot movement (LFO / envelope) |
| **Dynamical** | `dynamical` | audio (stereo) | Integrates a chaotic ODE tuned to a note |
| **Sum** | `sum` | audio (stereo) | Adds audio signals |
| **Control Sum** | `control_sum` | control in [0, 1] | Adds control signals explicitly |
| **Output** | `output` | speakers / WAV | Final volume, play/stop, WAV export |

Systems: **Lorenz, Rössler, Chua, Rikitake dynamo, Duffing (forced)**.

Not in v1 (see the roadmap): chaotic modulators, modulator properties (duty, min/max, phase),
noise, filters, effects, feedback cables, MIDI, oversampling, and languages other than
English.

## 2. Glossary

| Term | Meaning |
|---|---|
| **Patch** | The whole graph: boxes plus cables. |
| **Block / box** | A processing unit. Code says *block*; the UI says *box*. |
| **Port** | A named input or output of a block, typed `audio` or `control`. |
| **Cable** | A directed connection from an output port to an input port of the same type. |
| **Knob** | A user setting in [0, 1]. Some knobs have an input port with the same name that overrides them. |
| **Setting** | A choice that can't be modulated (system, note, shape, mode, …). |
| **System time τ** | The ODE's own time variable. |
| **Real time t** | Seconds of audio. |
| **Time scale k** | System time per second: τ = k·t. |
| **Characteristic period P** | The period of the system's main oscillation, in system time, measured by the lab on the most pitched variable and used whatever variable is heard (ADR 0010). |
| **Observable** | The state variable that becomes the audio. Phase variables (Duffing's z) are never observables. |
| **Normalized parameter u** | The [0, 1] knob, mapped linearly onto the system parameter's range [p_min, p_max]. |
| **Pitch lock** | Adjusting k as the parameter moves, so that the note stays fixed and only the timbre changes. |
| **Catalog** | The generated JSON (`catalog/systems.json`): per system, ranges and tables. |

## 3. Signal conventions and graph rules

- **Sample rate** fs: any positive rate. The browser uses the device rate; offline renders
  default to 48 000 Hz. Engines reject non-finite or non-positive rates.
- **Audio** is stereo with a nominal range of [-1, 1]. A dynamical box at amp = 1 has an RMS
  of at most 0.25 (spec §4.2 step 6).
- **Control** signals are mono, in [0, 1].
- **Sanitizing.** Before a control value reaches any block input, NaN → 0, +∞ → 1, −∞ → 0,
  then it is clipped to [0, 1]. This applies to **each cable separately**.
- **Cables.**
  - One output may feed any number of inputs.
  - Inputs accept **exactly one cable**, except `sum.in` (audio) and `control_sum.in`
    (control), which accept any number. The engine adds those cables (after sanitizing, for
    control).
  - The same (from, to) pair may appear only once.
  - Cables must join ports of the same type.
- **Override.** A connected cable replaces its knob's value.
- **Graph.**
  - It must be acyclic (no feedback in v1).
  - It has exactly one Output block, which may have no cable, in which case it renders
    silence.
  - Block ids are non-empty strings without `.`.
  - A port reference `"block.port"` splits at the first `.`.

## 4. Boxes

### 4.1 Modulator

| Name | Kind | Values | Default |
|---|---|---|---|
| `shape` | setting | `sine`, `triangle`, `square`, `ramp_up`, `ramp_down` | `sine` |
| `period_s` | setting | number ≥ 0.001 (seconds) | 4.0 |
| `mode` | setting | `loop`, `once` | `loop` |
| `out` | output | control | |

For sample i (i = 0 at the start of playback or render), compute in float64:

  t = i / fs,  c = t / T  (T = `period_s`),
  φ = c − floor(c) in `loop` mode,  φ = min(c, 1) in `once` mode,

and output shape(φ):

| Shape | shape(φ) | Value at φ = 0 | Value held at the end of `once` (φ = 1) |
|---|---|---|---|
| sine | (1 − cos 2πφ) / 2 | 0 | 0 |
| triangle | 1 − \|2φ − 1\| | 0 | 0 |
| square | 1 if φ < ½, else 0 | 1 | 0 |
| ramp_up | φ | 0 | 1 |
| ramp_down | 1 − φ | 1 | 0 |

### 4.2 Dynamical

| Name | Kind | Values | Default |
|---|---|---|---|
| `system` | setting | `lorenz`, `rossler`, `chua`, `rikitake`, `duffing` | `rossler` |
| `note` | setting | note name, C0 … C8 (grammar below) | `A3` (220 Hz) |
| `cents` | setting | −100 … +100 | 0 |
| `pitch_min`, `pitch_max` | settings | note names, C0 … C8, pitch_min < pitch_max | `A1`, `A5` |
| `observable` | setting | an audible variable of the system | catalog `default_observable` |
| `observable_right` | setting | an audible variable, or omitted (mono) | omitted |
| `pitch_lock` | setting | `true` / `false` | `true` |
| `amp_curve` | setting | `perceptual`, `linear` | `perceptual` |
| `seed` | setting | integer in [0, 2³¹) | stable hash of the block id |
| `param` | knob + control input | [0, 1] | catalog `u_default` |
| `amp` | knob + control input | [0, 1] | 1.0 |
| `pitch` | control input | [0, 1] (no knob: `note` is the manual value) | |
| `out` | output | audio | |

**Note grammar**: a letter `A`–`G` (either case), at most one accidental (`#` or `♯` sharp,
`b` or `♭` flat), and an octave from −1 to 9, with no spaces. MIDI number
m = 12·(octave + 1) + semitone(letter) ± accidental (C4 = 60, A4 = 69). A box accepts only
notes from C0 (12) to C8 (108).

Per chunk and per sample i:

1. **Pitch.**
   - Without a `pitch` cable: f = 440·2^((m − 69)/12)·2^(cents/1200), constant.
   - With a cable: q is smoothed by the control smoother of step 2, with
     y[−1] = the first q value. Then m(t) = m_min + q_s·(m_max − m_min), with m_min, m_max
     the MIDI numbers of `pitch_min`, `pitch_max` (cents ignored), and
     f = 440·2^((m(t) − 69)/12).
   - Engines reject f ≥ fs/2 at reset.
2. **Control smoothing**: one-pole filters, output taken after the update:
   y[n] = y[n−1] + α_n·(x[n] − y[n−1]).

   | Signal | α_n | Initial value y[−1] |
   |---|---|---|
   | amp a | α = 1 − exp(−1/(0.005·fs)) | 0, so every box fades in |
   | parameter u (**slew**, ADR 0013) | 1 − exp(−1/(τ_n·fs)), τ_n = max(0.005, 2/f_n) | the first control value (no initial glide) |
   | pitch q | α = 1 − exp(−1/(0.005·fs)) | the first control value (no initial glide) |

   Here x is the cable value if connected, otherwise the knob. A state with |y| < 1e-30 is
   set to 0 (flush-to-zero).
3. **Amp curve.** g = a_s^(1/(2·log₁₀2)) ≈ a_s^1.6609640474436813 (`perceptual`: halving a
   is −10 dB) or g = a_s (`linear`).
4. **Parameter.** p = p_min + clip(u_s, 0, 1)·(p_max − p_min).
5. **Time scale.**
   - With pitch lock: k = P(u_s)·f.
   - Without: k = P(u_default)·f.
   - P(u) is the catalog's `period` table, interpolated linearly in u (clip u to [0, 1];
     linear interpolation between grid nodes).
6. **Integration.**
   - Δτ = k/fs, and n_sub = clamp(⌈Δτ/h_max⌉, 1, 4096).
   - Take n_sub classical RK4 steps of h = Δτ/n_sub, with p held constant within the sample.
   - Wrap phase variables (Duffing's z) to [0, 2π) with the floating-point remainder: r = fmod(x, 2π), plus 2π if r < 0 (Python's `%`).
   - h_max comes from the catalog.
   - **Sample timing**: the sample's output is the state *after* this advance.
7. **Audio.**
   - Per channel: y = g · s(u_s) · (x_obs − μ(u_s)), with
     s(u) = min(0.25/σ(u), 0.8/π(u)).
   - μ, σ and π are the catalog's mean, standard deviation and robust peak tables of the
     observable, interpolated as in step 5.
   - Then the **DC blocker** y_out[n] = y[n] − y[n−1] + R·y_out[n−1], with
     R = exp(−2π·5/fs), zero initial state and flush-to-zero.
   - Mono puts `observable` on both channels; stereo puts `observable` on the left and
     `observable_right` on the right.
8. **Safety.**
   - A reset happens if the state becomes non-finite, leaves the catalog's bounding box
     [`bounds.lo`, `bounds.hi`], or Δτ is non-finite or negative.
   - On a reset, the state goes back to the perturbed initial condition of step 9, and a
     `safety_resets` counter is incremented and reported as diagnostics.
9. **Initial condition and seeding (portable).**
   - seed = CRC-32 (IEEE 802.3, as in zlib) of the block id's UTF-8 bytes, ANDed with
     0x7FFFFFFF, unless `seed` is given.
   - Draw from the **mulberry32** generator, 32-bit arithmetic modulo 2³²:

     ```
     a ← (a + 0x6D2B79F5) mod 2³²
     t ← imul(a ⊕ (a ≫ 15), a ∨ 1)
     t ← ((t + imul(t ⊕ (t ≫ 7), t ∨ 61)) mod 2³²) ⊕ t
     uniform = (t ⊕ (t ≫ 14)) / 2³²
     ```

     Here ≫ is the logical right shift and imul is the low 32 bits of the product.
   - For each state variable j in order, z_j = √(−2·ln(1 − U₁))·cos(2π·U₂) (two uniforms per
     variable).
   - x₀_j = IC_j + 10⁻⁶·σ_j(u_default)·z_j, where σ_j is replaced by 1 for phase variables
     and IC is the catalog's `initial_condition`.

### 4.3 Sum

| Name | Kind | Values | Default |
|---|---|---|---|
| `in` | input (any number of cables) | audio | |
| `gain` | knob | [0, 1] | 1.0 |
| `out` | output | audio | |

out = gain · Σ inputs (0 with nothing connected).

### 4.4 Output

| Name | Kind | Values | Default |
|---|---|---|---|
| `in` | input (one cable) | audio | |
| `volume` | knob | [0, 1] | 0.8 |

- y = softclip(volume · in), where softclip(x) = x for |x| ≤ 0.9, and
  sign(x)·(0.9 + 0.1·tanh((|x| − 0.9)/0.1)) otherwise.
- **WAV export**: an offline render of a chosen length (default 10 s) at 48 kHz, stereo.
  16-bit PCM (round(clip(x, −1, 1)·32767)) by default; 32-bit float is available.

### 4.5 Control Sum

| Name | Kind | Values | Default |
|---|---|---|---|
| `in` | input (any number of cables) | control | |
| `gain` | knob | [0, 1] | 1.0 |
| `out` | output | control | |

out = clip(gain · Σ inputs, 0, 1), where each input is sanitized first (§3). With nothing
connected, out = 0. gain = 0.5 averages two inputs.

## 5. Patch format (JSON, version 0)

```json
{
  "format": "chaotic-sound-patch",
  "version": 0,
  "blocks": [
    {"id": "lfo", "type": "modulator", "params": {"shape": "sine", "period_s": 8.0}},
    {"id": "ross", "type": "dynamical", "params": {"system": "rossler", "note": "A3"},
     "ui": {"x": 120, "y": 40}},
    {"id": "out", "type": "output", "params": {"volume": 0.8}}
  ],
  "cables": [
    {"from": "lfo.out", "to": "ross.param"},
    {"from": "ross.out", "to": "out.in"}
  ]
}
```

- **Defaults.** An omitted param takes its default, and `null` means the same as omission.
  Writers omit defaulted values and never write `null`.
- **Types are checked.** Numbers may be integers or decimals (not booleans), settings are
  strings, `pitch_lock` is a boolean, and `seed` is an integer.
- **Unknown keys are errors:**
  - at the top level (allowed: `format`, `version`, `blocks`, `cables`, `ui`);
  - in blocks (`id`, `type`, `params`, `ui`);
  - in cables (`from`, `to`);
  - and unknown params.
- **The optional `ui` object** of a block is preserved by every engine and otherwise ignored.
- **Block order** in the file does not matter: engines process in topological order.

## 6. Processing model

- Blocks are processed in topological order (Kahn's algorithm, ties broken in file order),
  a chunk of samples at a time.
- **Output must not depend on the chunk size.** Chunks of 1, 128 or 4096 samples give
  bit-identical output in a given engine.
- All blocks start at t = 0 when playback or a render starts.
- **Determinism**: the same patch, sample rate and length give bit-identical output within an
  engine.
- **Across engines:**
  - the first ~2000 samples agree to about 1e-9 (implementations differ only in the last
    bits of libm functions);
  - over longer times, chaos amplifies those differences, so engines must agree
    statistically: level, pitch, spectral envelope and diagnostics;
  - modulator outputs must agree exactly.

## 7. Systems and catalog

The numbers are generated by `lab/scripts/build_catalog.py` into `catalog/systems.json`
(format `chaotic-sound-catalog`, version 2): per system the range, P(u) and μ, σ, π per
variable, h_max, the bounding box, the initial condition and the reference value. Engines read
them from there and never hard-code them. The current catalog (details in `math/tuning.md` §4,
ADR 0012):

| System | State | Modulated parameter | Knob range | Default (dysts value) | Heard by default | Tuned by |
|---|---|---|---|---|---|---|
| Lorenz | x, y, z | ρ | [24.8, 69.45] | 48.03 (28) | z | peak centroid |
| Rössler | x, y, z | c | [4.237, 8.815] | 6.562 (5.7) | x | peak centroid |
| Chua | x, y, z | α | [13.7, 18.05] | 15.8 (15.6) | y | peak centroid |
| Rikitake dynamo | x, y, z | μ | [0.513, 1.8] | 1.153 (1) | z | peak centroid |
| Duffing (forced) | x, y, z = drive phase | γ | [0.3858, 0.5083] | 0.4471 (0.35) | y | drive 2π/ω |
