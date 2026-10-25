"""Screening batch B, step 6: Markdown summary of the builds (reads builds/*.json)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[3] / "outputs" / "studies" / "screening" / "batch_b"


def main() -> None:
    lines = [
        "| Job | Range (default) | rel. width | u_def | chaotic | windows | λ·P_ref @def | tuning | "
        "prom. obs @def / median / min | max ΔP step | P(u) span | pitch @def (6 seeds) | pitch @u=0.1 | pitch @u=0.9 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for f in sorted((OUT / "builds").glob("*.json")):
        r = json.loads(f.read_text())
        if not r.get("ok"):
            lines.append(f"| {r['job']} | build failed: {r['error']} |" + " |" * 12)
            continue
        obs = r["period_observable"]
        pr = r["pitch"]

        def spread(label: str) -> str:
            c = np.array(pr[label]["cents_centroid"])
            return f"{c.min():+.0f}…{c.max():+.0f} c"

        lines.append(
            f"| {r['job']} | [{r['p_min']:.4g}, {r['p_max']:.4g}] ({r['p_default']:g}) | {r['rel_width']:.2f} | "
            f"{r['u_default']:.2f} | {100 * r['chaotic_fraction']:.0f} % | {len(r['windows'])} | "
            f"{r['lyapunov_per_period_default']:.3f} | {obs}, {r['period_method']} | "
            f"{r['prominence_default'][obs]:.2f} / {r['prominence_table_median'][obs]:.2f} / {r['prominence_table_min'][obs]:.2f} | "
            f"{100 * r['max_period_step']:.1f} % | {r['period_range'][1] / r['period_range'][0]:.2f}× | "
            f"{spread('u_default')} | {spread('u0.1')} | {spread('u0.9')} |"
        )
    text = "\n".join(lines) + "\n"
    (OUT / "summary.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
