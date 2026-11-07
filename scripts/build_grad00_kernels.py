#!/usr/bin/env python3
"""Render local GRAD-00 kernels from committed inputs; this command never contacts Kaggle.

Without --reference, the rendered workers are deliberately unconfigured and stop
before GPU inventory. Configured renders use the committed, provenance-bearing
FD-08 epsilon/spread reference and may replace generated files in existing
directories. Reference-free renders never overwrite an existing directory.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_lowdim04a_kernel import sha, verify_source  # noqa: E402
from build_grad_ta1_kernel import (  # noqa: E402
    DIRECTIONS, INPUT_DIR, PHI_RAW, PROJECT, TEMPLATE, metadata as ta1_metadata,
)

ARMS = ("quick", "quick_nobound", "cds", "vanLeer", "vanLeer_safe")
SCRIPT = "scripts/waterlily_grad00_lambda_2026_11.jl"
# TA1 used 10800 s, including install/JIT margin. GRAD-00 rev 0 budgets
# one hour per arm; the published TA1 138.9 s plain run predicts 39–49 min
# for 9 plain and 4 bounded Dual runs at 2–3x plain cost, before setup.
TIMEOUT_S = 10800
PIN_PATHS = (
    f"{PROJECT}/Project.toml", f"{PROJECT}/Manifest.toml", SCRIPT,
    "scripts/quick_nobound.jl", "scripts/vanleer_safe.jl", "julia/CFDSDFWaterLily/src", PHI_RAW,
    *(f"{INPUT_DIR}/{direction}.dir_f4_fortran.raw" for direction in DIRECTIONS),
    # Renderer provenance, plus the frozen control sources used for CPU review.
    "scripts/build_grad00_kernels.py", "scripts/grad00_reference_from_fd08.py", "scripts/build_lowdim04a_kernel.py",
    "scripts/build_grad_ta1_kernel.py", str(TEMPLATE.relative_to(ROOT)),
    "scripts/waterlily_grad_ta1_2026_10_15.jl", "scripts/quick_tie.jl",
    # Consumer byte provenance; this does not freeze or register a study.
    "scripts/analyze_grad00.py", "scripts/grad_g2_window.py", "scripts/verify_grad_g2_terminal.py",
)


def reference_config(path: Path | None) -> dict | None:
    if path is None:
        return None
    path = Path(path).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise ValueError("reference JSON must be inside the repository so it can be commit-pinned") from error
    from analyze_grad00 import load_reference
    reference = load_reference(path, repo_root=ROOT)
    return {"path": relative, "sha256": sha(path), "definition": reference["definition"],
            "sources": reference["sources"], "directions": reference["directions"]}


def pin_paths(reference: dict | None) -> set[str]:
    paths = set(PIN_PATHS)
    if reference is not None:
        paths.add(reference["path"])
        paths.update(reference["sources"])
    return paths


def pins(reference: dict | None) -> dict[str, str]:
    return {path: sha(ROOT / path) for path in sorted(pin_paths(reference))}


def tree_id(source_commit: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", f"{source_commit}^{{tree}}"], text=True).strip()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"frozen TA1 template substitution count differs: {old!r}")
    return text.replace(old, new)


def kernel_id(arm: str) -> str:
    if arm not in ARMS:
        raise ValueError(f"unknown GRAD-00 arm: {arm}")
    return "ramhachi888/cfd-opt-sdf-grad00-" + arm.lower().replace("_", "-")


def render(source_commit: str, arm: str, reference: dict | None = None) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", source_commit):
        raise ValueError("source commit must be a full lowercase SHA")
    identity = kernel_id(arm)
    text = TEMPLATE.read_text()
    for key, value in {"PIN_SOURCE_COMMIT": source_commit, "PIN_SOURCE_TREE_ID": tree_id(source_commit),
                       "PIN_KERNEL_ID": identity}.items():
        text = replace_once(text, json.dumps(key), json.dumps(value))
    text = replace_once(text, "PINS = PIN_PINS", f"PINS = {pins(reference)!r}\nARM = {arm!r}\nREFERENCE = {reference!r}")
    replacements = (
        ("Run GRAD-TA1 (tie-averaged forward-AD bridge, QuickTie(1f-5), Dual width 1, full window)",
         "Run GRAD-00 (one convection scheme, Dual width 1, full window, central FD)"),
        ("decides the verdict from the pinned freeze.", "applies exploratory labels from the explicit reference, without registering or qualifying the study."),
        ("Rendered from scripts/grad_ta1_runner_template.py by scripts/build_grad_ta1_kernel.py.",
         "Rendered from frozen scripts/grad_ta1_runner_template.py by scripts/build_grad00_kernels.py."),
        ('SCRIPT = "scripts/waterlily_grad_ta1_2026_10_15.jl"', f"SCRIPT = {SCRIPT!r}"),
        ('OUT = Path("/kaggle/working/grad_ta1")', f'OUT = Path("/kaggle/working/grad00_{arm}")'),
        ('prefix="grad-ta1-"', 'prefix="grad00-"'),
        ('    (source / ".git/info/sparse-checkout").write_text("\\n".join("/" + p + "/" for p in SPARSE) + "\\n")',
         '    patterns = ["/" + p + "/" for p in SPARSE]\n    if REFERENCE is not None:\n        patterns += ["/" + REFERENCE["path"], *("/" + p for p in REFERENCE["sources"])]\n    (source / ".git/info/sparse-checkout").write_text("\\n".join(patterns) + "\\n")'),
        ('DRYRUN_SWITCHES = ("G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY", "TA1_BLOCK_LIMIT")',
         'DRYRUN_SWITCHES = ("G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY", "TA1_BLOCK_LIMIT", "GRAD00_PREFLIGHT_ONLY")'),
        ('stage = "gpu_inventory"', 'stage = "reference_configuration"'),
        ('"failure_stage": None}', '"failure_stage": None, "arm": ARM, "reference": REFERENCE}'),
        ('    try:\n        gpu =',
         '    try:\n        if REFERENCE is None:\n            raise RuntimeError("GRAD-00 FD-08 epsilon/plateau-spread reference is not configured; render again with --reference after its definition is supplied")\n        stage = "gpu_inventory"\n        gpu ='),
        ('"G2_BACKEND": "cuda"}', '"G2_BACKEND": "cuda", "GRAD00_ARM": ARM, "GRAD00_T": "Float32"}'),
        ('stage = "measurement"  # the script\'s first action is the 20-step QuickTie-vs-quick Dual preflight (INCOMPLETE if it fails)',
         'stage = "measurement"  # unchanged 20-step finite-primal/tangent preflight; quick also checks its control bytes'),
        ('            code = run(args, OUT / "measurement.log"',
         '            args += [str(REFERENCE["directions"][name]["epsilon_m"]) for name, _ in DIRECTION_INPUTS]\n            code = run(args, OUT / "measurement.log"'),
        ('GRAD-TA1 script returned', 'GRAD-00 script returned'),
        ('                raise RuntimeError(f"measurement script exited {code}")',
         '                raise RuntimeError(f"measurement script exited {code}")\n            stage = "terminal_verification"\n            verify_terminal(code)'),
        ('def main():', '''def verify_terminal(code):
    expected_status = {0: "COMPLETE", 3: "BLOCKED"}[code]
    expected_runs = {"plain", *(name + suffix for name, _ in DIRECTION_INPUTS for suffix in ("", "__plus", "__minus"))}
    for filename in ("g2_run_index.json", "grad00_index.json"):
        index = json.loads((OUT / filename).read_text())
        if (index["status"] != expected_status or index["arm"] != ARM or index["real_type"] != "Float32"
                or index["backend"] != "cuda" or index["preflight"]["pass"] is not True):
            raise RuntimeError(f"{filename}: exit status, arm, runtime or preflight mismatch")
        statuses = index["run_status"]
        if set(index["runs"]) != expected_runs or set(statuses) != expected_runs:
            raise RuntimeError(f"{filename}: incomplete 13-run inventory")
        for name, status in statuses.items():
            allowed = ("COMPLETE", "BLOCKED") if name in dict(DIRECTION_INPUTS) else ("COMPLETE",)
            if status not in allowed:
                raise RuntimeError(f"{filename}: invalid run status for {name}")
        if ("BLOCKED" in statuses.values()) != (code == 3):
            raise RuntimeError(f"{filename}: BLOCKED status does not match exit code")


def main():'''),
    )
    # The analyzer's path appears in the docstring and DONE text, unlike other
    # substitutions. Require its known count before replacing both occurrences.
    if text.count("scripts/analyze_grad_ta1.py") != 2:
        raise ValueError("frozen TA1 analyzer-path substitution count differs")
    text = text.replace("scripts/analyze_grad_ta1.py", "scripts/analyze_grad00.py")
    for old, new in replacements:
        text = replace_once(text, old, new)
    if "PIN_" in text:
        raise ValueError("unresolved runner placeholder")
    compile(text, "runner.py", "exec")
    namespace: dict = {}
    exec(compile(text.split("def sha256")[0], "runner.py", "exec"), namespace)
    if namespace["PROJECT"] != PROJECT or namespace["KERNEL_TIMEOUT_S"] != TIMEOUT_S:
        raise ValueError("frozen template project or timeout differs")
    expected = namespace["PINS"]
    for direction, digest in namespace["DIRECTION_INPUTS"]:
        if expected[f"{INPUT_DIR}/{direction}.dir_f4_fortran.raw"] != digest:
            raise ValueError(f"template direction hash differs: {direction}")
    if expected[PHI_RAW] != namespace["PHI_SHA256"]:
        raise ValueError("template baseline hash differs")
    return text


def metadata(arm: str) -> dict:
    value = ta1_metadata()
    value.update(id=kernel_id(arm), title=kernel_id(arm).split("/")[1])
    return value


def build(source_commit: str, *, output_root: Path | None = None, reference: dict | None = None) -> None:
    output_root = ROOT / "infra/kaggle" if output_root is None else Path(output_root)
    destinations = {arm: output_root / f"kernel_grad00_{arm}" for arm in ARMS}
    for directory in destinations.values():
        if reference is None and directory.exists():
            raise FileExistsError(f"refusing to overwrite rendered worker: {directory}")
    if reference is not None and reference_config(ROOT / reference["path"]) != reference:
        raise ValueError("reference configuration differs from repository bytes")
    verify_source(source_commit, pin_paths(reference))
    # Validate every runner and metadata payload before replacing any old render.
    rendered = {arm: {
        "runner.py": render(source_commit, arm, reference),
        "kernel-metadata.json": json.dumps(metadata(arm), sort_keys=True, indent=2) + "\n",
        "timeout": f"{TIMEOUT_S}\n",
    } for arm in ARMS}
    for arm, directory in destinations.items():
        directory.mkdir(parents=True, exist_ok=reference is not None)
        for name, content in rendered[arm].items():
            (directory / name).write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--reference", type=Path, help="committed FD-08 reference JSON; permits replacing generated files")
    parser.add_argument("--output-root", type=Path, help="parent for the five kernel directories (default: infra/kaggle)")
    args = parser.parse_args()
    reference = reference_config(args.reference)
    build(args.source_commit, output_root=args.output_root, reference=reference)
    print("CONFIGURED" if reference is not None else "UNCONFIGURED: workers stop before GPU inventory; FD-08 reference required")


if __name__ == "__main__":
    main()
