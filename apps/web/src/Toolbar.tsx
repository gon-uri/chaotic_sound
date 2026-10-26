/** Top bar: add boxes, examples, file operations, undo/redo, play. */

import type { BlockType, PatchDocument } from "@chaotic-sound/engine";
import { withoutDefaults } from "@chaotic-sound/engine";
import { useReactFlow } from "@xyflow/react";
import type { ReactNode } from "react";
import { play, stop, useAudioStore } from "./audio/engineBridge.ts";
import { EXAMPLES } from "./examples.ts";
import { defaultPatch, usePatchStore } from "./store/patchStore.ts";
import { useUiStore } from "./store/uiStore.ts";
import { t } from "./strings.ts";

const ADDABLE: BlockType[] = ["modulator", "dynamical", "sum", "control_sum"];

function download(name: string, text: string): void {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  a.download = name;
  a.click();
}

export function Toolbar(): ReactNode {
  const { screenToFlowPosition } = useReactFlow();
  const playing = useAudioStore((s) => s.playing);
  const canUndo = usePatchStore((s) => s.past.length > 0);
  const canRedo = usePatchStore((s) => s.future.length > 0);
  const store = usePatchStore.getState;
  const notify = useUiStore((s) => s.notify);

  const add = (type: BlockType): void => {
    const center = screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
    const jitter = () => (Math.random() - 0.5) * 120;
    store().addBlock(type, { x: center.x + jitter(), y: center.y + jitter() });
  };

  return (
    <header className="toolbar">
      <div className="brand">
        <strong>{t.appTitle}</strong>
        <span className="tagline">{t.tagline}</span>
      </div>
      <div className="group">
        <span className="group-label">{t.add}</span>
        {ADDABLE.map((type) => (
          <button key={type} type="button" onClick={() => add(type)}>
            + {t.boxNames[type]}
          </button>
        ))}
      </div>
      <div className="group">
        <select
          aria-label={t.examples}
          value=""
          onChange={(e) => {
            const ex = EXAMPLES.find((x) => x.name === e.target.value);
            if (ex) store().load(structuredClone(ex.patch));
          }}
        >
          <option value="">{t.examples}…</option>
          {EXAMPLES.map((ex) => (
            <option key={ex.name} value={ex.name}>
              {ex.name}
            </option>
          ))}
        </select>
        <button type="button" onClick={() => store().load(defaultPatch())}>
          {t.newPatch}
        </button>
        <label className="file-button">
          {t.open}
          <input
            type="file"
            accept="application/json,.json"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              file
                .text()
                .then((text) => store().load(JSON.parse(text) as PatchDocument))
                .catch((err: unknown) => notify(`${t.error}: ${String(err)}`));
              e.target.value = "";
            }}
          />
        </label>
        <button
          type="button"
          onClick={() =>
            download("patch.json", JSON.stringify(withoutDefaults(store().doc), null, 2))
          }
        >
          {t.save}
        </button>
        <button type="button" disabled={!canUndo} onClick={() => store().undo()}>
          ↶ {t.undo}
        </button>
        <button type="button" disabled={!canRedo} onClick={() => store().redo()}>
          ↷ {t.redo}
        </button>
      </div>
      <div className="group">
        {playing ? (
          <button type="button" className="primary" onClick={stop}>
            ■ {t.stop}
          </button>
        ) : (
          <button type="button" className="primary" onClick={() => void play()}>
            ▶ {t.play}
          </button>
        )}
      </div>
    </header>
  );
}
