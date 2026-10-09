"""Synthetic G2-DIAG5 output directories (small, analytic) for analyzer tests."""
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts import analyze_grad_g2_diag5 as A

FLAGS = {k: False for k in A.FLAGS}
RUNTIME = {"waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32, "waterlily_poisson_jl_sha256": "55" * 32}
PINS = {"scripts/x.jl": "11" * 32}
E3_HEADER = ["eps", "lambda", "region", "rel", "cos", "ratio", "norm_jvp", "norm_fd", "max_jvp", "max_fd", "flip_rate_box_predict", "flip_rate_box_correct", "flip_rate_all_predict",
             "flip_rate_all_correct", "mismatch_share_in_flip_cells_d1", "mismatch_share_in_flip_cells_d2", "flip_cell_fraction_d1", "flip_cell_fraction_d2", "gain_jvp_box_max", "gain_fd_box_max"]
E5_HEADER = ["variant", "eps", "step", "gmax", "imax", "bmax", "l2_int", "l2_box", "argmax", "argmax_box", "u_xor", "u_sum"]
SCENARIOS = {
    # smooth at small eps, mismatch concentrated at flips, surrogate closes it, finite growth well below the AD growth, ulp sensitive
    "R1": dict(rel_by_eps={1e-6: 0.04, 1e-5: 0.05, 1e-4: 0.6, 1e-3: 0.7, 1e-2: 0.9}, flip_by_eps={1e-6: 0.0, 1e-5: 0.005, 1e-4: 0.06, 1e-3: 0.15, 1e-2: 0.3}, share=0.9, frac=0.3,
               tie_rel=0.05, fd_rate=0.03, ad_rate=0.1, tie_rate=0.035, ulp=0.2),
    # AD agrees with FD at every amplitude and the finite growth equals the AD growth
    "R3": dict(rel_by_eps={e: 0.03 for e in A.EPS_E3}, flip_by_eps={1e-6: 0.0, 1e-5: 0.0, 1e-4: 0.02, 1e-3: 0.04, 1e-2: 0.08}, share=0.3, frac=0.3, tie_rel=0.03, fd_rate=0.1, ad_rate=0.1, tie_rate=0.1, ulp=0.001),
    # AD and FD disagree where the map is smooth (no flips)
    "R2": dict(rel_by_eps={1e-6: 0.5, 1e-5: 0.5, 1e-4: 0.5, 1e-3: 0.5, 1e-2: 0.5}, flip_by_eps={e: 0.0 for e in A.EPS_E3}, share=0.0, frac=0.0, tie_rel=0.5, fd_rate=0.03, ad_rate=0.1, tie_rate=0.1, ulp=0.001),
    # nothing fits
    "R4": dict(rel_by_eps={1e-6: 0.04, 1e-5: 0.05, 1e-4: 0.2, 1e-3: 0.2, 1e-2: 0.3}, flip_by_eps={1e-6: 0.0, 1e-5: 0.005, 1e-4: 0.06, 1e-3: 0.15, 1e-2: 0.3}, share=0.5, frac=0.3, tie_rel=0.19, fd_rate=0.06, ad_rate=0.1, tie_rate=0.1, ulp=0.001),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path, header, rows):
    with Path(path).open("w", newline="") as handle:
        w = csv.writer(handle); w.writerow(header); w.writerows(rows)


def status(group, state, **kw):
    d = {"tier": "G2-DIAG5", "state": state, "group": group, "dryrun": False, "k_steps": A.K_STEPS, "threads": 1, "status": "COMPLETE", "qualification_flags": FLAGS, **RUNTIME}
    d.update(kw)
    return d


def e5_rows(variant, eps, rate, start=1.0, tag=0):
    rows = []
    for k in range(A.K_STEPS + 1):
        l2 = start * 10 ** (rate * k)
        rows.append([variant, eps, k, l2 * 2, l2 * 2, l2, l2 * 3, l2, "1;1;1;1", "6;4;51;1", 100 + k, 1000 + k + tag])
    return rows


def jstr(e):
    """Julia's string of a Float64: 1.0e-6 / 1.0e-5 / 0.0001 / 0.001 / 0.01 (Python prints 1e-06 / 1e-05)."""
    if e >= 1e-4:
        return str(e)
    mant, exp = f"{e:e}".split("e")
    return f"{float(mant):.1f}e{int(exp)}"


def make_output(root, scenario="R1", *, break_gate=None, freeze_pins=True, dryrun=False, overrides=None, drop_e3_eps=None, nan_row=False, e6_n=None):
    sc = {**SCENARIOS[scenario], **(overrides or {})}
    out = Path(root); out.mkdir(parents=True, exist_ok=True)

    def put(state, group, result, csvs=None, **st):
        if state in A.STATES and "dt_closure" not in result:
            result = {**result, "dt_closure": {"stored_value": 0.33, "cfl_value": 0.33, "stored_tangent": 1e8, "cfl_tangent": 1e8 * (1 + (1e-2 if break_gate == "dt" else 1e-7))}}
        d = out / A.tag(state, group); d.mkdir(parents=True, exist_ok=True)
        (d / "status.json").write_text(json.dumps(status(group, state, **({"dryrun": True} if dryrun else {}), **st)))
        (d / "result.json").write_text(json.dumps(result))
        for name, (header, rows) in (csvs or {}).items():
            write_csv(d / name, header, rows)

    put("R1188", "E0", {"group": "E0", "dt_input": {"stored_tangent_scaled": 7.5e-8, "cfl_tangent": 7.5e-8, "stored_value": 0.33, "cfl_value": 0.33},
                        "dt_output": {"stored_tangent_scaled": 8.66e-8, "cpu_tangent": 8.66e-8 * (1 + (1e-2 if break_gate == "e0" else 1e-7))},
                        "primal_u": {"rel": 3.6e-6}, "primal_p": {"rel": 1.2e-4}, "ghost_closure": {"ghost_entries": 10, "ghost_entries_changed_by_BC": 3}, "gain_box_max": {"cpu": 1.12, "stored_t4": 1.32}})
    for state in A.STATES:
        rows = []
        for e in A.EPS_E3:
            if e == drop_e3_eps:
                continue
            flip = sc["flip_by_eps"][e]
            for lam in A.LAMBDAS:
                rel = sc["rel_by_eps"][e] if lam in ("quick", "linear") else (sc["tie_rel"] if e >= 1e-4 else sc["rel_by_eps"][e])
                agree = rel <= A.AGREE_REL
                cos = 0.999 if agree else 0.8
                ratio = 1.0 if agree else 0.75
                if nan_row and e == 1e-3 and lam == "quick":
                    rel = float("nan")
                for region in ("box", "interior"):
                    rows.append([e, lam, region, rel, cos, ratio, 10, 10, 5, 5, flip, flip, flip / 10, flip / 10, sc["share"], sc["share"], sc["frac"], sc["frac"],
                                 1.12 if lam == "quick" else 1.0, 1.0])
        e3 = {"group": "E3"}
        for e in A.EPS_E3:
            for lam in A.LAMBDAS:
                e3[f"primal_bits_{jstr(e)}_{lam}"] = [1, 2] if not (break_gate == "e3" and lam == "tie1e-4") else [3, 4]
        put(state, "E3", e3, {"e3_rows.csv": (E3_HEADER, rows)})
        put(state, "E3C", {**e3, "group": "E3C"}, {"e3c_rows.csv": (E3_HEADER, rows)})
        ad_rows = []
        for lam in A.LAMBDAS:
            rate = {"quick": sc["ad_rate"], "tie1e-5": sc["tie_rate"], "tie1e-4": sc["tie_rate"], "linear": sc["ad_rate"]}[lam]
            ad_rows += e5_rows("AD/" + lam, 0.0, rate, tag=1 if (break_gate == "e5ad" and lam == "tie1e-5") else 0)
        ad_rows += e5_rows("ADC/quick", 0.0, sc["ad_rate"])
        put(state, "E5AD", {"group": "E5AD", "instrumented_step_bit_identical_to_sim_step": break_gate != "ident"}, {"e5ad_rows.csv": (E5_HEADER, ad_rows)})
        for e in A.EPS_E5:
            variants = [("A", sc["fd_rate"])] + ([("B", sc["fd_rate"]), ("C", sc["fd_rate"])] if e in A.EPS_E5_VARIANT_B else [])
            rows = []
            for v, r in variants:
                rows += e5_rows("FD/" + v, e, r)
            if break_gate == "fd_incomplete" and e == "1e-3":
                rows = rows[:-5]
            put(state, f"E5FD:{e}", {"group": "E5FD"}, {"e5fd_rows.csv": (E5_HEADER, rows)})
        n = e6_n if e6_n is not None else A.ENSEMBLE_N
        put(state, "E6", {"group": "E6", "gain_baseline": 1.12, "gains": [1.1 + 0.04 * (i % 2) for i in range(n)], "pattern_changes": [sc["ulp"] * (1 + 0.2 * (i % 2)) for i in range(n)], "fd_changes": [0.01] * n})
        put(state, "E2", {"group": "E2", "predict_conv": {"box": {"fluxes": 100, "branch_counts": [50, 30, 10, 0, 10]}}, "correct_conv": {"box": {"fluxes": 100}}})
        stage = [["full/quick", "input", "u", 1, 1, 1, 10, 5, "", ""], ["full/quick", "input", "dt", 0.1, 0, 0, 0, 0, "", ""], ["full/quick", "predict_bdim", "u", 2, 2, 2, 25, 12, "1;1;1;1", "6;4;51;1"]]
        (out / A.tag(state, "E1")).mkdir(parents=True, exist_ok=True)
        write_csv(out / A.tag(state, "E1") / "e1_stages.csv", ["variant", "stage", "field", "max_all", "max_interior", "max_box", "l2_interior", "l2_box", "argmax", "argmax_box"], stage)
        terms = [["full/quick", "predict_conv", 1, 1, "fld", "interior", 2, 6, 7, 8], ["full/quick", "predict_conv", 0, 0, "closure", "all", 1, 1, 1, 1e-8],
                 ["full/quick", "predict_bdim", 0, 0, "dt_df", "bdim", 1, 5, 5, 5]]
        write_csv(out / A.tag(state, "E1") / "e1_terms.csv", ["variant", "call", "i", "j", "role", "region", "max_box", "l2_box", "l2_interior", "max_all_or_closure"], terms)
        put(state, "E1", {"group": "E1"})
    drv = {"tier": "G2-DIAG5", "source_commit": "a" * 40, "pins": PINS if freeze_pins else {}, "status": "COMPLETE", "processes": []}
    (out / "driver_index.json").write_text(json.dumps(drv))
    (out / "DONE").write_text("x\n")
    return out


def freeze_for(analyzer_path):
    return {"source_commit": "a" * 40, "pins": PINS, "runtime_source_hashes": RUNTIME, "file_hashes": {"analyzer": sha(analyzer_path)}}
