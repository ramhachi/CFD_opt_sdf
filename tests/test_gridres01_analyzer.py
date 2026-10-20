"""GRIDRES-01 analyzer: every verdict branch on synthetic tables, the guard-band edges, the residual INCOMPLETE rule, and the retained flow_24/flow_32 reproduction from the real CSVs."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_gridres01 as A  # noqa: E402
import gridres01_states as G  # noqa: E402


def table(a, b, bump=0.0, drag=(0.0, 0.0), base=0.33):
    """One grid's five-state table with downforce change a*s + b*s^2 (a bump added at +1.25 mm) and drag change drag[0]*s + drag[1]*s^2."""
    out = {G.PARENT_NAME: {"downforce_n": base, "drag_n": 0.32}}
    for s in G.STEPS_MM:
        out[G.state_name(s)] = {"downforce_n": base + a * s + b * s * s + (bump if s == 1.25 else 0.0), "drag_n": 0.32 + drag[0] * s + drag[1] * s * s}
    return out


T24, T32 = table(9.9e-5, -2.28e-4), table(4.75e-4, -7.6e-5)


def verdict(a, b, **kw):
    return A.report({"flow_24": T24, "flow_32": T32, "flow_40": table(a, b, **kw)}, "flow_40")


def test_fit_recovers_synthetic_coefficients_and_g_max_endpoint_and_vertex():
    fit = A.lsq({s: 3e-4 * s - 5e-5 * s * s for s in G.STEPS_MM})
    assert fit["a"] == pytest.approx(3e-4) and fit["b"] == pytest.approx(-5e-5) and fit["max_residual_n"] < 1e-15
    assert A.g_max(4e-5, 0.0) == pytest.approx(5e-5)                       # endpoint
    assert A.g_max(1e-4, -2.28e-4) == pytest.approx(1e-4 ** 2 / (4 * 2.28e-4))  # interior vertex at 0.22 mm
    assert A.g_max(-1e-4, -1e-4) == 0.0 and A.g_max(-1e-4, 5e-5) == 0.0   # never positive: the s -> 0 limit


@pytest.mark.parametrize("a,b,expected", [(4.75e-4, -7.6e-5, "FLOW40_SIDES_WITH_FLOW32"), (9.9e-5, -2.28e-4, "FLOW40_SIDES_WITH_FLOW24"), (3e-5, 0.0, "FLOW40_AMBIGUOUS"),
                                          (0.0, 0.0, "FLOW40_SIDES_WITH_FLOW24"), (-1e-4, 5e-5, "FLOW40_SIDES_WITH_FLOW24")])
def test_each_verdict_branch(a, b, expected):
    assert verdict(a, b)["verdict"] == expected  # a=3e-5, b=0: G_max = 3.75e-5, inside the guard band


def test_guard_band_edges_are_strict():
    up, dn = float(np.nextafter(A.HI_N, 1)), float(np.nextafter(A.LO_N, 0))
    assert [A.classify(x) for x in (up, A.HI_N, A.LO_N, dn)] == ["SIDES_WITH_FLOW32", "AMBIGUOUS", "AMBIGUOUS", "SIDES_WITH_FLOW24"]
    assert verdict(4e-5 / 1.25 * 1.001, 0.0)["verdict"] == "FLOW40_SIDES_WITH_FLOW32" and verdict(2e-5 / 1.25 * 0.999, 0.0)["verdict"] == "FLOW40_SIDES_WITH_FLOW24"


def test_a_fit_residual_above_2e_5_makes_the_run_incomplete_on_any_grid():
    assert verdict(4.75e-4, -7.6e-5, bump=1.5e-5)["verdict"] == "FLOW40_SIDES_WITH_FLOW32"   # residual below the limit stays decidable
    bad = verdict(4.75e-4, -7.6e-5, bump=1e-4)
    assert bad["verdict"] == "INCOMPLETE" and bad["max_downforce_fit_residual_n"] > A.RESIDUAL_MAX_N
    rep = A.report({"flow_24": table(9.9e-5, -2.28e-4, bump=1e-4), "flow_32": T32, "flow_40": table(4.75e-4, -7.6e-5)}, "flow_40")
    assert rep["verdict"] == "INCOMPLETE"


def test_flow_48_uses_the_same_code():
    rep = A.report({"flow_24": T24, "flow_32": T32, "flow_48": table(4.75e-4, -7.6e-5)}, "flow_48")
    assert rep["verdict"] == "FLOW48_SIDES_WITH_FLOW32" and rep["fine_grid"] == "flow_48"


