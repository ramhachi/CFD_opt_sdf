"""Synthetic five-kernel GRID-02 outputs built from the real inventory (structure copied from the retained OPT-01 Stage B summaries); no CFD, no network."""
from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import analyze_grid02 as A  # noqa: E402
import build_grid02_kernel as K  # noqa: E402
import freeze_grid02 as F  # noqa: E402
from cfd_sdf import grid02_contract as C  # noqa: E402
from fd08_v2_campaign_io import FORCE_COLUMNS, recompute_force_n  # noqa: E402

UUID = "GPU-synthetic-physical-index-zero"
BASE = {"f16": 0.2545, "s24": 0.34, "s32": 0.37, "f48a": 0.39}
DRAG0 = 0.30
INVENTORY = json.loads((ROOT / A.EVIDENCE_REL / "inventory.json").read_text())
NATIVE = {c: {n: {"downforce_n": f["downforce_n"], "drag_n": f["drag_n"]} for n, f in v.items()} for c, v in INVENTORY["native_reference"]["state_forces_n"].items()}


def real_b(case):
    nat = NATIVE[case]
    return C.fit_quadratic(list(C.FORWARD_MM), [nat[n]["downforce_n"] - nat[C.PARENT]["downforce_n"] for n in C.FORWARD])["b_n_per_mm"]


B24, B32 = real_b("flow_24"), real_b("flow_32")
G = B32 - B24


def targets(m24=0.6, m32=0.6, r=0.7):
    """Slopes realising chosen alignment movements and the fine position against the real native 24n/32n slopes."""
    return {"16n": (2e-4, -2e-4), "24s": (B24 + m24 * G, -1.5e-4), "32s": (B32 - m32 * G, -1.0e-4), "48n": (B24 + r * G, -1.0e-4)}


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def identity_proof(extra=None):
    proof = {"kind": "grid02_authenticated_identity_free_check", "owner": "ramhachi888", "all_free": True, "kernel_ids": list(K.KERNEL_IDS.values()),
             "captured_utc": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), "listings": {}, "positive_controls": {}}
    for kind in ("kernels", "datasets"):
        rows = [{"ref": "ramhachi888/existing-synthetic-resource", "title": "existing synthetic resource"}] + ([{"ref": extra, "title": "x"}] if extra else [])
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=("ref", "title"))
        writer.writeheader(); writer.writerows(rows)
        proof["listings"][kind] = {"complete": True, "rows": rows, "pages": [{"command": ["kaggle", kind, "list", "--mine", "--page-size", "100", "--page", "1", "--csv"],
                                                                                "exit_code": 0, "stdout": buffer.getvalue(), "stderr": "", "rows": rows}]}
        command = ["kaggle", kind, "status", rows[0]["ref"]] if kind == "kernels" else ["kaggle", kind, "files", rows[0]["ref"], "--csv"]
        proof["positive_controls"][kind] = {"command": command, "exit_code": 0, "stdout": "existing resource accessible", "stderr": ""}
    return proof


@pytest.fixture(scope="module")
def registered(tmp_path_factory, request):
    """A separate Git repository binds the real reviewed inputs; modules are re-pointed at it."""
    root = tmp_path_factory.mktemp("grid02-source")
    paths = A.required_file_paths(INVENTORY)
    for rel in paths:
        src, dst = ROOT / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst) if src.is_file() else dst.write_text("synthetic pinned registration input\n")
    proof_path = root / A.EVIDENCE_REL / "identity_free_check.json"
    proof = identity_proof()
    dump(proof_path, proof)
    proof_path.with_name(proof_path.name + ".sha256").write_text(A.sha256(proof_path) + "\n")
    git(root, "init", "-q"); git(root, "config", "user.name", "GRID-02 synthetic test"); git(root, "config", "user.email", "grid02-test@example.invalid")
    git(root, "add", "."); git(root, "commit", "-qm", "synthetic registration source")
    commit = git(root, "rev-parse", "HEAD")
    remote = tmp_path_factory.mktemp("grid02-remote")  # a real (local bare) remote: the freeze script checks `git ls-remote`, not the local remote-tracking cache
    git(remote, "init", "-q", "--bare")
    git(root, "remote", "add", "origin", str(remote)); git(root, "push", "-q", "origin", "HEAD:refs/heads/main")
    patch = pytest.MonkeyPatch()
    request.addfinalizer(patch.undo)
    for mod, name, value in ((A, "ROOT", root), (A, "PARENT_COMMIT", commit), (K, "ROOT", root), (K, "EVIDENCE", root / A.EVIDENCE_REL), (K, "TEMPLATE", root / "scripts/grid02_runner_template.py"),
                             (F, "ROOT", root), (F, "E", root / A.EVIDENCE_REL), (F, "IDENTITY", proof_path)):
        patch.setattr(mod, name, value)
    freeze = {"kind": A.FREEZE_KIND, "parent_integration_commit": commit, "source_commit": commit, "frozen_utc": datetime.now(timezone.utc).isoformat(), "inventory_sha256": A.sha256(root / A.EVIDENCE_REL / "inventory.json"),
              "file_hashes": {p: A.sha256(root / p) for p in paths}, "identity_free_check": proof, "rules": deepcopy(A.RULES), "qualification_flags": {k: False for k in A.QUALIFICATION_FLAGS},
              "selected_delta": None, "reinitialization": "none", "shape_update_allowed": False, "known_before_run": A.KNOWN_BEFORE_RUN, "prohibitions": list(A.PROHIBITIONS), "pins": {}, "runtime": {}}
    for k in C.KERNELS:
        d = root / f"infra/kaggle/kernel_grid02_{k}"
        d.mkdir(parents=True)
        (d / "runner.py").write_text(K.render(commit, k))
        dump(d / "kernel-metadata.json", K.metadata(k))
        freeze["pins"][k] = K.pins(k)
        freeze["runtime"][k] = A.expected_runtime(k, INVENTORY["kernel_config"][k], A.sha256(d / "runner.py"), A.sha256(d / "kernel-metadata.json"))
    yield root, deepcopy(INVENTORY), freeze
    patch.undo()


def force_csv(path, lift, drag, scale):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=FORCE_COLUMNS)
        w.writeheader()
        for step, t in enumerate((0, 80, 100, 120, 121), 1):
            row = dict.fromkeys(FORCE_COLUMNS, 0.0)
            row.update(step=step, t_u_l=t, fx_solver=drag / scale, drag_solver=drag / scale, fz_solver=-lift / scale, downforce_solver=lift / scale, pressure_fx_solver=drag / scale, pressure_fz_solver=-lift / scale)
            w.writerow(row)


def manifest(out):
    dump(out / "output_manifest.json", {"files": {str(p.relative_to(out)): A.sha256(p) for p in sorted(out.rglob("*")) if p.is_file() and p != out / "output_manifest.json"}})


