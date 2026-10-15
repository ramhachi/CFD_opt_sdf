"""GRID-02 inventory rederivation, the five kernel plans and per-kernel environment, the rendered worker, and its behaviour against a fake job (no GPU, no network, no Julia)."""
import copy
import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_grid02_inputs as B  # noqa: E402
import build_grid02_kernel as K  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf import grid02_contract as C  # noqa: E402

EV = ROOT / "docs/evidence/grid02_trend_2026_10_16"
OPT = ROOT / "docs/evidence/opt01b_stage_b_2026_10_15"
INV = json.loads((EV / "inventory.json").read_text())
OPT_INV = json.loads((OPT / "inventory.json").read_text())
OPT_AN = json.loads((OPT / "opt01b_analysis.json").read_text())
DUMMY = "0" * 40
UUID = "GPU-11111111-2222-3333-4444-555555555555"
SMI = f"0, Tesla T4, {UUID}, 15360 MiB, 535.54.03\n"


# ---------------------------------------------------------------- inventory
def test_inventory_rederives_byte_for_byte_and_is_hash_bound():
    data = B.canonical_json(B.build())
    assert data == (EV / "inventory.json").read_bytes() and (EV / "inventory.json.sha256").read_text().strip() == hashlib.sha256(data).hexdigest()
    s = INV["source"]
    assert s["opt01b_inventory_sha256"] == B.OPT01B_INVENTORY_SHA == B.sha(ROOT / s["opt01b_inventory_path"]) and s["opt01b_analysis_sha256"] == B.OPT01B_ANALYSIS_SHA == B.sha(ROOT / s["opt01b_analysis_path"])
    assert INV["kind"] == "grid02_inventory" and INV["stage_status"] == "READY" and INV["blockers"] == []


def test_build_refuses_a_changed_source(monkeypatch):
    monkeypatch.setattr(B, "OPT01B_ANALYSIS_SHA", "0" * 64)
    with pytest.raises(ValueError, match="pinned immutable"):
        B.build()


def test_rows_are_the_seven_opt01b_rows_unchanged_plus_a_parent_repeat_with_the_parent_identity():
    rows = INV["states"]
    assert rows[:7] == OPT_INV["states"] and [r["name"] for r in rows] == list(C.SEVEN) + [C.REPEAT]
    rep, par = rows[7], rows[0]
    assert rep["kind"] == "parent_repeat" and rep["repeat_of"] == C.PARENT and all(rep[k] == par[k] for k in B.IDENTITY_KEYS)
    assert {k: v for k, v in rep.items() if k not in ("name", "kind", "repeat_of")} == {k: v for k, v in par.items() if k not in ("name", "kind")}
    assert all(k in r for r in rows for k in B.IDENTITY_KEYS) and len({r["phi_fortran_order_sha256"] for r in rows}) == 7
    for k in ("parent", "proposal", "directions", "job_env_common"):
        assert INV[k] == OPT_INV[k]


def test_kernel_state_lists_are_the_registered_table():
    assert INV["kernels"] == {k: list(v["states"]) for k, v in C.KERNELS.items()}
    assert {k: len(v) for k, v in INV["kernels"].items()} == {"s24": 7, "s32": 7, "f48a": 4, "f48b": 3, "f16": 8}  # the JSON is key-sorted; index by kernel name
    assert INV["kernels"]["f48a"][0] == C.PARENT and INV["kernels"]["f48b"][0] == C.REPEAT and INV["kernels"]["f16"][0] == C.PARENT and INV["kernels"]["f16"][-1] == C.REPEAT
    names = {r["name"] for r in INV["states"]}
    assert all(set(v) <= names for v in INV["kernels"].values())


