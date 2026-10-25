import { ReactFlowProvider } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { lazy, type ReactNode, Suspense, useEffect } from "react";
import { useAudioStore } from "./audio/engineBridge.ts";
import { Canvas } from "./Canvas.tsx";
import { usePatchStore } from "./store/patchStore.ts";
import { useUiStore } from "./store/uiStore.ts";
import { t } from "./strings.ts";
import { Toolbar } from "./Toolbar.tsx";

// The Learn-more page pulls in Three.js, KaTeX and Markdown: load it only when opened.
const LearnMore = lazy(() =>
  import("./learn/LearnMore.tsx").then((m) => ({ default: m.LearnMore })),
);

function StatusBar(): ReactNode {
  const error = usePatchStore((s) => s.error);
  const clear = usePatchStore((s) => s.clearError);
  const audio = useAudioStore();
  const toast = useUiStore((s) => s.toast);
  return (
    <footer className="statusbar">
      {error ? (
        <button type="button" className="error" onClick={clear} title="dismiss">
          {error}
        </button>
      ) : (
        <span className="muted">{t.helpCables}</span>
      )}
      <span className="spacer" />
      {toast && <span>{toast}</span>}
      {audio.error && <span className="error">{audio.error}</span>}
      <span className="muted">
        {audio.playing
          ? `▶ ${audio.seconds.toFixed(1)} s · ${audio.sampleRate} Hz`
          : t.audioStartHint}
      </span>
    </footer>
  );
}

function LearnMoreSlot(): ReactNode {
  const open = useUiStore((s) => s.learnMoreBlock !== null);
  return open ? (
    <Suspense fallback={<div className="modal-backdrop" />}>
      <LearnMore />
    </Suspense>
  ) : null;
}

export function App(): ReactNode {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) usePatchStore.getState().redo();
        else usePatchStore.getState().undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <ReactFlowProvider>
      <div className="app">
        <Toolbar />
        <main className="canvas">
          <Canvas />
        </main>
        <StatusBar />
        <LearnMoreSlot />
      </div>
    </ReactFlowProvider>
  );
}
