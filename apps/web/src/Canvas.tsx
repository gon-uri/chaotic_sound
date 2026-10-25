/**
 * The patch editor canvas (React Flow). Nodes and edges are derived from the patch document;
 * every user action becomes a store action, which the engine validates.
 */

import { applyEdit, checkAndOrder, type PatchDocument, splitRef } from "@chaotic-sound/engine";
import {
  Background,
  type Connection,
  Controls,
  type Edge,
  type EdgeChange,
  type IsValidConnection,
  type Node,
  type NodeChange,
  ReactFlow,
  useReactFlow,
} from "@xyflow/react";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { type BoxData, nodeTypes } from "./nodes/boxes.tsx";
import { layout, usePatchStore } from "./store/patchStore.ts";

function cableId(from: string, to: string): string {
  return `${from}->${to}`;
}

function signalType(doc: PatchDocument, ref: string): "audio" | "control" {
  const [blockId] = splitRef(ref);
  const block = doc.blocks.find((b) => b.id === blockId);
  return block?.type === "modulator" || block?.type === "control_sum" ? "control" : "audio";
}

export function Canvas(): ReactNode {
  const doc = usePatchStore((s) => s.doc);
  const loads = usePatchStore((s) => s.loads);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (loads === 0) return;
    // Wait one frame so React Flow has measured the new boxes.
    const id = requestAnimationFrame(() => void fitView({ maxZoom: 1, padding: 0.2 }));
    return () => cancelAnimationFrame(id);
  }, [loads, fitView]);

  const positions = useMemo(() => layout(doc), [doc]);
  const nodes: Node<BoxData>[] = useMemo(
    () =>
      doc.blocks.map((block) => ({
        id: block.id,
        type: `box_${block.type}`, // prefixed: React Flow has built-in 'input'/'output' types
        position: positions.get(block.id)!,
        data: { block },
        selected: selected.has(block.id),
        deletable: block.type !== "output",
      })),
    [doc, selected, positions],
  );

  const edges: Edge[] = useMemo(
    () =>
      doc.cables.map((c) => {
        const [source, sourceHandle] = splitRef(c.from);
        const [target, targetHandle] = splitRef(c.to);
        return {
          id: cableId(c.from, c.to),
          source,
          sourceHandle,
          target,
          targetHandle,
          className: `cable cable-${signalType(doc, c.from)}`,
          selected: selected.has(cableId(c.from, c.to)),
        };
      }),
    [doc, selected],
  );

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    const store = usePatchStore.getState();
    for (const ch of changes) {
      if (ch.type === "position" && ch.position) store.moveBlock(ch.id, ch.position);
      if (ch.type === "select") {
        setSelected((prev) => {
          const next = new Set(prev);
          if (ch.selected) next.add(ch.id);
          else next.delete(ch.id);
          return next;
        });
      }
    }
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    for (const ch of changes) {
      if (ch.type === "select") {
        setSelected((prev) => {
          const next = new Set(prev);
          if (ch.selected) next.add(ch.id);
          else next.delete(ch.id);
          return next;
        });
      }
    }
  }, []);

  const onConnect = useCallback((c: Connection) => {
    usePatchStore.getState().edit({
      op: "connect",
      from: `${c.source}.${c.sourceHandle}`,
      to: `${c.target}.${c.targetHandle}`,
    });
  }, []);

  // Cheap, exact check while dragging: the engine's graph rules on the candidate patch.
  const isValidConnection: IsValidConnection = useCallback((c) => {
    try {
      const candidate = applyEdit(usePatchStore.getState().doc, {
        op: "connect",
        from: `${c.source}.${c.sourceHandle}`,
        to: `${c.target}.${c.targetHandle}`,
      });
      checkAndOrder(candidate);
      return true;
    } catch {
      return false;
    }
  }, []);

  const onDelete = useCallback(({ nodes: ns, edges: es }: { nodes: Node[]; edges: Edge[] }) => {
    const store = usePatchStore.getState();
    for (const e of es) {
      const cable = store.doc.cables.find((c) => cableId(c.from, c.to) === e.id);
      if (cable) store.edit({ op: "disconnect", from: cable.from, to: cable.to });
    }
    for (const n of ns) {
      if (store.doc.blocks.some((b) => b.id === n.id && b.type !== "output")) {
        store.edit({ op: "removeBlock", id: n.id });
      }
    }
    setSelected(new Set());
  }, []);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      isValidConnection={isValidConnection}
      onDelete={onDelete}
      deleteKeyCode={["Backspace", "Delete"]}
      fitView
      fitViewOptions={{ maxZoom: 1, padding: 0.2 }}
      minZoom={0.3}
      maxZoom={2}
      proOptions={{ hideAttribution: false }}
    >
      <Background gap={24} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