def test_native_reference_is_the_hash_bound_opt01b_analysis_forces():
    ref = INV["native_reference"]
    assert ref["analysis_sha256"] == B.OPT01B_ANALYSIS_SHA and ref["analysis_path"] == INV["source"]["opt01b_analysis_path"]
    assert set(ref["state_forces_n"]) == {"flow_24", "flow_32"} and ref["state_forces_n"] == {c: OPT_AN["state_forces_n"][c] for c in ("flow_24", "flow_32")}
    assert all(sorted(v) == sorted(C.SEVEN) for v in ref["state_forces_n"].values())


@pytest.mark.parametrize("kernel", list(C.KERNELS))
def test_kernel_config_plan_budgets_and_environment_values(kernel):
    cfg, spec = INV["kernel_config"][kernel], C.KERNELS[kernel]
    assert cfg["kernel_id"] == f"ramhachi888/cfd-opt-sdf-grid02-{kernel}" and cfg["case_id"] == spec["case"] and cfg["job"] == spec["job"] and cfg["placement"] == spec["placement"]
    assert cfg["W4_CANONICAL_ORIGIN_M"] == ("-0.9875,-0.7875,-0.6" if kernel in ("s24", "s32") else "-1.0,-0.8,-0.6") == ",".join(map(repr, cfg["canonical_origin_m"]))
    assert cfg["GRID02_CASE"] == (spec["case"] if kernel.startswith("f") else None)
    assert (cfg["job"] == "scripts/waterlily_grid02_job.jl") == (cfg["GRID02_CASE"] is not None)
    assert (cfg["per_state_timeout_s"], cfg["solver_wall_time_cap_s"], cfg["kernel_timeout_s"]) == (spec["per_state_timeout_s"], len(spec["states"]) * spec["per_state_timeout_s"], spec["kernel_timeout_s"])
    assert (cfg["instantiate_timeout_s"], cfg["gpu_probe_timeout_s"], cfg["reserve_s"]) == (2400, 300, 300) and cfg["kernel_timeout_s"] - cfg["reserve_s"] > cfg["solver_wall_time_cap_s"]
    m = cfg["measurement"]
    assert m["case"]["case_id"] == spec["case"] and {k: m["case"][k] for k in C.case_dict(spec["case"])} == C.case_dict(spec["case"]) and m["time_window_t_u_l"] == [80.0, 120.0]
    assert m["candidate_operator"] == OPT_INV["grids"]["a"]["measurement"]["candidate_operator"] and m["solver_wall_time_cap_s"] == cfg["solver_wall_time_cap_s"] and m["per_state_timeout_s"] == cfg["per_state_timeout_s"]
    assert cfg["force_scale_n_per_solver_force"] == C.force_scale_n(spec["case"]) == C.DENSITY * m["case"]["flow_spacing_m"] ** 2
    assert {"s24": "scripts/waterlily_xfid_candidate_c_job.jl", "s32": "scripts/waterlily_lowdim02_flow32_job.jl"}.get(kernel, "scripts/waterlily_grid02_job.jl") == cfg["job"]


def test_new_slugs_are_distinct_titled_like_their_slug_and_not_used_by_any_other_kernel():
    ids = {k: v["kernel_id"] for k, v in INV["kernel_config"].items()}
    assert len(set(ids.values())) == 5 and ids == K.KERNEL_IDS
    used = set()
    for meta in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json"):
        if "grid02" in meta.parent.name:
            continue
        m = json.loads(meta.read_text())
        used |= {m.get("id"), m.get("title")}
    for k, v in ids.items():
        meta = K.metadata(k)
        assert v not in used and v.split("/")[1] not in used and meta["title"] == v.split("/")[1] and meta["id"] == v and meta["machine_shape"] == "NvidiaTeslaT4" and meta["dataset_sources"] == []


