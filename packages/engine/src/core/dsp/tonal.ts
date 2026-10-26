/**
 * Tonality: harmonic resynthesis (spec §4.2 step 7, ADR 0015). Mirrors `tonal()` in
 * `lab/src/chaotic_sound/dsp.py` operation by operation, so both engines agree to the last
 * bits of libm. C-style: one state object per channel, typed arrays, no allocation.
 *
 * Each harmonic band [k − ½, k + ½]·f_a of the level-normalized signal r is moved onto one
 * partial with the band's smoothed power and smoothed phase. The output is the mix
 * m = (1 − τ)^0.75·r + τ^0.75·t.
 */

/** Harmonics resynthesized (they hold more than 99.99% of the power of every v1 system). */
export const TONAL_HARMONICS = 8;
/** Q of the two state-variable sections of the 4th-order Butterworth band low-pass. */
export const TONAL_Q1 = 1 / (2 * Math.cos(Math.PI / 8));
export const TONAL_Q2 = 1 / (2 * Math.cos((3 * Math.PI) / 8));
/** Mix law exponent: between equal amplitude (coherent) and equal power (incoherent). */
export const TONAL_MIX_EXPONENT = 0.75;
/**
 * Phase normalization floor d_k = max(|v_k|, 0.1·(1 − τ)·√p_k): an incoherent band fades out
 * instead of flipping its partial's phase (a tick). It vanishes at τ = 1, where 2 s of
 * smoothing makes phase changes slow.
 */
export const TONAL_COHERENCE_FLOOR = 0.1;

const TWO_PI = 2 * Math.PI;

/** State of one tonality channel (reset by creating a new one). */
export class TonalChannel {
  /** φ, n, f_last, τ_last, β_env, raw gain, tonal gain (NaN forces the first update). */
  readonly scalars = Float64Array.of(0, 0, Number.NaN, Number.NaN, 0, 0, 0);
  /** Coefficients [a1, a2, a3] of the two state-variable sections. */
  readonly coef = new Float64Array(6);
  /** Filter states: per harmonic, (re, im) × (section 1, 2) × (s1, s2). */
  readonly filt = new Float64Array(8 * TONAL_HARMONICS);
  /** Per harmonic: smoothed power p and smoothed complex amplitude (Re v, Im v). */
  readonly bands = new Float64Array(3 * TONAL_HARMONICS);

  reset(): void {
    this.scalars.set([0, 0, Number.NaN, Number.NaN, 0, 0, 0]);
    this.coef.fill(0);
    this.filt.fill(0);
    this.bands.fill(0);
  }
}

/**
 * Process `n` samples of one channel: `r` level-normalized signal, `fA` the fundamental
 * actually heard (Hz) and `tau` the smoothed tonality, per sample; writes m to `out`.
 */
export function tonal(
  r: Float64Array,
  fA: Float64Array,
  tau: Float64Array,
  fs: number,
  ch: TonalChannel,
  out: Float64Array,
  n: number,
): void {
  const { scalars, coef, filt, bands } = ch;
  for (let i = 0; i < n; i++) {
    const f = fA[i]!;
    if (f !== scalars[2]) {
      // Butterworth low-pass at f_a/2: two TPT state-variable sections, which stay
      // well-behaved when the cut-off moves (a biquad's memories overshoot when f_a drops).
      const g = Math.tan((Math.PI * (f * 0.5)) / fs);
      for (let j = 0; j < 2; j++) {
        const kappa = 1 / (j === 0 ? TONAL_Q1 : TONAL_Q2);
        const a1 = 1 / (1 + g * (g + kappa));
        const a2 = g * a1;
        coef[3 * j] = a1;
        coef[3 * j + 1] = a2;
        coef[3 * j + 2] = g * a2;
      }
      scalars[2] = f;
    }
    const t = tau[i]!;
    if (t !== scalars[3]) {
      const tEnv = 0.002 * 10 ** (3 * t);
      scalars[4] = 1 - Math.exp(-1 / (tEnv * fs));
      scalars[5] = (1 - t) ** TONAL_MIX_EXPONENT;
      scalars[6] = t ** TONAL_MIX_EXPONENT;
      scalars[3] = t;
    }
    let ph = scalars[0]! + f / fs;
    ph = ph - Math.floor(ph);
    scalars[0] = ph;
    const zr = Math.cos(TWO_PI * ph);
    const zi = Math.sin(TWO_PI * ph);
    const count = scalars[1]!;
    const beta = Math.max(scalars[4]!, 1 / (count + 1));
    scalars[1] = count + 1;
    const x = r[i]!;
    const fl = TONAL_COHERENCE_FLOOR * (1 - t);
    let wr = 1;
    let wi = 0;
    let acc = 0;
    for (let k = 0; k < TONAL_HARMONICS; k++) {
      const nr = wr * zr - wi * zi;
      const ni = wr * zi + wi * zr;
      wr = nr;
      wi = ni;
      let cRe = 0;
      let cIm = 0;
      for (let part = 0; part < 2; part++) {
        let y = part === 0 ? x * wr : -(x * wi);
        for (let j = 0; j < 2; j++) {
          const m = 8 * k + 4 * part + 2 * j;
          const s1 = filt[m]!;
          const s2 = filt[m + 1]!;
          const v3 = y - s2;
          const v1 = coef[3 * j]! * s1 + coef[3 * j + 1]! * v3;
          const v2 = s2 + coef[3 * j + 1]! * s1 + coef[3 * j + 2]! * v3;
          filt[m] = 2 * v1 - s1;
          filt[m + 1] = 2 * v2 - s2;
          y = v2;
        }
        if (part === 0) cRe = y;
        else cIm = y;
      }
      const pw = cRe * cRe + cIm * cIm;
      const pk = bands[3 * k]! + beta * (pw - bands[3 * k]!);
      const vr = bands[3 * k + 1]! + beta * (cRe - bands[3 * k + 1]!);
      const vi = bands[3 * k + 2]! + beta * (cIm - bands[3 * k + 2]!);
      bands[3 * k] = pk;
      bands[3 * k + 1] = vr;
      bands[3 * k + 2] = vi;
      const sp = Math.sqrt(pk);
      const den = Math.max(Math.sqrt(vr * vr + vi * vi), fl * sp);
      if (den > 0) {
        let w = (0.45 * fs - (k + 1) * f) / (0.05 * fs);
        w = w < 0 ? 0 : w > 1 ? 1 : w;
        acc += (w * 2 * sp * (vr * wr - vi * wi)) / den;
      }
    }
    out[i] = scalars[5]! * x + scalars[6]! * acc;
  }
}
