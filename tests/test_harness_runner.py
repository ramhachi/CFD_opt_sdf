"""harness v1.1 acceptance (b), (e): the rendered runner against a fake job and fake source tree (no GPU, no network, no Julia); it equals the grid02 runner and fails closed; smoke differs only in the PIN block."""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import harness_testlib as T  # noqa: E402
from cfd_harness import campaign_build as B  # noqa: E402

SC = T.SC
DUMMY, UUID, SMI = T.DUMMY, T.UUID, T.SMI
KERNELS = ["f16", "f48a", "f48b", "s24", "s32"]
CAMPAIGN = json.loads(T.REPLAY.read_text())
REL = str(T.REPLAY.relative_to(T.ROOT))


H01 = T.ROOT / "docs/harness/harness01_replay_campaign.json"  # a real non-legacy campaign (kernel a: the cheapest case, one state, byte-gated first state)


def load(kernel, smoke=False, campaign_file=T.REPLAY, where=None):
    """Exec the rendered runner; with `where` it is written there first so that runner_sha256 is the hash of the rendered text, as on Kaggle."""
    text = B.render(campaign_file, DUMMY, kernel, smoke, T.ROOT)
    path = T.ROOT / B.TEMPLATE_REL
    if where is not None:
        path = Path(where) / "runner.py"
        path.write_text(text)
    ns = {"__name__": "rendered_harness_worker", "__file__": str(path)}
    exec(compile(text, f"runner_{kernel}.py", "exec"), ns)
    return ns


class Fake:
    """The grid02 test harness, pointed at the harness runner: a fake source tree (symlinks to the real julia/scripts/src/evidence plus a possibly tampered copy of the campaign)."""

    def __init__(self, tmp, kernel, *, smi=SMI, campaign=None, fail=None, case_file=None, probe_uuid=UUID, smoke=False, pin_override=None, campaign_file=T.REPLAY, signed=False):
        self.kernel, self.calls, self.fail, self.case_file, self.probe_uuid = kernel, [], fail, case_file, probe_uuid
        self.ns = load(kernel, smoke, campaign_file, tmp if signed else None)
        src = tmp / "src"
        (src / "docs/harness").mkdir(parents=True)
        (src / "docs/evidence").mkdir()
        (src / "src").mkdir(parents=True)
        for rel in ("julia", "scripts", "src/cfd_harness", "docs/evidence/opt01b_stage_b_2026_10_15", "docs/evidence/grid02_trend_2026_10_16"):
            (src / rel).symlink_to(T.ROOT / rel)
        rel = str(campaign_file.relative_to(T.ROOT))
        target = src / rel
        if campaign is None:
            target.write_bytes(campaign_file.read_bytes())  # the genuine bytes: its hash is the pinned one
        else:
            target.write_text(json.dumps(campaign, sort_keys=True))
        self.src = src
        self.ns["PINS"][self.ns["CAMPAIGN"]] = SC.sha256_path(target)
        self.ns.update(pin_override or {})
        (tmp / "out").mkdir()
        self.out = tmp / "out" / self.ns["OUT_DIR_NAME"]
        self.ns.update(OUT=self.out, nvidia_smi=lambda: smi, fetch_source=lambda base: self.src, install_julia=lambda base: Path("/fake/julia"), run=self.run)
        base = json.loads(campaign_file.read_text())
        self.rows = base["states"]
        self.case = base["kernels"][kernel]["case"]["case_id"]

    def run(self, args, log_path, env=None, timeout=3600):
        a = [str(x) for x in args]
        self.calls.append({"args": a, "env": env, "timeout": timeout})
        Path(log_path).write_text("fake log\n")  # the real run() always leaves its log
        if "-e" in a:
            if "Pkg.instantiate()" in a[-1]:
                return 0
            Path(env["GRID01_GPU_PROBE_OUT"]).write_text(json.dumps(dict(SC.GPU_EXPECTED, visible_gpu_uuids=[self.probe_uuid], default_device_uuid=self.probe_uuid)))
            return 0
        phi, outdir = Path(a[-2]), Path(a[-1])
        name = phi.name[: -len(".phi.f32f")]
        assert hashlib.sha256(phi.read_bytes()).hexdigest() == self.rows[name]["phi_fortran_order_sha256"], "the job must receive the registered phi bytes"
        if name == self.fail:
            return 1
        case = self.case_file or self.case
        if getattr(self, "real", None):  # replay the saved real job outputs of this state
            for f in (f"{case}.forces.csv", f"{case}.summary.json", "W4_JOB_DONE"):
                shutil.copy(self.real / "states" / name / f, outdir / f)
            return 0
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
        return json.loads((self.out / self.ns["INDEX_NAME"]).read_text())

    def identity(self):
        return json.loads((self.out / "run_identity.json").read_text())


