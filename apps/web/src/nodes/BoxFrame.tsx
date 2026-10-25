/** Common box frame: title bar and typed ports (inputs left, outputs right). */

import { BLOCK_SPECS, type BlockType } from "@chaotic-sound/engine";
import { Handle, Position } from "@xyflow/react";
import type { ReactNode } from "react";
import { t } from "../strings.ts";

export function BoxFrame(props: {
  type: BlockType;
  id: string;
  title?: string;
  selected: boolean;
  children: ReactNode;
}): ReactNode {
  const spec = BLOCK_SPECS[props.type];
  const portTop = (i: number, n: number): string => `${((i + 1) / (n + 1)) * 100}%`;
  return (
    <div className={`box box-${props.type}${props.selected ? " selected" : ""}`}>
      <div className="box-title">
        <span>{props.title ?? t.boxNames[props.type]}</span>
        <span className="box-id">{props.id}</span>
      </div>
      <div className="box-body">{props.children}</div>
      {spec.inputs.map((port, i) => (
        <Handle
          key={`in-${port.name}`}
          id={port.name}
          type="target"
          position={Position.Left}
          className={`handle handle-${port.type}${port.multi ? " handle-multi" : ""}`}
          style={{ top: portTop(i, spec.inputs.length) }}
        >
          <span className="handle-label handle-label-in">{port.name}</span>
        </Handle>
      ))}
      {spec.outputs.map((port, i) => (
        <Handle
          key={`out-${port.name}`}
          id={port.name}
          type="source"
          position={Position.Right}
          className={`handle handle-${port.type}`}
          style={{ top: portTop(i, spec.outputs.length) }}
        />
      ))}
    </div>
  );
}