def build_kernel(out, kernel, freeze, inventory, tg, pair, reverse_shift):
    out.mkdir(parents=True)
    cfg, runtime = inventory["kernel_config"][kernel], freeze["runtime"][kernel]
    case, names, rows = cfg["case_id"], inventory["kernels"][kernel], {r["name"]: r for r in inventory["states"]}
    cell = {"f16": "16n", "s24": "24s", "s32": "32s", "f48a": "48n", "f48b": "48n"}[kernel]
    base = BASE["f48a" if kernel.startswith("f48") else kernel] + (pair.get(kernel, 0.0))
    (out / "nvidia_smi.csv").write_text(f"0, Tesla T4, {UUID}, 15360 MiB, 535.1\n1, Tesla T4, GPU-other, 15360 MiB, 535.1\n")
    (out / "gpu_device_probe.log").write_text("synthetic observed CUDA identity\n")
    dump(out / "gpu_device_probe.json", {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "visible_gpu_uuids": [UUID], "default_device_uuid": UUID, "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"})
    dump(out / "run_identity.json", {"source_commit": freeze["source_commit"], "kernel": kernel, "kernel_id": runtime["kernel_id"], "case_id": case, "runner_sha256": runtime["runner_sha256"], "pins": freeze["pins"][kernel],
                                     "verified": freeze["pins"][kernel], "failure_stage": None, "config": {k: cfg[k] for k in K.RUNTIME_KEYS}, "expected_names": names, "selected_gpu": {"index": 0, "name": "Tesla T4", "uuid": UUID},
                                     "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"})
    index = {"kernel": kernel, "kernel_id": runtime["kernel_id"], "case_id": case, "status": "COMPLETE", "states": []}
    m, job_env, total = cfg["measurement"], inventory["job_env_common"], 0.0
    seconds = 2000.0 if kernel.startswith("f48") else 100.0
    for name in names:
        row, d = rows[name], out / "states" / name
        s = row["sign"] * row["step_mm"]
        b, a = tg[cell] if row["kind"] == "candidate" or row["sign"] else (0.0, 0.0)
        lift = base + b * s + a * s * s + (reverse_shift if row["sign"] < 0 else 0.0)
        drag = DRAG0 - 2e-5 * s
        p = d / f"{case}.forces.csv"
        force_csv(p, lift, drag, cfg["force_scale_n_per_solver_force"])
        host = recompute_force_n(p, {"measurement": m})
        summary = {**m["case"], "cells_per_reference_length": C.CELLS[case], "flow_origin_m": [-2.5, -1.2, -0.9], "physical_box_max_m": [2.5, 1.2, 0.9], "gpu_name": "Tesla T4", "gpu_uuid": UUID,
                   "phi_fortran_sha256": row["phi_fortran_order_sha256"], "phi_c_order_sha256": row["phi_c_order_sha256"], "state_sha256": row["state_sha256"], "state_npz_sha256": row["npz_sha256"],
                   "canonical_sdf_origin_m": cfg["canonical_origin_m"], "canonical_design_spacing_m": float(job_env["W4_CANONICAL_DESIGN_SPACING_M"]), "canonical_state_label": job_env["W4_CANONICAL_STATE_LABEL"],
                   "canonical_design_point_shape": [int(v) for v in job_env["W4_POINT_SHAPE"].split(",")], "canonical_design_cell_shape": [int(v) for v in job_env["W4_CELL_SHAPE"].split(",")],
                   "source_surface_sha256": job_env["W4_SOURCE_SURFACE_SHA256"], "device_roundtrip_sha256": row["phi_fortran_order_sha256"], "force_integration_body": m["candidate_operator"],
                   "force_projection_semantics": "drag=+Fx; downforce=-Fz", "finite_u": True, "finite_p": True, "finite_forces": True, "julia_threads": 1, "t_end_reached": 120.0086, "burn_in_t_u_l": 80.0,
                   "phi_margin_m": row["zero_level_margin_m"], "phi_margin_gate_m": 0.15, "wall_seconds": seconds - 20, "downforce_time_weighted_n": host["downforce_n"], "drag_time_weighted_n": host["drag_n"]}
        dump(d / f"{case}.summary.json", summary)
        (d / "W4_JOB_DONE").write_text("synthetic job done\n")
        index["states"].append({"name": name, "kind": row["kind"], "direction": row["direction"], "step_mm": row["step_mm"], "sign": row["sign"], "exit_code": 0, "seconds": seconds,
                                "forces_csv_sha256": A.sha256(p), "complete": True})
        total += seconds
        if len(index["states"]) == 1:
            index["parent_forces_csv_sha256"] = A.sha256(p)
    index["solver_process_wall_seconds_total"] = total
    dump(out / "grid02_index.json", index)
    (out / "DONE").write_text("synthetic all completed\n")
    manifest(out)


def build_all(root_dir, freeze, inventory, tg=None, pair=None, reverse_shift=0.0):
    tg = tg or targets()
    for k in C.KERNELS:
        build_kernel(root_dir / f"grid02_{k}", k, freeze, inventory, tg, pair or {}, reverse_shift)
    return {k: root_dir / f"grid02_{k}" for k in C.KERNELS}


@pytest.fixture(scope="module")
def base_tree(registered, tmp_path_factory):
    root, inv, freeze = registered
    d = tmp_path_factory.mktemp("grid02-out") / "valid"
    build_all(d, freeze, inv)
    return d


@pytest.fixture
def valid(registered, base_tree, tmp_path, monkeypatch):
    """Fast variant: outputs copied per test; the (separately tested) registration check is skipped."""
    root, inv, freeze = registered
    d = tmp_path / "out"
    shutil.copytree(base_tree, d)
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)
    return d, deepcopy(freeze), deepcopy(inv)


def run(case, **kw):
    d, freeze, inv = case
    return A.analyze({k: d / f"grid02_{k}" for k in C.KERNELS}, freeze, inv)


def full(registered, tmp_path, **kw):
    """Full registration validation on freshly built outputs."""
    root, inv, freeze = registered
    dirs = build_all(tmp_path / "out", freeze, inv, **kw)
    return A.analyze(dirs, deepcopy(freeze), deepcopy(inv))


# ---------------------------------------------------------------- happy path and analysis content
def test_complete_five_kernel_study_is_recorded_with_full_registration_check(registered, tmp_path):
    r = full(registered, tmp_path)
    assert r["integrity"] == {"pass": True, "failures": []} and r["verdict"] == "GRID02_RECORDED"
    assert set(r["cells"]) == set(A.CELL_LABELS) and set(r["qualification_flags"].values()) == {False} and r["selected_delta"] is None and r["shape_update_allowed"] is False
    assert r["alignment"]["classification"] == "GRID02_ALIGNMENT_DOMINANT" and r["fine"]["classification"] == "FINE_CONTINUES_TO_FLOW32" and r["stable_32_to_48"] is True
    assert r["decision_text"] == C.decision_text("GRID02_ALIGNMENT_DOMINANT", "FINE_CONTINUES_TO_FLOW32", True)


def test_cells_fits_resolution_and_same_kernel_references(valid):
    r = run(valid)
    tg = targets()
    for cell, (b, a) in tg.items():
        assert r["cells"][cell]["fit"]["b_n_per_mm"] == pytest.approx(b, rel=1e-6) and r["cells"][cell]["fit"]["a_n_per_mm2"] == pytest.approx(a, rel=1e-5)
        assert r["cells"][cell]["fit"]["max_residual_n"] < 1e-9 and r["cells"][cell]["resolution_n"] == C.RESOLUTION_FLOOR_N
    for cell, case in (("24n", "flow_24"), ("32n", "flow_32")):
        assert r["cells"][cell]["fit"]["b_n_per_mm"] == pytest.approx(B24 if cell == "24n" else B32, rel=1e-12) and r["cells"][cell]["placement"] == "native"
        assert r["pair_differences"][f"native_{case}"]["downforce_n"] == 0.0
    assert r["cells"]["24s"]["placement"] == "shifted" and r["cells"]["16n"]["case"] == "flow_16" and r["cells"]["48n"]["case"] == "flow_48"
    st = r["cells"]["48n"]["states"]
    assert set(st) == set(C.FORWARD) | {C.REVERSE[1]} and r["cells"]["16n"]["states"].keys() == set(C.SEVEN[1:])  # f48 has one reverse, the parent repeat is the pair not a point
    assert r["cells"]["24s"]["fit_with_intercept"]["c_n"] == pytest.approx(0, abs=1e-9) and set(r["cells"]["24s"]["reverse_check"]) == set(C.REVERSE)
    assert r["pair_differences"]["f48"]["forces_csv_byte_identical"] is True and r["pair_differences"]["f16"]["forces_csv_byte_identical"] is True
    assert "no parent pair" in r["pair_differences"]["s24"]["basis"]


