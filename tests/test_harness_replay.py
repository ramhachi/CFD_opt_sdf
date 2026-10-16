"""harness v1.1 acceptance (a), (c), (d): replay equivalence on the saved GRID-02 outputs, planted truth, C- versus Fortran-order SHA fields, and verifier fail-closed mutations."""
import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import harness_testlib as T  # noqa: E402
from cfd_harness import campaign_verify as V  # noqa: E402
import harness as H  # noqa: E402

SC = T.SC
KERNELS = ["f16", "f48a", "f48b", "s24", "s32"]
OUT = T.EV / "kernel_output"
ANALYSIS = json.loads((T.EV / "grid02_analysis.json").read_text())
REAL_FREEZE = json.loads((T.EV / "prerun_freeze.json").read_text())
CAMPAIGN = json.loads(T.REPLAY.read_text())
SHA = SC.sha256_path(T.REPLAY)
REL = str(T.REPLAY.relative_to(T.ROOT))


def synthetic_freeze(tmp):
    """A harness-format freeze built from the real GRID-02 freeze (same source commit, pins and runner hashes), written with its sidecar."""
    f = {"kind": SC.FREEZE_KIND, "harness_version": SC.HARNESS_VERSION, "legacy_replay": True, "campaign_path": REL, "frozen_utc": REAL_FREEZE["frozen_utc"], "source_commit": REAL_FREEZE["source_commit"],
         "campaign_sha256": SHA, "pins": REAL_FREEZE["pins"],
         "runtime": {k: {"kernel_id": v["kernel_id"], "runner_sha256": v["runner_sha256"]} for k, v in REAL_FREEZE["runtime"].items()}, "identity_free_check": REAL_FREEZE["identity_free_check"]}
    path = Path(tmp) / "freeze.json"
    path.write_text(json.dumps(f))
    path.with_name("freeze.json.sha256").write_text(SC.sha256_path(path) + "\n")
    return path, f


@pytest.fixture(scope="module")
def freeze_file(tmp_path_factory):
    return synthetic_freeze(tmp_path_factory.mktemp("freeze"))[0]


# ---------------------------------------------------------------- (a) replay equivalence
def test_replay_campaign_is_valid_and_regenerates_from_the_inventory():
    SC.validate_campaign(CAMPAIGN)
    assert CAMPAIGN == T.replay_campaign() and set(CAMPAIGN["kernels"]) == set(KERNELS)
    inv = json.loads((T.EV / "inventory.json").read_text())
    for k, cfg in inv["kernel_config"].items():
        kernel = CAMPAIGN["kernels"][k]
        assert SC.run_names(kernel) == inv["kernels"][k] and kernel["config"]["kernel_timeout_s"] == cfg["kernel_timeout_s"] and kernel["case"]["case_id"] == cfg["case_id"]
        assert SC.force_scale_n(kernel["case"]) == cfg["force_scale_n_per_solver_force"]


def test_verify_passes_all_five_saved_kernels_and_reproduces_the_registered_state_forces_exactly(freeze_file):
    table = V.verify(T.REPLAY, [OUT / f"grid02_{k}" for k in KERNELS], freeze_file)
    assert table["kind"] == SC.TABLE_KIND and table["integrity"] == {"pass": True, "failures": []} and table["smoke"] is False
    assert table["state_forces_n"] == ANALYSIS["state_forces_n"]  # all six fields of every state, bit for bit
    assert table["kernel_manifest_sha256"] == ANALYSIS["provenance"]["kernel_manifest_sha256"]
    assert sum(len(v) for v in table["state_forces_n"].values()) == 29


def test_cli_verify_prints_the_table_and_fails_closed_with_exit_3(freeze_file, tmp_path, capsys):
    dirs = [str(OUT / f"grid02_{k}") for k in KERNELS]
    out = tmp_path / "table.json"
    H.main(["verify", *dirs, "--campaign", str(T.REPLAY), "--freeze", str(freeze_file), "--out", str(out)])
    assert json.loads(out.read_text())["state_forces_n"] == ANALYSIS["state_forces_n"]
    with pytest.raises(SystemExit) as e:  # never overwrites
        H.main(["verify", *dirs, "--campaign", str(T.REPLAY), "--freeze", str(freeze_file), "--out", str(out)])
    assert e.value.code == 3
    with pytest.raises(SystemExit) as e:  # a missing kernel
        H.main(["verify", *dirs[:4], "--campaign", str(T.REPLAY), "--freeze", str(freeze_file)])
    assert e.value.code == 3 and "kernel directories" in capsys.readouterr().err


