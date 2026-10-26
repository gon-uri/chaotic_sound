// rk4_bench.js: cost of one dynamical box in JavaScript (study: docs/studies/cost.md).
//
// A standalone benchmark of the inner loop the planned TypeScript AudioWorklet engine will
// run: per audio sample, n = ceil(dtau / h_max) classical RK4 sub-steps (spec §4.2 step 6),
// with the state in Float64Array / scalar locals and no allocation in the hot loop.
//
// Three implementations are timed:
//   A  "specialized": code generated per system (RHS inlined, state in scalar locals);
//   B  "generic":     mirrors the Python kernels (rhs(x, p, out) on Float64Arrays, a shared
//                     rk4Step), run monomorphic (one code copy per system) and megamorphic
//                     (one shared copy used by all five systems, as in a multi-box patch);
//   C  "full box":    A plus everything else Dynamical.process (engine v0.3) does per sample:
//                     pitch input (optional), parameter slew max(5 ms, 2 periods), amp
//                     smoother and perceptual curve a^1.661, u -> p map, P/mu/sigma/peak table
//                     lookup, peak-limited normalization, DC blocker, safety check. One call
//                     per 128-sample render quantum.
//
// Configuration (catalog tables, notes, Python reference values) comes from the global
// BENCH_CONFIG, written by cost.py as bench_config.js / bench_config.json:
//   JavaScriptCore:  jsc bench_config.js rk4_bench.js
//   node (V8):       node rk4_bench.js bench_config.json
//   browser:         load bench_config.js, then this file (results go to console / globalThis)
// The last line printed is "RESULT_JSON {...}".
'use strict';

