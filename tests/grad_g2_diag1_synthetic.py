"""Synthetic G2-DIAG1 kernel outputs (small, analytic) for analyzer/verifier tests."""
import csv
import hashlib
import json
from pathlib import Path

G2_MESSAGE = "non-finite force/tangent at step 1200 (t=16.409412384033203)\nStacktrace:\n"
STAGES = [(1, "measure", ["sigma", "mu0"]), (9, "project1_solve", ["x", "r"]), (18, "project2_solve", ["x", "r"]),
          (20, "project2_bc", ["u", "p"]), (23, "force_candidate_pressure", ["x", "y", "z"])]
FLAGS = {k: False for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")}
PINS = {"julia/CFDSDFWaterLilyT4/Project.toml": "11" * 32, "scripts/x.jl": "22" * 32}
D0 = "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"
PHI = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
FREEZE = {"source_commit": "a" * 40, "pins": PINS, "directions": {"fortran_raw_sha256_d0_only": {"D0_interface_offset": D0}},
          "canonical_state": {"phi_fortran_sha256": PHI},
          "runtime_source_hashes": {"waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def u_log10(scenario, step, fail_step):
    if scenario in ("A", "A_in_solve", "F"):
        return 0.03 * step                      # roughly exponential: 0 .. ~36 decades
    if scenario == "B":
        return 3.0 + (33.0 if step >= fail_step - 1 else 0.0)   # flat, then one big jump
    return 2.0 + 0.001 * step                   # slow


def make_output(root, scenario="A", *, selfcheck_ok=True, exception=None, dryrun=False, flags=None):
    out = Path(root)
    out.mkdir(parents=True, exist_ok=True)
    notrepro = scenario == "notrepro"
    horizon = 1400
    fail_step = {"A": 1198, "A_in_solve": 1198, "B": 1198, "C": 1196, "D": 1198, "E": 1200, "F": 1198, "slow": 1198}.get(scenario, None)
    bad = None if notrepro else {"A": ("project2_bc", "u", "tangent"), "A_in_solve": ("project1_solve", "x", "tangent"), "F": ("project2_bc", "u", "primal"), "B": ("project2_bc", "u", "tangent"),
                                 "C": ("project1_solve", "x", "tangent"), "D": ("project2_bc", "u", "tangent"),
                                 "E": ("force_candidate_pressure", "x", "tangent"), "slow": ("project2_bc", "u", "tangent")}[scenario]
    last = horizon if notrepro else fail_step
    # stage ledger
    with (out / "stage_ledger.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["step", "stage_idx", "stage", "field", "n", "nonfinite_primal", "nonfinite_tangent", "maxabs_primal", "maxabs_tangent",
                    "rms_primal", "rms_tangent", "argmax_primal", "argmax_tangent"])
        for step in range(1, last + 1):
            for idx, stage, fields in STAGES:
                for field in fields:
                    hit = bool(bad and step == fail_step and (stage, field) == bad[:2])
                    nt = 1 if hit and bad[2] == "tangent" else 0
                    npr = 1 if hit and bad[2] == "primal" else 0
                    mt = 10.0 ** u_log10(scenario, step, fail_step) if field == "u" else 1.0 + 0.01 * step
                    w.writerow([step, idx, stage, field, 1000, npr, nt, 1.0, mt, 0.5, mt / 100, "3;4;5;1", "6;7;8;1"])
    with (out / "poisson_ledger.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["step", "stage", "iters", "dt_value", "dt_tangent", "r2_value", "r2_tangent"])
        for step in range(1, last + 1):
            for stage in ("project1_solve", "project2_solve"):
                w.writerow([step, stage, 32 if scenario == "C" else 5, 0.01, 0.0, 1e-5, 1e-3])
    force_cols = ["step", "t_u_l", "t_u_l_tan", "candidate_pressure_x", "candidate_pressure_x_tan", "ground_pressure_x", "ground_pressure_x_tan"]
    with (out / "force_ledger.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(force_cols)
        for step in range(1, last + 1):
            badf = scenario == "E" and step == fail_step
            w.writerow([step, 0.01 * step, 0.0, 10.0, "Inf" if badf else 5.0, 0.0, 0.0])
    # checksums
    for name, tweak in (("reference", False), ("instrumented", not selfcheck_ok)):
        with (out / f"{name}_checksums.csv").open("w", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(["step", "u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits"])
            for step in range(0, last + 1):
                w.writerow([step, step, step * 7, step, step * 3, 1, 2 + (1 if tweak and step == 500 else 0)])
    geo_bad = 3 if scenario == "D" else 0
    geo = {k: {"n": 10, "nonfinite_primal": 0, "nonfinite_tangent": geo_bad if k == "mu0" else 0, "min_primal": 0.0, "max_primal": 1.0,
               "min_tangent": -3.0, "max_tangent": 30.0, "top10_abs_tangent": []} for k in ("V", "mu0", "mu1", "sigma")}
    geo["derived"] = {"band_cells_abs_d_lt_3": 100}
    (out / "geometry_static_audit.json").write_text(json.dumps(geo))
    (out / "localization.json").write_text(json.dumps({"first_bad_cell": {"cell": [3, 4, 5], "in_band_abs_d_lt_3": scenario != "slow", "xyz_m": [0.1, 0.2, 0.3]}}))
    first_bad = None
    if bad:
        first_bad = {"step": fail_step, "time_step_start_u_l": 16.3, "stage": bad[0], "stage_index": [s for s in STAGES if s[1] == bad[0]][0][0], "field": bad[1],
                     "component": bad[2], "first_bad_element_class": "B_primal_finite_tangent_nonfinite" if bad[2] == "tangent" else "C_primal_nonfinite_tangent_finite", "first_bad_index": "3;4;5;1",
                     "first_nonfinite_primal": 0.1, "first_nonfinite_tangent": None, "first_nonfinite_primal_repr": "0.1", "first_nonfinite_tangent_repr": "Inf", "last_finite_maxabs_primal_same_field": 1.0,
                     "last_finite_maxabs_tangent_same_field": 1e30}
        (out / "first_bad.json").write_text(json.dumps(first_bad))
    ref_fail = None if notrepro else {"step": 1200, "message": G2_MESSAGE}
    ok = selfcheck_ok and exception is None
    verdict = "DIAG_NOT_REPRODUCED" if notrepro and ok else "DIAG_LOCALIZED" if ok else "DIAG_INCOMPLETE"
    (out / "selfcheck.json").write_text(json.dumps({"pass": selfcheck_ok, "sha256_mismatch_steps": [], "compared_steps": last + 1}))
    index = {"tier": "G2-DIAG1", "backend": "cuda", "dryrun": dryrun, "status": "COMPLETE" if ok else "INCOMPLETE", "verdict": verdict,
             "qualification_flags": flags or FLAGS, "waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32, "reference": {"fail": ref_fail, "steps_run": last},
             "instrumented": {"exception": exception, "first_bad": first_bad, "steps_run": last, "t_end_u_l": 19.0, "ground_decomposition": "available"}}
    (out / "diag_index.json").write_text(json.dumps(index))
    (out / "stage_order.json").write_text(json.dumps([{"index": i, "stage": s} for i, s, _ in STAGES]))
    (out / "snapshots").mkdir(exist_ok=True)
    snap = out / "snapshots" / "step0000.u.raw"
    snap.write_bytes(b"\x00" * 16)
    (out / "snapshot_index.json").write_text(json.dumps({"step0000.u.raw": {"sha256": sha(snap), "step": 0}}))
    (out / "run_identity.json").write_text(json.dumps({"source_commit": FREEZE["source_commit"], "verified": PINS, "direction_sha256": {"D0_interface_offset": D0},
                                                        "phi_sha256": PHI, "failure_stage": None if ok else "diagnostic"}))
    if ok:
        (out / "DONE").write_text("done\n")
    else:
        (out / "ERROR.txt").write_text("error\n")
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}))
    return out