def test_report_only_labels_and_acceptance_emulation_and_drag_fit():
    spread = 4.75e-4 - 9.9e-5
    beyond = verdict(4.75e-4 + 0.8 * spread, -7.6e-5)["report_only_labels"]   # past flow_32 by 0.8 of the 24-32 spread: not contracting, a third value
    assert beyond["contracting"] is False and beyond["third_value"] is True and beyond["ratios"]["a"] == pytest.approx(0.8, rel=1e-6)
    between = verdict(9.9e-5 + 0.45 * spread, -7.6e-5)["report_only_labels"]   # 0.55 of the spread from flow_32: contracting, within half of one of the two
    assert between["contracting"] is True and between["third_value"] is False
    near32 = verdict(4.8e-4, -7.7e-5)["report_only_labels"]
    assert near32["contracting"] is True and near32["third_value"] is False
    rep = verdict(4.75e-4, -7.6e-5, drag=(-1e-4, 2e-5))
    emu = rep["grids"]["flow_40"]["acceptance_emulation"]
    assert set(emu) == {"0.3125", "0.625", "1.25"} and all(v["accepted"] for v in emu.values())   # gain > 3e-5, drag change <= 0
    assert rep["grids"]["flow_40"]["fit"]["drag"]["a"] == pytest.approx(-1e-4) and rep["grids"]["flow_40"]["fit"]["drag"]["b"] == pytest.approx(2e-5)
    flat = verdict(1e-5, 0.0, drag=(1e-4, 0.0))["grids"]["flow_40"]["acceptance_emulation"]
    assert not any(v["accepted"] for v in flat.values())   # gain below 3e-5 N and a computed drag increase
    assert verdict(4.75e-4, -7.6e-5)["grids"]["flow_40"]["forward_fit"]["downforce"]["a"] == pytest.approx(4.75e-4)  # forward-only uses the three positive steps


def test_retained_flow_24_and_flow_32_fits_reproduce_the_plan_figures_from_the_real_csvs():
    t = A.retained_tables()
    r24, r32 = A.grid_report(t["flow_24"]), A.grid_report(t["flow_32"])
    f24, f32 = r24["fit"]["downforce"], r32["fit"]["downforce"]
    # the plan's figures come from the six retained states of each grid; the matched five-state subset is within a few percent
    assert f24["a"] == pytest.approx(9.9e-5, rel=0.03) and f24["b"] == pytest.approx(-2.28e-4, rel=0.03) and f24["max_residual_n"] < 6e-6
    assert f32["a"] == pytest.approx(4.75e-4, rel=0.03) and f32["b"] == pytest.approx(-7.6e-5, rel=0.03) and f32["max_residual_n"] < 1.1e-5
    assert r24["g_max_n"] == pytest.approx(1.1e-5, rel=0.06) and r32["g_max_n"] == pytest.approx(4.75e-4, rel=0.02)
    assert A.classify(r24["g_max_n"]) == "SIDES_WITH_FLOW24" and A.classify(r32["g_max_n"]) == "SIDES_WITH_FLOW32"
    assert not any(v["accepted"] for v in r24["acceptance_emulation"].values()) and all(v["accepted"] for v in r32["acceptance_emulation"].values())


def test_a_tampered_retained_csv_is_refused(tmp_path):
    import shutil
    root = tmp_path
    shutil.copytree(ROOT / G.OPT01B_REL, root / G.OPT01B_REL, ignore=shutil.ignore_patterns("*.raw", "*.log"))
    A.retained_tables(root)   # untampered copy passes the pinned-hash gates
    csv = root / G.OPT01B_REL / "kernel_output/opt01b_a/states/opt01b__parent/flow_24.forces.csv"
    csv.write_text(csv.read_text().replace("\n", "\n", 1) + "\n")
    with pytest.raises(ValueError, match="retained force CSV differs"):
        A.retained_tables(root)


def test_analyze_fails_closed_without_a_valid_freeze(tmp_path):
    rep = A.analyze("flow_40", tmp_path, {"kind": "nope"})
    assert rep["verdict"] == "INCOMPLETE" and rep["integrity"]["pass"] is False and rep["integrity"]["failures"]


# ---- check_kernel replayed over the REAL retained flow_32 kernel output (identity regenerated for flow_40) -------------------------------------------------------------------------------
import hashlib  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402

