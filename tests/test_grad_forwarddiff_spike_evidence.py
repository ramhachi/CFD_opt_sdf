"""GRAD-02 forward-AD spike evidence: frozen inputs, registered decision rule, claim limits (no Julia needed)."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad02_forward_ad_spike_2026_10_08"
CLASS_LIMITS = (("A", 1e-4), ("B", 1e-2), ("C", 1e-1))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name):
    return json.loads((E / name).read_text())


def grade(run, eps_ref):
    row = next(f for f in run["fd"] if f["eps_m"] == eps_ref)
    value = max(row["rel_diff_dfx"], row["rel_diff_dfz"])
    return next((name for name, limit in CLASS_LIMITS if value <= limit), "D")


def tol_run(result, tol):
    return next(r for r in result["runs"] if r["poisson"][0] == tol)


def decide():
    toy, canon = tol_run(load("result_toy64.json"), 1e-10), tol_run(load("result_canonical.json"), 1e-10)
    ok = lambda r: r["ad_ok"] and r["ad_tangent_finite"]
    if not ok(toy) or grade(toy, 1e-5) == "D":
        return "NO-GO-forward"
    go = (grade(toy, 1e-5) in "AB" and toy["ad_primal_rel_diff"] <= 1e-10 and ok(canon) and grade(canon, 1e-5) in "ABC")
    return "GO-forward" if go else "PARTIAL"


def test_frozen_script_and_note_match_the_freeze_record():
    freeze = load("prerun_freeze.json")
    assert sha(ROOT / "scripts/waterlily_grad_forwarddiff_spike_2026_10_08.jl") == freeze["script_sha256"]
    assert sha(E / "prerun_note.md") == freeze["prerun_note_sha256"]
    assert sha(ROOT / "julia/CFDSDFWaterLily/Manifest.toml") == freeze["julia_manifest_sha256"]


def test_registered_decision_rule_gives_partial():
    assert decide() == "PARTIAL"


def test_canonical_tier_is_class_a_and_toy_class_c_at_the_registered_reference_epsilon():
    assert grade(tol_run(load("result_canonical.json"), 1e-10), 1e-5) == "A"
    assert grade(tol_run(load("result_toy64.json"), 1e-10), 1e-5) == "C"


def test_every_result_keeps_flags_false_and_states_its_claim_limit():
    for name in ("result_toy64.json", "result_toy32.json", "result_canonical.json", "result_toy64sweep_posthoc.json"):
        data = load(name)
        assert set(data["qualification_flags"].values()) == {False}
        assert "not" in data["claim_limit"]


def test_ad_primal_matches_plain_primal_and_tangents_are_finite_in_all_registered_runs():
    for name in ("result_toy64.json", "result_toy32.json", "result_canonical.json"):
        for run in load(name)["runs"]:
            assert run["ad_ok"] and run["ad_tangent_finite"]
    for name in ("result_toy64.json", "result_canonical.json"):
        assert all(r["ad_primal_rel_diff"] < 1e-10 for r in load(name)["runs"])


def test_posthoc_diagnostic_shows_ad_matches_fd_below_the_nonsmooth_scale():
    sweep = load("result_toy64sweep_posthoc.json")["sweep"]
    small = [r for r in sweep["decade_sweep"] if r["eps_m"] <= 1e-6]
    assert small and all(abs(r["fd_dfx"] - sweep["ad_dfx"]) / abs(sweep["ad_dfx"]) < 1e-6 for r in small)
    assert all(abs(r["fd_dfz"] - sweep["ad_dfz"]) / abs(sweep["ad_dfz"]) < 1e-5 for r in small)