(function main() {
  const G = typeof globalThis !== 'undefined' ? globalThis : this;
  const now =
    typeof performance !== 'undefined' && performance.now
      ? () => performance.now()
      : typeof preciseTime === 'function'
        ? () => preciseTime() * 1e3
        : () => Date.now();
  const log =
    typeof console !== 'undefined' && console.log ? (s) => console.log(s) : (s) => print(s);

  let CFG = G.BENCH_CONFIG;
  if (CFG === undefined && typeof process !== 'undefined' && process.argv) {
    // node: CommonJS (require) or ES module (process.getBuiltinModule, node >= 22.3)
    const fs = typeof require === 'function' ? require('fs') : process.getBuiltinModule('fs');
    CFG = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  }
  if (CFG === undefined) throw new Error('BENCH_CONFIG not found (see header comment)');
  const QUICK = !!CFG.quick;

  const TWO_PI = 2.0 * Math.PI;
  const FS = CFG.fs;
  const QUANTUM = 128;
  const FTZ = 1e-30; // dsp.FLUSH_TO_ZERO

  // RHS as JS expressions in x0.., p0..; same operation order as lab/src/chaotic_sound/systems
  // so that, without transcendental functions, results are bit-identical to numba.
  const RHS = {
    lorenz: { rhs: ['p0 * (x1 - x0)', 'x0 * (p1 - x2) - x1', 'x0 * x1 - p2 * x2'] },
    rossler: { rhs: ['-x1 - x2', 'x0 + p0 * x1', 'p1 + x2 * (x0 - p2)'] },
    chua: {
      pre: 'const hh = p3 * x0 + 0.5 * (p2 - p3) * (Math.abs(x0 + 1.0) - Math.abs(x0 - 1.0));',
      rhs: ['p0 * (x1 - x0 - hh)', 'x0 - x1 + x2', '-p1 * x1'],
    },
    rikitake: { rhs: ['-p1 * x0 + x1 * x2', '-p1 * x1 - p0 * x0 + x0 * x2', '1.0 - x0 * x1'] },
    // alpha * x**3 in numba is alpha * ((x * x) * x); with alpha = 1 both orders agree.
    duffing: { rhs: ['x1', '-p2 * x1 - p1 * x0 - p0 * (x0 * x0 * x0) + p3 * Math.cos(x2)', 'p4'] },
  };
  // Generic array RHS (variant B), same arithmetic.
  const RHS_ARRAY = {
    lorenz(x, p, o) {
      o[0] = p[0] * (x[1] - x[0]);
      o[1] = x[0] * (p[1] - x[2]) - x[1];
      o[2] = x[0] * x[1] - p[2] * x[2];
    },
    rossler(x, p, o) {
      o[0] = -x[1] - x[2];
      o[1] = x[0] + p[0] * x[1];
      o[2] = p[1] + x[2] * (x[0] - p[2]);
    },
    chua(x, p, o) {
      const h = p[3] * x[0] + 0.5 * (p[2] - p[3]) * (Math.abs(x[0] + 1.0) - Math.abs(x[0] - 1.0));
      o[0] = p[0] * (x[1] - x[0] - h);
      o[1] = x[0] - x[1] + x[2];
      o[2] = -p[1] * x[1];
    },
    rikitake(x, p, o) {
      o[0] = -p[1] * x[0] + x[1] * x[2];
      o[1] = -p[1] * x[1] - p[0] * x[0] + x[0] * x[2];
      o[2] = 1.0 - x[0] * x[1];
    },
    duffing(x, p, o) {
      o[0] = x[1];
      o[1] = -p[2] * x[1] - p[1] * x[0] - p[0] * (x[0] * x[0] * x[0]) + p[3] * Math.cos(x[2]);
      o[2] = p[4];
    },
  };

  // ---------------------------------------------------------------- code generation (A, C)
  // One RHS evaluation: inputs src0.., outputs const dst0..; `k` suffixes every name so
  // several independent states can share one loop body (interleaving test).
  function stage(sys, src, dst, k) {
    const sub = (e) =>
      e.replace(/\bx(\d)\b/g, src + '$1' + k).replace(/\bhh\b/g, 'hh_' + dst + k);
    let c = sys.pre ? sub(sys.pre) + '\n' : '';
    sys.rhs.forEach((e, i) => (c += `const ${dst}${i}${k} = ${sub(e)};\n`));
    return c;
  }
  // One classical RK4 step of size h (h2 = h/2, h6 = h/6), in the order of integrate.rk4_step.
  function stepCode(sys, dim, k = '') {
    const r = (f) => Array.from({ length: dim }, (_, i) => f(i)).join('\n') + '\n';
    return (
      stage(sys, 'x', 'a', k) +
      r((i) => `const u${i}${k} = x${i}${k} + h2 * a${i}${k};`) +
      stage(sys, 'u', 'b', k) +
      r((i) => `const v${i}${k} = x${i}${k} + h2 * b${i}${k};`) +
      stage(sys, 'v', 'c', k) +
      r((i) => `const w${i}${k} = x${i}${k} + h * c${i}${k};`) +
      stage(sys, 'w', 'e', k) +
      r((i) => `x${i}${k} += h6 * (a${i}${k} + 2.0 * b${i}${k} + 2.0 * c${i}${k} + e${i}${k});`)
    );
  }
  // Pure stepping of `count` independent states in one loop (no per-sample work): with
  // count = 2, a cost per state-step well below count = 1 means the step is latency-bound.
  function genInterleaved(c, count) {
    const sys = RHS[c.name];
    const ks = Array.from({ length: count }, (_, j) => '_' + j);
    let s = 'return function kernelI(st, pp, h, nsteps) {\n';
    for (let j = 0; j < c.params.length; j++) s += `const p${j} = pp[${j}];\n`;
    ks.forEach((k, j) => {
      for (let i = 0; i < c.dim; i++) s += `let x${i}${k} = st[${j * c.dim + i}];\n`;
    });
    s += 'const h2 = 0.5 * h, h6 = h / 6.0;\nfor (let s = 0; s < nsteps; s++) {\n';
    for (const k of ks) s += stepCode(sys, c.dim, k);
    s += '}\n';
    ks.forEach((k, j) => {
      for (let i = 0; i < c.dim; i++) s += `st[${j * c.dim + i}] = x${i}${k};\n`;
    });
    return new Function(s + '};\n')();
  }
  function header(c) {
    let s = '';
    for (let j = 0; j < c.params.length; j++) if (j !== c.mod) s += `const p${j} = pp[${j}];\n`;
    for (let i = 0; i < c.dim; i++) {
      s += `let x${i} = st[${i}];\nconst lo${i} = lo[${i}], hi${i} = hi[${i}], xr${i} = xr[${i}];\n`;
    }
    return s;
  }
  function wrapAndSafety(c) {
    let s = '';
    for (const i of c.wrap) s += `x${i} = x${i} % TWO_PI;\nif (x${i} < 0) x${i} += TWO_PI;\n`;
    const conds = Array.from({ length: c.dim }, (_, i) => `x${i} >= lo${i} && x${i} <= hi${i}`);
    s += `if (!(${conds.join(' && ')})) {\n`;
    s += Array.from({ length: c.dim }, (_, i) => `x${i} = xr${i};`).join(' ') + ' resets++;\n}\n';
    return s;
  }
  function storeState(c) {
    return Array.from({ length: c.dim }, (_, i) => `st[${i}] = x${i};`).join(' ') + '\n';
  }
  // A: like integrate.render_tuned (per-sample p and dtau given as arrays).
  function genKernelA(c) {
    const sys = RHS[c.name];
    let s = 'return function kernelA(st, pp, pv, dtau, n, hmax, lo, hi, xr, out) {\n';
    s += header(c) + 'let resets = 0;\nfor (let i = 0; i < n; i++) {\n';
    s += `const p${c.mod} = pv[i];\nconst dd = dtau[i];\nlet ns = Math.ceil(dd / hmax);\n`;
    s += 'if (ns < 1) ns = 1;\nconst h = dd / ns, h2 = 0.5 * h, h6 = h / 6.0;\n';
    s += 'for (let s = 0; s < ns; s++) {\n' + stepCode(sys, c.dim) + '}\n';
    s += wrapAndSafety(c);
    for (let i = 0; i < c.dim; i++) s += `out[${c.dim} * i + ${i}] = x${i};\n`;
    s += '}\n' + storeState(c) + 'return resets;\n};\n';
    return new Function('TWO_PI', s)(TWO_PI);
  }
  // numpy.interp, reproduced exactly (same formula and special cases) on table T.
  function interpCode(name, T) {
    return (
      `let ${name};\n` +
      `if (uc >= ugL) ${name} = ${T}[GL];\n` +
      `else if (ug[j0] === uc) ${name} = ${T}[j0];\n` +
      `else { const sl = (${T}[j0 + 1] - ${T}[j0]) / (ug[j0 + 1] - ug[j0]);` +
      ` ${name} = sl * (uc - ug[j0]) + ${T}[j0]; }\n`
    );
  }
  // C: a whole dynamical box (Dynamical.process of engine v0.3), one call per render quantum.
  // withPitch: a cable on the pitch input, so the frequency, and with it the parameter-slew
  // coefficient, is recomputed every sample (two transcendental calls). Without it both are
  // constants of the box (computed once, as an engine would).
  // linear: amp_curve = "linear" (gain = a) instead of the perceptual g = a^1.661 (Math.pow).
  function genBox(c, withPitch, linear = false) {
    const sys = RHS[c.name];
    let s = 'return function boxProcess(B, n, uIn, uOff, qIn, outL, outR) {\n';
    s += 'const st = B.x, pp = B.p, lo = B.lo, hi = B.hi, xr = B.xr;\n' + header(c);
    s += 'const ug = B.ug, Pt = B.Pt, mt = B.mt, sdt = B.sdt, pkt = B.pkt;\n';
    s += 'const GL = ug.length - 1, ugL = ug[GL];\n';
    s += 'const alpha = B.alpha, knob = B.knob, amp = B.amp, pmin = B.pmin, prange = B.prange;\n';
    s += 'const hmax = B.hmax, r = B.r, ampExp = B.ampExp, mlo = B.mlo, mspan = B.mspan;\n';
    s += 'let us = B.us, as = B.as, qs = B.qs, dx = B.dcx, dy = B.dcy, resets = 0;\n';
    s += 'let f = B.f, au = B.alphaU;\n';
    s += 'for (let i = 0; i < n; i++) {\n';
    if (withPitch) {
      // spec: pitch smoother (5 ms), MIDI mapping, then the slew time constant max(5 ms, 2/f)
      s += 'qs += alpha * (qIn[uOff + i] - qs);\nif (Math.abs(qs) < FTZ) qs = 0.0;\n';
      s += 'const midi = mlo + qs * mspan;\n';
      s += 'f = 440.0 * Math.pow(2.0, (midi - 69.0) / 12.0);\n';
      s += 'const tau = Math.max(0.005, 2.0 / f);\nau = 1.0 - Math.exp(-1.0 / (tau * FS));\n';
    }
    s += 'const ur = uIn === null ? knob : uIn[uOff + i];\n';
    s += 'us += au * (ur - us);\nif (Math.abs(us) < FTZ) us = 0.0;\n';
    s += 'as += alpha * (amp - as);\nif (Math.abs(as) < FTZ) as = 0.0;\n';
    s += linear ? 'const g = as;\n' : 'const g = Math.pow(as, ampExp);\n';
    s += 'const uc = us < 0.0 ? 0.0 : us > 1.0 ? 1.0 : us;\n';
    s += `const p${c.mod} = pmin + uc * prange;\n`;
    // binary search: ug[j0] <= uc < ug[j0 + 1]
    s += 'let j0 = 0, j1 = GL;\n';
    s += 'while (j1 - j0 > 1) { const m = (j0 + j1) >> 1; if (ug[m] <= uc) j0 = m; else j1 = m; }\n';
    s += interpCode('Pu', 'Pt') + interpCode('mu', 'mt') + interpCode('sd', 'sdt');
    s += interpCode('pk', 'pkt');
    s += 'const dd = Pu * f / FS;\nlet ns = Math.ceil(dd / hmax);\nif (ns < 1) ns = 1;\n';
    s += 'const h = dd / ns, h2 = 0.5 * h, h6 = h / 6.0;\n';
    s += 'for (let s = 0; s < ns; s++) {\n' + stepCode(sys, c.dim) + '}\n';
    s += wrapAndSafety(c);
    s += 'const sc = Math.min(0.25 / sd, 0.8 / pk);\n';
    s += `const v = g * sc * (x${c.obs} - mu);\n`;
    s += 'let y = v - dx + r * dy;\nif (Math.abs(y) < FTZ) y = 0.0;\n';
    s += 'dx = v;\ndy = y;\noutL[i] = y;\noutR[i] = y;\n}\n';
    s += storeState(c) + 'B.us = us; B.as = as; B.qs = qs; B.dcx = dx; B.dcy = dy;\n';
    s += 'B.resets += resets;\n};\n';
    return new Function('TWO_PI', 'FS', 'FTZ', s)(TWO_PI, FS, FTZ);
  }

  // ---------------------------------------------------------------- generic code (B)
  // Source of the generic kernel; instantiated with new Function so every copy has its own
  // JIT type feedback (a copy used by one system only stays monomorphic).
  const GENERIC_SRC = `
    function rk4Step(rhs, x, p, h, k1, k2, k3, k4, tmp) {
      const n = x.length;
      rhs(x, p, k1);
      for (let i = 0; i < n; i++) tmp[i] = x[i] + 0.5 * h * k1[i];
      rhs(tmp, p, k2);
      for (let i = 0; i < n; i++) tmp[i] = x[i] + 0.5 * h * k2[i];
      rhs(tmp, p, k3);
      for (let i = 0; i < n; i++) tmp[i] = x[i] + h * k3[i];
      rhs(tmp, p, k4);
      for (let i = 0; i < n; i++) x[i] += (h / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]);
    }
    return function kernelB(rhs, x, p, mi, pv, dtau, n, hmax, wrap, lo, hi, xr, out, S) {
      const dim = x.length, k1 = S.k1, k2 = S.k2, k3 = S.k3, k4 = S.k4, tmp = S.tmp;
      let resets = 0;
      for (let i = 0; i < n; i++) {
        p[mi] = pv[i];
        const d = dtau[i];
        let ns = Math.ceil(d / hmax);
        if (ns < 1) ns = 1;
        const h = d / ns;
        for (let s = 0; s < ns; s++) rk4Step(rhs, x, p, h, k1, k2, k3, k4, tmp);
        for (let j = 0; j < dim; j++) if (wrap[j]) { x[j] = x[j] % TWO_PI; if (x[j] < 0) x[j] += TWO_PI; }
        let ok = true;
        for (let j = 0; j < dim; j++) { const v = x[j]; if (!(v >= lo[j] && v <= hi[j])) ok = false; }
        if (!ok) { for (let j = 0; j < dim; j++) x[j] = xr[j]; resets++; }
        for (let j = 0; j < dim; j++) out[dim * i + j] = x[j];
      }
      return resets;
    };`;
  const makeGeneric = () => new Function('TWO_PI', GENERIC_SRC)(TWO_PI);

  // ---------------------------------------------------------------- setup
  const f64 = (a) => Float64Array.from(a);
  const systems = CFG.systems.map((c) => ({
    ...c,
    wrapMask: Uint8Array.from({ length: c.dim }, (_, i) => (c.wrap.includes(i) ? 1 : 0)),
    kA: genKernelA(c),
    kB: makeGeneric(),
    box: genBox(c, false),
    boxPitch: genBox(c, true),
    boxLinear: genBox(c, false, true),
    scratch: {
      k1: new Float64Array(c.dim),
      k2: new Float64Array(c.dim),
      k3: new Float64Array(c.dim),
      k4: new Float64Array(c.dim),
      tmp: new Float64Array(c.dim),
    },
  }));
  const byName = {};
  for (const s of systems) byName[s.name] = s;

  // Timer resolution: the smallest non-zero difference between two readings.
  let tick = Infinity;
  {
    let a = now();
    for (let i = 0; i < 200000; i++) {
      const b = now();
      if (b > a) tick = Math.min(tick, b - a);
      a = b;
    }
  }
  const results = {
    engine: CFG.engine || 'unknown',
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
    timer_resolution_us: tick * 1e3,
    validation: [],
    step: [],
    box: [],
    multibox: [],
    deopt: [],
  };

  // ---------------------------------------------------------------- 1. validation
  // Fixed-step RK4 from the catalog initial condition vs numba (integrate_sampled).
  for (const s of systems) {
    const K = s.ref_steps;
    const pv = new Float64Array(K).fill(s.params[s.mod]);
    const dt = new Float64Array(K).fill(s.h_max);
    const out = new Float64Array(K * s.dim);
    const stA = f64(s.ic);
    s.kA(stA, f64(s.params), pv, dt, K, s.h_max, f64(s.lo), f64(s.hi), f64(s.ic), out);
    const stB = f64(s.ic);
    s.kB(RHS_ARRAY[s.name], stB, f64(s.params), s.mod, pv, dt, K, s.h_max, s.wrapMask,
      f64(s.lo), f64(s.hi), f64(s.ic), out, s.scratch);
    let dA = 0, dB = 0;
    for (let i = 0; i < s.dim; i++) {
      dA = Math.max(dA, Math.abs(stA[i] - s.ref_x[i]));
      dB = Math.max(dB, Math.abs(stB[i] - s.ref_x[i]));
    }
    results.validation.push({ system: s.name, kind: 'rk4', steps: K, max_abs_diff_A: dA, max_abs_diff_B: dB });
  }

  // ---------------------------------------------------------------- box helpers
  // opt: { knob, xInit, pitch: { mlo, mhi }, linear } (pitch: a cable on the pitch input;
  // linear: amp_curve = "linear").
  function makeBox(s, f0, uIn, qIn, opt = {}) {
    const pmin = s.p_min, prange = s.p_max - s.p_min;
    const knob = opt.knob === undefined ? s.u_default : opt.knob;
    const tau = Math.max(0.005, 2.0 / f0);
    return {
      sys: s,
      fn: qIn !== null ? s.boxPitch : opt.linear ? s.boxLinear : s.box,
      x: f64(opt.xInit || s.ic),
      p: f64(s.params),
      lo: f64(s.lo),
      hi: f64(s.hi),
      xr: f64(opt.xInit || s.ic),
      ug: f64(s.u_grid),
      Pt: f64(s.period),
      mt: f64(s.mean),
      sdt: f64(s.std),
      pkt: f64(s.peak),
      alpha: CFG.alpha,
      alphaU: 1.0 - Math.exp(-1.0 / (tau * FS)),
      ampExp: CFG.amp_exponent,
      knob,
      amp: 1.0,
      pmin,
      prange,
      f: f0,
      mlo: opt.pitch ? opt.pitch.mlo : 0.0,
      mspan: opt.pitch ? opt.pitch.mhi - opt.pitch.mlo : 0.0,
      hmax: s.h_max,
      r: CFG.dc_r,
      us: uIn === null ? knob : uIn[0],
      as: 0.0,
      qs: qIn === null ? 0.0 : qIn[0],
      dcx: 0.0,
      dcy: 0.0,
      resets: 0,
      uIn,
      qIn,
    };
  }
  const LFO_LEN = Math.round(CFG.seconds * FS) + 4 * QUANTUM;
  const lfo = new Float64Array(LFO_LEN);
  for (let i = 0; i < LFO_LEN; i++) {
    lfo[i] = 0.5 * (1.0 - Math.cos(2.0 * Math.PI * ((i / FS / CFG.lfo_period_s) % 1.0)));
  }
  const outL = new Float32Array(QUANTUM), outR = new Float32Array(QUANTUM);

  // Box output vs the Python Dynamical block (same initial state; outputs are float32).
  for (const v of CFG.box_validation) {
    const s = byName[v.system];
    const uIn = v.modulated ? lfo : null;
    const qIn = v.pitch_signal ? f64(v.pitch_signal) : null;
    const pitch = v.pitch_signal ? { mlo: v.midi_min, mhi: v.midi_max } : undefined;
    const B = makeBox(s, v.f0, uIn, qIn, { xInit: v.x_init, pitch });
    B.fn = genBox(s, qIn !== null, !!v.linear); // own copy: leaves no JIT feedback behind
    const n = v.n_samples, stride = v.stride;
    const y = new Float64Array(n);
    for (let pos = 0; pos < n; pos += QUANTUM) {
      const m = Math.min(QUANTUM, n - pos);
      B.fn(B, m, uIn, pos, qIn, outL, outR);
      for (let i = 0; i < m; i++) y[pos + i] = outL[i];
    }
    let maxd = 0, maxdShort = 0;
    const nShort = Math.floor(v.short_samples / stride);
    for (let k = 0; k < v.expected.length; k++) {
      const d = Math.abs(y[k * stride] - v.expected[k]);
      maxd = Math.max(maxd, d);
      if (k < nShort) maxdShort = Math.max(maxdShort, d);
    }
    results.validation.push({
      system: v.system, kind: 'box', note: v.note, modulated: v.modulated, pitch_input: !!qIn,
      linear_amp: !!v.linear,
      n_samples: n, max_abs_diff: maxd, short_samples: v.short_samples, max_abs_diff_short: maxdShort,
    });
  }

  // ---------------------------------------------------------------- 2. pure step cost
  const STEPS_PER_SAMPLE = 1000;
  const N_SAMPLES = QUICK ? 500 : 2000;
  function timeSteps(run, reps) {
    run(); // warm-up / JIT tier-up
    let best = Infinity;
    for (let r = 0; r < reps; r++) {
      const t0 = now();
      run();
      best = Math.min(best, now() - t0);
    }
    return (best * 1e6) / (STEPS_PER_SAMPLE * N_SAMPLES); // ns per step
  }
  const stepInputs = {};
  for (const s of systems) {
    stepInputs[s.name] = {
      pv: new Float64Array(N_SAMPLES).fill(s.params[s.mod]),
      dt: new Float64Array(N_SAMPLES).fill(STEPS_PER_SAMPLE * s.h_max * 0.999999),
      out: new Float64Array(N_SAMPLES * s.dim),
      st: f64(s.ic),
      pp: f64(s.params),
      lo: f64(s.lo),
      hi: f64(s.hi),
      xr: f64(s.ic),
    };
  }
  const runA = (s) => {
    const I = stepInputs[s.name];
    I.st.set(s.ic);
    s.kA(I.st, I.pp, I.pv, I.dt, N_SAMPLES, s.h_max, I.lo, I.hi, I.xr, I.out);
  };
  const runB = (s, k) => {
    const I = stepInputs[s.name];
    I.st.set(s.ic);
    k(RHS_ARRAY[s.name], I.st, I.pp, s.mod, I.pv, I.dt, N_SAMPLES, s.h_max, s.wrapMask, I.lo, I.hi, I.xr, I.out, s.scratch);
  };
  const shared = makeGeneric();
  const reps = QUICK ? 2 : 5;
  for (const s of systems) {
    results.step.push({
      system: s.name,
      ns_per_step_A_specialized: timeSteps(() => runA(s), reps),
      ns_per_step_B_generic_mono: timeSteps(() => runB(s, s.kB), reps),
    });
  }
  // Megamorphic: the shared generic kernel sees all five RHS functions.
  for (const s of systems) runB(s, shared);
  for (const row of results.step) {
    row.ns_per_step_B_generic_mega = timeSteps(() => runB(byName[row.system], shared), reps);
  }
  // Interleaving: 1 vs 2 independent states stepped in one loop.
  for (const row of results.step) {
    const s = byName[row.system];
    for (const count of [1, 2]) {
      const k = genInterleaved(s, count);
      const st = new Float64Array(count * s.dim);
      const pp = f64(s.params);
      const total = STEPS_PER_SAMPLE * N_SAMPLES;
      const run = () => {
        for (let j = 0; j < count; j++) for (let i = 0; i < s.dim; i++) st[j * s.dim + i] = s.ic[i] * (1 + 1e-6 * j);
        k(st, pp, s.h_max, total);
      };
      row[`ns_per_state_step_interleaved_${count}`] = timeSteps(run, reps) / count;
    }
  }

  // ---------------------------------------------------------------- 3. full box, per quantum
  // Distribution of per-quantum times ts (µs): mean, percentiles, max, and the largest
  // moving average over 16 consecutive quanta (43 ms; the slow, u-dependent part of the load).
  function dist(ts) {
    const n = ts.length;
    const sorted = Float64Array.from(ts).sort();
    const pct = (p) => sorted[Math.min(n - 1, Math.floor(p * n))];
    let sum = 0;
    for (let i = 0; i < n; i++) sum += ts[i];
    let w = 0, peak16 = 0;
    for (let i = 0; i < n; i++) {
      w += ts[i];
      if (i >= 16) w -= ts[i - 16];
      if (i >= 15) peak16 = Math.max(peak16, w / 16);
    }
    return { mean: sum / n, p50: pct(0.5), p99: pct(0.99), p999: pct(0.999), max: sorted[n - 1], peak16 };
  }
  const nQ = Math.floor((CFG.seconds * FS) / QUANTUM);
  const qConst = new Float64Array(LFO_LEN).fill(CFG.pitch_q);
  // A warm-up of at least WARM_QUANTA calls, then timed reps of the whole loop with one timer
  // reading (mean cost), then one rep that reads the timer around every quantum (the
  // distribution; adds the timer's own cost). WARM_QUANTA is not always enough: in
  // JavaScriptCore the first timed rep of a code copy's first configuration (A1) ran up to
  // 1.6x slower than the next reps (see §5 for the warm-up curve). Reports use the median.
  const WARM_QUANTA = 2000;
  // mode: 'default' (knob at the default u), 'worst' (knob where P(u), hence n, is largest),
  // 'lfo' (4 s full-range sine on param), 'pitch' (default knob + a pitch cable whose
  // constant value pitch_q maps to the note: midi_min = note − 12, midi_max = note + 3),
  // 'linear' (default knob, amp_curve = "linear": no Math.pow per sample).
  // Static modes pass a control array filled with the knob value, not null, so each system's
  // box code sees one input type only (the study's Rec. 2: keep to one convention).
  function timeBox(s, note, mode) {
    const f0 = note.f0;
    const qIn = mode === 'pitch' ? qConst : null;
    const opt = mode === 'worst' ? { knob: s.u_worst } : mode === 'linear' ? { linear: true } : {};
    const uIn = mode === 'lfo' ? lfo : new Float64Array(LFO_LEN).fill(opt.knob ?? s.u_default);
    if (mode === 'pitch') opt.pitch = { mlo: note.midi - 12, mhi: note.midi + 3 };
    const R = QUICK ? 2 : 3;
    const means = [];
    let resets = 0, d = null;
    const ts = new Float64Array(nQ);
    for (let r = 0; r <= R + 1; r++) {
      const B = makeBox(s, f0, uIn, qIn, opt);
      if (r === 0) {
        const W = Math.max(nQ, WARM_QUANTA);
        for (let q = 0; q < W; q++) B.fn(B, QUANTUM, uIn, (q % nQ) * QUANTUM, qIn, outL, outR);
      } else if (r <= R) {
        const t0 = now();
        for (let q = 0; q < nQ; q++) B.fn(B, QUANTUM, uIn, q * QUANTUM, qIn, outL, outR);
        means.push(((now() - t0) * 1e3) / nQ);
      } else {
        for (let q = 0; q < nQ; q++) {
          const t0 = now();
          B.fn(B, QUANTUM, uIn, q * QUANTUM, qIn, outL, outR);
          ts[q] = (now() - t0) * 1e3;
        }
        d = dist(ts);
      }
      resets = B.resets;
    }
    return { means, d, resets };
  }
  const MODES = ['default', 'worst', 'lfo', 'pitch', 'linear'];
  for (const s of systems) {
    for (const note of CFG.notes) {
      for (const mode of MODES) {
        const { means, d, resets } = timeBox(s, note, mode);
        const best = Math.min(...means);
        results.box.push({
          system: s.name,
          note: note.name,
          mode,
          modulated: mode === 'lfo',
          us_per_quantum: best,
          us_per_quantum_reps: means,
          ns_per_sample: (best * 1e3) / QUANTUM,
          realtime_factor: (QUANTUM / FS) * 1e6 / best,
          dist_us: d,
          resets,
        });
      }
    }
  }

  // ---------------------------------------------------------------- 4. many boxes at once
  // Each scenario is a list of [system, f0] boxes, all modulated by the same 4 s LFO, with
  // their outputs summed into a bus as an engine would. Timed over a whole LFO cycle.
  const busL = new Float32Array(QUANTUM), busR = new Float32Array(QUANTUM);
  const nqM = Math.floor((CFG.multibox_seconds * FS) / QUANTUM);
  const tsM = new Float64Array(nqM);
  for (const scen of CFG.multibox) {
    const N = scen.boxes.length;
    const means = [];
    let d = null;
    for (let r = 0; r < 3; r++) {
      const boxes = scen.boxes.map(([name, f0]) => makeBox(byName[name], f0, lfo, null));
      for (let q = 0; q < nqM; q++) {
        const t0 = now();
        busL.fill(0);
        busR.fill(0);
        for (let b = 0; b < N; b++) {
          const B = boxes[b];
          B.fn(B, QUANTUM, B.uIn, q * QUANTUM, null, outL, outR);
          for (let i = 0; i < QUANTUM; i++) {
            busL[i] += outL[i];
            busR[i] += outR[i];
          }
        }
        tsM[q] = (now() - t0) * 1e3;
      }
      if (r > 0) {
        const dd = dist(tsM);
        means.push(dd.mean);
        if (d === null || dd.mean < d.mean) d = dd;
      }
    }
    results.multibox.push({ label: scen.label, boxes: N, us_per_quantum: Math.min(...means), us_per_quantum_reps: means, dist_us: d });
  }

  // ---------------------------------------------------------------- 5. JIT warm-up, input type
  // Fresh copies of the Rössler box code (A1, static knob), each timed from its first call in
  // blocks of DEOPT_BLOCK quanta (4 s of audio). The control input is 'array' (a Float64Array
  // filled with the knob value) or 'null' (no cable). Copies 2 and 3 switch type halfway, as
  // when a cable is plugged or unplugged in an engine that passes null for "no cable".
  // The copies run in this fixed order, and the order matters: in JavaScriptCore the slowdown
  // after a switch to null appeared only when no earlier copy of the same code had run with
  // null in that process. (An earlier version warmed each copy for 38 quanta only and always
  // timed the null-warmed copy first, so it measured JIT warm-up, not the input type.)
  {
    const s = byName.rossler, f0 = CFG.notes[0].f0;
    const DEOPT_BLOCK = 1500, NB = 6;
    const arr = new Float64Array(DEOPT_BLOCK * QUANTUM).fill(s.u_default);
    const PLAN = [['array'], ['array', 'null'], ['null', 'array'], ['null']];
    for (const inputs of PLAN) {
      const fn = genBox(s, false);
      const B = makeBox(s, f0, inputs[0] === 'null' ? null : arr, null);
      const blocks = [];
      for (const kind of inputs) {
        const uIn = kind === 'null' ? null : arr;
        for (let b = 0; b < NB; b++) {
          const t0 = now();
          for (let q = 0; q < DEOPT_BLOCK; q++) fn(B, QUANTUM, uIn, q * QUANTUM, null, outL, outR);
          blocks.push(((now() - t0) * 1e3) / DEOPT_BLOCK);
        }
      }
      results.deopt.push({
        system: 'rossler',
        note: CFG.notes[0].name,
        inputs,
        blocks_per_input: NB,
        block_quanta: DEOPT_BLOCK,
        blocks_us: blocks,
      });
    }
  }

  G.BENCH_RESULTS = results;
  log('RESULT_JSON ' + JSON.stringify(results));
})();