def test_replay_pins_contain_every_grid02_pin_with_the_same_hash():
    from cfd_harness import campaign_build as B
    rel = str(T.REPLAY.relative_to(T.ROOT))
    for k in KERNELS:
        mine = B.pins(CAMPAIGN, rel, k, T.ROOT)
        assert all(mine[p] == h for p, h in REAL_FREEZE["pins"][k].items()), k
        assert {rel, B.SCHEMA_REL, "scripts/fd08_v2_campaign_io.py"} <= set(mine)


# ---------------------------------------------------------------- verifier fail-closed mutations on a copy of one real kernel output
def edit_json(path, fn):
    data = json.loads(Path(path).read_text())
    fn(data)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def remanifest(d):
    (d / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(d), indent=2, sort_keys=True) + "\n")


@pytest.fixture
def s24(tmp_path):
    d = tmp_path / "grid02_s24"
    shutil.copytree(OUT / "grid02_s24", d)
    return d


def check(d, smoke=False):
    f = {"source_commit": REAL_FREEZE["source_commit"], "pins": REAL_FREEZE["pins"], "runtime": {k: {"kernel_id": v["kernel_id"], "runner_sha256": v["runner_sha256"]} for k, v in REAL_FREEZE["runtime"].items()}}
    return V.check_kernel(d, CAMPAIGN, SHA, str(T.REPLAY.relative_to(T.ROOT)), f, smoke)


PARENT = "opt01b__parent"
ROW = CAMPAIGN["states"]


def summary_of(d, name=PARENT):
    return d / "states" / name / "flow_24.summary.json"


MUTATIONS = {
    "missing DONE": (lambda d: (d / "DONE").unlink(), "DONE must exist"),
    "csv byte changed": (lambda d: (d / "states" / PARENT / "flow_24.forces.csv").write_bytes((d / "states" / PARENT / "flow_24.forces.csv").read_bytes() + b" "), "manifest hash mismatch"),
    "ERROR.txt present": (lambda d: ((d / "ERROR.txt").write_text("x"), remanifest(d)), "ERROR.txt must not"),
    "state order": (lambda d: (edit_json(d / "grid02_index.json", lambda i: i["states"].reverse()), remanifest(d)), "exact registered state order"),
    "device roundtrip is the C-order SHA": (lambda d: (edit_json(summary_of(d), lambda s: s.update(device_roundtrip_sha256=ROW[PARENT]["phi_c_order_sha256"])), remanifest(d)), "device_roundtrip_sha256"),
    "phi_c_order SHA is the Fortran-order SHA": (lambda d: (edit_json(summary_of(d), lambda s: s.update(phi_c_order_sha256=ROW[PARENT]["phi_fortran_order_sha256"])), remanifest(d)), "phi_c_order_sha256"),
    "julia force summary off by 1e-6": (lambda d: (edit_json(summary_of(d), lambda s: s.update(drag_time_weighted_n=s["drag_time_weighted_n"] * (1 + 1e-6))), remanifest(d)), "differs from Julia force summary"),
    "per-state budget": (lambda d: (edit_json(d / "grid02_index.json", lambda i: i["states"][0].update(seconds=1e6)), remanifest(d)), "exceeds budget"),
    "non-T4 GPU": (lambda d: ((d / "nvidia_smi.csv").write_text("0, NVIDIA A100, GPU-1, 40960 MiB, 535\n"), remanifest(d)), "Tesla T4"),
    "runner hash": (lambda d: (edit_json(d / "run_identity.json", lambda i: i.update(runner_sha256="0" * 64)), remanifest(d)), "runner differs from the freeze"),
    "pin map": (lambda d: (edit_json(d / "run_identity.json", lambda i: (i["pins"].update({"scripts/grid01_gpu.py": "0" * 64}), i["verified"].update({"scripts/grid01_gpu.py": "0" * 64}))), remanifest(d)), "pins differ from the freeze"),
    "probe UUID": (lambda d: (edit_json(d / "gpu_device_probe.json", lambda p: p.update(default_device_uuid="GPU-other")), remanifest(d)), "singleton/default"),
    "case in identity": (lambda d: (edit_json(d / "run_identity.json", lambda i: i.update(case_id="flow_32")), remanifest(d)), "case_id identity"),
    "unknown kernel": (lambda d: (edit_json(d / "grid02_index.json", lambda i: i.update(kernel="zz")), remanifest(d)), "unknown kernel"),
}