def sub(tmp, name):
    (tmp / name).mkdir()
    return tmp / name


def tampered(mutate):
    c = copy.deepcopy(CAMPAIGN)
    mutate(c)
    return c


# ---------------------------------------------------------------- rendering
@pytest.mark.parametrize("kernel", KERNELS)
def test_render_binds_this_kernel_and_the_campaign(kernel):
    text = B.render(T.REPLAY, DUMMY, kernel, False, T.ROOT)
    assert "PIN_BLOCK" not in text and "PIN_" not in text.replace("SC.PIN_", "")
    ns = load(kernel)
    k = CAMPAIGN["kernels"][kernel]
    assert (ns["KERNEL"], ns["KERNEL_ID"], ns["SMOKE"], ns["CAMPAIGN"], ns["OUT_DIR_NAME"], ns["INDEX_NAME"]) == (kernel, k["kernel_id"], False, REL, f"grid02_{kernel}", "grid02_index.json")
    assert ns["PINS"][REL] == SC.sha256_path(T.REPLAY) and ns["PINS"][k["job"]] == SC.sha256_path(T.ROOT / k["job"]) and ns["HARNESS_VERSION"] == SC.HARNESS_VERSION
    assert ns["SPARSE"] == sorted(set(B.ALWAYS_SPARSE) | set(ns["PINS"]))


def test_rendered_kernels_differ_only_inside_the_pin_block():
    texts = {k: B.render(T.REPLAY, DUMMY, k, False, T.ROOT) for k in KERNELS}
    for a in KERNELS:
        for b in KERNELS:
            if a < b:
                B.assert_pin_only_diff(texts[a], texts[b])


def test_metadata_title_equals_the_slug_for_formal_and_smoke():
    for k in KERNELS:
        for smoke in (False, True):
            m = B.metadata(CAMPAIGN, k, smoke)
            assert m["title"] == m["id"].split("/")[1] and m["id"].endswith("-smoke") == smoke and m["machine_shape"] == "NvidiaTeslaT4" and m["dataset_sources"] == []


# ---------------------------------------------------------------- (e) smoke
def test_smoke_render_differs_from_formal_only_in_the_pin_block_and_only_in_the_declared_lines():
    formal, smoke = B.render(T.REPLAY, DUMMY, "f16", False, T.ROOT), B.render(T.REPLAY, DUMMY, "f16", True, T.ROOT)
    B.assert_pin_only_diff(formal, smoke)
    changed = [(a, b) for a, b in zip(formal.splitlines(), smoke.splitlines()) if a != b]
    assert len(formal.splitlines()) == len(smoke.splitlines()) and [a.split(" =")[0] for a, _ in changed] == ["KERNEL_ID", "SMOKE"]
    assert smoke.count('-smoke"') == 2 and formal.count('-smoke"') == 1 and "SMOKE = True" in smoke and "SMOKE = False" in formal
    with pytest.raises(ValueError, match="only inside the PIN block"):
        B.assert_pin_only_diff(formal, smoke.replace("def remaining", "def remaining2"))
    with pytest.raises(ValueError, match="only inside the PIN block"):
        B.assert_pin_only_diff(formal, formal)
    assert B.smoke_kernel(CAMPAIGN) == "f16" and B.smoke_kernel(CAMPAIGN, "s24") == "s24"


def test_smoke_runner_runs_only_the_first_state_and_says_so_in_its_identity(tmp_path):
    h = Fake(tmp_path, "f16", smoke=True)
    assert h.go() == 0
    names = SC.run_names(CAMPAIGN["kernels"]["f16"])
    assert [e["name"] for e in h.index()["states"]] == names[:1] and len(h.jobs()) == 1 and h.index()["kernel_id"].endswith("-smoke")
    ident = h.identity()
    assert ident["smoke"] is True and ident["expected_names"] == names[:1] and (h.out / "DONE").is_file()


