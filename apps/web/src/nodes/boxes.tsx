/** One React Flow node component per box type (spec §4). */

import { type BlockJson, getSystem, shapeValue } from "@chaotic-sound/engine";
import type { NodeProps } from "@xyflow/react";
import type { ReactNode } from "react";
import { play, stop, useAudioStore } from "../audio/engineBridge.ts";
import { exportWav } from "../audio/exportWav.ts";
import { catalog } from "../store/catalog.ts";
import { usePatchStore } from "../store/patchStore.ts";
import { useUiStore } from "../store/uiStore.ts";
import { t } from "../strings.ts";
import { BoxFrame } from "./BoxFrame.tsx";
import { Knob, NumberField, Select, Toggle } from "./controls.tsx";

export interface BoxData extends Record<string, unknown> {
  block: BlockJson;
}

type BoxProps = NodeProps & { data: BoxData };

const param = (b: BlockJson, name: string): unknown => b.params?.[name] ?? undefined;
const setter =
  (id: string) =>
  (name: string, value: number | string | boolean | null): void =>
    usePatchStore.getState().setParam(id, name, value);

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const NOTES = Array.from({ length: 12 * 7 + 1 }, (_, i) => {
  const name = `${NOTE_NAMES[i % 12]}${Math.floor(i / 12) + 1}`;
  return { value: name, label: name };
}); // C1 … C8

const SYSTEM_OPTIONS = ["lorenz", "rossler", "chua", "rikitake", "duffing"].map((s) => ({
  value: s,
  label: getSystem(s).displayName,
}));

const PARAM_SYMBOLS: Record<string, string> = { rho: "ρ", c: "c", alpha: "α", mu: "μ", gamma: "γ" };

export function DynamicalBox({ id, data, selected }: BoxProps): ReactNode {
  const b = data.block;
  const set = setter(id);
  const system = (param(b, "system") as string | undefined) ?? "rossler";
  const entry = catalog.get(system);
  const u = (param(b, "param") as number | undefined) ?? entry.uDefault;
  const audio = getSystem(system).variables.filter(
    (_, i) => !getSystem(system).phaseIndices.includes(i),
  );
  const resets = useAudioStore((s) => s.diagnostics[id]?.safety_resets ?? 0);
  const symbol = PARAM_SYMBOLS[entry.param] ?? entry.param;
  return (
    <BoxFrame type="dynamical" id={id} selected={selected} title={getSystem(system).displayName}>
      <Select
        label={t.system}
        value={system}
        options={SYSTEM_OPTIONS}
        onChange={(v) => {
          set("system", v);
        }}
      />
      <div className="row">
        <Select
          label={t.note}
          value={(param(b, "note") as string | undefined) ?? "A3"}
          options={NOTES}
          onChange={(v) => set("note", v)}
        />
        <NumberField
          label={t.cents}
          value={(param(b, "cents") as number | undefined) ?? 0}
          min={-100}
          max={100}
          step={1}
          onChange={(v) => set("cents", v)}
        />
      </div>
      <Knob
        label={`${t.parameter} ${symbol}`}
        value={u}
        display={`${symbol} = ${entry.paramValue(u).toPrecision(4)}`}
        onChange={(v) => set("param", v)}
      />
      <Knob
        label={t.amp}
        value={(param(b, "amp") as number | undefined) ?? 1}
        onChange={(v) => set("amp", v)}
      />
      <Select
        label={t.observable}
        value={(param(b, "observable") as string | undefined) ?? entry.defaultObservable}
        options={audio.map((v) => ({ value: v, label: v }))}
        onChange={(v) => set("observable", v)}
      />
      <div className="row">
        <Toggle
          label={t.pitchLock}
          value={(param(b, "pitch_lock") as boolean | undefined) ?? true}
          onChange={(v) => set("pitch_lock", v)}
        />
        <Toggle
          label={t.perceptualAmp}
          value={((param(b, "amp_curve") as string | undefined) ?? "perceptual") === "perceptual"}
          onChange={(v) => set("amp_curve", v ? "perceptual" : "linear")}
        />
      </div>
      <div className="row">
        <button
          type="button"
          className="nodrag link"
          onClick={() => useUiStore.getState().openLearnMore(id)}
        >
          {t.learnMore} →
        </button>
        {resets > 0 && (
          <span className="warn">
            {resets} {t.resets}
          </span>
        )}
      </div>
    </BoxFrame>
  );
}

const SHAPES = ["sine", "triangle", "square", "ramp_up", "ramp_down"] as const;

function ShapePreview({ shape }: { shape: (typeof SHAPES)[number] }): ReactNode {
  const pts = Array.from({ length: 41 }, (_, i) => {
    const phase = i / 40;
    return `${phase * 60},${18 - shapeValue(shape, phase) * 16}`;
  }).join(" ");
  return (
    <svg className="shape-preview" viewBox="0 0 60 20" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function ModulatorBox({ id, data, selected }: BoxProps): ReactNode {
  const b = data.block;
  const set = setter(id);
  const shape = ((param(b, "shape") as string | undefined) ?? "sine") as (typeof SHAPES)[number];
  return (
    <BoxFrame type="modulator" id={id} selected={selected}>
      <ShapePreview shape={shape} />
      <Select
        label={t.shape}
        value={shape}
        options={SHAPES.map((s) => ({ value: s, label: s.replace("_", " ") }))}
        onChange={(v) => set("shape", v)}
      />
      <NumberField
        label={t.period}
        value={(param(b, "period_s") as number | undefined) ?? 4}
        min={0.001}
        max={3600}
        step={0.1}
        onChange={(v) => set("period_s", v)}
      />
      <Toggle
        label={`${t.loop} (off = ${t.once})`}
        value={((param(b, "mode") as string | undefined) ?? "loop") === "loop"}
        onChange={(v) => set("mode", v ? "loop" : "once")}
      />
    </BoxFrame>
  );
}

export function SumBox({ id, data, selected, type }: BoxProps): ReactNode {
  const b = data.block;
  return (
    <BoxFrame type={type === "box_control_sum" ? "control_sum" : "sum"} id={id} selected={selected}>
      <Knob
        label={t.gain}
        value={(param(b, "gain") as number | undefined) ?? 1}
        onChange={(v) => setter(id)("gain", v)}
      />
    </BoxFrame>
  );
}

export function OutputBox({ id, data, selected }: BoxProps): ReactNode {
  const b = data.block;
  const playing = useAudioStore((s) => s.playing);
  const notify = useUiStore((s) => s.notify);
  return (
    <BoxFrame type="output" id={id} selected={selected}>
      <Knob
        label={t.volume}
        value={(param(b, "volume") as number | undefined) ?? 0.8}
        onChange={(v) => setter(id)("volume", v)}
      />
      <div className="row">
        {playing ? (
          <button type="button" className="nodrag primary" onClick={stop}>
            ■ {t.stop}
          </button>
        ) : (
          <button type="button" className="nodrag primary" onClick={() => void play()}>
            ▶ {t.play}
          </button>
        )}
        <button
          type="button"
          className="nodrag"
          onClick={() => {
            notify(t.rendering);
            exportWav(usePatchStore.getState().doc, 10, "chaotic_sound.wav")
              .then((msg) => notify(msg))
              .catch((e: unknown) => notify(`${t.error}: ${String(e)}`));
          }}
        >
          {t.exportWav} (10 {t.seconds})
        </button>
      </div>
    </BoxFrame>
  );
}

export const nodeTypes = {
  box_dynamical: DynamicalBox,
  box_modulator: ModulatorBox,
  box_sum: SumBox,
  box_control_sum: SumBox,
  box_output: OutputBox,
};
