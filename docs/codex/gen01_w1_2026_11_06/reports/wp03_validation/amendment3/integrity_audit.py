"""Read-only WP3 input/preservation audit; writes new JSON only when requested."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
FORMAL = "docs/evidence/fd08_v2_formal_2026_10_07_amend3"
REFERENCE = "docs/evidence/grad00_lambda_2026_11/reference.json"
AUTHORITY = (
    "AGENTS.md", "docs/codex/gen01_w1_2026_11_06/00_README.md",
    "docs/opencode_handoff_2026_09.md", "docs/README.md", "docs/phase_plan.md",
    "docs/problem_register_2026_09.md", "docs/problem_resolution_plan_2026_09.md",
    "docs/STATE.md", "docs/git_branching_strategy.md", "docs/gen_system_plan_2026_11_01.md",
    "docs/grad00_lambda_swap_spec_2026_11_01.md", "docs/grad_ta1_plan_2026_10_15.md",
    "docs/issues/23_grad_ta1_result_2026_10_15.md",
    "docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md",
)
EXTERNAL_DOCS = Path("/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1/docs")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def command(*args):
    try:
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    except OSError as error:
        return {"command": list(args), "exit_code": None, "stdout": "", "stderr": str(error)}
    return {"command": list(args), "exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def protected_snapshot():
    previous = read_json(HERE.parent / "amendment2/protected_before.json")
    names = set(previous["protected_sha256"]) | set(AUTHORITY)
    for pattern in ("infra/kaggle/kernel_grad00_*/*", "infra/kaggle/kernel_grad_ta1/*",
                    "src/**/*", "julia/CFDSDFWaterLily/src/**/*",
                    "julia/CFDSDFWaterLilyT4/*.toml", "scripts/*grad*diag*", "scripts/*quick_tie*",
                    "scripts/build_grad_ta1_kernel.py", "scripts/vanleer_safe.jl", "tests/conftest.py"):
        names.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file() and "__pycache__" not in p.parts)
    frozen = read_json(ROOT / "docs/evidence/grad_ta1_2026_10_15/prerun_freeze.json")
    names.update(name for name in frozen["pins"] if (ROOT / name).is_file())
    hashes = {name: digest((ROOT / name).read_bytes()) for name in sorted(names)}
    for name, actual in hashes.items():
        committed = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=ROOT)
        assert digest(committed) == actual, f"protected file differs from starting HEAD: {name}"
    src = {name: value for name, value in hashes.items() if name.startswith("src/")}
    return {"evidence_class": "software_input_integrity", "start_commit": command("git", "rev-parse", "HEAD")["stdout"].strip(),
            "protected_sha256": hashes, "protected_file_count": len(hashes),
            "src_file_count": len(src), "src_inventory_sha256": digest(json.dumps(src, sort_keys=True).encode()),
            "note": "Captured against starting HEAD; GRAD00 job/analyzer/builder and reports are intended changes, excluded."}


def audit():
    reference = read_json(ROOT / REFERENCE)
    for name, expected in reference["sources"].items():
        assert digest((ROOT / name).read_bytes()) == expected
    reference_check = command(sys.executable, "scripts/grad00_reference_from_fd08.py", "--check")
    assert reference_check["exit_code"] == 0, reference_check
    analysis = read_json(ROOT / FORMAL / "formal_analysis.json")
    criteria = read_json(ROOT / FORMAL / "formal_criteria.json")
    assert analysis["verdict"] == "PASS" and analysis["comparison_count"] == 24
    archives = {}
    baseline = (ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw").read_bytes()
    for name, inventory in (("formal_registered_payload.tar.gz", "formal_registered_payload_inventory.json"),
                            ("formal_kernel_output.tar.gz", "formal_kernel_output_manifest.json")):
        path = ROOT / FORMAL / name
        expected = read_json(ROOT / FORMAL / inventory)
        sha = digest(path.read_bytes())
        assert sha == expected["archive_sha256"] == path.with_name(name + ".sha256").read_text().split()[0]
        with tarfile.open(path) as archive:
            contents = {m.name: archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
        assert {n: digest(b) for n, b in contents.items()} == expected["files"]
        if name == "formal_registered_payload.tar.gz":
            assert contents["baseline_v17.phi.f32f"] == baseline
        archives[name] = {"sha256": sha, "members_verified": len(contents), "all_member_hashes_match": True}
    frozen = read_json(ROOT / "docs/evidence/grad_ta1_2026_10_15/prerun_freeze.json")
    raw = {}
    for name, expected in frozen["pins"].items():
        if not name.endswith(".raw"):
            continue
        data = (ROOT / name).read_bytes()
        assert digest(data) == expected
        row = {"sha256": expected, "bytes": len(data)}
        if ".dir_" in name:
            direction = Path(name).name.split(".dir_")[0]
            c_hash = digest(np.frombuffer(data, dtype="<f4").reshape((121, 65, 49), order="F").tobytes(order="C"))
            assert c_hash == criteria["direction_inventory"]["hashes"][direction]
            row["formal_c_order_sha256"] = c_hash
        raw[name] = row
    numerical = {}
    for direction, row in reference["directions"].items():
        eps = sorted({r["epsilon_m"] for r in analysis["comparisons"] if r["direction_id"] == direction})
        assert row["epsilon_m"] == max(eps) <= 0.005
        fits = criteria["calibration_binding"]["fits"]
        for component, response in (("fx", "drag"), ("fz", "downforce")):
            assert row["spread_n_per_m"][component] == fits[f"{direction}|{response}"]["se_g_n_per_m"]
        numerical[direction] = {**row, "formal_interior_epsilon_m": eps,
                                "model_a_gradient_drag_downforce_n_per_m": [fits[f"{direction}|{r}"]["g_n_per_m"] for r in ("drag", "downforce")]}
    runtimes = {}
    for project in ("CFDSDFWaterLily", "CFDSDFWaterLilyT4", "CFDSDFWaterLily110"):
        folder = ROOT / "julia" / project
        manifest = tomllib.loads((folder / "Manifest.toml").read_text())
        runtimes[project] = {"julia": manifest["julia_version"], "project_sha256": digest((folder / "Project.toml").read_bytes()),
                             "manifest_sha256": digest((folder / "Manifest.toml").read_bytes()),
                             "versions": {key: manifest["deps"][key][0]["version"] for key in ("WaterLily", "ForwardDiff", "CUDA", "KernelAbstractions") if key in manifest["deps"]}}
    external = {str(EXTERNAL_DOCS / name): digest((EXTERNAL_DOCS / name).read_bytes()) for name in (
        "grad00_lambda_swap_spec_2026_11_01.md", "codex/gen01_w1_2026_11_06/reviews/wp03_review_1_opus.md")}
    return {"kind": "grad00_amendment3_input_integrity_audit", "evidence_class": "software_input_integrity",
            "captured_utc": datetime.now(timezone.utc).isoformat(), "reference_sha256": digest((ROOT / REFERENCE).read_bytes()),
            "reference_sources": reference["sources"], "reference_check": reference_check, "archives": archives,
            "raw_input_checks": raw, "numerical_reference": numerical, "runtime_manifests": runtimes,
            "external_authority_sha256": external,
            "resources": {"process_list": command("ps", "-axo", "pid,ppid,%cpu,rss,etime,comm"), "uptime": command("uptime"), "vm_stat": command("vm_stat")},
            "scope": "No solve, GPU, Kaggle, reference write, commit, or push. Formal PASS is Model A interior interpolation only; current tests are software capability evidence."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    outputs = {"integrity_audit.json": audit(), "protected_before.json": protected_snapshot()}
    for name, result in outputs.items():
        if args.write:
            with (HERE / name).open("x") as stream:
                json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
        else:
            print(name, "PASS", result.get("protected_file_count", ""))


if __name__ == "__main__":
    main()