def test_f48_parent_pair_byte_difference_raises_resolution_and_is_the_reference_of_f48b(registered, tmp_path):
    root, inv, freeze = registered
    d = tmp_path / "pair"
    build_all(d, freeze, inv, pair={"f48b": 1e-4})
    r = A.analyze({k: d / f"grid02_{k}" for k in C.KERNELS}, deepcopy(freeze), deepcopy(inv))
    assert r["integrity"]["pass"] is True  # a byte difference is not an integrity failure
    c = r["cells"]["48n"]
    assert r["pair_differences"]["f48"]["forces_csv_byte_identical"] is False and r["pair_differences"]["f48"]["downforce_n"] == pytest.approx(1e-4, rel=1e-6)
    assert c["resolution_n"] == pytest.approx(1e-4, rel=1e-6)
    # +1.25 mm and reverse 1.25 mm are measured against the repeat, so the pair shift cancels from dL and b is unchanged
    assert c["states"][C.FORWARD[3]]["dL_n"] == pytest.approx(r["cells"]["48n"]["fit"]["b_n_per_mm"] * 1.25 + c["fit"]["a_n_per_mm2"] * 1.5625, rel=1e-5)
    assert c["fit"]["b_n_per_mm"] == pytest.approx(targets()["48n"][0], rel=1e-5) and c["states"][C.FORWARD[0]]["dL_status"] in ("positive_resolved", "unresolved", "negative_resolved")
    assert r["cells"]["16n"]["resolution_n"] == C.RESOLUTION_FLOOR_N and r["cells"]["24n"]["resolution_n"] == C.RESOLUTION_FLOOR_N