def test_the_unmutated_copy_passes(s24):
    k, states = check(s24)
    assert k == "s24" and states == ANALYSIS["state_forces_n"]["s24"]


@pytest.mark.parametrize("label", list(MUTATIONS))
def test_verify_fails_closed_on(s24, label):
    mutate, message = MUTATIONS[label]
    mutate(s24)
    with pytest.raises(ValueError, match=message):
        check(s24)


def test_a_consistent_edit_of_the_force_history_is_caught_by_the_host_recomputation(s24):
    csv = s24 / "states" / PARENT / "flow_24.forces.csv"
    lines = csv.read_text().splitlines()
    cols = lines[0].split(",")
    last = lines[-1].split(",")
    last[cols.index("drag_solver")] = last[cols.index("fx_solver")] = repr(float(last[cols.index("drag_solver")]) + 5.0)
    last[cols.index("pressure_fx_solver")] = repr(float(last[cols.index("pressure_fx_solver")]) + 5.0)
    csv.write_text("\n".join(lines[:-1] + [",".join(last)]) + "\n")
    new = SC.sha256_path(csv)
    edit_json(s24 / "grid02_index.json", lambda i: i["states"][0].update(forces_csv_sha256=new) or i.update(parent_forces_csv_sha256=new))
    remanifest(s24)
    with pytest.raises(ValueError, match="recomputation|identities"):
        check(s24)


def test_a_legacy_output_cannot_be_passed_off_as_a_smoke_output(s24):
    with pytest.raises(ValueError, match="smoke output must come from a harness runner"):
        check(s24, smoke=True)


# ---------------------------------------------------------------- (c) planted truth
def planted(tmp, scale_spacing=0.5):
    """Linear force history with exactly known window means: drag = 2 + t/2, downforce = 1 + t/4 (fz = -downforce), window [3.5, 6.5] -> means 4.5 and 2.25 (trapezoid is exact for linear data)."""
    rows = [",".join(SC.FORCE_COLUMNS)]
    for i in range(11):
        t = float(i)
        drag, down = 2 + t / 2, 1 + t / 4
        rows.append(",".join(repr(float(v)) for v in (i, t, drag, 0.0, -down, drag, down, drag, 0.0, -down, 0.0, 0.0, 0.0)))
    path = Path(tmp) / "planted.forces.csv"
    path.write_text("\n".join(rows) + "\n")
    case = {"density_kg_m3": 1.0, "freestream_mps": [1.0, 0.0, 0.0], "flow_spacing_m": scale_spacing}
    return path, case


def test_planted_force_history_is_recomputed_exactly_with_the_case_force_scale(tmp_path):
    path, case = planted(tmp_path)
    c = {"measurement": {"time_window_t_u_l": [3.5, 6.5]}}
    kernel = {"case": {**case, "solver_length": 1.0}}
    summary = {"drag_time_weighted_n": 4.5 * 0.25, "downforce_time_weighted_n": 2.25 * 0.25}
    host = SC.host_forces(path, c, kernel, summary)
    assert (host["drag_n"], host["downforce_n"], host["force_scale_n_per_solver_force"]) == (1.125, 0.5625, 0.25)
    with pytest.raises(ValueError, match="differs from Julia"):
        SC.host_forces(path, c, kernel, dict(summary, downforce_time_weighted_n=0.5625 * (1 + 1e-6)))
    with pytest.raises(ValueError, match="differs from Julia"):  # the wrong scale (e.g. another grid's spacing) is not silently accepted
        SC.host_forces(path, c, {"case": {**case, "flow_spacing_m": 0.25, "solver_length": 1.0}}, summary)
    SC.selftest_force_check()