# ---------------------------------------------------------------- (b) behaviour
@pytest.mark.parametrize("kernel", KERNELS)
def test_complete_run_goes_baseline_first_sets_the_per_run_environment_and_writes_done_index_manifest(tmp_path, monkeypatch, kernel):
    monkeypatch.setenv("GRID02_CASE", "inherited-bogus")
    h = Fake(tmp_path, kernel)
    assert h.go() == 0
    spec = CAMPAIGN["kernels"][kernel]
    names, cfg = SC.run_names(spec), spec["config"]
    idx, ident = h.index(), h.identity()
    SC.validate_index(idx, terminal=True)
    SC.validate_identity(ident)
    assert [e["name"] for e in idx["states"]] == names and all(e["complete"] for e in idx["states"]) and idx["parent_forces_csv_sha256"] == idx["states"][0]["forces_csv_sha256"]
    assert "matches_retained_parent_reference" not in idx["states"][0] and ident["failure_stage"] is None and ident["config"] == cfg and ident["expected_names"] == names and ident["smoke"] is False
    assert (h.out / "DONE").is_file() and not (h.out / "ERROR.txt").exists()
    SC.check_manifest(h.out, {f for f in SC.required_files(CAMPAIGN, spec, names) if not f.endswith(SC.PROBE_LOG_NAME)})  # the fake probe writes no log
    assert json.loads((h.out / "self_test.json").read_text()) == {"harness_version": SC.HARNESS_VERSION, "imports": True, "schema_dry_write": True, "phi_identities_verified": len(names), "gpu_probe": True}
    jobs = h.jobs()
    assert [Path(j["args"][-2]).name[:-9] for j in jobs] == names and all(j["args"][3].endswith(spec["job"]) for j in jobs)
    for j in jobs:
        env = j["env"]
        assert env["W4_CANONICAL_ORIGIN_M"] == cfg["W4_CANONICAL_ORIGIN_M"] and env["W4_SELECTED_GPU_UUID"] == UUID and env["CUDA_VISIBLE_DEVICES"] == "0" and env["JULIA_NUM_THREADS"] == "1"
        assert env.get("GRID02_CASE") == cfg["GRID02_CASE"]
        assert env["W4_PHI_FORTRAN_SHA256"] == h.rows[Path(j["args"][-2]).name[:-9]]["phi_fortran_order_sha256"]
    assert min(j["timeout"] for j in jobs) <= cfg["per_state_timeout_s"]


@pytest.mark.parametrize("kernel", ["s24", "f48a", "f48b", "s32"])  # f48b starts with the parent_repeat, s32 has the shifted origin
def test_harness_runner_equals_the_grid02_runner_on_the_same_inputs(tmp_path, kernel):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    old, new = T.Grid02Harness(old_dir, kernel), Fake(new_dir, kernel)
    assert old.go() == 0 and new.go() == 0
    assert [j["env"] for j in old.jobs()] == [j["env"] for j in new.jobs()]  # identical job environments, state by state
    assert [(Path(j["args"][-2]).name, Path(j["args"][3]).name) for j in old.jobs()] == [(Path(j["args"][-2]).name, Path(j["args"][3]).name) for j in new.jobs()]
    oi, ni = json.loads((old.out / "grid02_index.json").read_text()), new.index()
    assert set(oi) == set(ni) and [set(e) for e in oi["states"]] == [set(e) for e in ni["states"]]
    assert {k: v for k, v in oi.items() if k not in ("states", "solver_process_wall_seconds_total")} == {k: v for k, v in ni.items() if k not in ("states", "solver_process_wall_seconds_total")}
    assert [{k: e[k] for k in ("name", "kind", "direction", "step_mm", "sign", "exit_code", "forces_csv_sha256", "complete")} for e in oi["states"]] == \
           [{k: e[k] for k in ("name", "kind", "direction", "step_mm", "sign", "exit_code", "forces_csv_sha256", "complete")} for e in ni["states"]]
    files = lambda h: {f for f in json.loads((h.out / "output_manifest.json").read_text())["files"] if not f.endswith(".log")}  # the grid02 fake job leaves no logs
    om, nm = files(old), files(new)
    assert nm - om == {"self_test.json"} and om <= nm
    oid, nid = json.loads((old.out / "run_identity.json").read_text()), new.identity()
    assert set(nid) - set(oid) == set(SC.IDENTITY_HARNESS_KEYS) and oid["config"] == nid["config"] and oid["pins"].items() <= nid["pins"].items()