@pytest.mark.parametrize("m24,m32,expected", [(0.6, 0.6, "GRID02_ALIGNMENT_DOMINANT"), (0.5001, 0.5001, "GRID02_ALIGNMENT_DOMINANT"), (0.4999, 0.9, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"),
                                              (0.1, -0.1, "GRID02_ALIGNMENT_NEGLIGIBLE"), (0.1999, 0.1999, "GRID02_ALIGNMENT_NEGLIGIBLE"), (0.2001, 0.0, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"),
                                              (0.0, -0.2001, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"), (0.3, 0.3, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"), (0.6, 0.1, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"),
                                              (-0.5, -0.5, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED")])
def test_alignment_classification_through_the_analyzer(registered, tmp_path, monkeypatch, m24, m32, expected):
    root, inv, freeze = registered
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)
    d = tmp_path / "o"
    build_all(d, freeze, inv, tg=targets(m24, m32, 0.7))
    r = A.analyze({k: d / f"grid02_{k}" for k in C.KERNELS}, freeze, inv)
    assert r["verdict"] == "GRID02_RECORDED" and r["alignment"]["classification"] == expected
    assert r["alignment"]["m24"] == pytest.approx(m24, abs=1e-6) and r["alignment"]["m32"] == pytest.approx(m32, abs=1e-6)
    assert r["decision_text"].startswith(expected) and r["alignment"]["G"] == pytest.approx(G, rel=1e-12)


@pytest.mark.parametrize("rr,expected,stable", [(1.0, "FINE_CONTINUES_TO_FLOW32", True), (0.7, "FINE_CONTINUES_TO_FLOW32", True), (0.5001, "FINE_CONTINUES_TO_FLOW32", False), (0.4999, "FINE_INTERMEDIATE", False),
                                                (0.2001, "FINE_INTERMEDIATE", False), (0.1999, "FINE_REVERSES_TOWARD_FLOW24", False), (-0.3, "FINE_REVERSES_TOWARD_FLOW24", False)])
def test_fine_classification_and_stable_flag_are_independent(registered, tmp_path, monkeypatch, rr, expected, stable):
    root, inv, freeze = registered
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)
    d = tmp_path / "o"
    build_all(d, freeze, inv, tg=targets(0.1, 0.1, rr))  # negligible alignment: the decision text depends on the stable flag
    r = A.analyze({k: d / f"grid02_{k}" for k in C.KERNELS}, freeze, inv)
    assert r["fine"]["classification"] == expected and r["stable_32_to_48"] is stable and r["fine"]["r"] == pytest.approx(rr, abs=1e-6)
    assert r["decision_text"] == C.decision_text("GRID02_ALIGNMENT_NEGLIGIBLE", expected, stable)
    assert ("within 30% of flow_48" in r["decision_text"]) is stable and ("larger-step" in r["decision_text"]) is (not stable)


def test_tables_placement_effect_both_grid_rule_hindcast_and_interpretation(valid):
    r = run(valid)
    t = r["four_point_table"]
    assert set(t) == {"16", "24", "32", "48"} and t["48"]["parent_downforce_n"] == pytest.approx(0.39) and t["24"]["parent_downforce_n"] == NATIVE["flow_24"][C.PARENT]["downforce_n"]
    assert r["placement_effect"]["24"]["parent_downforce_shifted_minus_native_n"] == pytest.approx(0.34 - NATIVE["flow_24"][C.PARENT]["downforce_n"])
    assert r["placement_effect"]["32"]["parent_drag_shifted_minus_native_n"] == pytest.approx(DRAG0 - NATIVE["flow_32"][C.PARENT]["drag_n"])
    assert r["hindcast_flow_48_parent_downforce"] == {"downforce_n": pytest.approx(0.39), "band_n": [0.38, 0.40], "within_band": True, "descriptive_only": True}
    assert set(r["both_grid_rule_descriptive"]) == {"24n_32n", "24s_32s", "32n_48n", "48n_alone"}
    for tag, group in (("24n_32n", ("24n", "32n")), ("48n_alone", ("48n",))):
        for step, rule in r["both_grid_rule_descriptive"][tag]["per_step"].items():
            n = C.FORWARD[[f"{s:g}" for s in C.FORWARD_MM].index(step)]
            assert rule == C.both_grid_rule({g: r["cells"][g]["states"][n]["dL_n"] for g in group}, {g: r["cells"][g]["states"][n]["dD_n"] for g in group})
    assert all(v["descriptive_only"] for v in r["both_grid_rule_descriptive"].values()) and all(s["dD_status"] for s in r["cells"]["48n"]["states"].values())
    text = r["interpretation"]
    for needle in ("PARTIAL", "z is unshifted", "nominal flow_24", "One parent", "Not grid convergence or GCI", "not a gradient", "OPT-01 is not re-opened", "reproducibility, not noise"):
        assert needle in text
    assert r["no_gci_claim"] and r["no_gradient_claim"] and r["not_grid_converged"] and r["opt01_rule_unchanged"] and r["reinitialization"] == "none"


def test_hindcast_outside_band_is_descriptive_only(registered, tmp_path, monkeypatch):
    root, inv, freeze = registered
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)
    monkeypatch.setitem(BASE, "f48a", 0.45)
    d = tmp_path / "o"
    build_all(d, freeze, inv)
    r = A.analyze({k: d / f"grid02_{k}" for k in C.KERNELS}, freeze, inv)
    assert r["verdict"] == "GRID02_RECORDED" and r["hindcast_flow_48_parent_downforce"]["within_band"] is False


def test_reverse_states_never_change_b_a_or_the_classifications(registered, valid, tmp_path, monkeypatch):
    root, inv, freeze = registered
    base = run(valid)
    d = tmp_path / "wild"
    build_all(d, freeze, inv, reverse_shift=0.25)
    wild = A.analyze({k: d / f"grid02_{k}" for k in C.KERNELS}, freeze, inv)
    assert wild["verdict"] == "GRID02_RECORDED"
    for cell in A.CELL_LABELS:
        assert wild["cells"][cell]["fit"] == base["cells"][cell]["fit"] and wild["cells"][cell]["fit_with_intercept"] == base["cells"][cell]["fit_with_intercept"]
    for key in ("alignment", "fine", "stable_32_to_48", "decision_text", "both_grid_rule_descriptive"):
        assert wild[key] == base[key]
    assert wild["cells"]["24s"]["reverse_check"] != base["cells"]["24s"]["reverse_check"]


def test_zero_gap_is_a_computation_failure_not_a_verdict(valid, monkeypatch):
    native = deepcopy(NATIVE)
    native["flow_32"] = native["flow_24"]
    monkeypatch.setattr(A, "check_native", lambda inv: native)
    r = run(valid)
    assert r["verdict"] == "GRID02_INCOMPLETE" and r["integrity"]["pass"] is False and "gap G" in r["integrity"]["failures"][0] and "alignment" not in r and "cells" not in r


def test_nonfinite_computed_value_is_incomplete(valid, monkeypatch):
    native = deepcopy(NATIVE)
    native["flow_24"][C.FORWARD[0]]["downforce_n"] = float("nan")
    monkeypatch.setattr(A, "check_native", lambda inv: native)
    assert run(valid)["verdict"] == "GRID02_INCOMPLETE"


# ---------------------------------------------------------------- descriptive robustness, peak fields, shift gate, minors
def test_descriptive_robustness_fields_on_exact_data(valid):
    r = run(valid)
    for cell in ("16n", "24s", "32s", "48n"):  # synthetic exact quadratics (the native 24/32 cells hold the real retained data)
        c = r["cells"][cell]
        b = c["fit"]["b_n_per_mm"]
        assert c["b_central_n_per_mm"] == pytest.approx(b, rel=1e-6) and c["b_with_intercept_n_per_mm"] == pytest.approx(b, rel=1e-5)
        assert [x["dropped_step_mm"] for x in c["b_leave_one_out"]] == list(C.FORWARD_MM) and all(x["b_n_per_mm"] == pytest.approx(b, rel=1e-4) for x in c["b_leave_one_out"])
        assert c["fit"]["peak_step_mm"] is None or c["fit"]["peak_step_mm"] == pytest.approx(b / (2 * abs(c["fit"]["a_n_per_mm2"])))
    rb = r["slope_robustness"]
    assert rb["descriptive_only"] is True and set(rb["would_change_if_slopes_were"]) == {"b_central", "b_with_intercept", "b_48n_all_vs_f48a_parent"}
    assert all(v == {"alignment": "unchanged", "fine": "unchanged", "stable_32_to_48": "unchanged"} for k, v in rb["would_change_if_slopes_were"].items() if k != "b_central")  # real native b_c differ by ~5%: reported, not asserted
    assert set(rb["would_change_if_slopes_were"]["b_central"]) == {"alignment", "fine", "stable_32_to_48"}
    assert set(r["cells"]["24n"]) >= {"b_central_n_per_mm", "b_with_intercept_n_per_mm", "b_leave_one_out"}
    assert rb["b_48n_all_vs_f48a_parent"]["b_n_per_mm"] == pytest.approx(r["cells"]["48n"]["fit"]["b_n_per_mm"], rel=1e-5)
    al = r["alignment"]
    assert al["gap_after_shift_ratio"] == pytest.approx(1 - al["m24"] - al["m32"]) and al["abs_b_24s_minus_b_32s"] == pytest.approx(abs(targets()["24s"][0] - targets()["32s"][0]))
    assert al["gap_after_shift_ratio"] == pytest.approx((targets()["32s"][0] - targets()["24s"][0]) / G)


def test_b_central_is_model_free_and_the_variants_never_change_the_verdict(registered, tmp_path, monkeypatch):
    root, inv, freeze = registered
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)
    base = A.analyze(build_all(tmp_path / "a", freeze, inv), freeze, inv)
    wild = A.analyze(build_all(tmp_path / "b", freeze, inv, reverse_shift=0.25), freeze, inv)
    for cell in ("16n", "24s", "32s", "48n"):  # (synthetic cells) the reverse point moves b_c by -0.25/2.5 on every cell; b, the classes and the verdict do not move
        assert wild["cells"][cell]["b_central_n_per_mm"] == pytest.approx(base["cells"][cell]["b_central_n_per_mm"] - 0.1, abs=1e-9)
    assert (wild["verdict"], wild["alignment"]["classification"], wild["fine"]["classification"]) == (base["verdict"], base["alignment"]["classification"], base["fine"]["classification"])


def test_class_changes_reports_other_class_unchanged_and_not_computable():
    align, fine = C.alignment_classification(0.0, 3.0, 4.0, 1.0), C.fine_classification(0.0, 4.0, 3.0)
    assert align["classification"] == "GRID02_ALIGNMENT_DOMINANT" and fine["classification"] == "FINE_CONTINUES_TO_FLOW32" and fine["stable_32_to_48"] is True
    same = {"24n": 0.0, "24s": 3.0, "32n": 4.0, "32s": 1.0, "48n": 3.0}
    assert A.class_changes(same, align, fine) == {"alignment": "unchanged", "fine": "unchanged", "stable_32_to_48": "unchanged"}
    other = A.class_changes({**same, "24s": 0.0, "32s": 4.0, "48n": 0.4}, align, fine)
    assert other == {"alignment": "GRID02_ALIGNMENT_NEGLIGIBLE", "fine": "FINE_REVERSES_TOWARD_FLOW24", "stable_32_to_48": False}
    assert A.class_changes({**same, "32n": 0.0}, align, fine) == {"alignment": "not computable", "fine": "not computable", "stable_32_to_48": "not computable"}  # G = 0
    assert A.class_changes({**same, "24s": None}, align, fine)["alignment"] == "not computable"


def with_native_parent(valid, monkeypatch, drag_equal):
    r = run(valid)
    native = deepcopy(NATIVE)
    forces = r["state_forces_n"]["s24"][C.PARENT]
    native["flow_24"][C.PARENT] = {"downforce_n": forces["downforce_n"], "drag_n": forces["drag_n"] if drag_equal else forces["drag_n"] + 1e-3}
    monkeypatch.setattr(A, "check_native", lambda inv: native)


def test_a_shifted_parent_bit_identical_to_the_native_parent_is_incomplete(valid, monkeypatch):
    with_native_parent(valid, monkeypatch, drag_equal=True)
    r = run(valid)
    assert r["verdict"] == "GRID02_INCOMPLETE" and "shift ineffective" in r["integrity"]["failures"][0] and "cells" not in r


def test_a_shifted_parent_differing_in_drag_or_downforce_alone_passes_the_gate(valid, monkeypatch):
    with_native_parent(valid, monkeypatch, drag_equal=False)
    assert run(valid)["verdict"] == "GRID02_RECORDED"


def test_manifest_symlink_is_refused_before_the_manifest_is_read(valid):
    d, freeze, inv = valid
    out = d / "grid02_s24"
    (out / "output_manifest.json").unlink()
    (out / "link").symlink_to(d)
    with pytest.raises(ValueError, match="symlinks"):
        A._manifest(out, inv["kernels"]["s24"], "flow_24")


def test_inventory_states_must_equal_the_opt01b_inventory_rows(registered, monkeypatch):
    root, inv, freeze = registered
    path = root / A.EVIDENCE_REL / "inventory.json"
    side = path.with_name("inventory.json.sha256")
    original, original_side = path.read_text(), side.read_text()
    bad = deepcopy(inv)
    bad["states"][2]["maximum_pointwise_change_m"] += 1e-9
    try:
        dump(path, bad)
        digest = A.sha256(path)
        side.write_text(digest + "\n")
        f = deepcopy(freeze)
        f["inventory_sha256"] = digest
        f["file_hashes"][f"{A.EVIDENCE_REL}/inventory.json"] = digest
        f["file_hashes"][f"{A.EVIDENCE_REL}/inventory.json.sha256"] = A.sha256(side)
        monkeypatch.setattr(A, "_source_commit_failures", lambda *a, **k: [])
        with pytest.raises(ValueError, match="differ from the OPT-01 Stage B inventory rows"):
            A.validate_registration(f, bad)
    finally:
        path.write_text(original)
        side.write_text(original_side)


def test_committed_freeze_must_match_the_blob_at_head(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / A.EVIDENCE_REL).mkdir(parents=True)
    blob = repo / A.EVIDENCE_REL / "prerun_freeze.json"
    git(repo, "init", "-q"); git(repo, "config", "user.name", "t"); git(repo, "config", "user.email", "t@example.invalid")
    monkeypatch.setattr(A, "ROOT", repo)
    other = tmp_path / "freeze.json"
    other.write_text("{}\n")
    A.check_committed_freeze(other)  # nothing committed at HEAD yet: no constraint
    blob.write_text('{"a": 1}\n')
    git(repo, "add", "."); git(repo, "commit", "-qm", "freeze")
    with pytest.raises(ValueError, match="differs from the committed"):
        A.check_committed_freeze(other)
    other.write_text('{"a": 1}\n')
    A.check_committed_freeze(other)
    fp = freeze_file(tmp_path, {"a": 2})
    monkeypatch.setattr(sys, "argv", ["analyze_grid02.py", "--kernel-root", str(tmp_path), "--freeze", str(fp), "--check"])
    with pytest.raises(SystemExit) as err:
        A.main()
    assert err.value.code == 3


# ---------------------------------------------------------------- integrity failures (registration skipped for speed; tested below with the full check)
def edit_json(path, fn):
    obj = A.jload(path)
    fn(obj)
    dump(path, obj)


def refresh(out, name=None, csv_changed=None):
    if csv_changed is not None:
        ix = out / "grid02_index.json"
        edit_json(ix, lambda o: next(e for e in o["states"] if e["name"] == csv_changed[0]).update(forces_csv_sha256=A.sha256(csv_changed[1])))
    manifest(out)


def mutate(valid, mutation):
    d, freeze, inv = valid
    f48b, f16, s24, f48a = d / "grid02_f48b", d / "grid02_f16", d / "grid02_s24", d / "grid02_f48a"
    summ = lambda out, name, case: out / "states" / name / f"{case}.summary.json"  # noqa: E731
    ix = lambda out: out / "grid02_index.json"  # noqa: E731
    P = C.PARENT
    if mutation == "missing_kernel": shutil.rmtree(f48b)
    elif mutation == "missing_state": shutil.rmtree(s24 / "states" / C.REVERSE[0]); manifest(s24)
    elif mutation == "extra_state": (s24 / "states/unregistered").mkdir(); manifest(s24)
    elif mutation == "extra_file": (s24 / "unmanifested.txt").write_text("x")
    elif mutation == "ERROR": (f48a / "ERROR.txt").write_text("runner failed"); manifest(f48a)
    elif mutation == "no_DONE": (f48a / "DONE").unlink(); manifest(f48a)
    elif mutation == "empty_manifest": dump(f48a / "output_manifest.json", {"files": {}})
    elif mutation == "manifest_tamper": (f48a / "states" / P / "flow_48.summary.json").write_text("{}")
    elif mutation == "manifest_escape": edit_json(f48a / "output_manifest.json", lambda o: o["files"].update({"../escaped": "b" * 64}))
    elif mutation == "wrong_gpu": (f16 / "nvidia_smi.csv").write_text("0, A100, GPU-wrong, 40000 MiB, 535.1\n"); manifest(f16)
    elif mutation == "no_index0": (f16 / "nvidia_smi.csv").write_text("1, Tesla T4, GPU-x, 15360 MiB, 535.1\n"); manifest(f16)
    elif mutation == "wrong_probe": edit_json(f16 / "gpu_device_probe.json", lambda o: o.update(default_device_uuid="GPU-other")); manifest(f16)
    elif mutation == "two_visible": edit_json(f16 / "gpu_device_probe.json", lambda o: o.update(logical_device_count=2, visible_gpu_names=["Tesla T4"] * 2, visible_gpu_uuids=[UUID, "GPU-other"])); manifest(f16)
    elif mutation == "wrong_case_file":  # an s24 state whose files are the flow_32 case
        for name in ("forces.csv", "summary.json"): shutil.move(s24 / "states" / P / f"flow_24.{name}", s24 / "states" / P / f"flow_32.{name}")
        manifest(s24)
    elif mutation == "wrong_summary_case": edit_json(summ(f16, P, "flow_16"), lambda o: o.update(case_id="flow_24")); manifest(f16)
    elif mutation == "native_origin_on_shifted": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(canonical_sdf_origin_m=[-1.0, -0.8, -0.6])); manifest(s24)
    elif mutation == "shifted_origin_on_native": edit_json(summ(f48a, P, "flow_48"), lambda o: o.update(canonical_sdf_origin_m=[-0.9875, -0.7875, -0.6])); manifest(f48a)
    elif mutation == "z_shifted": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(canonical_sdf_origin_m=[-0.9875, -0.7875, -0.5875])); manifest(s24)
    elif mutation == "swapped_kernels": shutil.move(s24, d / "tmp"); shutil.move(d / "grid02_s32", s24); shutil.move(d / "tmp", d / "grid02_s32")
    elif mutation == "swapped_f48": shutil.move(f48a, d / "tmp"); shutil.move(f48b, f48a); shutil.move(d / "tmp", f48b)
    elif mutation == "device_roundtrip_c_order": edit_json(summ(f48a, C.FORWARD[0], "flow_48"), lambda o: o.update(device_roundtrip_sha256={r["name"]: r for r in inv["states"]}[C.FORWARD[0]]["phi_c_order_sha256"])); manifest(f48a)
    elif mutation == "wrong_phi": edit_json(summ(f16, C.FORWARD[1], "flow_16"), lambda o: o.update(phi_fortran_sha256="a" * 64)); manifest(f16)
    elif mutation == "wrong_state_sha": edit_json(summ(f16, C.FORWARD[1], "flow_16"), lambda o: o.update(state_sha256="a" * 64)); manifest(f16)
    elif mutation == "wrong_npz": edit_json(summ(f16, C.FORWARD[1], "flow_16"), lambda o: o.update(state_npz_sha256="a" * 64)); manifest(f16)
    elif mutation == "wrong_spacing": edit_json(summ(f48a, P, "flow_48"), lambda o: o.update(flow_spacing_m=0.8 / 32)); manifest(f48a)
    elif mutation == "wrong_dims": edit_json(summ(f48a, P, "flow_48"), lambda o: o.update(flow_dims=[200, 96, 72])); manifest(f48a)
    elif mutation == "wrong_cells": edit_json(summ(f48a, P, "flow_48"), lambda o: o.update(cells_per_reference_length=32)); manifest(f48a)
    elif mutation == "bool_threads": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(julia_threads=True)); manifest(s24)
    elif mutation == "two_threads": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(julia_threads=2)); manifest(s24)
    elif mutation == "short_horizon": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(t_end_reached=119.0)); manifest(s24)
    elif mutation == "nonfinite_flag": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(finite_p=False)); manifest(s24)
    elif mutation == "margin": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(phi_margin_m=0.2)); manifest(s24)
    elif mutation == "gpu_uuid_summary": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(gpu_uuid="GPU-other")); manifest(s24)
    elif mutation == "bad_summary_force": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(downforce_time_weighted_n=0.123)); manifest(s24)
    elif mutation == "bad_summary_drag": edit_json(summ(s24, P, "flow_24"), lambda o: o.update(drag_time_weighted_n=0.5)); manifest(s24)
    elif mutation in ("nan_force", "force_component"):
        p = s24 / "states" / P / "flow_24.forces.csv"
        rows = list(csv.DictReader(io.StringIO(p.read_text())))
        rows[1]["downforce_solver"] = "nan" if mutation == "nan_force" else "100000"
        with p.open("w", newline="") as h:
            w = csv.DictWriter(h, fieldnames=FORCE_COLUMNS); w.writeheader(); w.writerows(rows)
        refresh(s24, csv_changed=(P, p))
    elif mutation == "csv_not_indexed": (s24 / "states" / P / "flow_24.forces.csv").write_text((s24 / "states" / P / "flow_24.forces.csv").read_text() + "\n"); manifest(s24)
    elif mutation == "bool_complete": edit_json(ix(s24), lambda o: o["states"][1].update(complete=1)); manifest(s24)
    elif mutation == "nonzero_exit": edit_json(ix(s24), lambda o: o["states"][1].update(exit_code=1)); manifest(s24)
    elif mutation == "bad_runtime_sum": edit_json(ix(s24), lambda o: o.update(solver_process_wall_seconds_total=1.0)); manifest(s24)
    elif mutation == "over_budget_state": edit_json(ix(s24), lambda o: (o["states"][1].update(seconds=901.0), o.update(solver_process_wall_seconds_total=o["solver_process_wall_seconds_total"] + 801.0))); manifest(s24)
    elif mutation == "over_budget_f48": edit_json(ix(f48a), lambda o: (o["states"][1].update(seconds=6001.0), o.update(solver_process_wall_seconds_total=o["solver_process_wall_seconds_total"] + 4001.0))); manifest(f48a)
    elif mutation == "wrong_first_state": edit_json(ix(f48b), lambda o: o["states"].reverse()); manifest(f48b)
    elif mutation == "parent_not_first": edit_json(ix(f48a), lambda o: o.update(states=o["states"][1:] + o["states"][:1])); manifest(f48a)
    elif mutation == "repeat_missing_in_f16": edit_json(ix(f16), lambda o: o.update(states=o["states"][:-1])); manifest(f16)
    elif mutation == "parent_hash": edit_json(ix(f48a), lambda o: o.update(parent_forces_csv_sha256="a" * 64)); manifest(f48a)
    elif mutation == "status": edit_json(ix(f48a), lambda o: o.update(status="RUNNING")); manifest(f48a)
    elif mutation == "kernel_id": edit_json(f48a / "run_identity.json", lambda o: o.update(kernel_id="ramhachi888/other")); manifest(f48a)
    elif mutation == "source_commit": edit_json(f48a / "run_identity.json", lambda o: o.update(source_commit="b" * 40)); manifest(f48a)
    elif mutation == "failure_stage": edit_json(f48a / "run_identity.json", lambda o: o.update(failure_stage="instantiate")); manifest(f48a)
    elif mutation == "runner_sha": edit_json(f48a / "run_identity.json", lambda o: o.update(runner_sha256="c" * 64)); manifest(f48a)
    elif mutation == "pins": edit_json(f48a / "run_identity.json", lambda o: o["pins"].update({"scripts/grid02_case.jl": "d" * 64})); manifest(f48a)
    elif mutation == "config_origin": edit_json(s24 / "run_identity.json", lambda o: o["config"].update(W4_CANONICAL_ORIGIN_M="-1.0,-0.8,-0.6")); manifest(s24)
    elif mutation == "config_case": edit_json(f48a / "run_identity.json", lambda o: o["config"].update(GRID02_CASE="flow_16")); manifest(f48a)
    elif mutation == "expected_names": edit_json(f48a / "run_identity.json", lambda o: o.update(expected_names=o["expected_names"][::-1])); manifest(f48a)
    elif mutation == "identity_gpu": edit_json(f16 / "run_identity.json", lambda o: o["selected_gpu"].update(uuid="GPU-other")); manifest(f16)
    elif mutation == "cuda_env": edit_json(f16 / "run_identity.json", lambda o: o.update(cuda_visible_devices="0,1")); manifest(f16)
    else:
        raise AssertionError(mutation)
    return d, freeze, inv


