"""harness v1 verifier: the integrity half of every campaign analyzer.  Kaggle kernel outputs + campaign.json + freeze -> a validated state-force table (or a ValueError; fail closed).

Checks per kernel: safe manifest paths and hashes, DONE xor ERROR, exact state order, index/identity schema, run identity and pins against the freeze, GPU (T4, index 0, singleton UUID),
per-state job-summary identity (both phi byte orders), host recomputation of drag/downforce with the case's force scale against the Julia summary at 1e-9, per-state/aggregate/kernel budgets,
and the optional first-state byte gate.  Statistics on the table are the campaign analyzer's job, not this module's.
"""
from __future__ import annotations

import math
from pathlib import Path

from cfd_harness import campaign_schema as SC
from grid01_gpu import select_worker_gpu  # scripts/ is on the path once campaign_schema is imported

REPO = Path(__file__).resolve().parents[2]


def load_campaign(path, repo=REPO):
    path = Path(path).resolve()
    campaign = SC.jload(path)
    SC.validate_campaign(campaign)
    return campaign, SC.sha256_path(path), str(path.relative_to(Path(repo).resolve()))


def validate_freeze(freeze, freeze_path, campaign, campaign_sha):
    SC.req(isinstance(freeze, dict) and freeze.get("kind") == SC.FREEZE_KIND and freeze.get("harness_version") == SC.HARNESS_VERSION, "freeze kind or harness version differs")
    SC.req(SC.COMMIT.fullmatch(str(freeze.get("source_commit"))) and freeze.get("campaign_sha256") == campaign_sha, "freeze source commit or campaign hash differs")
    sidecar = Path(freeze_path).with_name(Path(freeze_path).name + ".sha256")
    SC.req(sidecar.is_file() and sidecar.read_text().strip() == SC.sha256_path(freeze_path), "freeze SHA-256 sidecar missing or mismatched")
    SC.req(set(freeze.get("runtime", {})) == set(campaign["kernels"]) == set(freeze.get("pins", {})), "freeze must cover exactly the campaign's kernels")
    SC.req((freeze.get("identity_free_check") or {}).get("all_free") is True, "freeze lacks a passed identity-free check")
    for k, kernel in campaign["kernels"].items():
        SC.req(freeze["runtime"][k].get("kernel_id") == kernel["kernel_id"] and SC.is_sha(freeze["runtime"][k].get("runner_sha256")), f"freeze runtime of {k}")