import build_gridres01_kernel as K  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

EV = ROOT / G.OPT01B_REL
INV = json.loads((ROOT / A.EVIDENCE_REL / "inventory.json").read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
CASE = "flow_40"
FREEZE = {"kind": A.FREEZE_KIND, "case_id": CASE, "source_commit": "0" * 40, "source_tree_id": "0" * 40, "inventory_sha256": sha(ROOT / A.EVIDENCE_REL / "inventory.json"), "pins": K.pins(CASE),
          "runtime": {**A.runtime_fixed(CASE), "kernel_id": K.KERNEL_IDS[CASE], "case_id": CASE, "runner_sha256": "0" * 64}}


POISSON_HEADER = "step,t_u_l,solves,iters_sum,iters_max,solves_at_cap,final_residual_l2,iters"


def poisson_csv(path, steps, iters=(7, 9), residual=5e-5):
    """A poisson CSV in the Julia probe's format: one row per force sample, `iters` the per-solve counts."""
    rows = [POISSON_HEADER] + [f"{st},{st * 0.01},{len(iters)},{sum(iters)},{max(iters)},{sum(v == 32 for v in iters)},{residual},{' '.join(map(str, iters))}" for st in steps]
    Path(path).write_text("\n".join(rows) + "\n")


def replay(tmp, mutate=None, after_manifest=None):
    """A five-state flow_40 output built from the real retained flow_32 OPT-01 Stage B run (real CSVs, GPU and identity files); the case fields of each summary are rewritten to flow_40 and its
    force summary recomputed with the flow_40 measurement, so that every integrity check runs on real bytes."""
    real, out = EV / "kernel_output/opt01b_b", Path(tmp) / "k"
    shutil.copytree(real, out, ignore=shutil.ignore_patterns("states", "output_manifest.json", "opt01b_index.json", "*.log"))
    ident = json.loads((out / "run_identity.json").read_text())
    ident.pop("baseline_csv_sha256", None)
    ident.update(kernel=CASE, kernel_id=K.KERNEL_IDS[CASE], case_id=CASE, source_commit=FREEZE["source_commit"], runner_sha256=FREEZE["runtime"]["runner_sha256"], pins=FREEZE["pins"], verified=FREEZE["pins"])
    (out / "run_identity.json").write_text(json.dumps(ident))
    cfg = INV["grids"][CASE]["measurement"]
    real_entries = {e["name"]: e for e in json.loads((real / "opt01b_index.json").read_text())["states"]}
    entries = []
    for row in INV["states"]:
        d, src = out / "states" / row["name"], real / "states" / row["name"]
        d.mkdir(parents=True)
        shutil.copy(src / "flow_32.forces.csv", d / f"{CASE}.forces.csv"); shutil.copy(src / "W4_JOB_DONE", d / "W4_JOB_DONE")
        poisson_csv(d / f"{CASE}.poisson.csv", A.csv_steps(d / f"{CASE}.forces.csv"))
        s = json.loads((src / "flow_32.summary.json").read_text())
        host = recompute_force_n(d / f"{CASE}.forces.csv", {"measurement": cfg})
        case = cfg["case"]
        s.update({"case_id": CASE, "cells_per_reference_length": G.GRIDS[CASE]["cells"], "flow_dims": case["flow_dims"], "flow_spacing_m": case["flow_spacing_m"], "solver_length": case["solver_length"],
                  "solver_time_unit_s": case["solver_time_unit_s"], "solver_viscosity": case["solver_viscosity"], "downforce_time_weighted_n": host["downforce_n"], "drag_time_weighted_n": host["drag_n"]})
        (d / f"{CASE}.summary.json").write_text(json.dumps(s))
        entries.append({**real_entries[row["name"]], "forces_csv_sha256": sha(d / f"{CASE}.forces.csv"), "poisson_csv_sha256": sha(d / f"{CASE}.poisson.csv")})
    # the instrumented parent reruns on flow_24 / flow_32: the real retained Stage B parent files (so byte-identical by construction), gpu uuid of this replay
    uuid = ident["selected_gpu"]["uuid"]
    reruns = []
    for rec in INV["grids"][CASE]["parent_reruns"]:
        g, src = rec["case_id"], EV / f"kernel_output/opt01b_{G.RETAINED_KERNEL[rec['case_id']]}/states/{G.PARENT_NAME}"
        d = out / "parent_reruns" / g
        d.mkdir(parents=True)
        shutil.copy(src / f"{g}.forces.csv", d / f"{g}.forces.csv"); shutil.copy(src / "W4_JOB_DONE", d / "W4_JOB_DONE")
        poisson_csv(d / f"{g}.poisson.csv", A.csv_steps(d / f"{g}.forces.csv"))
        s = json.loads((src / f"{g}.summary.json").read_text()); s["gpu_uuid"] = uuid
        (d / f"{g}.summary.json").write_text(json.dumps(s))
        reruns.append({**{k: real_entries[G.PARENT_NAME][k] for k in ("name", "kind", "direction", "step_mm", "sign")}, "exit_code": 0, "seconds": 300.0, "forces_csv_sha256": sha(d / f"{g}.forces.csv"),
                       "poisson_csv_sha256": sha(d / f"{g}.poisson.csv"), "complete": True, "case_id": g, "retained_forces_csv_sha256": rec["retained_forces_csv_sha256"], "byte_identical_to_retained": True})
    (out / "gridres01_index.json").write_text(json.dumps({"kernel": CASE, "kernel_id": K.KERNEL_IDS[CASE], "case_id": CASE, "states": entries, "parent_reruns": reruns, "status": "COMPLETE",
                                                          "solver_process_wall_seconds_total": sum(e["seconds"] for e in entries + reruns)}))
    if mutate:
        mutate(out)
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}))
    if after_manifest:
        after_manifest(out)
    return out


