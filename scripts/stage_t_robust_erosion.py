"""Robust (eroded) three-field driver: reuses scripts/stage_t_filtered_ramp.py
(filter H/H.T, tanh projection, RAMP, chain_gradient, thickness_metrics)
unmodified, only repointing its output root to a NEW work/ directory so the
existing work/filtered_ramp/* trees stay untouched (read-only inputs).

Objective is driven on the ERODED design: physical(ctx, rho, q) already
projects at ctx.eta (set by setup(width_m, eta=eta_e) with eta_e > 0.5), and
chain_gradient already evaluates dproject at that same eta_e before H.T. This
script does not re-derive that math; it only calls it with eta_e > 0.5 and a
deliberately chosen b (see README note printed by `params`).

Phases: params | fd <w> <eta> <q> <b> | optimize <w> <eta> <q_csv> <b_csv> <steps_csv> <v_final> [resume]
        | geom <w> <eta> <cids_csv> | stagev <w> <eta> <cids_csv>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stage_t_filtered_ramp as ftr  # noqa: E402

NEW_ROOT = ROOT / "work" / "robust_erosion"
ftr.SWEEP_ROOT = NEW_ROOT  # only this line diverts output; setup()/phase_* bodies are untouched


def params(width_m: float, eta: float) -> None:
    ctx = ftr.setup(width_m, eta)
    R = ctx.filter.radius_cells
    print(f"width_m={width_m} radius_cells={R} eta_e={eta}")
    print("1D estimate (rho_tilde crosses eta_e at slab centre):",
          ctx.filter.meta["predicted_min_slab_thickness_cells_1d_estimate"], "cells")


if __name__ == "__main__":
    phase = sys.argv[1]
    if phase == "params":
        params(float(sys.argv[2]), float(sys.argv[3]))
    elif phase == "fd":  # fd <w> <eta> <q> <b>
        ctx = ftr.setup(float(sys.argv[2]), float(sys.argv[3]))
        ftr.phase_fd(ctx, float(sys.argv[4]), float(sys.argv[5]))
    elif phase == "optimize":  # optimize <w> <eta> <q_csv> <b_csv> <steps_csv> <v_final> [resume]
        ctx = ftr.setup(float(sys.argv[2]), float(sys.argv[3]))
        ftr.phase_optimize(ctx, [float(x) for x in sys.argv[4].split(",")],
                            [int(x) for x in sys.argv[6].split(",")], float(sys.argv[7]),
                            resume_from=(sys.argv[8] if len(sys.argv) > 8 and sys.argv[8] != "-" else None),
                            b_schedule=[float(x) for x in sys.argv[5].split(",")])
    elif phase == "geom":  # geom <w> <eta> <cids_csv>
        ctx = ftr.setup(float(sys.argv[2]), float(sys.argv[3]))
        ftr.phase_geom(ctx, sys.argv[4].split(","))
    elif phase == "stagev":  # stagev <w> <eta> <cids_csv>
        ctx = ftr.setup(float(sys.argv[2]), float(sys.argv[3]))
        ftr.phase_stagev(ctx, sys.argv[4].split(","))
    else:
        raise SystemExit(__doc__)
