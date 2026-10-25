/**
 * "Learn more" page of a dynamical box: 3D attractor, the parameter the knob moves, and the
 * system's page from docs/systems/ (Markdown with KaTeX equations).
 */

import "katex/dist/katex.min.css";
import { getSystem } from "@chaotic-sound/engine";
import { type ReactNode, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";
import { catalog } from "../store/catalog.ts";
import { usePatchStore } from "../store/patchStore.ts";
import { useUiStore } from "../store/uiStore.ts";
import { t } from "../strings.ts";
import { Attractor3D } from "./Attractor3D.tsx";

const pages = import.meta.glob<string>("../../../../docs/systems/*.md", {
  eager: true,
  query: "?raw",
  import: "default",
});

function page(system: string): string | null {
  const entry = Object.entries(pages).find(([path]) => path.endsWith(`/${system}.md`));
  return entry ? entry[1].replace(/<!--[\s\S]*?-->/g, "").trim() : null;
}

export function LearnMore(): ReactNode {
  const blockId = useUiStore((s) => s.learnMoreBlock);
  const close = useUiStore((s) => s.closeLearnMore);
  const block = usePatchStore((s) => s.doc.blocks.find((b) => b.id === blockId));
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);
  if (!blockId || !block) return null;
  const system = (block.params?.system as string | undefined) ?? "rossler";
  const entry = catalog.get(system);
  const u = (block.params?.param as number | undefined) ?? entry.uDefault;
  const md = page(system);
  return (
    <div className="modal-backdrop">
      <dialog open className="modal" aria-label={getSystem(system).displayName}>
        <button type="button" className="modal-close" onClick={close} aria-label={t.close}>
          ✕
        </button>
        <h1>{getSystem(system).displayName}</h1>
        <Attractor3D system={system} u={u} />
        <p className="controls-note">
          Your knob moves <strong>{entry.param}</strong> from {entry.pMin.toPrecision(4)} to{" "}
          {entry.pMax.toPrecision(4)} (now {entry.paramValue(u).toPrecision(4)}; the classic value
          is {entry.pReference}). The note is set by rescaling time, so the shape you see is the
          sound you hear.
        </p>
        <p className="draft">Draft page: facts are being reviewed before publication.</p>
        {md ? (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
              {md}
            </ReactMarkdown>
          </div>
        ) : (
          <p>No page yet for this system.</p>
        )}
      </dialog>
    </div>
  );
}