def check_kernel(out, c, campaign_sha, campaign_rel, freeze, smoke=False):
    """Integrity of one kernel output directory; returns (kernel name, host-recomputed forces by state)."""
    out = Path(out)
    SC.req(out.is_dir() and (out / SC.DONE_NAME).is_file() and not any(out.rglob(SC.ERROR_NAME)), "DONE must exist and ERROR.txt must not")
    index_path = out / SC.index_name(c)
    index, identity = SC.jload(index_path), SC.jload(out / SC.IDENTITY_NAME)
    k = index.get("kernel")
    SC.req(k in c["kernels"], f"unknown kernel in output: {k!r}")
    kernel = c["kernels"][k]
    case_id, cfg = kernel["case"]["case_id"], kernel["config"]
    harness = "harness_version" in identity
    SC.req(harness or not smoke, "a smoke output must come from a harness runner")
    names = SC.run_names(kernel)[:1] if smoke else SC.run_names(kernel)
    SC.check_manifest(out, SC.required_files(c, kernel, names, harness))
    SC.validate_index(index, terminal=True)
    SC.validate_identity(identity, harness)
    kernel_id = kernel["kernel_id"] + ("-smoke" if smoke else "")
    for record in (index, identity):
        for key, want in (("kernel", k), ("kernel_id", kernel_id), ("case_id", case_id)):
            SC.req(record.get(key) == want, f"output {key} identity differs")
    SC.req(identity["failure_stage"] is None, "failure stage is set")
    SC.req(not harness or (identity["smoke"] is smoke and identity["campaign_sha256"] == campaign_sha and identity["pins"].get(campaign_rel) == campaign_sha), "campaign pin or smoke flag differs")
    SC.req(harness or campaign_rel not in identity["pins"] or identity["pins"][campaign_rel] == campaign_sha, "campaign pin differs")
    if freeze is not None:
        runtime = freeze["runtime"][k]
        SC.req(identity["source_commit"] == freeze["source_commit"] and identity["runner_sha256"] == runtime["runner_sha256"], "source commit or runner differs from the freeze")
        SC.req(identity["pins"] == freeze["pins"][k], "run identity pins differ from the freeze")
    else:
        SC.req(SC.COMMIT.fullmatch(identity["source_commit"]), "smoke source commit")
    SC.req(identity["verified"] == identity["pins"], "verified pin map differs from the pins")
    SC.equal(identity["config"], cfg, "run identity kernel configuration")
    SC.equal(identity["expected_names"], names, "run identity state plan")
    SC.equal(identity["direction_files"], {n: identity["pins"][d["path"]] for n, d in c["directions"].items()}, "run identity direction files")
    selected = select_worker_gpu((out / SC.SMI_NAME).read_text())
    SC.equal(identity["selected_gpu"], selected, "physical GPU selection")
    for key, want in (("cuda_device_order", "PCI_BUS_ID"), ("cuda_visible_devices", "0")):
        SC.req(identity[key] == want, "run identity CUDA environment differs")
    SC.equal(SC.jload(out / SC.PROBE_NAME), dict(SC.GPU_EXPECTED, visible_gpu_uuids=[selected["uuid"]], default_device_uuid=selected["uuid"]), "observed CUDA singleton/default identity")
    if harness:
        SC.equal(SC.jload(out / SC.SELF_TEST_NAME), {"harness_version": SC.HARNESS_VERSION, "imports": True, "schema_dry_write": True, "phi_identities_verified": len(names), "gpu_probe": True}, "self-test record")
    entries = index["states"]
    SC.req(index["status"] == "COMPLETE" and [e.get("name") for e in entries] == names, "completed entries differ from the exact registered state order")
    SC.req({p.name for p in (out / "states").iterdir() if p.is_dir()} == set(names), "state directories differ from the exact plan")
    runs = {r["state"]: r for r in kernel["runs"]}
    states, process_total, summary_total = {}, 0.0, 0.0
    for name, entry in zip(names, entries):
        row = c["states"][name]
        for key in ("kind", "direction", "step_mm", "sign"):
            SC.equal(entry.get(key), row[key], f"index state {key}")
        SC.req(entry["complete"] is True and type(entry.get("exit_code")) is int and entry["exit_code"] == 0, "state process is incomplete")
        seconds = SC.finite(entry.get("seconds"), "state process wall time")
        SC.req(0 < seconds <= cfg["per_state_timeout_s"], "state process wall time exceeds budget")
        process_total += seconds
        directory = out / "states" / name
        csv, summary_path = directory / SC.forces_name(case_id), directory / SC.summary_name(case_id)
        SC.req(entry.get("forces_csv_sha256") == SC.sha256_path(csv), "state force CSV differs from index")
        summary = SC.jload(summary_path)
        wall = SC.check_summary(summary, c, kernel, runs[name], row, selected["uuid"])
        summary_total += wall
        host = SC.host_forces(csv, c, kernel, summary)
        states[name] = {"drag_n": host["drag_n"], "downforce_n": host["downforce_n"], "forces_csv_sha256": SC.sha256_path(csv), "summary_sha256": SC.sha256_path(summary_path),
                        "solver_process_wall_seconds": seconds, "julia_summary_wall_seconds": wall}
    total = SC.finite(index.get("solver_process_wall_seconds_total"), "total process time")
    SC.req(math.isclose(total, process_total, rel_tol=1e-12) and process_total <= cfg["solver_wall_time_cap_s"] and summary_total <= cfg["solver_wall_time_cap_s"]
           and process_total + cfg["reserve_s"] <= cfg["kernel_timeout_s"], "aggregate or kernel wall-time budget exceeded or the recorded process sum differs")
    first = states[names[0]]["forces_csv_sha256"]
    SC.req(index.get("parent_forces_csv_sha256") == first, "recorded first-state force CSV hash differs")
    gate = kernel.get("first_state_csv_sha256")
    SC.req(gate is None or (first == gate and entries[0].get("matches_retained_parent_reference") is True), "first state differs from the pinned historical CSV")
    return k, states


def verify(campaign_path, kernel_dirs, freeze_path=None, smoke=False, repo=REPO):
    """The validated state-force table of a campaign (or of one smoke kernel with smoke=True and no freeze)."""
    SC.req(smoke == (freeze_path is None), "a formal verification needs --freeze; a smoke verification takes none")
    c, campaign_sha, rel = load_campaign(campaign_path, repo)
    freeze = None
    if not smoke:
        freeze = SC.jload(freeze_path)
        validate_freeze(freeze, freeze_path, c, campaign_sha)
    kernels, manifests = {}, {}
    for d in kernel_dirs:
        k, states = check_kernel(d, c, campaign_sha, rel, freeze, smoke)
        SC.req(k not in kernels, f"kernel {k} given twice")
        kernels[k], manifests[k] = states, SC.sha256_path(Path(d) / SC.MANIFEST_NAME)
    SC.req(len(kernels) == 1 if smoke else set(kernels) == set(c["kernels"]), "a formal verification needs exactly the campaign's kernel directories; a smoke one exactly one")
    return {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "campaign_id": c["campaign_id"], "campaign_sha256": campaign_sha, "smoke": smoke,
            "source_commit": None if freeze is None else freeze["source_commit"], "freeze_sha256": None if freeze_path is None else SC.sha256_path(freeze_path),
            "integrity": {"pass": True, "failures": []}, "kernel_manifest_sha256": manifests, "state_forces_n": kernels}