# ---------------------------------------------------------------- rendering
@pytest.mark.parametrize("kernel", list(C.KERNELS))
def test_render_has_no_placeholder_and_binds_this_kernels_plan(kernel):
    text = K.render(DUMMY, kernel)
    assert "PIN_" not in text and "BASELINE_FORCE_CSV" not in text
    ns = load(kernel)
    cfg = INV["kernel_config"][kernel]
    assert (ns["KERNEL"], ns["KERNEL_ID"], ns["CASE_ID"], ns["JOB"], ns["EXPECTED_NAMES"]) == (kernel, cfg["kernel_id"], cfg["case_id"], cfg["job"], INV["kernels"][kernel])
    assert (ns["PER_STATE_TIMEOUT_S"], ns["SOLVER_WALL_TIME_CAP_S"], ns["KERNEL_TIMEOUT_S"], ns["MARGIN_S"]) == (cfg["per_state_timeout_s"], cfg["solver_wall_time_cap_s"], cfg["kernel_timeout_s"], 300)
    assert ns["CONFIG"] == {k: cfg[k] for k in K.RUNTIME_KEYS} and "docs/evidence/opt01b_stage_b_2026_10_15/" in ns["SPARSE"] and "docs/evidence/grid02_trend_2026_10_16/" in ns["SPARSE"]
    assert len(ns["expected_plan"](INV)) == len(INV["kernels"][kernel])


def test_rendered_kernels_differ_only_in_the_intended_lines():
    texts = {k: K.render(DUMMY, k).splitlines() for k in C.KERNELS}
    allowed = ("KERNEL =", "KERNEL_ID =", "CASE_ID =", "JOB =", "PINS =", "CONFIG =", "EXPECTED_NAMES =")
    for a in texts:
        for b in texts:
            if a < b:
                diff = [d[1:] for d in difflib.unified_diff(texts[a], texts[b], lineterm="", n=0) if d[0] in "+-" and not d.startswith(("+++", "---"))]
                assert diff and all(d.startswith(allowed) for d in diff), (a, b, [d[:40] for d in diff if not d.startswith(allowed)])


@pytest.mark.parametrize("kernel", list(C.KERNELS))
def test_pins_bind_the_job_the_raws_the_inventory_and_the_julia_tree_to_the_real_bytes(kernel):
    pins, cfg = load(kernel)["PINS"], INV["kernel_config"][kernel]
    assert pins[INV["parent"]["raw_path"]] == INV["parent"]["phi_fortran_order_sha256"] == K.sha(ROOT / INV["parent"]["raw_path"]) and pins[INV["proposal"]["file"]] == INV["proposal"]["sha256_fortran_raw"]
    assert pins[cfg["job"]] == K.sha(ROOT / cfg["job"]) and pins["docs/evidence/grid02_trend_2026_10_16/inventory.json"] == INV_SHA and pins["julia/CFDSDFWaterLily/src"]
    assert pins["julia/CFDSDFWaterLilyT4/Project.toml"] and pins["julia/CFDSDFWaterLilyT4/Manifest.toml"] and pins["scripts/step01_states.py"] and pins["scripts/grid01_gpu.py"]
    assert ("scripts/grid02_case.jl" in pins) == (cfg["job"] == "scripts/waterlily_grid02_job.jl") and not any("opt01b_states" in p or "forces.csv" in p for p in pins)


# ---------------------------------------------------------------- runner behaviour
INV_SHA = hashlib.sha256((EV / "inventory.json").read_bytes()).hexdigest()


def load(kernel):
    ns = {"__name__": "rendered_worker", "__file__": str(K.TEMPLATE)}
    exec(compile(K.render(DUMMY, kernel), f"runner_{kernel}.py", "exec"), ns)
    return ns


def source_tree(tmp, inventory=None):
    """A fake checkout: symlinks to the real julia/scripts/opt01b evidence and a (possibly tampered) copy of the inventory; returns (tree, inventory sha)."""
    src = tmp / "src"
    (src / "docs/evidence/grid02_trend_2026_10_16").mkdir(parents=True)
    (src / "julia").symlink_to(ROOT / "julia")
    (src / "scripts").symlink_to(ROOT / "scripts")
    (src / "docs/evidence/opt01b_stage_b_2026_10_15").symlink_to(OPT)
    target = src / "docs/evidence/grid02_trend_2026_10_16/inventory.json"
    if inventory is None:
        shutil.copy(EV / "inventory.json", target)
    else:
        target.write_bytes(B.canonical_json(inventory))
    return src, hashlib.sha256(target.read_bytes()).hexdigest()


