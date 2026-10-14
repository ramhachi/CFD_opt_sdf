#!/usr/bin/env python3
"""GRAD-TA1 prerun freeze: capture the authenticated Kaggle identity-free proof, then freeze every reviewed byte the T4 run and its analysis depend on.

    python scripts/freeze_grad_ta1.py --check-identities          # read-only Kaggle listings; writes identity_free_check.json (+ .sha256)
    python scripts/freeze_grad_ta1.py --source-commit <sha>       # after the source commit is pushed and the worker is rendered from it

Pattern of scripts/freeze_lowdim04a.py (committed-bytes check, source tree id, import-discovered project closure, identity-free proof, rendered-runner re-render check).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts")]
import analyze_grad_ta1 as A  # noqa: E402
import build_grad_ta1_kernel as K  # noqa: E402

E = ROOT / "docs/evidence/grad_ta1_2026_10_15"
IDENTITY = E / "identity_free_check.json"
FREEZE = E / "prerun_freeze.json"
OWNER = "ramhachi888"
RUNTIME_PINS = {"julia": "1.12.6", "waterlily": "1.8.0", "forwarddiff": "1.4.5", "cuda_jl": "6.3.1"}
KERNEL_TIMEOUT_S = 10800
EXTRA_FILES = (
    "docs/grad_ta1_plan_2026_10_15.md", "docs/evidence/grad_ta1_2026_10_15/prerun_note.md", "docs/evidence/grad_ta1_2026_10_15/tau_sensitivity.json",
    "docs/evidence/grad_ta1_2026_10_15/tau_sensitivity.json.sha256", "scripts/grad_ta1_runner_template.py", "scripts/quick_tie.jl", "scripts/test_quick_tie.jl",
    "scripts/waterlily_grad_ta1_tau_sensitivity.jl", "scripts/assemble_grad_ta1_tau_sensitivity.py", "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl",
    "scripts/waterlily_grad_g2_diag5_stages.jl", "scripts/waterlily_grad_g2_diag5_one_step_gain_2026_10_09.jl",
    "docs/evidence/fd08_v2_oracle_scope_record_2026_10_08/record.json", "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_terminal_verification.json",
    "src/cfd_sdf/gradients/directional_comparison.py", "docs/evidence/grad_ta1_2026_10_15/identity_free_check.json", "docs/evidence/grad_ta1_2026_10_15/identity_free_check.json.sha256",
)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def command(args):
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    return {"command": ["kaggle", *args], "exit_code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def capture_identity() -> None:
    if IDENTITY.exists():
        raise ValueError("refusing to overwrite the identity preflight")
    record = {"kind": "grad_ta1_authenticated_identity_free_check", "owner": OWNER, "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "kernel_ids": [K.KERNEL_ID], "listings": {}, "positive_controls": {}}
    target = K.KERNEL_ID.split("/")[1]
    for kind in ("kernels", "datasets"):
        pages, rows = [], []
        for page in range(1, 101):
            result = command([kind, "list", "--mine", "--page-size", "100", "--page", str(page), "--csv"])
            if result["exit_code"] or re.search(r"403|forbidden|unauthorized", result["stdout"] + result["stderr"], re.I):
                raise ValueError(f"{kind} authenticated listing failed")
            parsed = [] if result["stdout"].strip() in ("Not found", "No datasets found", "No kernels found", "") else list(csv.DictReader(io.StringIO(result["stdout"])))
            if any(not row.get("ref", "").startswith(OWNER + "/") for row in parsed):
                raise ValueError(f"{kind} listing returned a different owner or malformed CSV")
            pages.append({**result, "rows": parsed}); rows.extend(parsed)
            if len(parsed) < 100:
                break
        else:
            raise ValueError("listing pagination limit reached")
        if not rows or len({r["ref"] for r in rows}) != len(rows):
            raise ValueError("positive owned listing or unique rows missing")
        taken = {r["ref"].split("/")[1] for r in rows} | {slug(r.get("title", "")) for r in rows}
        if target in taken:
            raise ValueError(f"{kind} provider identity collision: {target}")
        ref = rows[0]["ref"]
        control = command([kind, "status", ref] if kind == "kernels" else [kind, "files", ref, "--csv"])
        if control["exit_code"] or not control["stdout"].strip() or re.search(r"403|forbidden|unauthorized", control["stdout"] + control["stderr"], re.I):
            raise ValueError("existing-resource positive access control failed")
        record["listings"][kind] = {"pages": pages, "rows": rows, "complete": True}
        record["positive_controls"][kind] = control
    record["all_free"] = True
    IDENTITY.write_bytes(canonical_json(record))
    IDENTITY.with_suffix(".json.sha256").write_text(K.sha(IDENTITY) + "\n")
    print("authenticated identity absence captured", K.sha(IDENTITY))


def require_identity(record: dict, *, as_of=None) -> None:
    if record.get("all_free") is not True or record.get("kernel_ids") != [K.KERNEL_ID] or record.get("owner") != OWNER:
        raise ValueError("identity preflight mismatch")
    age = ((as_of or datetime.datetime.now(datetime.timezone.utc)) - datetime.datetime.fromisoformat(record["captured_utc"])).total_seconds()
    if not 0 <= age <= 86400 or IDENTITY.with_suffix(".json.sha256").read_text().strip() != K.sha(IDENTITY):
        raise ValueError("stale identity proof or sidecar mismatch")
    target = K.KERNEL_ID.split("/")[1]
    for kind in ("kernels", "datasets"):
        listing = record["listings"][kind]; rows, pages = listing["rows"], listing["pages"]
        if listing["complete"] is not True or not rows or not pages or len(pages[-1]["rows"]) >= 100:
            raise ValueError("incomplete provider listing")
        if [r for page in pages for r in page["rows"]] != rows or len({r["ref"] for r in rows}) != len(rows):
            raise ValueError("provider page mismatch")
        for i, page in enumerate(pages, 1):
            if page["command"] != ["kaggle", kind, "list", "--mine", "--page-size", "100", "--page", str(i), "--csv"] or page["exit_code"] != 0:
                raise ValueError("provider listing command mismatch")
            if list(csv.DictReader(io.StringIO(page["stdout"]))) != page["rows"] and page["stdout"].strip() not in ("Not found", "No datasets found", "No kernels found", ""):
                raise ValueError("provider CSV mismatch")
        if target in ({r["ref"].split("/")[1] for r in rows} | {slug(r.get("title", "")) for r in rows}) or any(not r["ref"].startswith(OWNER + "/") for r in rows):
            raise ValueError("provider collision or owner mismatch")
        control = record["positive_controls"][kind]; ref = control["command"][3]
        expected = ["kaggle", kind, "status", ref] if kind == "kernels" else ["kaggle", kind, "files", ref, "--csv"]
        if control["command"] != expected or ref not in {r["ref"] for r in rows} or control["exit_code"] != 0 or not control["stdout"].strip():
            raise ValueError("provider access control mismatch")


def project_closure() -> set[str]:
    """Every project file loaded by importing the host scripts (hashed in the freeze), found by importing them, not by a glob."""
    code = ("import sys;sys.path[:0]=['src','scripts'];import analyze_grad_ta1,build_grad_ta1_kernel,freeze_grad_ta1;"
            "print('\\n'.join(sorted(getattr(m,'__file__','') or '' for m in sys.modules.values())))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=True).stdout.splitlines()
    return {str(Path(p).resolve().relative_to(ROOT)) for p in out if p and str(Path(p).resolve()).startswith(str(ROOT) + "/") and "/.venv/" not in p and "/site-packages/" not in p}


def package_pins() -> dict:
    manifest = tomllib.loads((ROOT / K.PROJECT / "Manifest.toml").read_text())["deps"]
    return {name: {"version": manifest[name][0]["version"], "git_tree_sha1": manifest[name][0].get("git-tree-sha1")} for name in ("WaterLily", "ForwardDiff", "CUDA")}


def freeze(source_commit: str) -> None:
    if FREEZE.exists():
        raise ValueError("refusing to overwrite an immutable freeze")
    proof = json.loads(IDENTITY.read_text()); require_identity(proof)
    files = (project_closure() | set(K.PIN_PATHS) | set(EXTRA_FILES) | {str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_grad_ta1_*.py")}
             | {"scripts/freeze_grad_ta1.py", "scripts/build_grad_ta1_kernel.py", "scripts/analyze_grad_ta1.py", "scripts/waterlily_grad_ta1_2026_10_15.jl"})
    if subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip():
        raise ValueError("tracked files have uncommitted changes; freeze only committed reviewed bytes")
    if not subprocess.run(["git", "-C", str(ROOT), "branch", "-r", "--contains", source_commit], capture_output=True, text=True).stdout.strip():
        raise ValueError("the source commit is not on a remote branch; push it before freezing (the Kaggle runner fetches it from GitHub)")
    K.verify_source(source_commit, files)
    runner = K.KERNEL_DIR / "runner.py"
    if runner.read_text() != K.render(source_commit):
        raise ValueError("rendered worker differs from reviewed source")
    meta = K.KERNEL_DIR / "kernel-metadata.json"
    if json.loads(meta.read_text()) != K.metadata():
        raise ValueError("kernel metadata mismatch")
    record = json.loads(A.B.SCOPE_RECORD.read_text())
    result = {
        "kind": "grad_ta1_prerun_freeze", "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_commit": source_commit, "source_tree_id": K.tree_id(source_commit),
        "head_at_freeze": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "file_hashes": {p: K.sha(ROOT / p) for p in sorted(files)}, "pins": K.pins(), "runtime_pins": RUNTIME_PINS, "package_pins": package_pins(),
        "runtime": {"kernel_id": K.KERNEL_ID, "runner_sha256": K.sha(runner), "metadata_sha256": K.sha(meta), "machine_shape": "NvidiaTeslaT4",
                    "kernel_timeout_s": KERNEL_TIMEOUT_S, "julia_threads": 1, "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0", "dataset_sources": []},
        "identity_free_check": proof,
        "contract": {"lambda": "QuickTie", "tau": A.TAU, "tau_literal": "Float32 1f-5", "dual_width": 1, "real_type": "Float32", "order": ["plain", *K.DIRECTIONS],
                     "window_t_u_l": [80.0, 120.0], "sample_every_steps": 8, "preflight_steps": 20, "watchdog_every_steps": 100, "block_limit": A.BLOCK_LIMIT,
                     "wall_abort": "3 x the plain run's total seconds (error -> INCOMPLETE)", "exit_codes": {"COMPLETE": 0, "BLOCKED": 3, "other": 2},
                     "registered_plain_baseline_v17": {"drag_n": 0.3239039699743226, "downforce_n": 0.3316344583180616}},
        "rules": {"gates": {"dual_window_mean_primal_rel_vs_plain": A.V.PRIMAL_GATE, "plain_vs_registered_baseline_v17_rel": A.V.BASELINE_GATE, "preflight": "QuickTie-Dual vs quick-Dual primal u,p bit-equal, tangents finite"},
                  "grad01_rule": {"relative_error_tolerance": A.RELATIVE_ERROR_TOLERANCE, "absolute_noise_floor": "3 * SE per row", "source": "src/cfd_sdf/gradients/directional_comparison.py:218-234",
                                  "effective_option": "B (every |g_hat| > 3 SE)", "additive_form": "secondary, with effective tolerance", "comparator": "dual_time; frozen_time reported"},
                  "report_only": ["per-response 4-direction cosine and relative L2", "additive form", "tangent max-norm history every 100 steps", "per-run wall time and VRAM"],
                  "verdicts": list(A.VERDICTS), "priority": "INCOMPLETE > BLOCKED > DISAGREE > AGREE"},
        "fd08": {"scope_record_sha256": K.sha(A.B.SCOPE_RECORD), "formal_terminal_verification_sha256": K.sha(A.V.FORMAL_VERIFICATION),
                 "g_hat_rows": [(r["direction_id"], r["response_id"], r["g_hat_n_per_m"], r["se_g_n_per_m"]) for r in record["rows"]]},
        "tau_sensitivity_sha256": K.sha(E / "tau_sensitivity.json"),
        "known_before_run": ["tau = 1e-5 was chosen post hoc from {1e-5, 1e-4} on D0 corner-box states (DIAG5); not blind", "the tau sensitivity at {3e-6, 1e-5, 3e-5} on the DIAG5 states is known and disclosed",
                             "the FD-08 slopes and SE, G2-BLOCKED and DIAG1-5 are known; delta_rel = 0.25 is a judgement, not a standard"],
        "claims": A.CLAIMS,
        "prohibitions": ["no resubmission or repair after a terminal or integrity failure", "no change of tau, delta, window, directions or rule after the freeze", "no Float64, no Dual width > 1, no flow_32, no reverse",
                         "a verdict is not a go-ahead: the next action needs its own preregistration"],
        "qualification_flags": {k: False for k in A.B.FLAGS},
        "selected_delta": {"scope": "GRAD-TA1 contract only", "relative_error_tolerance": A.RELATIVE_ERROR_TOLERANCE}, "grad03_verdict": None, "reverse": "untouched",
    }
    FREEZE.write_bytes(canonical_json(result)); FREEZE.with_suffix(".json.sha256").write_text(K.sha(FREEZE) + "\n"); print("freeze", K.sha(FREEZE))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check-identities", action="store_true")
    g.add_argument("--source-commit")
    args = p.parse_args()
    capture_identity() if args.check_identities else freeze(args.source_commit)


if __name__ == "__main__":
    main()