def test_check_kernel_replay_over_the_real_retained_output_passes(tmp_path):
    states = A.check_kernel(replay(tmp_path), CASE, FREEZE, INV)
    assert list(states) == list(G.NAMES)
    ret = A.retained_tables()["flow_32"]
    assert states[G.PARENT_NAME]["downforce_n"] == pytest.approx(ret[G.PARENT_NAME]["downforce_n"] * (0.02 / 0.025) ** 2, rel=1e-12)   # flow_40 force scale on the flow_32 solver forces


@pytest.mark.parametrize("name,mutate,match", [
    ("fc_swap", lambda o: (lambda p, s: (s.update(phi_fortran_sha256=s["phi_c_order_sha256"], phi_c_order_sha256=s["phi_fortran_sha256"]), p.write_text(json.dumps(s))))(
        o / "states" / G.state_name(0.625) / f"{CASE}.summary.json", json.loads((o / "states" / G.state_name(0.625) / f"{CASE}.summary.json").read_text())), "phi_fortran_sha256"),
    ("no_done", lambda o: (o / "DONE").unlink(), "DONE"),
    ("old_grid_dims", lambda o: (lambda p, s: (s.update(flow_dims=[200, 96, 72]), p.write_text(json.dumps(s))))(
        o / "states" / G.PARENT_NAME / f"{CASE}.summary.json", json.loads((o / "states" / G.PARENT_NAME / f"{CASE}.summary.json").read_text())), "grid dimensions"),
])
def test_integrity_negatives(tmp_path, name, mutate, match):
    with pytest.raises(ValueError, match=match):
        A.check_kernel(replay(tmp_path, mutate=mutate), CASE, FREEZE, INV)


def test_post_manifest_edit_and_budget_overrun_and_wrong_state_set_fail(tmp_path):
    with pytest.raises(ValueError, match="hash mismatch"):
        A.check_kernel(replay(tmp_path / "1", after_manifest=lambda o: (o / "nvidia_smi.csv").write_text("x")), CASE, FREEZE, INV)

    def slow(o):
        idx = json.loads((o / "gridres01_index.json").read_text()); idx["states"][2]["seconds"] = 1801.0
        idx["solver_process_wall_seconds_total"] = sum(e["seconds"] for e in idx["states"] + idx["parent_reruns"]); (o / "gridres01_index.json").write_text(json.dumps(idx))
    with pytest.raises(ValueError, match="exceeds budget"):
        A.check_kernel(replay(tmp_path / "2", mutate=slow), CASE, FREEZE, INV)

    def extra(o):
        (o / "states" / "opt01b__prop__s0.9375mm").mkdir()
    with pytest.raises(ValueError):
        A.check_kernel(replay(tmp_path / "3", mutate=extra), CASE, FREEZE, INV)


