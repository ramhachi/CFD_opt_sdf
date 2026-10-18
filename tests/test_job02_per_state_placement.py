"""JOB-02 (#59): per-run flow-grid placement (x, y of the canonical origin) inside one kernel, named runs, and the byte-identity gate.

Default behaviour: a campaign without run names is unchanged (run name == state); the existing harness suites (runner == grid02 runner, GRID-02 replay bit for bit) cover it and must keep passing.
The gate dry run feeds the historical force CSVs and summaries through the harness runner, the verifier and scripts/job02_gate.py (planted truth: they must pass, a flipped byte must fail).
"""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import harness_testlib as T  # noqa: E402
import test_harness_runner as R  # noqa: E402
from cfd_harness import campaign_verify as V  # noqa: E402
import job02_gate as G  # noqa: E402

SC = T.SC
JOB02 = T.ROOT / "docs/harness/job02_gate_campaign.json"
SPEC = T.ROOT / "docs/evidence/job02_gate_2026_10_19/gate_spec.json"
CAMPAIGN = json.loads(JOB02.read_text())
REL = str(JOB02.relative_to(T.ROOT))
NATIVE, SHIFTED = "-1.0,-0.8,-0.6", "-0.9875,-0.7875,-0.6"
SHIFT_RUN = "opt01b__parent__grid02_shift"
OPT, GRID02 = T.OPT / "kernel_output", T.EV / "kernel_output"
HISTORY = {"f24": {"opt01b__parent": OPT / "opt01b_a/states/opt01b__parent", SHIFT_RUN: GRID02 / "grid02_s24/states/opt01b__parent"},
           "f32": {"opt01b__parent": OPT / "opt01b_b/states/opt01b__parent", SHIFT_RUN: GRID02 / "grid02_s32/states/opt01b__parent"}}


def edited(mutate, campaign=CAMPAIGN):
    c = copy.deepcopy(campaign)
    mutate(c)
    return c


class Placed(R.Fake):
    """The harness fake job, with job inputs looked up by run name and (optionally) the historical job outputs of each run replayed (GPU UUID set to the fake GPU's)."""

    def __init__(self, tmp, kernel, history=None, **kw):
        super().__init__(tmp, kernel, campaign_file=JOB02, **kw)
        spec = (kw.get("campaign") or CAMPAIGN)["kernels"][kernel]
        self.rows = {n: CAMPAIGN["states"][r["state"]] for n, r in SC.runs_by_name(spec).items()}
        self.history = history

    def run(self, args, log_path, env=None, timeout=3600):
        a = [str(x) for x in args]
        if "-e" in a or self.history is None:
            return super().run(args, log_path, env, timeout)
        self.calls.append({"args": a, "env": env, "timeout": timeout})
        Path(log_path).write_text("fake log\n")
        phi, outdir = Path(a[-2]), Path(a[-1])
        name = phi.name[: -len(".phi.f32f")]
        assert hashlib.sha256(phi.read_bytes()).hexdigest() == self.rows[name]["phi_fortran_order_sha256"]
        src = self.history[name]
        shutil.copy(src / f"{self.case}.forces.csv", outdir)
        shutil.copy(src / "W4_JOB_DONE", outdir)
        summary = json.loads((src / f"{self.case}.summary.json").read_text())
        summary["gpu_uuid"] = T.UUID
        (outdir / f"{self.case}.summary.json").write_text(json.dumps(summary))
        return 0


# ---------------------------------------------------------------- default behaviour is unchanged
@pytest.mark.parametrize("path", [T.REPLAY, T.ROOT / "docs/harness/harness01_replay_campaign.json"])
def test_campaigns_without_run_names_keep_the_state_as_the_run_name(path):
    c = json.loads(path.read_text())
    SC.validate_campaign(c)
    for kernel in c["kernels"].values():
        assert SC.run_names(kernel) == [r["state"] for r in kernel["runs"]] and SC.runs_by_name(kernel) == {r["state"]: r for r in kernel["runs"]}


# ---------------------------------------------------------------- schema
def test_the_gate_campaign_runs_one_state_at_two_xy_placements_per_kernel_with_z_fixed():
    SC.validate_campaign(CAMPAIGN)
    for kernel in CAMPAIGN["kernels"].values():
        assert SC.run_names(kernel) == ["opt01b__parent", SHIFT_RUN] and [r["state"] for r in kernel["runs"]] == ["opt01b__parent"] * 2
        assert [r["env"]["W4_CANONICAL_ORIGIN_M"] for r in kernel["runs"]] == [NATIVE, SHIFTED]
    assert SC.ORIGIN_ENV not in CAMPAIGN["job_env_common"]