MUTATIONS = ["missing_kernel", "missing_state", "extra_state", "extra_file", "ERROR", "no_DONE", "empty_manifest", "manifest_tamper", "manifest_escape", "wrong_gpu", "no_index0", "wrong_probe", "two_visible",
             "wrong_case_file", "wrong_summary_case", "native_origin_on_shifted", "shifted_origin_on_native", "z_shifted", "swapped_kernels", "swapped_f48", "device_roundtrip_c_order", "wrong_phi", "wrong_state_sha",
             "wrong_npz", "wrong_spacing", "wrong_dims", "wrong_cells", "bool_threads", "two_threads", "short_horizon", "nonfinite_flag", "margin", "gpu_uuid_summary", "bad_summary_force", "bad_summary_drag",
             "nan_force", "force_component", "csv_not_indexed", "bool_complete", "nonzero_exit", "bad_runtime_sum", "over_budget_state", "over_budget_f48", "wrong_first_state", "parent_not_first",
             "repeat_missing_in_f16", "parent_hash", "status", "kernel_id", "source_commit", "failure_stage", "runner_sha", "pins", "config_origin", "config_case", "expected_names", "identity_gpu", "cuda_env"]


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_output_corruption_never_produces_a_verdict(valid, mutation):
    r = run(mutate(valid, mutation))
    assert r["verdict"] == "GRID02_INCOMPLETE" and r["integrity"]["pass"] is False and r["integrity"]["failures"]
    assert "cells" not in r and "alignment" not in r and "fine" not in r


