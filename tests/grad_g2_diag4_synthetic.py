"""Synthetic G2-DIAG4 kernel outputs (small, analytic) for analyzer tests."""
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts import analyze_grad_g2_diag4 as A

FLAGS = {k: False for k in A.FLAGS}
PINS = {"julia/CFDSDFWaterLilyT4/Project.toml": "11" * 32, "scripts/x.jl": "22" * 32}
D0 = "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"
PHI = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
FREEZE = {"file_hashes": {"analyzer": hashlib.sha256(Path(A.__file__).read_bytes()).hexdigest()}, "source_commit": "a" * 40, "pins": PINS, "directions": {"fortran_raw_sha256_d0_only": {"D0_interface_offset": D0}}, "canonical_state": {"phi_fortran_sha256": PHI},
          "runtime_source_hashes": {"waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32, "waterlily_poisson_jl_sha256": "55" * 32}}
VCS = ["u_val_xor", "u_val_sum", "p_val_xor", "p_val_sum", "dt_val_bits"]
HEADER = ["step", "t_u_l", "glob_max_tangent_u", "box_max_tangent_u", "glob_energy_tangent", "box_energy_tangent", "argmax_tangent_u", "glob_max_primal_u", "nonfinite_primal_u",
          "nonfinite_tangent_u", "inc_max", "inc_energy_glob", "inc_energy_box", "inc_argmax", "iters1", "iters2", "res_primal_last", "res_tangent_last", "fx", "fx_tan", "fz", "fz_tan",
          *A.CS_COLUMNS, *VCS]
CMP_HEADER = ["step", "rel_l2_u", "rel_l2_p", "max_abs_du", "argmax_du", "max_abs_dp", "argmax_dp", "box_rel_l2_u", "box_max_abs_du", "box_max_abs_dp", "drag_rel_diff", "downforce_rel_diff"]
FLOOR = 21.0
BODY = "89;37;36;1"
CORNER = "6;4;51;1"
OUTSIDE = "24;61;40;1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cs(step, tag=0):
    return [step * 2 + tag, step * 3, step * 5, step * 7, 11, 13]


def profile(kind, onset=None, rate=0.1, location=CORNER, spike=True):
    """box / glob series of one arm: 'stable' (bounded, spiky), 'grow' (exponential from `onset`), the location of the growing mode."""
    def f(step):
        box, glob, arg = 1.3e-2, FLOOR, BODY
        if spike and step % 97 == 0:
            box, glob = 2.1e-1, 210.0
        if kind == "grow" and step >= onset:
            amp = 1.3e-2 * 10 ** (rate * (step - onset))
            if location == CORNER:
                box = max(box, amp)
            glob = max(glob, amp)
            if amp > FLOOR:
                arg = location
        return box, glob, arg
    return f


def make_output(root, *, fork=None, fresh=None, b0=None, ref_break=None, status="COMPLETE", dryrun=False, flags=None, end=A.END_STEP, fork_stops=None, monkeypatch=None):
    """Writes a kernel-like output directory; returns (out, straight_ref_path, f32_ref_path)."""
    out = Path(root); out.mkdir(parents=True, exist_ok=True)
    arms = {"B0": b0 or profile("grow", onset=815), "B32fork": fork or profile("stable"), "B32fresh": fresh or profile("stable")}
    for name, f in arms.items():
        first = 1 if name != "B32fork" else A.FORK_STEP + 1
        last = end if not (name == "B32fork" and fork_stops) else fork_stops
        with (out / f"arm_{name}.steps.csv").open("w", newline="") as handle:
            w = csv.writer(handle); w.writerow(HEADER)
            for step in range(first, last + 1):
                box, glob, arg = f(step)
                nft = 1 if (name == "B32fork" and fork_stops and step == fork_stops) else 0
                body_e, box_e = 1e6 * 441.0, 1e-4 * 1e-4 * 100
                if arg == CORNER:
                    box_e = glob ** 2 * 50.0
                elif arg == OUTSIDE:
                    body_e = glob ** 2 * 50.0
                w.writerow([step, 0.011 * step, glob, box, body_e + box_e, box_e, arg, 1.2, 0, nft, glob, 1.0, 0.5, arg, 1, 1, 1e-6, 1e-4, 100.0, 1.0, -50.0, 1.0,
                            *cs(step, 1 if (ref_break == name and step == 900) else 0), 1, 2, 3, 4, 5])
    ref_s, ref_f = out.parent / (out.name + "_ref_straight.csv"), out.parent / (out.name + "_ref_f32.csv")
    for path, steps, tag in ((ref_s, range(0, A.REF_LAST_STEP + 1), "straight"), (ref_f, range(A.FORK_STEP + 1, A.REF_LAST_STEP + 1), "f32")):
        with path.open("w", newline="") as handle:
            w = csv.writer(handle); w.writerow(["step", *A.CS_COLUMNS])
            for step in steps:
                w.writerow([step, *cs(step)])
    for n in ("B32fork_vs_B0", "B32fresh_vs_B0", "B32fresh_vs_B32fork"):
        with (out / f"cmp_{n}.csv").open("w", newline="") as handle:
            w = csv.writer(handle); w.writerow(CMP_HEADER)
            for step in range(A.FORK_STEP + 1, end + 1):
                w.writerow([step, 1e-6 * (step - 700), 5e-4, 1e-4 * step / 1000, "86;31;25;3", 1e-2, "151;36;55", 2e-6, 1e-5, 1e-2, 1e-5, 2e-5])
    index = {"tier": "G2-DIAG4", "backend": "cuda", "dryrun": dryrun, "no_reference": False, "status": status, "verdict": "DIAG4_RECORDED" if status == "COMPLETE" else "DIAG4_INCOMPLETE",
             "fork_step": A.FORK_STEP, "end_step": A.END_STEP, "forced_iterations": 32, "reference_last_step": A.REF_LAST_STEP, "qualification_flags": flags or FLAGS,
             "waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32, "waterlily_poisson_jl_sha256": "55" * 32,
             "clone_bit_identical_at_fork": True, "independence_checked": True,
             "result": {a: {"alive_at_end": not (a == "B32fork" and fork_stops), "tangent_valid": True} for a in A.ARMS}}
    (out / "diag_index.json").write_text(json.dumps(index))
    (out / "run_identity.json").write_text(json.dumps({"source_commit": FREEZE["source_commit"], "verified": PINS, "direction_sha256": {"D0_interface_offset": D0}, "phi_sha256": PHI,
                                                        "failure_stage": None, "spike_exit_code": 0}))
    (out / ("DONE" if status == "COMPLETE" else "ERROR.txt")).write_text("x\n")
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}))
    if monkeypatch is not None:
        monkeypatch.setattr(A, "REF_STRAIGHT", ref_s); monkeypatch.setattr(A, "REF_F32", ref_f)
    return out