def test_the_gate_campaign_job_env_equals_the_historical_runs_env():
    for inv in (T.OPT / "inventory.json", T.EV / "inventory.json"):  # OPT-01 v1 Stage B (native) and GRID-02 (shifted)
        common = json.loads(inv.read_text())["job_env_common"]
        for kernel in CAMPAIGN["kernels"].values():
            native, shifted = (SC.effective_env(CAMPAIGN, r) for r in kernel["runs"])
            assert native == common and shifted == dict(common, W4_CANONICAL_ORIGIN_M=SHIFTED)


@pytest.mark.parametrize("mutate, message", [
    (lambda c: c["kernels"]["f24"]["runs"][1].pop("name"), "distinct run names"),  # the same state twice needs a run name
    (lambda c: c["kernels"]["f24"].update(runs=[dict(c["kernels"]["f24"]["runs"][1], name="opt01b__parent")]), "not a state name"),  # a name may not alias a state
    (lambda c: c["kernels"]["f24"]["runs"][1].update(name="a/b"), "safe name"),
    (lambda c: c["kernels"]["f24"]["runs"][1].update(name=7), "distinct run names"),
    (lambda c: c["kernels"]["f24"]["runs"][1].update(name=["a"]), "distinct run names"),
    (lambda c: c["kernels"]["f24"]["runs"][1].update(name=".."), "safe name"),
    (lambda c: c["kernels"]["f24"]["runs"][1].update(placement="x"), "run"),
    (lambda c: c["kernels"]["f24"]["runs"][1]["env"].update(W4_CANONICAL_ORIGIN_M="-0.9875,-0.7875,-0.59"), "ride height"),
])
def test_schema_rejects_ambiguous_run_names_and_a_per_run_z_change(mutate, message):
    with pytest.raises(ValueError, match=message):
        SC.validate_campaign(edited(mutate))


def test_a_z_change_is_rejected_also_through_the_common_origin():
    def mutate(c):
        c["job_env_common"]["W4_CANONICAL_ORIGIN_M"] = "-1.0,-0.8,-0.5"
        del c["kernels"]["f24"]["runs"][0]["env"]["W4_CANONICAL_ORIGIN_M"]  # this run inherits z = -0.5, the other keeps -0.6
    with pytest.raises(ValueError, match="ride height"):
        SC.validate_campaign(edited(mutate))


# ---------------------------------------------------------------- runner
@pytest.mark.parametrize("kernel", ["f24", "f32"])
def test_one_kernel_runs_each_named_run_with_its_own_origin_and_the_same_phi(tmp_path, kernel):
    h = Placed(tmp_path, kernel)
    assert h.go() == 0
    names = SC.run_names(CAMPAIGN["kernels"][kernel])
    idx = h.index()
    assert [e["name"] for e in idx["states"]] == names and all(e["complete"] and e["kind"] == "parent" for e in idx["states"])
    assert {p.name for p in (h.out / "states").iterdir()} == set(names) and (h.out / "DONE").is_file()
    jobs = h.jobs()
    assert [Path(j["args"][-2]).name for j in jobs] == [n + ".phi.f32f" for n in names]
    assert [j["env"]["W4_CANONICAL_ORIGIN_M"] for j in jobs] == [NATIVE, SHIFTED]
    assert jobs[0]["env"]["W4_PHI_FORTRAN_SHA256"] == jobs[1]["env"]["W4_PHI_FORTRAN_SHA256"] == CAMPAIGN["states"]["opt01b__parent"]["phi_fortran_order_sha256"]
    assert {k: v for k, v in jobs[0]["env"].items() if k != "W4_CANONICAL_ORIGIN_M"} == {k: v for k, v in jobs[1]["env"].items() if k != "W4_CANONICAL_ORIGIN_M"}
    assert json.loads((h.out / "self_test.json").read_text())["phi_identities_verified"] == 2


def test_the_smoke_runs_only_the_native_first_run(tmp_path):
    h = Placed(tmp_path, "f24", smoke=True)
    assert h.go() == 0 and [j["env"]["W4_CANONICAL_ORIGIN_M"] for j in h.jobs()] == [NATIVE] and h.identity()["expected_names"] == ["opt01b__parent"]


