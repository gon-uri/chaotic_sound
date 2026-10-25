/** Small form controls used on the boxes. `nodrag` stops React Flow from moving the box. */

import type { ReactNode } from "react";

export function Knob(props: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  display?: string;
}): ReactNode {
  return (
    <label className="knob nodrag">
      <span className="knob-label">
        {props.label}
        <span className="knob-value">{props.display ?? props.value.toFixed(2)}</span>
      </span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.001}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
      />
    </label>
  );
}

export function Select<T extends string>(props: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (v: T) => void;
}): ReactNode {
  return (
    <label className="field nodrag">
      <span>{props.label}</span>
      <select value={props.value} onChange={(e) => props.onChange(e.target.value as T)}>
        {props.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Toggle(props: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}): ReactNode {
  return (
    <label className="toggle nodrag">
      <input
        type="checkbox"
        checked={props.value}
        onChange={(e) => props.onChange(e.target.checked)}
      />
      {props.label}
    </label>
  );
}

export function NumberField(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}): ReactNode {
  return (
    <label className="field nodrag">
      <span>{props.label}</span>
      <input
        type="number"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v) && v >= props.min && v <= props.max) props.onChange(v);
        }}
      />
    </label>
  );
}