def test_a_failing_job_stops_the_kernel_with_error_and_no_done(tmp_path):
    h = Fake(tmp_path, "s24", fail="opt01b__prop__s0.625mm")
    assert h.go() == 1
    assert not (h.out / "DONE").exists() and (h.out / "ERROR.txt").is_file() and h.index()["status"] == "ERROR" and len(h.jobs()) == 3
    assert h.identity()["failure_stage"] == "state:opt01b__prop__s0.625mm" and (h.out / "output_manifest.json").is_file()


def test_a_failing_baseline_stops_before_any_perturbed_state(tmp_path):
    h = Fake(tmp_path, "f48b", fail=SC.run_names(CAMPAIGN["kernels"]["f48b"])[0])
    assert h.go() == 1 and len(h.jobs()) == 1 and not (h.out / "DONE").exists()


def test_a_wrong_case_file_name_is_a_failure(tmp_path):
    h = Fake(tmp_path, "f48a", case_file="flow_24")
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.index()["states"][0]["complete"] is False and len(h.jobs()) == 1


def test_wrong_gpu_fails_before_any_julia_call(tmp_path):
    h = Fake(tmp_path, "s32", smi=f"0, NVIDIA A100, {UUID}, 40960 MiB, 535\n")
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.calls == []
    h = Fake(sub(tmp_path, "b"), "s32", smi=f"1, Tesla T4, {UUID}, 15360 MiB, 535\n")
    assert h.go() == 1 and h.calls == []  # physical index 0 must exist


def test_a_probe_uuid_that_differs_from_the_selected_gpu_fails_before_any_state(tmp_path):
    h = Fake(tmp_path, "f16", probe_uuid="GPU-other")
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.jobs() == [] and h.identity()["failure_stage"] == "observed_cuda_device_probe"


def test_a_pin_mismatch_fails_at_source_checkout_before_any_call(tmp_path):
    h = Fake(tmp_path, "s24")
    h.ns["PINS"][CAMPAIGN["kernels"]["s24"]["job"]] = "0" * 64
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.calls == [] and h.identity()["failure_stage"] == "source_checkout"


def test_a_phi_that_differs_from_the_campaign_fails_in_the_self_test_before_any_julia_call(tmp_path):
    bad = tampered(lambda c: c["states"].__getitem__("opt01b__prop__s0.9375mm").update(phi_fortran_order_sha256="0" * 64))
    h = Fake(tmp_path, "f48a", campaign=bad)
    assert h.go() == 1 and not (h.out / "DONE").exists() and h.calls == [] and h.identity()["failure_stage"] == "self_test" and "Fortran-order SHA" in (h.out / "ERROR.txt").read_text()
    bad = tampered(lambda c: c["states"].__getitem__("opt01b__prop__s0.9375mm").update(phi_c_order_sha256="0" * 64))
    h = Fake(sub(tmp_path, "c"), "f48a", campaign=bad)
    assert h.go() == 1 and h.calls == [] and "C-order" in (h.out / "ERROR.txt").read_text()


def test_the_self_test_fails_closed_before_any_julia_call(tmp_path):
    def boom(SC_, tmp):
        raise RuntimeError("schema dry write failed")
    h = Fake(tmp_path, "s24", pin_override={"schema_dry_write": boom})
    assert h.go() == 1 and h.calls == [] and h.identity()["failure_stage"] == "self_test" and not (h.out / "DONE").exists()


def test_a_campaign_that_is_not_the_pinned_one_fails_the_pin_check(tmp_path):
    h = Fake(tmp_path, "s24", campaign=tampered(lambda c: c["kernels"]["s24"]["config"].update(per_state_timeout_s=1)))
    h.ns["PINS"][REL] = SC.sha256_path(T.REPLAY)  # the pin still names the genuine campaign
    assert h.go() == 1 and h.calls == [] and h.identity()["failure_stage"] == "source_checkout"


def test_exceeding_the_per_state_budget_is_an_integrity_failure(tmp_path):
    h = Fake(tmp_path, "s32", campaign=tampered(lambda c: c["kernels"]["s32"]["config"].update(per_state_timeout_s=1e-9)))
    assert h.go() == 1 and not (h.out / "DONE").exists() and "budget exceeded" in (h.out / "ERROR.txt").read_text()