def test_the_deviceroundtrip_failure_is_named_and_the_unmutated_tree_passes(valid):
    assert run(valid)["integrity"]["pass"] is True
    r = run(mutate(valid, "device_roundtrip_c_order"))
    assert "summary device_roundtrip_sha256" in r["integrity"]["failures"][0]


def test_exactly_five_kernel_directories_are_required(valid):
    d, freeze, inv = valid
    dirs = {k: d / f"grid02_{k}" for k in C.KERNELS}
    assert A.analyze({k: v for k, v in dirs.items() if k != "f16"}, freeze, inv)["verdict"] == "GRID02_INCOMPLETE"
    assert A.analyze({**dirs, "extra": d}, freeze, inv)["verdict"] == "GRID02_INCOMPLETE"
    assert A.analyze({**dirs, "s32": dirs["s24"]}, freeze, inv)["verdict"] == "GRID02_INCOMPLETE"


# ---------------------------------------------------------------- registration (full validation)
@pytest.mark.parametrize("mutation", ["closure", "source", "kind", "parent", "rules", "threshold", "flags", "identity", "delta", "shape", "reinit", "known", "prohibitions", "runtime_boolean", "runtime_origin", "pins",
                                      "inventory_sha", "inventory_state", "inventory_config", "inventory_native", "future", "file_hash", "runner", "extra_kernel"])