# ---------------------------------------------------------------- (d) C- versus Fortran-order SHA are distinct fields; device roundtrip is the Fortran SHA
def test_state_identity_has_distinct_c_and_fortran_sha_fields_and_every_state_differs_between_them():
    assert "phi_fortran_order_sha256" in SC.STATE_IDENTITY_KEYS and "phi_c_order_sha256" in SC.STATE_IDENTITY_KEYS
    assert all(r["phi_fortran_order_sha256"] != r["phi_c_order_sha256"] for r in ROW.values())
    kernel, run, row = CAMPAIGN["kernels"]["s24"], CAMPAIGN["kernels"]["s24"]["runs"][0], ROW[PARENT]
    exp = SC.expected_summary(CAMPAIGN, kernel, run, row, "GPU-x")
    assert exp["device_roundtrip_sha256"] == exp["phi_fortran_sha256"] == row["phi_fortran_order_sha256"] and exp["phi_c_order_sha256"] == row["phi_c_order_sha256"] != exp["device_roundtrip_sha256"]


def test_check_summary_accepts_the_real_summary_and_rejects_swapped_sha_orders():
    d = OUT / "grid02_s24" / "states" / PARENT
    summary = json.loads((d / "flow_24.summary.json").read_text())
    kernel, run, row = CAMPAIGN["kernels"]["s24"], CAMPAIGN["kernels"]["s24"]["runs"][0], ROW[PARENT]
    uuid = summary["gpu_uuid"]
    assert SC.check_summary(summary, CAMPAIGN, kernel, run, row, uuid) == summary["wall_seconds"]
    for key, other in (("device_roundtrip_sha256", "phi_c_order_sha256"), ("phi_fortran_sha256", "phi_c_order_sha256"), ("phi_c_order_sha256", "phi_fortran_order_sha256")):
        with pytest.raises(ValueError, match=key):
            SC.check_summary(dict(summary, **{key: row[other]}), CAMPAIGN, kernel, run, row, uuid)
    with pytest.raises(ValueError, match="canonical_sdf_origin_m"):  # the per-state origin override is checked per run (native origin is not the shifted s24 origin)
        SC.check_summary(dict(summary, canonical_sdf_origin_m=[-1.0, -0.8, -0.6]), CAMPAIGN, kernel, run, row, uuid)


def test_campaign_schema_rejects_malformed_campaigns():
    for mutate in (lambda c: c.update(harness_version="harness v0"), lambda c: c["states"]["opt01b__parent"].update(direction="robust_opt01a"),
                   lambda c: c["states"]["opt01b__prop__s0.625mm"].update(sign=0), lambda c: c["kernels"]["s24"]["runs"].reverse(),
                   lambda c: c["kernels"]["s24"]["config"].update(solver_wall_time_cap_s=10800), lambda c: c["kernels"]["s24"]["runs"][0]["env"].update(W4_CANONICAL_ORIGIN_M="0,0,0"),
                   lambda c: c["kernels"]["s32"].update(kernel_id=c["kernels"]["s24"]["kernel_id"]), lambda c: c["job_env_common"].pop("W4_MARGIN_GATE_M"),
                   lambda c: c["states"]["opt01b__parent"].pop("npz_sha256"), lambda c: c["baseline"].update(path="../x")):
        bad = copy.deepcopy(CAMPAIGN)
        mutate(bad)
        with pytest.raises(ValueError):
            SC.validate_campaign(bad)