# ---------------------------------------------------------------- verifier + gate on the historical outputs (planted truth)
def dry_run(tmp_path):
    root, states = tmp_path / "root", {}
    root.mkdir()
    for k in ("f24", "f32"):
        (tmp_path / k).mkdir()
        h = Placed(tmp_path / k, k, history=HISTORY[k])
        assert h.go() == 0
        ident = h.identity()
        freeze = {"source_commit": T.DUMMY, "pins": {k: ident["pins"]}, "runtime": {k: {"kernel_id": ident["kernel_id"], "runner_sha256": ident["runner_sha256"]}}}
        got, states[k] = V.check_kernel(h.out, CAMPAIGN, SC.sha256_path(JOB02), REL, freeze)
        assert got == k
        shutil.copytree(h.out, root / h.out.name)
    manifests = {k: SC.sha256_path(root / f"job02_gate_{k}" / SC.MANIFEST_NAME) for k in states}
    table = {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "smoke": False, "integrity": {"pass": True, "failures": []}, "campaign_sha256": SC.sha256_path(JOB02),
             "kernel_manifest_sha256": manifests, "state_forces_n": states}
    path = tmp_path / "table.json"
    path.write_text(json.dumps(table))
    return root, path, states


def test_the_historical_parents_pass_the_verifier_and_the_gate_and_differ_between_placements(tmp_path):
    root, table, states = dry_run(tmp_path)
    for k in ("f24", "f32"):
        assert states[k]["opt01b__parent"]["downforce_n"] != states[k][SHIFT_RUN]["downforce_n"]  # the two placements are different flows
    result = G.gate(SPEC, table, root)
    assert result["verdict"] == "JOB02_GATE_PASS" and len(result["comparisons"]) == 4 and all(r["byte_identical"] for r in result["comparisons"])
    analysis = json.loads((T.EV / "grid02_analysis.json").read_text())["state_forces_n"]
    assert states["f24"][SHIFT_RUN]["forces_csv_sha256"] == analysis["s24"]["opt01b__parent"]["forces_csv_sha256"]


def test_the_gate_fails_on_one_flipped_byte_and_on_a_spec_that_misses_a_run(tmp_path):
    root, table, _ = dry_run(tmp_path)
    csv = root / "job02_gate_f32" / "states" / SHIFT_RUN / "flow_32.forces.csv"
    data = bytearray(csv.read_bytes())
    data[-2] = ord("0") if data[-2] != ord("0") else ord("1")
    csv.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="differs from the verified table"):  # bytes that are not the verified output are refused outright
        G.gate(SPEC, table, root)
    out = root / "job02_gate_f32"
    (out / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(out)))
    t = json.loads(table.read_text())
    t["kernel_manifest_sha256"]["f32"] = SC.sha256_path(out / SC.MANIFEST_NAME)  # a table that (wrongly) verified the changed bytes still fails the byte comparison
    table.write_text(json.dumps(t))
    result = G.gate(SPEC, table, root)
    assert result["verdict"] == "JOB02_GATE_FAIL" and [r["byte_identical"] for r in result["comparisons"]] == [True, True, True, False]
    spec = json.loads(SPEC.read_text())
    spec["comparisons"].pop()
    short = tmp_path / "short_spec.json"
    short.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="exactly the campaign's runs"):
        G.gate(short, table, root)


def test_a_run_whose_summary_carries_another_origin_fails_the_verifier(tmp_path):
    swapped = {"opt01b__parent": HISTORY["f24"][SHIFT_RUN], SHIFT_RUN: HISTORY["f24"]["opt01b__parent"]}
    h = Placed(tmp_path, "f24", history=swapped)
    assert h.go() == 0
    ident = h.identity()
    freeze = {"source_commit": T.DUMMY, "pins": {"f24": ident["pins"]}, "runtime": {"f24": {"kernel_id": ident["kernel_id"], "runner_sha256": ident["runner_sha256"]}}}
    with pytest.raises(ValueError, match="canonical_sdf_origin_m"):
        V.check_kernel(h.out, CAMPAIGN, SC.sha256_path(JOB02), REL, freeze)


def test_the_gate_rejects_a_smoke_table(tmp_path):
    root, table, _ = dry_run(tmp_path)
    t = json.loads(table.read_text())
    t["smoke"] = True
    table.write_text(json.dumps(t))
    with pytest.raises(ValueError, match="smoke"):
        G.gate(SPEC, table, root)