def test_end_to_end_replay_has_integrity_and_a_verdict_and_a_broken_input_is_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)   # registration is validated against the real freeze in test_gridres01_freeze
    r = A.analyze(CASE, replay(tmp_path), FREEZE, INV)
    assert r["integrity"]["pass"] is True and r["verdict"] == "FLOW40_SIDES_WITH_FLOW32" and set(r["grids"]) == {"flow_24", "flow_32", "flow_40"}   # 0.64 x the flow_32 forces: G_max about 3e-4 N
    assert r["grids"]["flow_40"]["g_max_n"] == pytest.approx(0.64 * r["grids"]["flow_32"]["g_max_n"], rel=1e-9) and r["no_gradient_claim"] is True
    assert set(r["poisson"]["per_run"]) == {"flow_24", "flow_32", "flow_40"} and set(r["poisson"]["per_run"]["flow_40"]) == set(G.NAMES) and r["poisson"]["label"] is None   # synthetic CSVs: 7/9 iterations, never at the cap
    assert r["verdict_reason"].startswith("G_max(flow_40)") and "poisson" not in next(iter(r["state_forces_n"]["flow_40"].values()))
    bad = A.analyze(CASE, tmp_path / "missing", FREEZE, INV)
    assert bad["integrity"]["pass"] is False and bad["verdict"] == "INCOMPLETE"


# ---- Amendment 2: H1 summary parsing, H2 byte-identity gate, H3 writable INCOMPLETE, the confound label ----------------------------------------------------------------------------------------
def test_poisson_summary_parses_cap_fraction_quantiles_and_refuses_inconsistent_files(tmp_path):
    p = tmp_path / "p.csv"
    lines = [POISSON_HEADER, "8,0.1,4,100,32,3,2e-4,32 32 32 4", "16,0.2,4,12,3,0,1e-5,3 3 3 3"]
    p.write_text("\n".join(lines) + "\n")
    sm = A.poisson_summary(p, [8, 16])
    assert (sm["samples"], sm["solves"], sm["solves_at_cap"], sm["cap_fraction"]) == (2, 8, 3, 3 / 8)
    assert sm["iterations"]["max"] == 32 and sm["iterations"]["min"] == 3 and sm["iterations"]["p50"] == pytest.approx(3.5) and sm["final_residual_l2"]["max"] == 2e-4 and sm["final_residual_l2"]["min"] == 1e-5
    for bad, match in (("\n".join([POISSON_HEADER, "8,0.1,4,100,32,3,2e-4,32 32 32 4", "16,0.2,4,12,3,0,1e-5,3 3 3 33"]), "cap|aggregates"),
                       ("\n".join([POISSON_HEADER, "8,0.1,4,99,32,3,2e-4,32 32 32 4"]), "aggregates"), ("\n".join([POISSON_HEADER, "8,0.1,4,100,32,3,nan,32 32 32 4"]), "residual"),
                       ("\n".join(["step,x"] + lines[1:]), "header"), (POISSON_HEADER, "no samples")):
        p.write_text(bad + "\n")
        with pytest.raises(ValueError, match=match):
            A.poisson_summary(p, [8, 16][:len(bad.splitlines()) - 1] or None)
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="do not match the force samples"):
        A.poisson_summary(p, [8, 24])


def test_parent_rerun_must_be_byte_identical_to_the_retained_csv_else_the_record_is_refused(tmp_path):
    A.check_kernel(replay(tmp_path / "0"), CASE, FREEZE, INV)   # byte-identical reruns pass

    def tamper(o, g="flow_24"):
        csv = o / "parent_reruns" / g / f"{g}.forces.csv"
        csv.write_text(csv.read_text() + "\n")   # one byte differs; the index is made consistent so only the retained-hash gate can catch it
        idx = json.loads((o / "gridres01_index.json").read_text())
        for e in idx["parent_reruns"]:
            e["forces_csv_sha256"] = sha(csv) if e["case_id"] == g else e["forces_csv_sha256"]
        (o / "gridres01_index.json").write_text(json.dumps(idx))
    for i, g in enumerate(("flow_24", "flow_32")):
        with pytest.raises(ValueError, match="not byte-identical to the retained Stage B"):
            A.check_kernel(replay(tmp_path / f"t{i}", mutate=lambda o, g=g: tamper(o, g)), CASE, FREEZE, INV)

    def missing(o):
        shutil.rmtree(o / "parent_reruns")
    with pytest.raises(ValueError):
        A.check_kernel(replay(tmp_path / "m", mutate=missing), CASE, FREEZE, INV)


def stats(frac, n=100):
    return {"cap_fraction": frac, "solves": n}


