#!/usr/bin/env python3
"""T2-0a (#57, EXPLORATORY_COMMITTED): tabulate the kernel output. Reads forceCoeffs summaries already written by the kernel (nothing physical is recomputed),
puts Cl/Cd vs h/c per model next to Genua's OpenFOAM values and the quoted experimental Cl, and reports timing. Descriptive only: no threshold, no verdict."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data/t20/reference_genua2009.json"
GENUA = {"sa-wf": "Med30SA", "sst-wf": "Med30KWS"}   # nearest Genua case (same mesh spec Med30, wall function); sst-lm has no counterpart


def load(out: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((out / "cases").glob("*/case_result.json")) if not p.parent.name.endswith("_smoke")]


def genua_value(ref: dict, model: str, h: float, key: str):
    name = GENUA.get(model)
    if not name:
        return None
    sweep = ref["genua_ride_height_sweep"]["cases"].get(name, {}).get(f"{h}")
    if sweep:
        return sweep[key]
    t6 = ref["genua_table6_cases"]["cases"].get(name, {})
    return t6.get(f"Cl_h{h}") if key == "Cl" else None


def pct(a, b):
    return None if a is None or b in (None, 0) else 100.0 * (a - b) / b


def fmt(v, spec=".3f"):
    return "-" if v is None else format(v, spec)


def report(cases: list[dict], ref: dict) -> str:
    exp = ref["experimental"]["Cl"]
    lines = ["# T2-0a result tables (descriptive; EXPLORATORY_COMMITTED, no verdict)", "",
             "Cl = downforce coefficient, Cd drag, per unit span, reference chord. Ours = mean over the last 20 % of iterations (kernel `forces.Cl.tail_mean`).",
             "Genua = his Med30 case with the same turbulence-model family (sa-wf: Med30SA full sweep; sst-wf: Med30KWS, h/c 0.224 and 0.09 only). diff = (ours - Genua)/Genua.", ""]
    for model in sorted({c["model"] for c in cases}):
        lines += [f"## {model}", "", "| h/c | mesh | status | Cl ours | Cl Genua | diff % | Cl exp | diff vs exp % | Cd ours | Cd Genua | diff % | iters | plateau | res.conv | wall min |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in sorted((c for c in cases if c["model"] == model), key=lambda c: -c["h_over_c"]):
            f, h = c.get("forces"), c["h_over_c"]
            cl, cd = (f["Cl"]["tail_mean"], f["Cd"]["tail_mean"]) if f else (None, None)
            g_cl, g_cd, e = genua_value(ref, model, h, "Cl"), genua_value(ref, model, h, "Cd"), exp.get(f"{h}")
            lines.append(f"| {h} | {c['mesh']} | {c['status']} | {fmt(cl)} | {fmt(g_cl)} | {fmt(pct(cl, g_cl), '.1f')} | {fmt(e)} | {fmt(pct(cl, e), '.1f')} | "
                         f"{fmt(cd, '.4f')} | {fmt(g_cd, '.4f')} | {fmt(pct(cd, g_cd), '.1f')} | {c.get('solver', {}).get('iterations', '-')} | "
                         f"{f['force_plateau'] if f else '-'} | {c.get('residual_converged', '-')} | {fmt(c.get('total_wall_s', 0) / 60, '.1f')} |")
        lines.append("")
    done = [c for c in cases if "forces" in c]
    cl = {c["model"]: {} for c in done}
    for c in done:
        cl[c["model"]][c["h_over_c"]] = c["forces"]["Cl"]["tail_mean"]
    lines += ["## Cl peak location (h/c at the largest Cl among the heights run; Genua and the experiment place it at 0.134)", ""]
    lines += [f"- {m}: {max(v, key=v.get)}  (heights run: {sorted(v, reverse=True)})" for m, v in sorted(cl.items())]
    lines += ["", "## Mesh and timing", "", "| case | cells | max non-orth | max skew | max AR | checkMesh failed counts | solver wall min | total wall min | peak RSS MB |", "|---|---|---|---|---|---|---|---|---|"]
    for c in sorted(cases, key=lambda c: c["id"]):
        m, sw = c.get("check_mesh", {}), next((s["wall_s"] for s in c.get("stages", []) if s["stage"] == "simpleFoam"), None)
        rss = max((s.get("peak_rss_mb_sampled") or 0 for s in c.get("stages", [])), default=0)
        lines.append(f"| {c['id']} | {m.get('cells', '-')} | {m.get('max_non_orthogonality', '-')} | {m.get('max_skewness', '-')} | {m.get('max_aspect_ratio', '-')} | "
                     f"{m.get('failed_check_counts', '-')} | {fmt(None if sw is None else sw / 60, '.1f')} | {fmt(c.get('total_wall_s', 0) / 60, '.1f')} | {fmt(rss, '.0f')} |")
    lm = [c for c in cases if c["status"] == "LM_DIVERGED"]
    if lm:
        lines += ["", "## kOmegaSSTLM failures (LM_DIVERGED is a recorded result, not a kernel failure)", "", "| case | failed stage | last time | sigfpe | nan | last initial residuals |", "|---|---|---|---|---|---|"]
        for c in lm:
            s = (c.get("lm_diagnostics") or {}).get("solver") or {}
            lines.append(f"| {c['id']} | {c.get('lm_failed_stage')} | {s.get('last_time', '-')} | {s.get('sigfpe', '-')} | {s.get('nan_in_log', '-')} | {s.get('last_initial_residuals', '-')} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("kernel_output", type=Path)
    ap.add_argument("--reference", type=Path, default=REF)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if (a.kernel_output / "meshcheck.md").is_file():   # MESH_ONLY kernel: the table is the whole result
        text = "# T2-0a mesh-only check (checkMesh next to the local proxy)\n\n" + (a.kernel_output / "meshcheck.md").read_text()
    else:
        text = report(load(a.kernel_output), json.loads(a.reference.read_text()))
    (a.out.write_text(text) if a.out else print(text))


if __name__ == "__main__":
    main()