class Harness:
    def __init__(self, tmp, kernel, *, smi=SMI, inventory=None, fail=None, case_file=None, probe_uuid=UUID, pin_override=None):
        self.kernel, self.calls, self.fail, self.case_file, self.probe_uuid = kernel, [], fail, case_file, probe_uuid
        self.ns = load(kernel)
        self.src, inv_sha = source_tree(tmp, inventory)
        self.ns["PINS"][self.ns["INVENTORY"]] = inv_sha
        self.ns.update(pin_override or {})
        (tmp / "out").mkdir()
        self.out = tmp / "out" / f"grid02_{kernel}"
        self.ns.update(OUT=self.out, nvidia_smi=lambda: smi, fetch_source=lambda base: self.src, install_julia=lambda base: Path("/fake/julia"), run=self.run)
        self.case = self.ns["CASE_ID"]
        self.rows = {r["name"]: r for r in INV["states"]}

    def run(self, args, log_path, env=None, timeout=3600):
        a = [str(x) for x in args]
        self.calls.append({"args": a, "env": env, "timeout": timeout})
        if "-e" in a:
            if "Pkg.instantiate()" in a[-1]:
                return 0
            Path(env["GRID01_GPU_PROBE_OUT"]).write_text(json.dumps({"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "visible_gpu_uuids": [self.probe_uuid], "default_device_uuid": self.probe_uuid,
                                                                    "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}))
            return 0
        phi, outdir = Path(a[-2]), Path(a[-1])
        name = phi.name[: -len(".phi.f32f")]
        assert hashlib.sha256(phi.read_bytes()).hexdigest() == self.rows[name]["phi_fortran_order_sha256"], "the job must receive the registered phi bytes"
        if name == self.fail:
            return 1
        case = self.case_file or self.case
        (outdir / f"{case}.forces.csv").write_text(f"fake forces {name}\n")
        (outdir / f"{case}.summary.json").write_text("{}\n")
        (outdir / "W4_JOB_DONE").write_text("done\n")
        return 0

    def jobs(self):
        return [c for c in self.calls if "-e" not in c["args"]]

    def go(self):
        try:
            self.ns["main"]()
            return 0
        except SystemExit as e:
            return e.code

    def index(self):
        return json.loads((self.out / "grid02_index.json").read_text())


@pytest.mark.parametrize("kernel", list(C.KERNELS))
def test_complete_run_goes_parent_first_sets_the_per_kernel_environment_and_writes_done_and_manifest(tmp_path, monkeypatch, kernel):
    monkeypatch.setenv("GRID02_CASE", "inherited-bogus")
    h = Harness(tmp_path, kernel)
    assert h.go() == 0
    cfg, names = INV["kernel_config"][kernel], INV["kernels"][kernel]
    idx = h.index()
    assert idx["status"] == "COMPLETE" and [e["name"] for e in idx["states"]] == names and idx["states"][0]["kind"] in ("parent", "parent_repeat") and all(e["complete"] for e in idx["states"])
    assert idx["parent_forces_csv_sha256"] == idx["states"][0]["forces_csv_sha256"] and "matches_retained_parent_reference" not in idx["states"][0]
    assert (h.out / "DONE").is_file() and not (h.out / "ERROR.txt").exists() and json.loads((h.out / "run_identity.json").read_text())["failure_stage"] is None
    manifest = json.loads((h.out / "output_manifest.json").read_text())["files"]
    assert f"states/{names[0]}/{cfg['case_id']}.forces.csv" in manifest and "DONE" in manifest and "grid02_index.json" in manifest and "gpu_device_probe.json" in manifest
    jobs = h.jobs()
    assert [Path(j["args"][-2]).name[:-9] for j in jobs] == names and all(j["args"][3].endswith(cfg["job"]) for j in jobs)
    for j in jobs:
        env = j["env"]
        assert env["W4_CANONICAL_ORIGIN_M"] == cfg["W4_CANONICAL_ORIGIN_M"] and env["W4_SELECTED_GPU_UUID"] == UUID and env["CUDA_VISIBLE_DEVICES"] == "0" and env["JULIA_NUM_THREADS"] == "1"
        assert env.get("GRID02_CASE") == cfg["GRID02_CASE"] and env["W4_CANONICAL_DESIGN_SPACING_M"] == "0.025"
        assert env["W4_PHI_FORTRAN_SHA256"] == h.rows[Path(j["args"][-2]).name[:-9]]["phi_fortran_order_sha256"]
    shifted = {j["env"]["W4_CANONICAL_ORIGIN_M"] for j in jobs} == {"-0.9875,-0.7875,-0.6"}
    assert shifted == (kernel in ("s24", "s32")) and ("GRID02_CASE" in jobs[0]["env"]) == kernel.startswith("f")
    assert min(j["timeout"] for j in jobs) <= cfg["per_state_timeout_s"]


def test_a_failing_job_stops_the_kernel_with_error_and_no_done(tmp_path):
    h = Harness(tmp_path, "s24", fail="opt01b__prop__s0.625mm")
    assert h.go() == 1
    assert not (h.out / "DONE").exists() and (h.out / "ERROR.txt").is_file() and h.index()["status"] == "ERROR" and len(h.jobs()) == 3
    assert json.loads((h.out / "run_identity.json").read_text())["failure_stage"] == "state:opt01b__prop__s0.625mm" and (h.out / "output_manifest.json").is_file()


def test_a_failing_parent_stops_before_any_perturbed_state(tmp_path):
    h = Harness(tmp_path, "f48b", fail=C.REPEAT)
    assert h.go() == 1 and len(h.jobs()) == 1 and not (h.out / "DONE").exists()


def test_a_wrong_case_file_name_is_a_failure(tmp_path):
    h = Harness(tmp_path, "f48a", case_file="flow_24")
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.index()["states"][0]["complete"] is False and len(h.jobs()) == 1


def test_a_non_t4_or_malformed_gpu_inventory_fails_before_any_julia_call(tmp_path):
    h = Harness(tmp_path, "s32", smi=f"0, NVIDIA A100, {UUID}, 40960 MiB, 535\n")
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.calls == []


def test_a_probe_uuid_that_differs_from_the_selected_gpu_fails_before_any_state(tmp_path):
    h = Harness(tmp_path, "f16", probe_uuid="GPU-other")
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.jobs() == [] and json.loads((h.out / "run_identity.json").read_text())["failure_stage"] == "observed_cuda_device_probe"


def test_a_pin_mismatch_fails_at_source_checkout(tmp_path):
    h = Harness(tmp_path, "s24")
    h.ns["PINS"][h.ns["JOB"]] = "0" * 64
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.calls == [] and json.loads((h.out / "run_identity.json").read_text())["failure_stage"] == "source_checkout"


def test_a_phi_that_differs_from_the_inventory_fails_before_the_job_runs(tmp_path):
    bad = copy.deepcopy(INV)
    next(r for r in bad["states"] if r["name"] == "opt01b__prop__s0.9375mm")["phi_fortran_order_sha256"] = "0" * 64
    h = Harness(tmp_path, "f48a", inventory=bad)
    assert h.go() == 1 and not (h.out / "DONE").exists() and len(h.jobs()) == 3 and "differs from inventory" in (h.out / "ERROR.txt").read_text()


def test_exceeding_the_per_state_budget_is_an_integrity_failure(tmp_path):
    h = Harness(tmp_path, "s32", pin_override={"PER_STATE_TIMEOUT_S": 1e-9})
    assert h.go() == 1 and not (h.out / "DONE").exists() and "budget exceeded" in (h.out / "ERROR.txt").read_text()


def test_expected_plan_refuses_inconsistent_inventories_and_bindings():
    ns = load("f48b")
    for mutate in (lambda i: i.update(stage_status="BLOCKED"), lambda i: i["kernels"].update(f48b=list(reversed(i["kernels"]["f48b"]))), lambda i: i.update(kind="x"),
                   lambda i: i["kernel_config"]["f48b"].update(per_state_timeout_s=1), lambda i: i["kernel_config"]["f48b"].update(W4_CANONICAL_ORIGIN_M="-1.0,-0.8,-0.5"),
                   lambda i: i["kernel_config"]["f48b"].update(job="scripts/waterlily_lowdim02_flow32_job.jl"),
                   lambda i: next(r for r in i["states"] if r["kind"] == "parent_repeat").update(state_sha256="0" * 64),
                   lambda i: i["parent"].update(phi_fortran_order_sha256="0" * 64), lambda i: i["blockers"].append("x")):
        bad = copy.deepcopy(INV)
        mutate(bad)
        with pytest.raises(ValueError):
            ns["expected_plan"](bad)
    ns["CONFIG"] = dict(ns["CONFIG"], GRID02_CASE=None)  # the new job requires GRID02_CASE
    with pytest.raises(ValueError):
        ns["expected_plan"](INV)
    ns = load("s24")
    ns["CONFIG"] = dict(ns["CONFIG"], GRID02_CASE="flow_24")  # a proven job must not receive it
    with pytest.raises(ValueError):
        ns["expected_plan"](INV)
    ns = load("f16")
    assert [r["name"] for r in ns["expected_plan"](INV)] == INV["kernels"]["f16"]
    ns = load("f48b")  # a second parent inside the list is refused
    ns["EXPECTED_NAMES"] = [C.REPEAT, C.PARENT] + ns["EXPECTED_NAMES"][1:]
    inv = copy.deepcopy(INV)
    inv["kernels"]["f48b"] = ns["EXPECTED_NAMES"]
    with pytest.raises(ValueError, match="exactly one parent"):
        ns["expected_plan"](inv)


def test_generate_phi_regenerates_every_state_in_both_byte_orders_and_refuses_a_wrong_row():
    ns = load("f16")
    import numpy as np
    parent = S.read_f4(ROOT / INV["parent"]["raw_path"])
    dirs = {"robust_opt01a": S.read_f4(ROOT / INV["proposal"]["file"])}
    for row in ns["expected_plan"](INV):
        raw = ns["generate_phi"](S, ROOT, row, parent, dirs)
        assert S.sha256_bytes(raw) == row["phi_fortran_order_sha256"] and (raw == S.to_raw(parent)) == (row["kind"] in ("parent", "parent_repeat"))
    bad = dict(INV["states"][2], changed_node_count=INV["states"][2]["changed_node_count"] + 1)
    with pytest.raises(RuntimeError, match="change metrics"):
        ns["generate_phi"](S, ROOT, bad, parent, dirs)
    bad = dict(INV["states"][2], phi_c_order_sha256="0" * 64)
    with pytest.raises(RuntimeError, match="C-order"):
        ns["generate_phi"](S, ROOT, bad, parent, dirs)
    assert np.array_equal(S.read_f4(ROOT / INV["parent"]["raw_path"]), parent)


def test_kernel_builder_refuses_to_overwrite_and_a_non_sha_commit(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="full lowercase SHA"):
        K.verify_source("abc", {"scripts/step01_states.py"})
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "TEMPLATE", tmp_path / "t.py")
    (tmp_path / "infra/kaggle/kernel_grid02_s24").mkdir(parents=True)
    monkeypatch.setattr(K, "pins", lambda k: {})
    monkeypatch.setattr(K, "verify_source", lambda *a: None)
    monkeypatch.setattr(sys, "argv", ["x", "--source-commit", DUMMY])
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        K.main()