def test_poisson_confounded_label_threshold_is_strict_and_uses_the_worst_flow_40_state():
    def label(f24, f32, f40):
        return A.poisson_report({"flow_24": stats(f24), "flow_32": stats(f32), "flow_40": {n: stats(f) for n, f in zip(G.NAMES, f40)}}, "flow_40")["label"]
    assert G.POISSON_MATERIAL_ABS == 0.10
    assert label(0.0, 0.0, [0.0] * 5) is None
    assert label(0.10, 0.0, [0.0] * 5) is None                                  # excess exactly 0.10: not material
    assert label(0.1001, 0.0, [0.0] * 5) == "POISSON_CONFOUNDED"                # flow_24 saturates more than flow_32
    assert label(0.0, 0.0, [0.0, 0.0, 0.0, 0.0, 0.25]) == "POISSON_CONFOUNDED"  # one flow_40 state (the reverse state) saturates
    assert label(0.9, 0.9, [0.9] * 5) is None                                   # all saturate equally: the cap does not discriminate the grids
    assert label(0.0, 0.5, [0.0] * 5) is None                                   # flow_32 saturating more than the others is not a confound of this kind
    rep = A.poisson_report({"flow_24": stats(0.3), "flow_32": stats(0.1), "flow_40": {n: stats(0.1) for n in G.NAMES}}, "flow_40")
    assert rep["cap_fraction_excess_over_flow_32"]["flow_24"] == pytest.approx(0.2) and "multigrid" in rep["note"]


def residual_failing_analysis(monkeypatch, kernel_dir):
    """analyze() over a synthetic flow_40 table whose fit residual is above 2e-5 N (the quadratic model fails): integrity holds, the verdict is INCOMPLETE."""
    fine = {n: {**v, "poisson": {"cap_fraction": 0.0, "solves": 8, "solves_at_cap": 0, "samples": 1, "iterations": {}, "final_residual_l2": {}}} for n, v in table(4.75e-4, -7.6e-5, bump=1e-4).items()}
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)
    monkeypatch.setattr(A, "check_kernel", lambda *a, **k: fine)
    monkeypatch.setattr(A, "rerun_poisson", lambda *a, **k: {"flow_24": stats(0.0), "flow_32": stats(0.0)})
    (Path(kernel_dir) / "output_manifest.json").write_text("{}")
    return A.analyze(CASE, kernel_dir, FREEZE, INV)


def test_residual_gate_incomplete_is_written_with_all_deltas_fits_label_and_reason_while_integrity_failures_are_not(tmp_path, monkeypatch):
    r = residual_failing_analysis(monkeypatch, tmp_path)
    assert r["integrity"]["pass"] is True and r["verdict"] == "INCOMPLETE" and "flow_40" in r["verdict_reason"] and "2e-05" in r["verdict_reason"]
    assert set(r["grids"]) == {"flow_24", "flow_32", "flow_40"} and r["grids"]["flow_40"]["fit"]["downforce"]["max_residual_n"] > A.RESIDUAL_MAX_N and r["grids"]["flow_40"]["delta_n"]["downforce"]
    assert r["poisson"]["label"] is None and "disclosures" in r and "Multigrid-depth" in r["disclosures"]
    freeze = tmp_path / "freeze.json"
    freeze.write_text("{}"); freeze.with_name("freeze.json.sha256").write_text(A.sha256(freeze) + "\n")
    out, argv = tmp_path / "analysis.json", ["analyze", "--grid", CASE, "--kernel-dir", str(tmp_path), "--freeze", str(freeze), "--write", str(tmp_path / "analysis.json")]
    monkeypatch.setattr(A, "analyze", lambda *a, **k: r)
    monkeypatch.setattr(sys, "argv", argv)
    A.main()
    written = json.loads(out.read_text())
    assert written["verdict"] == "INCOMPLETE" and written["verdict_reason"] == r["verdict_reason"] and written["provenance"]["freeze_sha256"] == A.sha256(freeze)
    bad = {**r, "integrity": {"pass": False, "failures": ["x"]}, "verdict": "INCOMPLETE"}
    monkeypatch.setattr(A, "analyze", lambda *a, **k: bad)
    monkeypatch.setattr(sys, "argv", argv[:-1] + [str(tmp_path / "refused.json")])
    with pytest.raises(SystemExit) as exc:
        A.main()
    assert exc.value.code == 3 and not (tmp_path / "refused.json").exists()