def test_exceeding_the_aggregate_budget_is_an_integrity_failure(tmp_path):
    h = Fake(tmp_path, "s32", campaign=tampered(lambda c: c["kernels"]["s32"]["config"].update(per_state_timeout_s=1e-9, solver_wall_time_cap_s=2e-9)))
    assert h.go() == 1 and "budget exceeded" in (h.out / "ERROR.txt").read_text() and len(h.jobs()) == 1


def test_first_state_byte_gate_passes_on_the_pinned_csv_and_fails_closed_otherwise(tmp_path):
    first = SC.run_names(CAMPAIGN["kernels"]["s24"])[0]
    good = hashlib.sha256(f"fake forces {first}\n".encode()).hexdigest()
    h = Fake(sub(tmp_path, "a"), "s24", campaign=tampered(lambda c: c["kernels"]["s24"].update(first_state_csv_sha256=good)))
    assert h.go() == 0 and h.index()["states"][0]["matches_retained_parent_reference"] is True
    h = Fake(sub(tmp_path, "b"), "s24", campaign=tampered(lambda c: c["kernels"]["s24"].update(first_state_csv_sha256="1" * 64)))
    assert h.go() == 1 and len(h.jobs()) == 1 and h.index()["states"][0]["matches_retained_parent_reference"] is False and not (h.out / "DONE").exists()


def test_a_baseline_raw_whose_pin_differs_from_the_campaign_hash_fails_the_binding(tmp_path):
    h = Fake(tmp_path, "s24", campaign=tampered(lambda c: c["baseline"].update(sha256_fortran_raw="2" * 64)))  # the campaign is pinned as given, the raw's real pin differs from its declared hash
    assert h.go() == 1 and h.calls == [] and h.identity()["failure_stage"] == "self_test" and "not pinned to the campaign hash" in (h.out / "ERROR.txt").read_text()


