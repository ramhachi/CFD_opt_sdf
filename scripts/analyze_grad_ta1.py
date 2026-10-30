#!/usr/bin/env python3
"""GRAD-TA1 analyzer: tie-averaged forward-AD slopes vs the FD-08 Model-A oracle, verdict fixed before the run
(docs/grad_ta1_plan_2026_10_15.md, Amendment 1 C1-C3).

    python scripts/analyze_grad_ta1.py <kernel_output_dir> --check           # print the report, write nothing
    python scripts/analyze_grad_ta1.py <kernel_output_dir> --write OUT.json  # the single write (+ OUT.json.sha256); refuses to overwrite

Integrity, window means and the primal gates (C1) are scripts/verify_grad_g2_terminal.py, the row table is scripts/analyze_grad_g2_bridge.py (both reused
unchanged, as the kernel keeps the G2 output layout).  New here: the GRAD-01 row rule (src/cfd_sdf/gradients/directional_comparison.py:218-234) with
relative_error_tolerance = 0.25 and absolute_noise_floor = 3*SE per row, the verdict, and the BLOCKED / INCOMPLETE paths.

Verdict (priority INCOMPLETE > BLOCKED > DISAGREE > AGREE):
  GRAD_TA1_INCOMPLETE  integrity failure: pins/commit/manifest/T4, a failed preflight (primal bit identity of QuickTie-Dual vs quick-Dual, finite tangents), a
                       kernel error or wall-time abort, a primal gate failure (C1), any host-recomputation mismatch
  GRAD_TA1_BLOCKED     intact output, but a Dual run's tangent became non-finite or exceeded 1e30 (onset step and cell reported)
  GRAD_TA1_DISAGREE    complete, finite, primal gates passed, at least one of the 8 rows fails the GRAD-01 rule
  GRAD_TA1_AGREE       complete, finite, primal gates passed, all 8 rows pass
The verdict row uses `dual_time` (the tangent of the time step propagated); `frozen_time` is reported.  The additive form 0.25|g_hat| + 3 SE, the per-response
4-direction cosine and relative L2 are reported only.
Disclosures: (1) the BLOCKED path returns after the common integrity checks WITHOUT the full verifier (no plain-baseline gate, no history/window-mean checks);
(2) a wall-time abort (8x the plain run) or any other kernel error stops the whole kernel (status ERROR => INCOMPLETE), there is no per-direction continue after an error;
(3) sim.flow.λ types recorded by the kernel must be `quick` (plain) and QuickTie{Float32} (every Dual run and the preflight's second arm), else INCOMPLETE.  No flag changes; selected_delta is recorded for this contract only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_grad_g2_bridge as B  # noqa: E402
import verify_grad_g2_terminal as V  # noqa: E402

RELATIVE_ERROR_TOLERANCE = 0.25   # delta_rel: the middle illustrative value of docs/issues/46 (a judgement, not a standard)
NOISE_FLOOR_SE_MULTIPLE = 3.0     # absolute_noise_floor = 3 * SE per row (option C; never fires while every |g_hat| > 3 SE, which makes it option B)
BLOCK_LIMIT = 1.0e30              # the kernel's watchdog threshold
TAU = 1e-5
PLAIN_LAMBDA_TYPE = "typeof(quick)"   # string(typeof(sim.flow.λ)) for the plain run
DEFAULT_FREEZE = ROOT / "docs/evidence/grad_ta1_2026_10_15/prerun_freeze.json"
ANALYZER_FREEZE_KEY = "scripts/analyze_grad_ta1.py"
VERDICTS = ("GRAD_TA1_AGREE", "GRAD_TA1_DISAGREE", "GRAD_TA1_BLOCKED", "GRAD_TA1_INCOMPLETE")
CLAIMS = ("a tie-averaged surrogate derivative of the implemented primal (values bit-identical in the preflight, within 1e-3 in the window mean), not the derivative of "
          "the implemented map at ties; flow_24, canonical v17, four registered directions, Re 80 only; not reverse/full-field qualification, not flow_32, not a production "
          "selection, not a step-usefulness result, no flag changes")


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def grad01_row(g: float, g_hat: float, se: float, *, tolerance: float = RELATIVE_ERROR_TOLERANCE, floor_multiple: float = NOISE_FLOOR_SE_MULTIPLE) -> dict:
    """The GRAD-01 rule of compare_field_gradient_to_centered_fd (lines 218-234), applied to one scalar row; plus the additive form as a secondary report."""
    floor = floor_multiple * se
    error = abs(g - g_hat)
    near_zero = abs(g_hat) <= floor
    if near_zero:
        rel, sign_match, rule, applied = None, None, "absolute_noise_floor", floor
        passed = error <= applied
        reason = None if passed else "absolute_error"
    else:
        rel, sign_match, rule, applied = error / abs(g_hat), _sign(g) == _sign(g_hat), "relative", tolerance
        passed = sign_match and rel <= applied
        reason = None if passed else ("sign_mismatch" if not sign_match else "relative_error")
    additive = tolerance * abs(g_hat) + floor
    return {"passed": passed, "reason": reason, "error_rule": rule, "tolerance_applied": applied, "relative_error": rel, "sign_match": sign_match,
            "absolute_noise_floor": floor, "absolute_error": error, "standardized_error": error / se,
            "additive_form_passed_secondary": _sign(g) == _sign(g_hat) and error <= additive,
            "additive_effective_relative_tolerance": additive / abs(g_hat)}


def vector_metrics(rows: list[dict]) -> dict:
    """Per response, the 4-direction vector g_TA vs g_hat (report-only): the optimizer consumes the vector."""
    out = {}
    for response in B.RESPONSES:
        g = [r["g_forward_n_per_m"] for r in rows if r["response_id"] == response]
        h = [r["g_hat_fd08_modelA_n_per_m"] for r in rows if r["response_id"] == response]
        ng, nh = math.sqrt(sum(x * x for x in g)), math.sqrt(sum(x * x for x in h))
        out[response] = {"cosine": sum(a * b for a, b in zip(g, h)) / (ng * nh) if ng and nh else None,
                         "relative_l2": math.sqrt(sum((a - b) ** 2 for a, b in zip(g, h))) / nh, "directions": [r["direction_id"] for r in rows if r["response_id"] == response]}
    return out


def judge(bridge: dict) -> dict:
    """Add the GRAD-01 rule and the verdict to the rows of analyze_grad_g2_bridge.analyze."""
    rows = []
    for r in bridge["rows"]:
        rows.append({**r, "grad01": grad01_row(r["g_forward_n_per_m"], r["g_hat_fd08_modelA_n_per_m"], r["se_g_fd08_n_per_m"])})
    failed = [(r["direction_id"], r["response_id"], r["grad01"]["reason"]) for r in rows if not r["grad01"]["passed"]]
    return {"rows": rows, "verdict": "GRAD_TA1_DISAGREE" if failed else "GRAD_TA1_AGREE", "failed_rows": failed, "vector_metrics": vector_metrics(rows),
            "option_b_equivalent": all(r["grad01"]["error_rule"] == "relative" for r in rows)}


def read_watchdog(path: Path) -> list[dict]:
    numeric = ("step", "t_u_l", "tan_max_u", "tan_max_p", "elapsed_s", "vram_bytes")
    keep = (*numeric, "tan_argmax_u", "tan_argmax_p")

    def num(v):  # a non-finite tangent is reported as its text (NaN / Inf), never as a JSON number
        return float(v) if math.isfinite(float(v)) else v

    with Path(path).open(newline="") as handle:
        return [{k: (num(v) if k in numeric else v) for k, v in row.items() if k in keep} for row in csv.DictReader(handle)]


def run_reports(out_dir: Path, index: dict) -> dict:
    reports = {}
    for label in index.get("run_order", []):
        entry: dict = {"status": index.get("run_status", {}).get(label)}
        try:
            summary = json.loads((out_dir / f"{label}.summary.json").read_text())
            entry.update({k: summary.get(k) for k in ("total_seconds", "loop_seconds", "peak_vram_bytes", "steps", "blocked")})
        except (OSError, ValueError):
            entry["summary"] = "missing"
        watchdog = out_dir / f"{label}.watchdog.csv"
        if watchdog.is_file():
            history = read_watchdog(watchdog)
            entry["tangent_history_every_100_steps"] = history
            finite = [max(h["tan_max_u"], h["tan_max_p"]) for h in history if all(isinstance(h[k], float) for k in ("tan_max_u", "tan_max_p"))]
            entry["tangent_max_over_run"] = max(finite) if finite else None
        reports[label] = entry
    return reports


def lambda_ok(label: str, lambda_type) -> bool:
    """The convective scheme actually stored in sim.flow.λ (type string recorded by the kernel): `quick` for the plain run, QuickTie{Float32} for every Dual run."""
    if label == "plain":
        return lambda_type == PLAIN_LAMBDA_TYPE
    return isinstance(lambda_type, str) and re.fullmatch(r"(WaterLily\.)?QuickTie\{Float32\}", lambda_type) is not None


def lambda_problems(out_dir: Path, index: dict) -> list[str]:
    """INCOMPLETE unless every run that ran, and both preflight arms, recorded the right sim.flow.λ type (sim_step!(sim; λ) ignores λ, so the type is the only proof)."""
    problems = []
    types = index.get("lambda_types") or {}
    for label in index.get("run_status", {}):
        if not lambda_ok(label, types.get(label)):
            problems.append(f"index lambda_types[{label}] = {types.get(label)!r}: expected {'quick' if label == 'plain' else 'QuickTie{Float32}'} in sim.flow.λ")
        try:
            recorded = json.loads((out_dir / f"{label}.summary.json").read_text()).get("lambda_type")
        except (OSError, ValueError):
            continue  # a missing or unreadable summary is reported by the manifest / verifier checks
        if not lambda_ok(label, recorded):
            problems.append(f"{label}.summary.json lambda_type = {recorded!r}: expected {'quick' if label == 'plain' else 'QuickTie{Float32}'} in sim.flow.λ")
    arms = (index.get("preflight") or {}).get("arms") or {}
    if not (lambda_ok("plain", (arms.get("quick") or {}).get("lambda_type")) and lambda_ok("dual", (arms.get("quick_tie") or {}).get("lambda_type"))):
        problems.append("preflight arms did not record quick / QuickTie in sim.flow.λ (the arms may not have differed)")
    return problems


def artifact_problems(out_dir: Path, freeze: dict) -> list[str]:
    """Integrity common to every outcome (the full-window checks of the verifier run only for a COMPLETE index)."""
    problems = []
    if not (out_dir / "DONE").is_file():
        problems.append("DONE marker missing")
    if (out_dir / "ERROR.txt").exists() or (out_dir / "ERROR.json").exists():
        problems.append("ERROR artifact present")
    try:
        identity = json.loads((out_dir / "run_identity.json").read_text())
        manifest = json.loads((out_dir / "output_manifest.json").read_text())["files"]
        index = json.loads((out_dir / "g2_run_index.json").read_text())
    except (OSError, ValueError, KeyError) as error:
        return problems + [f"run identity / manifest / index unreadable: {error}"]
    if identity.get("failure_stage") is not None or identity.get("spike_exit_code") not in (0, 3):
        problems.append(f"runner reports failure: stage={identity.get('failure_stage')} exit={identity.get('spike_exit_code')}")
    if identity.get("source_commit") != freeze["source_commit"]:
        problems.append("source commit differs from freeze")
    for rel_path, expected in freeze["pins"].items():
        if identity.get("verified", {}).get(rel_path) != expected:
            problems.append(f"pin mismatch: {rel_path}")
    for name, digest in manifest.items():
        if not (out_dir / name).is_file() or sha256(out_dir / name) != digest:
            problems.append(f"output SHA mismatch: {name}")
    if "Tesla T4" not in str(index.get("gpu_name", "")) or index.get("backend") != "cuda":
        problems.append("not a T4/CUDA run")
    for key, expected in freeze["runtime_pins"].items():
        if str(index.get(key)) != expected:
            problems.append(f"runtime pin differs: {key}={index.get(key)} expected {expected}")
    if index.get("tau") != float(TAU) or index.get("dual_width") != 1:
        problems.append("run is not QuickTie(1f-5) with Dual width 1")
    problems += lambda_problems(out_dir, index)
    pre = index.get("preflight") or {}
    if pre.get("pass") is not True or pre.get("primal_u_bit_equal") is not True or pre.get("primal_p_bit_equal") is not True:
        problems.append("preflight failed or missing: QuickTie-Dual vs quick-Dual primal not bit-equal, or a non-finite value/tangent (C6)")
    if index.get("run_status", {}).get("plain") != "COMPLETE":
        problems.append("plain baseline run is not COMPLETE")
    return problems


def analyze_output(out_dir: Path, freeze: dict, record: dict, formal: Path | None = None) -> dict:
    out_dir = Path(out_dir)
    base = {"kind": "grad_ta1_analysis", "rule": {"relative_error_tolerance": RELATIVE_ERROR_TOLERANCE, "absolute_noise_floor": f"{NOISE_FLOOR_SE_MULTIPLE} * SE per row",
                                                  "source": "src/cfd_sdf/gradients/directional_comparison.py:218-234", "comparator": "dual_time (frozen_time reported)", "tau": TAU,
                                                  "primal_gates": {"dual_window_mean_vs_plain_rel": V.PRIMAL_GATE, "plain_vs_registered_baseline_v17_rel": V.BASELINE_GATE}},
            "source_commit": freeze["source_commit"], "claims": CLAIMS,
            "selected_delta": {"scope": "GRAD-TA1 contract only", "relative_error_tolerance": RELATIVE_ERROR_TOLERANCE, "absolute_noise_floor": "3 SE per row"},
            "grad03_verdict": None, "reverse": "untouched", "qualification_flags": {k: False for k in B.FLAGS}}
    problems = artifact_problems(out_dir, freeze)
    if not (out_dir / "g2_run_index.json").is_file():
        return {**base, "verdict": "GRAD_TA1_INCOMPLETE", "problems": problems}
    index = json.loads((out_dir / "g2_run_index.json").read_text())
    base["runs"] = run_reports(out_dir, index)
    base["preflight"] = index.get("preflight")
    status = index.get("status")
    if status not in ("COMPLETE", "BLOCKED"):
        problems.append(f"kernel status {status}: {index.get('error')}")
    if problems:
        return {**base, "verdict": "GRAD_TA1_INCOMPLETE", "problems": problems}
    if status == "BLOCKED":
        blocked = {label: json.loads((out_dir / f"{label}.blocked.json").read_text()) for label in index.get("blocked_runs", [])}
        if not blocked or any(r.get("status") == "BLOCKED" for l, r in base["runs"].items() if l not in blocked):
            return {**base, "verdict": "GRAD_TA1_INCOMPLETE", "problems": ["BLOCKED status without a consistent blocked record"]}
        return {**base, "verdict": "GRAD_TA1_BLOCKED", "blocked": blocked, "block_limit": BLOCK_LIMIT}
    verification = V.verify(out_dir, freeze, formal or V.FORMAL_VERIFICATION)
    base["verification_status"] = verification["status"]
    base["integrity"] = verification["integrity"]
    if not verification["status"].startswith("PASS"):
        return {**base, "verdict": "GRAD_TA1_INCOMPLETE", "problems": verification["problems"]}
    bridge = B.analyze(verification, record)
    return {**base, **judge(bridge), "units": bridge["units"], "fd08_scope_record_sha256": bridge["fd08_scope_record_sha256"],
            "aggregate": bridge["aggregate"]}


def load_freeze(path: Path) -> dict:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != sha256(path):
        sys.exit("the freeze does not match its SHA sidecar")
    freeze = json.loads(path.read_text())
    if freeze["file_hashes"].get(ANALYZER_FREEZE_KEY) != sha256(__file__):
        sys.exit("this analyzer differs from the frozen bytes")
    return freeze


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="print the report; write nothing")
    group.add_argument("--write", type=Path, metavar="OUT", help="write the report once, with a .sha256 sidecar")
    args = p.parse_args()
    if args.write is not None and args.write.exists():
        sys.exit("refusing to overwrite evidence")
    if sha256(B.SCOPE_RECORD) != B.SCOPE_RECORD_SHA256:
        sys.exit("FD-08 scope record SHA mismatch")
    result = analyze_output(args.out_dir, load_freeze(args.freeze), json.loads(B.SCOPE_RECORD.read_text()))
    data = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if args.write is not None:
        args.write.write_bytes(data)
        args.write.with_name(args.write.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(result["verdict"], *result.get("problems", []), sep="\n")
    if args.check:
        print(json.dumps({k: result.get(k) for k in ("failed_rows", "vector_metrics", "aggregate", "blocked")}, indent=2))


if __name__ == "__main__":
    main()
