/**
 * About: the Appropriate Legal Notices of the GNU AGPL (section 5(d)): copyright, the author
 * attribution required by the additional term in NOTICE.md (section 7(b)), no warranty, the
 * license and where to get the source (section 13).
 */

import { type ReactNode, useEffect } from "react";
import { useUiStore } from "./store/uiStore.ts";
import { t } from "./strings.ts";

export const REPOSITORY = "https://github.com/gon-uri/chaotic_sound";
/** The attribution every copy and modified version must keep (NOTICE.md, section 7(b)). */
export const ATTRIBUTION = `Based on chaotic_sound by Gonzalo Uribarri (${REPOSITORY.replace("https://", "")})`;

function ExternalLink(props: { href: string; children: ReactNode }): ReactNode {
  return (
    <a href={props.href} target="_blank" rel="noreferrer">
      {props.children}
    </a>
  );
}

export function About(): ReactNode {
  const open = useUiStore((s) => s.aboutOpen);
  const setAbout = useUiStore((s) => s.setAbout);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") setAbout(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setAbout]);
  if (!open) return null;
  return (
    <div className="modal-backdrop">
      <dialog open className="modal about" aria-label={t.about}>
        <button
          type="button"
          className="modal-close"
          onClick={() => setAbout(false)}
          aria-label={t.close}
        >
          ×
        </button>
        <h1>chaotic_sound</h1>
        <p>{t.aboutTagline}</p>
        <p>
          <strong>{ATTRIBUTION}</strong>
          <br />
          Copyright © 2026 Gonzalo Uribarri.
        </p>
        <h2>{t.aboutLicense}</h2>
        <p>
          This program is free software: you can redistribute it and/or modify it under the terms of
          the{" "}
          <ExternalLink href="https://www.gnu.org/licenses/agpl-3.0.html">
            GNU Affero General Public License
          </ExternalLink>{" "}
          version 3 or later, with an attribution term (see{" "}
          <ExternalLink href={`${REPOSITORY}/blob/main/NOTICE.md`}>NOTICE.md</ExternalLink>
          ). It comes with <strong>no warranty</strong>. The source code is at{" "}
          <ExternalLink href={REPOSITORY}>{REPOSITORY.replace("https://", "")}</ExternalLink>.
        </p>
        <p>
          The texts of the Learn-more pages are licensed under{" "}
          <ExternalLink href="https://creativecommons.org/licenses/by-sa/4.0/">
            CC BY-SA 4.0
          </ExternalLink>
          . The sounds and music you make with chaotic_sound are yours, for any use.
        </p>
        <h2>{t.aboutCredits}</h2>
        <p>
          System definitions and parameters from{" "}
          <ExternalLink href="https://github.com/GilpinLab/dysts">dysts</ExternalLink> (W. Gilpin).
          Built with React, React Flow, Zustand, three.js and KaTeX.
        </p>
      </dialog>
    </div>
  );
}