# ---------------------------------------------------------------- campaign cross-state rules, JSON strictness, CLI fail-closed on malformed input
def test_campaign_schema_rejects_inconsistent_state_sets():
    parent, repeat = "opt01b__parent", "opt01b__parent_repeat"
    def second_parent(c):
        c["states"][repeat]["kind"] = "parent"
    mutations = {
        "baseline kind with a direction": (lambda c: c["states"][parent].update(direction="robust_opt01a", step_mm=1.0, sign=1, changed_node_count=5), "baseline kinds"),
        "candidate without a direction": (lambda c: c["states"]["opt01b__prop__s0.625mm"].update(direction=None, step_mm=0, sign=0, changed_node_count=0), "baseline kinds"),
        "second parent": (second_parent, "exactly one parent"),
        "no parent": (lambda c: c["states"][parent].update(kind="parent_repeat"), "exactly one parent"),
        "repeat with another identity": (lambda c: c["states"][repeat].update(phi_fortran_order_sha256="1" * 64), "parent_repeat must equal"),
        "candidate shares the parent phi": (lambda c: c["states"]["opt01b__prop__s0.625mm"].update(phi_fortran_order_sha256=c["states"][parent]["phi_fortran_order_sha256"]), "share phi_fortran_order_sha256"),
        "two candidates share the C-order phi": (lambda c: c["states"]["opt01b__prop__s0.625mm"].update(phi_c_order_sha256=c["states"]["opt01b__prop__s1.25mm"]["phi_c_order_sha256"]), "share phi_c_order_sha256"),
        "aggregate cap below the per-state timeout": (lambda c: c["kernels"]["s24"]["config"].update(solver_wall_time_cap_s=800), "aggregate solver cap"),
        "legacy flag not a boolean": (lambda c: c.update(legacy_replay="yes"), "legacy_replay"),
    }
    for label, (mutate, message) in mutations.items():
        bad = copy.deepcopy(CAMPAIGN)
        mutate(bad)
        with pytest.raises(ValueError, match=message):
            SC.validate_campaign(bad)
        assert label


def test_jload_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path):
    path = tmp_path / "d.json"
    path.write_text('{"a": 1, "a": 2}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        SC.jload(path)
    path.write_text('{"a": {"b": 1, "b": 1}}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        SC.jload(path)
    path.write_text('{"a": NaN}')
    with pytest.raises(ValueError, match="nonfinite"):
        SC.jload(path)
    path.write_text('{"a": [1, 2]}')
    assert SC.jload(path) == {"a": [1, 2]}


def test_cli_turns_malformed_inputs_into_exit_3_not_a_traceback(s24, freeze_file, tmp_path, capsys):
    summary = summary_of(s24)
    summary.write_text("[]\n")  # AttributeError inside the summary check without the CLI guard
    remanifest(s24)
    with pytest.raises(AttributeError):
        check(s24)
    for argv in (["verify", str(s24), "--campaign", str(T.REPLAY), "--freeze", str(freeze_file)],
                 ["verify", str(s24), "--campaign", str(tmp_path / "missing.json"), "--freeze", str(freeze_file)],
                 ["verify", str(s24), "--campaign", str(T.REPLAY), "--freeze", str(tmp_path / "missing.json")]):
        with pytest.raises(SystemExit) as e:
            H.main(argv)
        assert e.value.code == 3
    bad = tmp_path / "bad_freeze.json"
    bad.write_text("[1]")
    with pytest.raises(SystemExit) as e:  # TypeError/AttributeError on a malformed freeze
        H.main(["verify", str(s24), "--campaign", str(T.REPLAY), "--freeze", str(bad)])
    assert e.value.code == 3 and "FAILED (fail closed)" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:  # a smoke verification without --source-commit
        H.main(["verify", str(s24), "--campaign", str(T.REPLAY), "--smoke"])
    assert e.value.code == 3


def test_a_legacy_freeze_must_name_the_campaign_flag_and_path(freeze_file):
    f = json.loads(freeze_file.read_text())
    c = copy.deepcopy(CAMPAIGN)
    V.validate_freeze(f, freeze_file, c, SHA, REL)
    for mutate in (lambda x: x.update(legacy_replay=False), lambda x: x.pop("legacy_replay"), lambda x: x.update(campaign_path="docs/harness/other.json"), lambda x: x["pins"]["s24"].pop(c["kernels"]["s24"]["job"])):
        bad = copy.deepcopy(f)
        mutate(bad)
        freeze_file.write_text(json.dumps(bad))
        freeze_file.with_name("freeze.json.sha256").write_text(SC.sha256_path(freeze_file) + "\n")
        with pytest.raises(ValueError):
            V.validate_freeze(bad, freeze_file, c, SHA, REL)
    freeze_file.write_text(json.dumps(f))
    freeze_file.with_name("freeze.json.sha256").write_text(SC.sha256_path(freeze_file) + "\n")