def test_malformed_or_changed_freeze_is_fail_closed(registered, tmp_path, mutation):
    root, inv, freeze = registered
    freeze, inv = deepcopy(freeze), deepcopy(inv)
    dirs = build_all(tmp_path / "out", freeze, inv)
    restore = []
    if mutation == "closure": freeze["file_hashes"].pop("scripts/analyze_grid02.py")
    if mutation == "source": freeze["source_commit"] = "a" * 40
    if mutation == "kind": freeze["kind"] = "another_campaign"
    if mutation == "parent": freeze["parent_integration_commit"] = "a" * 40
    if mutation == "rules": freeze["rules"]["alignment"]["dominant"] = "m24 >= 0.4 and m32 >= 0.4"
    if mutation == "threshold": freeze["rules"]["resolution_floor_n"] = 1e-5
    if mutation == "flags": freeze["qualification_flags"]["optimizer"] = True
    if mutation == "identity": freeze.pop("identity_free_check")
    if mutation == "delta": freeze["selected_delta"] = 0.001
    if mutation == "shape": freeze["shape_update_allowed"] = True
    if mutation == "reinit": freeze["reinitialization"] = "level_set"
    if mutation == "known": freeze["known_before_run"] = "nothing was known"
    if mutation == "prohibitions": freeze["prohibitions"] = freeze["prohibitions"][:-1]
    if mutation == "runtime_boolean": freeze["runtime"]["f48a"]["julia_threads"] = True
    if mutation == "runtime_origin": freeze["runtime"]["s24"]["W4_CANONICAL_ORIGIN_M"] = "-1.0,-0.8,-0.6"
    if mutation == "pins": freeze["pins"]["f16"].pop("scripts/grid02_case.jl", None); freeze["pins"]["f16"].pop("scripts/step01_states.py")
    if mutation == "inventory_sha": freeze["inventory_sha256"] = "e" * 64
    if mutation == "inventory_state": inv["states"][1]["sign"] = -1
    if mutation == "inventory_config": inv["kernel_config"]["f48a"]["per_state_timeout_s"] = 9000
    if mutation == "inventory_native": inv["native_reference"]["state_forces_n"]["flow_24"][C.PARENT]["downforce_n"] += 1e-3
    if mutation == "future": freeze["frozen_utc"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    if mutation == "file_hash":
        p = root / "scripts/grid02_case.jl"; restore.append((p, p.read_text())); p.write_text(p.read_text() + "# tampered\n")
    if mutation == "runner":
        p = root / "infra/kaggle/kernel_grid02_s24/runner.py"; restore.append((p, p.read_text())); p.write_text(p.read_text() + "\n# tampered\n")
    if mutation == "extra_kernel": freeze["runtime"]["extra"] = {}
    try:
        r = A.analyze(dirs, freeze, inv)
    finally:
        for p, text in restore:
            p.write_text(text)
    assert r["verdict"] == "GRID02_INCOMPLETE" and r["integrity"]["pass"] is False


def test_the_real_registered_inputs_close_under_the_freeze_closure(registered):
    root, inv, freeze = registered
    A.validate_registration(deepcopy(freeze), deepcopy(inv))
    assert {"scripts/analyze_grid02.py", "scripts/freeze_grid02.py", "scripts/waterlily_grid02_job.jl", "scripts/grid02_case.jl", "scripts/waterlily_xfid_candidate_c_job.jl", "scripts/waterlily_lowdim02_flow32_job.jl",
            "scripts/grid02_runner_template.py", "scripts/build_grid02_kernel.py", "scripts/build_grid02_inputs.py", "scripts/step01_states.py", "scripts/grid01_gpu.py", "scripts/fd08_v2_campaign_io.py",
            "src/cfd_sdf/grid02_contract.py", "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json", "docs/evidence/grid02_trend_2026_10_16/prerun_note.md",
            "docs/evidence/grid02_trend_2026_10_16/identity_free_check.json", "docs/evidence/opt01b_stage_b_2026_10_15/opt01b_analysis.json", "docs/evidence/opt01b_stage_b_2026_10_15/inventory.json",
            "julia/CFDSDFWaterLilyT4/Project.toml", "julia/CFDSDFWaterLilyT4/Manifest.toml", "tests/test_grid02_analyzer.py", "tests/test_grid02_prereg.py"} <= A.required_file_paths(inv)


# ---------------------------------------------------------------- CLI
def cli(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["analyze_grid02.py", *argv])
    A.main()


def freeze_file(tmp_path, freeze):
    p = tmp_path / "freeze.json"
    dump(p, freeze)
    p.with_name(p.name + ".sha256").write_text(A.sha256(p) + "\n")
    return p


def test_cli_check_writes_nothing_and_modes_are_exclusive(registered, base_tree, tmp_path, monkeypatch, capsys):
    root, inv, freeze = registered
    fp = freeze_file(tmp_path, freeze)
    before = sorted(p.name for p in tmp_path.iterdir())
    cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--check"], monkeypatch)
    out = json.loads(capsys.readouterr().out)
    assert out == {"integrity": {"failures": [], "pass": True}, "verdict": "GRID02_RECORDED"} and sorted(p.name for p in tmp_path.iterdir()) == before
    target = tmp_path / "analysis.json"
    with pytest.raises(SystemExit) as err:
        cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--check", "--write", str(target)], monkeypatch)
    assert err.value.code == 2 and not target.exists()
    with pytest.raises(SystemExit) as err:
        cli(["--kernel-root", str(base_tree), "--freeze", str(fp)], monkeypatch)
    assert err.value.code == 2


def test_cli_write_once_then_refuse_overwrite_and_never_writes_on_integrity_failure(registered, base_tree, tmp_path, monkeypatch):
    root, inv, freeze = registered
    fp = freeze_file(tmp_path, freeze)
    target = tmp_path / "analysis.json"
    cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--write", str(target)], monkeypatch)
    rep = A.jload(target)
    assert rep["verdict"] == "GRID02_RECORDED" and rep["provenance"]["freeze_sha256"] == A.sha256(fp) and rep["integrity"]["pass"] is True
    assert target.with_name("analysis.json.sha256").read_text() == A.sha256(target) + "\n"
    original = target.read_bytes()
    with pytest.raises(SystemExit) as err:
        cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--write", str(target)], monkeypatch)
    assert "refusing to overwrite" in str(err.value) and target.read_bytes() == original
    only_sidecar = tmp_path / "other.json"
    only_sidecar.with_name("other.json.sha256").write_text("x\n")  # a leftover sidecar also blocks the write
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--write", str(only_sidecar)], monkeypatch)
    assert not only_sidecar.exists()
    bad = tmp_path / "bad"
    shutil.copytree(base_tree, bad)
    (bad / "grid02_f48a" / "ERROR.txt").write_text("failed")
    target2 = tmp_path / "analysis2.json"
    with pytest.raises(SystemExit) as err:
        cli(["--kernel-root", str(bad), "--freeze", str(fp), "--write", str(target2)], monkeypatch)
    assert err.value.code == 3 and not target2.exists()


def test_cli_missing_sidecar_or_changed_freeze_is_refused_before_any_write(registered, base_tree, tmp_path, monkeypatch):
    root, inv, freeze = registered
    fp = freeze_file(tmp_path, freeze)
    target = tmp_path / "analysis.json"
    fp.with_name("freeze.json.sha256").unlink()
    with pytest.raises(SystemExit) as err:
        cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--write", str(target)], monkeypatch)
    assert err.value.code == 3 and not target.exists()
    changed = deepcopy(freeze)
    changed["rules"]["resolution_floor_n"] = 1.0
    fp = freeze_file(tmp_path, changed)
    with pytest.raises(SystemExit) as err:
        cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--write", str(target)], monkeypatch)
    assert err.value.code == 3 and not target.exists()


def test_cli_zero_gap_computation_failure_writes_nothing(registered, base_tree, tmp_path, monkeypatch):
    root, inv, freeze = registered
    fp = freeze_file(tmp_path, freeze)
    native = deepcopy(NATIVE)
    native["flow_32"] = native["flow_24"]
    monkeypatch.setattr(A, "check_native", lambda i: native)
    target = tmp_path / "analysis.json"
    with pytest.raises(SystemExit) as err:
        cli(["--kernel-root", str(base_tree), "--freeze", str(fp), "--write", str(target)], monkeypatch)
    assert err.value.code == 3 and not target.exists()


# ---------------------------------------------------------------- per-state checks on the REAL retained summaries, identity gate, freeze script
@pytest.mark.parametrize("kernel,src", [("s24", "opt01b_a"), ("s32", "opt01b_b")])
def test_per_state_checks_pass_on_the_real_retained_opt01b_summaries_and_csvs(kernel, src, tmp_path):
    inv = deepcopy(INVENTORY)
    cfg = inv["kernel_config"][kernel]
    cfg["canonical_origin_m"] = [-1.0, -0.8, -0.6]  # the retained OPT-01 runs are at the native origin
    out = tmp_path / f"grid02_{kernel}"
    shutil.copytree(ROOT / "docs/evidence/opt01b_stage_b_2026_10_15/kernel_output" / src, out)
    ridx = json.loads((out / "opt01b_index.json").read_text())
    (out / "opt01b_index.json").unlink()
    rid = json.loads((out / "run_identity.json").read_text())
    freeze = {"runtime": {kernel: {"kernel_id": cfg["kernel_id"], "runner_sha256": rid["runner_sha256"]}}, "source_commit": rid["source_commit"], "pins": {kernel: rid["pins"]}}
    rid.update(kernel=kernel, kernel_id=cfg["kernel_id"], config={k: cfg[k] for k in K.RUNTIME_KEYS}, expected_names=inv["kernels"][kernel])
    dump(out / "run_identity.json", rid)
    dump(out / "grid02_index.json", {"kernel": kernel, "kernel_id": cfg["kernel_id"], "case_id": cfg["case_id"], "status": "COMPLETE", "states": ridx["states"],
                                     "solver_process_wall_seconds_total": ridx["solver_process_wall_seconds_total"], "parent_forces_csv_sha256": ridx["states"][0]["forces_csv_sha256"]})
    manifest(out)
    states = A.check_kernel(out, kernel, freeze, inv)
    assert list(states) == list(C.SEVEN)
    nat = NATIVE[cfg["case_id"]]
    assert all(states[n]["downforce_n"] == pytest.approx(nat[n]["downforce_n"], rel=1e-12) for n in C.SEVEN)  # host recomputation reproduces the analyzed OPT-01 numbers
    summary = out / "states" / C.PARENT / f"{cfg['case_id']}.summary.json"
    edit_json(summary, lambda o: o.update(canonical_sdf_origin_m=[-0.9875, -0.7875, -0.6]))
    manifest(out)
    with pytest.raises(ValueError, match="canonical_sdf_origin_m"):
        A.check_kernel(out, kernel, freeze, inv)  # the registered (native) origin is demanded: a summary carrying the shifted origin is refused


def test_identity_gate_rejects_a_taken_slug_stale_proof_and_overwrite(registered):
    root, inv, freeze = registered
    taken = identity_proof(extra="ramhachi888/cfd-opt-sdf-grid02-f16")
    with pytest.raises(ValueError, match="provider collision"):
        F.require_identity(taken)
    stale = deepcopy(freeze["identity_free_check"])
    stale["captured_utc"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with pytest.raises(ValueError, match="stale"):
        F.require_identity(stale)
    incomplete = deepcopy(freeze["identity_free_check"])
    incomplete["listings"]["kernels"]["rows"] = []
    with pytest.raises(ValueError, match="incomplete"):
        F.require_identity(incomplete)
    assert F.require_identity(freeze["identity_free_check"]) is None
    with pytest.raises(ValueError, match="refusing to overwrite identity"):
        F.capture_identity()


def test_freeze_script_output_validates_with_the_analyzer_and_is_write_once(registered):
    root, inv, freeze = registered
    F.freeze(freeze["source_commit"])
    target = root / A.EVIDENCE_REL / "prerun_freeze.json"
    got = A.jload(target)
    assert target.with_name("prerun_freeze.json.sha256").read_text().strip() == A.sha256(target)
    A.validate_registration(got, deepcopy(inv))
    assert {k: v for k, v in got.items() if k not in ("frozen_utc", "file_hashes", "pins", "runtime")} == {k: v for k, v in freeze.items() if k not in ("frozen_utc", "file_hashes", "pins", "runtime")}
    assert got["file_hashes"] == freeze["file_hashes"] and got["pins"] == freeze["pins"] and got["runtime"] == freeze["runtime"]
    with pytest.raises(ValueError, match="refusing to overwrite an immutable freeze"):
        F.freeze(freeze["source_commit"])


def test_freeze_script_refuses_a_dirty_tree_an_unpushed_commit_and_a_wrong_ancestor(registered, monkeypatch):
    root, inv, freeze = registered
    (root / A.EVIDENCE_REL / "prerun_freeze.json").unlink(missing_ok=True)
    (root / A.EVIDENCE_REL / "prerun_freeze.json.sha256").unlink(missing_ok=True)
    note = root / A.EVIDENCE_REL / "prerun_note.md"
    text = note.read_text()
    note.write_text(text + "dirty\n")
    try:
        with pytest.raises(ValueError, match="uncommitted"):
            F.freeze(freeze["source_commit"])
    finally:
        note.write_text(text)
    url = git(root, "remote", "get-url", "origin")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")  # a stale local remote-tracking ref must not satisfy the check
    git(Path(url), "update-ref", "-d", "refs/heads/main")
    with pytest.raises(ValueError, match="remote branch"):
        F.freeze(freeze["source_commit"])
    git(root, "remote", "set-url", "origin", str(root / "nonexistent-remote"))
    with pytest.raises(ValueError, match="cannot fetch origin"):
        F.freeze(freeze["source_commit"])  # offline / unreachable remote: fail closed
    git(root, "remote", "set-url", "origin", url)
    git(root, "push", "-q", "origin", "HEAD:refs/heads/main")
    monkeypatch.setattr(A, "PARENT_COMMIT", "a" * 40)
    with pytest.raises(ValueError):
        F.freeze(freeze["source_commit"])