# ---------------------------------------------------------------- environment allowlist (S2) and identity fields
def test_a_run_env_or_common_env_that_sets_device_or_state_identity_is_rejected_by_the_schema_and_before_any_julia_call(tmp_path):
    for key in ("CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "JULIA_NUM_THREADS", "W4_STATE_SHA256", "W4_PHI_FORTRAN_SHA256", "W4_EXPECTED_MARGIN_M", "W4_SELECTED_GPU_UUID", "CUDA_FOO"):
        assert SC.forbidden_env(key)
        for where in ("run", "common", "keys"):
            def mutate(c, key=key, where=where):
                if where == "run":
                    c["kernels"]["s24"]["runs"][0]["env"][key] = "1"
                elif where == "common":
                    c["job_env_common"][key] = "dead"
                else:
                    c["job_env_keys"].append(key)
            with pytest.raises(ValueError):
                SC.validate_campaign(tampered(mutate))
    assert not SC.forbidden_env("W4_CANONICAL_STATE_LABEL") and not SC.forbidden_env("GRID02_CASE")
    with pytest.raises(ValueError, match="job_env_keys"):  # an undeclared run variable is not allowed either
        SC.validate_campaign(tampered(lambda c: c["kernels"]["s24"]["runs"][0]["env"].update(SOME_OTHER="1")))
    with pytest.raises(ValueError, match="job_env_keys"):
        SC.validate_campaign(tampered(lambda c: c["job_env_keys"].remove("GRID02_CASE")))
    h = Fake(tmp_path, "s24", campaign=tampered(lambda c: c["kernels"]["s24"]["runs"][1]["env"].update(CUDA_VISIBLE_DEVICES="1")))
    assert h.go() == 1 and h.calls == [] and h.identity()["failure_stage"] == "self_test" and not (h.out / "DONE").exists()


def test_job_env_reasserts_the_runner_owned_variables_after_the_last_update():
    kernel = CAMPAIGN["kernels"]["s24"]
    base = {"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_NUM_THREADS": "1", "GRID02_CASE": "inherited", "PATH": "/bin"}
    env = SC.job_env(CAMPAIGN, kernel["runs"][0], CAMPAIGN["states"][kernel["runs"][0]["state"]], base, "GPU-x")
    assert (env["CUDA_VISIBLE_DEVICES"], env["CUDA_DEVICE_ORDER"], env["JULIA_NUM_THREADS"], env["W4_SELECTED_GPU_UUID"], "GRID02_CASE" in env) == ("0", "PCI_BUS_ID", "1", "GPU-x", False)
    for key in ("CUDA_VISIBLE_DEVICES", "W4_STATE_SHA256", "W4_SELECTED_GPU_UUID"):  # a validation bypass still cannot reach the job
        run = {"state": kernel["runs"][0]["state"], "env": {**kernel["runs"][0]["env"], key: "bad"}}
        with pytest.raises(RuntimeError, match="sets a device"):
            SC.job_env(CAMPAIGN, run, CAMPAIGN["states"][run["state"]], base, "GPU-x")
    with pytest.raises(RuntimeError, match="sets a device"):
        SC.job_env(dict(CAMPAIGN, job_env_common={**CAMPAIGN["job_env_common"], "W4_STATE_SHA256": "dead"}), kernel["runs"][0], CAMPAIGN["states"][kernel["runs"][0]["state"]], base, "GPU-x")


def test_the_work_root_is_recorded_in_the_run_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("CAMPAIGN_WORK_ROOT", raising=False)
    h = Fake(sub(tmp_path, "a"), "f16")
    assert h.go() == 0 and h.identity()["campaign_work_root"] == "/kaggle/working"
    monkeypatch.setenv("CAMPAIGN_WORK_ROOT", "/data/work")
    h = Fake(sub(tmp_path, "b"), "f16")
    assert h.go() == 0 and h.identity()["campaign_work_root"] == "/data/work"
    bad = json.loads((h.out / "run_identity.json").read_text())
    bad["campaign_work_root"] = None
    with pytest.raises(ValueError, match="harness identity fields"):
        SC.validate_identity(bad)


# ---------------------------------------------------------------- end to end: harness runner output -> verifier
NONLEGACY = dict(CAMPAIGN, legacy_replay=False)


def strip_harness(out):
    """Make a harness output look like a pre-harness one: no harness identity fields, no self_test.json."""
    ident = json.loads((out / "run_identity.json").read_text())
    for key in SC.IDENTITY_HARNESS_KEYS:
        ident.pop(key)
    (out / "run_identity.json").write_text(json.dumps(ident, indent=2, sort_keys=True) + "\n")
    (out / "self_test.json").unlink()
    (out / "output_manifest.json").write_text(json.dumps(SC.build_manifest(out), indent=2, sort_keys=True) + "\n")


def real_run(tmp_path, smoke):
    real = T.EV / "kernel_output/grid02_s24"
    probe = json.loads((real / "gpu_device_probe.json").read_text())["default_device_uuid"]
    h = Fake(tmp_path, "s24", smi=(real / "nvidia_smi.csv").read_text(), probe_uuid=probe, smoke=smoke)
    h.real = real  # the fake job replays the saved real force CSV / summary of each state
    assert h.go() == 0
    ident, sha = h.identity(), SC.sha256_path(h.src / REL)
    freeze = None if smoke else {"source_commit": DUMMY, "pins": {"s24": ident["pins"]}, "runtime": {"s24": {"kernel_id": ident["kernel_id"], "runner_sha256": ident["runner_sha256"]}}}
    ref = {"s24": {"source_commit": DUMMY, "pins": ident["pins"], "runner_sha256": ident["runner_sha256"]}} if smoke else None
    return h, sha, freeze, ref


@pytest.mark.parametrize("smoke", [False, True])
def test_runner_output_with_real_job_files_passes_the_verifier(tmp_path, smoke):
    from cfd_harness import campaign_verify as V
    h, sha, freeze, ref = real_run(tmp_path, smoke)
    k, states = V.check_kernel(h.out, NONLEGACY, sha, REL, freeze, smoke, ref)
    want = json.loads((T.EV / "grid02_analysis.json").read_text())["state_forces_n"]["s24"]
    names = SC.run_names(CAMPAIGN["kernels"]["s24"])[: 1 if smoke else None]
    cols = ("drag_n", "downforce_n", "forces_csv_sha256", "summary_sha256")
    assert k == "s24" and list(states) == names and all({c: states[n][c] for c in cols} == {c: want[n][c] for c in cols} for n in names)
    with pytest.raises(ValueError):  # a smoke output is not a formal output and vice versa
        V.check_kernel(h.out, NONLEGACY, sha, REL, freeze, not smoke, ref)


@pytest.mark.parametrize("smoke", [False, True])
def test_stripping_the_harness_fields_from_a_harness_output_fails_instead_of_downgrading_it_to_legacy(tmp_path, smoke):
    """S1: 'harness format' comes from the campaign, not from the output under test."""
    from cfd_harness import campaign_verify as V
    h, sha, freeze, ref = real_run(tmp_path, smoke)
    strip_harness(h.out)
    with pytest.raises(ValueError, match="manifest omits required|harness identity|run identity keys"):
        V.check_kernel(h.out, NONLEGACY, sha, REL, freeze, smoke, ref)
    if not smoke:  # the same bytes are a valid pre-harness output only under a campaign that is explicitly marked as a legacy replay
        assert V.check_kernel(h.out, CAMPAIGN, sha, REL, freeze, False)[0] == "s24"


def test_a_legacy_campaign_cannot_be_smoke_verified_and_a_freeze_must_agree_on_the_flag(tmp_path):
    from cfd_harness import campaign_verify as V
    h, sha, freeze, ref = real_run(tmp_path, True)
    with pytest.raises(ValueError, match="smoke output must come from a harness runner"):
        V.check_kernel(h.out, CAMPAIGN, sha, REL, None, True, ref)
    assert CAMPAIGN["legacy_replay"] is True and json.loads(H01.read_text())["legacy_replay"] is False
    SC.validate_campaign(json.loads(H01.read_text()))


def test_verify_smoke_checks_the_runner_source_commit_and_pins_against_the_rendering_at_the_given_commit(tmp_path):
    """Full path: runner output of the committed non-legacy campaign (kernel a) -> V.verify --smoke -> a table the freeze accepts."""
    from cfd_harness import campaign_verify as V
    real = T.EV / "kernel_output/grid02_f16"
    probe = json.loads((real / "gpu_device_probe.json").read_text())["default_device_uuid"]
    h = Fake(tmp_path, "a", smi=(real / "nvidia_smi.csv").read_text(), probe_uuid=probe, smoke=True, campaign_file=H01, signed=True)
    h.real = real
    assert h.go() == 0
    table = V.verify(H01, [h.out], smoke=True, source_commit=DUMMY, repo=T.ROOT)
    assert table["smoke"] is True and table["source_commit"] == DUMMY and set(table["harness_tool_sha256"]) == set(SC.TOOL_FILES) and table["legacy_replay"] is False
    path = tmp_path / "smoke_table.json"
    path.write_text(json.dumps(table))
    c, _, sha = B.load(H01, T.ROOT)
    assert B.check_smoke_record(path, c, sha, DUMMY) == SC.sha256_path(path)
    with pytest.raises(ValueError, match="another campaign or source commit"):
        B.check_smoke_record(path, c, sha, "1" * 40)
    with pytest.raises(ValueError, match="differs from the expected smoke rendering"):  # same output, verified against another commit's rendering
        V.verify(H01, [h.out], smoke=True, source_commit="1" * 40, repo=T.ROOT)
    with pytest.raises(ValueError, match="--source-commit"):
        V.verify(H01, [h.out], smoke=True, repo=T.ROOT)
    ident = h.identity()
    for label, edit, message in (("pins", lambda i: i["pins"].update({"scripts/step01_states.py": "0" * 64}), "pins differ"), ("commit", lambda i: i.update(source_commit="2" * 40), "source commit or runner"),
                                 ("runner", lambda i: i.update(runner_sha256="3" * 64), "source commit or runner")):
        bad = dict(ident, pins=dict(ident["pins"]))
        edit(bad)
        (h.out / "run_identity.json").write_text(json.dumps(bad, indent=2, sort_keys=True) + "\n")
        (h.out / "output_manifest.json").write_text(json.dumps(SC.build_manifest(h.out), indent=2, sort_keys=True) + "\n")
        with pytest.raises(ValueError, match=message):
            V.verify(H01, [h.out], smoke=True, source_commit=DUMMY, repo=T.ROOT)
    assert label
    with pytest.raises(ValueError, match="smoke or unverified"):  # downstream readers reject smoke tables
        SC.require_formal_table(table)
    assert SC.require_formal_table(dict(table, smoke=False)) is not None
