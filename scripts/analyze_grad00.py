#!/usr/bin/env python3
"""Check GRAD-00 output and apply its exploratory labels once.

The same-scheme ±epsilon primals supply FD. Historical FD-08 Model-A slopes
are descriptive only. Amendment 1 fixes epsilon/spread in the committed,
source-authenticated reference, which remains an explicit input.

    python scripts/analyze_grad00.py OUTPUT_ROOT --reference REF.json --check
    python scripts/analyze_grad00.py OUTPUT_ROOT --reference REF.json --write OUTPUT_ROOT/analysis.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import grad_g2_window as W  # noqa: E402
import verify_grad_g2_terminal as V  # noqa: E402

DIRECTIONS = V.DIRECTIONS
PRIMARY_ARMS = ("quick", "quick_nobound", "cds", "vanLeer")
ARMS = (*PRIMARY_ARMS, "vanLeer_safe")
# rev 0 §5 fixes B-D as the candidates; Amendment 2 adds optional D′ without
# changing that pre-written rule or automatically deciding when D′ should run.
NEXT_STEP_ARMS = PRIMARY_ARMS[1:]
# quick/cds are exported; Julia prints their imported names without a module.
# vanLeer and the included quick_nobound helper are not exported.
LAMBDA_TYPES = {"quick": "typeof(quick)", "quick_nobound": "typeof(WaterLily.quick_nobound)",
                "cds": "typeof(cds)", "vanLeer": "typeof(WaterLily.vanLeer)",
                "vanLeer_safe": "typeof(WaterLily.vanLeer_safe)"}
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
WINDOW = (80.0, 120.0)
RELATIVE_ERROR = 0.1  # GRAD-00 rev 0 §5; never inferred from measured results.
SPREAD_MULTIPLE = 3.0
BLOCK_LIMIT = 1e30  # The frozen TA1 watchdog blocks strictly > this value.
REQUIRED_INDEX_KEYS = frozenset((
    "schema_version", "tier", "arm", "real_type", "backend", "julia", "waterlily", "forwarddiff", "lambda_type",
    "window_t_u_l", "sample_every", "dual_width", "block_limit", "wall_factor", "directions", "input_sha256",
    "epsilon_m", "preflight", "runs", "by_direction", "status", "qualification_flags",
))
# Frozen TA1 prerun_freeze.json pins. Direction bytes are little-endian Float32,
# shape (121,65,49), Fortran order; formal_criteria direction hashes use C order.
INPUT_SHA256 = {
    "phi": "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431",
    "directions": dict(zip(DIRECTIONS, (
        "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549",
        "96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87",
        "2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de",
        "24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc",
    ))),
}
SCOPE_RECORD = ROOT / "docs/evidence/fd08_v2_oracle_scope_record_2026_10_08/record.json"
SCOPE_RECORD_SHA256 = "3f8b7d3e43f32633aa67106ba57f36e5be16f3e74e655bc54f862e463cc608d0"
REQUIRED_SOURCE_PINS = frozenset(("scripts/waterlily_grad00_lambda_2026_11.jl", "scripts/quick_nobound.jl", "scripts/vanleer_safe.jl", "scripts/analyze_grad00.py",
                                  "scripts/grad_g2_window.py", "scripts/verify_grad_g2_terminal.py", "julia/CFDSDFWaterLily/src"))


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, label, *, minimum=None, positive=False):
    _require(type(value) in (int, float) and math.isfinite(value), f"{label}: expected a finite number")
    _require(not positive or value > 0, f"{label}: must be positive")
    _require(minimum is None or value >= minimum, f"{label}: below {minimum}")
    return float(value)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(f"nonfinite JSON {s}")))
    except (OSError, ValueError) as error:
        raise ValueError(f"unreadable JSON {path}: {error}") from error


def _relative_file(root: Path, name) -> Path:
    _require(isinstance(name, str) and name and not Path(name).is_absolute(), f"expected a relative file path: {name!r}")
    path = root / name
    _require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), f"file missing or outside root: {name}")
    return path


def validate_reference(reference: dict, *, repo_root: Path = ROOT) -> dict:
    """Validate explicit epsilon/spread semantics and every source's actual SHA."""
    _require(isinstance(reference, dict), "reference must be an object")
    _require(reference.get("schema_version") == 1 and reference.get("kind") == "grad00_fd08_reference", "unknown reference schema")
    _require(isinstance(reference.get("definition"), str) and reference["definition"].strip(), "reference definition missing")
    sources = reference.get("sources")
    _require(isinstance(sources, dict) and sources, "reference sources path/SHA missing")
    for name, digest in sources.items():
        path = _relative_file(Path(repo_root), name)
        _require(sha256(path) == digest, f"reference source SHA mismatch: {name}")
    directions = reference.get("directions")
    _require(isinstance(directions, dict) and set(directions) == set(DIRECTIONS), "reference requires exactly four registered directions")
    for name in DIRECTIONS:
        row = directions[name]
        _require(isinstance(row, dict), f"reference {name} must be an object")
        _number(row.get("epsilon_m"), f"reference {name} epsilon_m", positive=True)
        _require(row["epsilon_m"] <= 5e-3, f"reference {name} epsilon_m exceeds the registered 5 mm amplitude")
        spread = row.get("spread_n_per_m")
        _require(isinstance(spread, dict) and set(spread) == {"fx", "fz"}, f"reference {name} requires explicit fx/fz spread_n_per_m")
        for response in ("fx", "fz"):
            _number(spread[response], f"reference {name} {response} spread", minimum=0)
    return reference


def load_reference(path: Path, *, repo_root: Path = ROOT) -> dict:
    """Renderer-compatible loader; return the original validated JSON object."""
    return validate_reference(_read_json(path), repo_root=repo_root)


def compare_row(tangent: float, fd: float, spread: float) -> dict:
    tangent = _number(tangent, "tangent")
    fd = _number(fd, "FD")
    spread = _number(spread, "plateau spread", minimum=0)
    floor = SPREAD_MULTIPLE * spread
    _require(math.isfinite(floor), "three-spread threshold overflow from finite spread")
    result = {"tangent_n_per_m": tangent, "fd_n_per_m": fd, "spread_n_per_m": spread, "three_spread_n_per_m": floor}
    if fd == 0 or abs(fd) < floor:
        return {**result, "label": "NOT_EVALUABLE", "reason": "zero_fd" if fd == 0 else "fd_below_three_spread",
                "sign_match": None, "ratio": None, "relative_error": None}
    ratio = tangent / fd
    sign_match = (tangent > 0) - (tangent < 0) == (fd > 0) - (fd < 0)
    if not math.isfinite(ratio):
        return {**result, "label": "DISAGREE", "reason": "ratio_overflow", "sign_match": sign_match, "ratio": None, "relative_error": None}
    # Algebraically |ratio-1| <= 0.1; this inclusive interval also preserves the
    # literal decimal endpoints 0.9 and 1.1 without an added tolerance.
    agree = sign_match and 1.0 - RELATIVE_ERROR <= ratio <= 1.0 + RELATIVE_ERROR
    return {**result, "label": "AGREE" if agree else "DISAGREE", "sign_match": sign_match,
            "ratio": ratio, "relative_error": abs(ratio - 1.0)}


def boundedness(run: dict) -> str:
    if run.get("status") == "BLOCKED":
        blocked = run.get("blocked")
        _require(isinstance(blocked, dict) and type(blocked.get("onset_step")) is int and blocked["onset_step"] > 0,
                 "BLOCKED run requires an onset_step")
        _require(any(blocked.get(k) for k in ("tan_argmax_u", "tan_argmax_p")) or blocked.get("reason") == "non_finite_tangent_in_force_sample",
                 "BLOCKED run requires an onset cell or force-sample reason")
        return "BLOCKED"
    _require(run.get("status") == "COMPLETE", f"run is not terminal: {run.get('status')}")
    maximum = _number(run.get("watchdog_max_tangent"), "watchdog maximum", minimum=0)
    _require(maximum <= BLOCK_LIMIT, "COMPLETE run exceeds watchdog threshold")
    return "BOUNDED"


@lru_cache(maxsize=None)
def _git_output(*args) -> bytes:
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    _require(result.returncode == 0, f"source commit unavailable or unreadable: {' '.join(args[:2])}")
    return result.stdout


@lru_cache(maxsize=None)
def committed_sha(commit: str, name: str) -> str:
    """Hash committed bytes with the existing renderer's directory-hash rule."""
    _require(not Path(name).is_absolute() and ".." not in Path(name).parts, f"unsafe source pin path: {name}")
    kind = _git_output("cat-file", "-t", f"{commit}:{name}").strip()
    if kind == b"blob":
        return hashlib.sha256(_git_output("show", f"{commit}:{name}")).hexdigest()
    _require(kind == b"tree", f"unsupported source pin object: {name}")
    names = _git_output("ls-tree", "-r", "--name-only", commit, "--", name).decode().splitlines()
    lines = [f"{Path(p).relative_to(name)}  {committed_sha(commit, p)}" for p in sorted(names)
             if "__pycache__" not in Path(p).parts and Path(p).suffix not in (".pyc", ".pyo")]
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def committed_reference(commit: str, name: str) -> dict:
    return json.loads(_git_output("show", f"{commit}:{name}"))


def _source_identity(identity: dict, index: dict, reference: dict):
    commit = identity.get("source_commit", "")
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "source commit identity missing")
    tree = _git_output("rev-parse", f"{commit}^{{tree}}").decode().strip()
    _require(identity.get("source_tree_id") == tree, "source tree identity mismatch")
    pins = identity.get("pins")
    _require(isinstance(pins, dict) and pins and identity.get("verified") == pins, "source pins/verified missing or unequal")
    project = "julia/CFDSDFWaterLily110" if index["waterlily"] == "1.10.0" else "julia/CFDSDFWaterLilyT4" if index["backend"] == "cuda" else "julia/CFDSDFWaterLily"
    required = REQUIRED_SOURCE_PINS | {f"{project}/Project.toml", f"{project}/Manifest.toml"}
    _require(required.issubset(pins), f"source pins omit required runtime/consumer files: {sorted(required - pins.keys())}")
    for name, digest in pins.items():
        _require(committed_sha(commit, name) == digest, f"source pin SHA mismatch at committed bytes: {name}")
    for name in ("scripts/analyze_grad00.py", "scripts/grad_g2_window.py", "scripts/verify_grad_g2_terminal.py"):
        _require(pins[name] == sha256(ROOT / name), f"analysis consumer differs from runtime source pin: {name}")
    _require(identity.get("phi_sha256") == INPUT_SHA256["phi"] and identity.get("direction_sha256") == INPUT_SHA256["directions"], "runner input SHA identities mismatch")
    _require(identity.get("arm") == index["arm"], "runner/index arm identity mismatch")
    recorded = identity.get("reference")
    _require(isinstance(recorded, dict) and all(recorded.get(k) == reference[k] for k in ("definition", "directions", "sources")), "runner/reference definitions mismatch")
    name = recorded.get("path")
    _require(isinstance(name, str) and name in pins and recorded.get("sha256") == pins[name], "reference JSON is not SHA-bound in committed source pins")
    _require(all(pins.get(name) == digest for name, digest in reference["sources"].items()), "reference source hashes missing from runtime pins")
    _require(committed_reference(commit, name) == reference, "reference differs from committed reference JSON")


@lru_cache(maxsize=None)
def expected_field_hash(precision: str, direction: str | None = None, epsilon: float = 0.0, *, tangent=False) -> str:
    """The registered Float64 perturbation arithmetic, followed by one cast."""
    import numpy as np  # existing repository dependency; no new numerical code

    base = ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
    _require(sha256(base) == INPUT_SHA256["phi"], "registered baseline raw SHA mismatch")
    phi = np.frombuffer(base.read_bytes(), dtype="<f4").astype("<f8")
    if direction is not None:
        path = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs" / f"{direction}.dir_f4_fortran.raw"
        _require(sha256(path) == INPUT_SHA256["directions"][direction], f"registered direction raw SHA mismatch: {direction}")
        d = np.frombuffer(path.read_bytes(), dtype="<f4").astype("<f8")
        phi = d if tangent else phi + epsilon * d
    _require(not tangent or direction is not None, "tangent hash requires a direction")
    return hashlib.sha256(phi.astype("<f4" if precision == "Float32" else "<f8").tobytes()).hexdigest()


def _watchdog(path: Path, summary: dict) -> dict:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        _require(set(("step", "t_u_l", "tan_max_u", "tan_max_p", "tan_argmax_u", "tan_argmax_p")).issubset(reader.fieldnames or ()), "watchdog schema mismatch")
        rows = list(reader)
    steps = summary["steps"]
    expected = list(range(100, steps + 1, 100))
    # TA1 breaks in force sampling before the scheduled watchdog on this edge.
    if (summary.get("blocked") or {}).get("reason") == "non_finite_tangent_in_force_sample" and steps % 100 == 0:
        expected = expected[:-1]
    _require([float(r["step"]) for r in rows] == expected, "scheduled watchdog cadence/inventory mismatch")
    _require(all(float(b["t_u_l"]) > float(a["t_u_l"]) for a, b in zip(rows, rows[1:])), "watchdog times are not increasing")
    finite, nonfinite, onset = [], [], None
    per_field = {"u": 0.0, "p": 0.0}
    for row in rows:
        _number(float(row["step"]), "watchdog step", positive=True)
        _number(float(row["t_u_l"]), "watchdog time", minimum=0)
        for key in ("tan_max_u", "tan_max_p"):
            value = float(row[key])
            if math.isfinite(value):
                _require(value >= 0, "watchdog tangent maximum is negative")
                finite.append(value)
                per_field[key[-1]] = max(per_field[key[-1]], value)
            else:
                nonfinite.append({"step": int(float(row["step"])), "field": key, "value": row[key]})
            if onset is None and (not math.isfinite(value) or value > BLOCK_LIMIT):
                onset = int(float(row["step"]))
    return {"watchdog_max_tangent": max(finite, default=0.0), "watchdog_nonfinite": nonfinite, "watchdog_onset_step": onset,
            "watchdog_sampled_max_u": per_field["u"], "watchdog_sampled_max_p": per_field["p"]}


def _history(path: Path, summary: dict, *, blocked: bool) -> list[dict]:
    if not blocked:
        rows = W.read_history(path)
    else:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            _require(tuple(reader.fieldnames or ()) == W.HEADER, "blocked history schema mismatch")
            rows = [{k: float(row[k]) for k in W.HEADER} for row in reader]
        _require(all(math.isfinite(row[k]) for row in rows for k in W.HEADER if not k.endswith("_tan")), "blocked history has nonfinite primal samples")
    steps = summary["steps"]
    expected = list(range(8, steps + 1, 8))
    if not blocked and steps % 8:
        expected.append(steps)
    _require([r["step"] for r in rows] == expected and summary.get("sample_count") == len(rows), "force sampling cadence/count mismatch")
    _require(all(b["t_u_l"] > a["t_u_l"] for a, b in zip(rows, rows[1:])), "history time is not strictly increasing")
    return rows


def verify_output(out_dir: Path, reference: dict) -> dict:
    """Authenticate a complete 13-run arm (7 runs for CPU Float64) and means.

    Short CPU preflights are intentionally rejected here: they cannot acquire
    scientific labels. The kernel's own index remains available for inspection.
    """
    validate_reference(reference)
    out_dir = Path(out_dir)
    _require((out_dir / "DONE").is_file() and not any((out_dir / p).exists() for p in ("ERROR.txt", "ERROR.json")), "DONE missing or ERROR present")
    inventory = _read_json(out_dir / "output_manifest.json").get("files")
    _require(isinstance(inventory, dict) and inventory, "output manifest files missing")
    actual = {str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file() and p.name != "output_manifest.json"}
    _require(actual == set(inventory), "output manifest does not cover the exact output file inventory")
    for name, digest in inventory.items():
        _require(sha256(_relative_file(out_dir, name)) == digest, f"output SHA mismatch: {name}")
    for required in ("DONE", "run_identity.json", "g2_run_index.json", "grad00_index.json"):
        _require(required in inventory, f"output manifest omits {required}")
    identity = _read_json(out_dir / "run_identity.json")
    _require(identity.get("failure_stage") is None and identity.get("spike_exit_code") in (0, 3), "runner reports failure")
    index = _read_json(out_dir / "grad00_index.json")
    _require(isinstance(index, dict), "grad00_index must be an object")
    missing = REQUIRED_INDEX_KEYS - index.keys()
    _require(not missing, f"grad00_index missing required keys: {sorted(missing)}")
    _require(index["schema_version"] == 1 and index["tier"] == "GRAD-00", "unknown grad00_index schema")
    arm, precision = index["arm"], index["real_type"]
    _require(arm in ARMS and precision in ("Float32", "Float64"), "unknown arm or precision")
    _require(index["waterlily"] in ("1.8.0", "1.10.0") and index["backend"] in ("cuda", "cpu"), "unknown WaterLily/backend identity")
    _require(index.get("evidence_class") in ("SYNTHETIC_TEST_FIXTURE", "exploratory_lambda_swap_forward_ad_measurement"), "unknown evidence class or CPU code-path dry run; no scientific labels allowed")
    _require(index["julia"] == "1.12.6", "Julia runtime differs from the registered 1.12.6 cohort")
    if index["backend"] == "cuda":
        _require(index["forwarddiff"] == "1.4.5" and index.get("cuda_jl") == "6.3.1" and "Tesla T4" in str(index.get("gpu_name", "")), "CUDA/T4/ForwardDiff runtime pin mismatch")
    else:
        _require(index["forwarddiff"] in ("1.4.5", "1.4.6"), "CPU ForwardDiff identity is unknown")
    _source_identity(identity, index, reference)
    if precision == "Float64":
        _require(arm in ARMS[:2] and index["backend"] == "cpu" and index["waterlily"] == "1.8.0", "precision F requires CPU Float64 arms A/B on WaterLily 1.8.0")
    if index["waterlily"] == "1.10.0":
        _require(arm == "quick" and precision == "Float32", "side E is quick Float32 on WaterLily 1.10.0")
    if index["backend"] == "cpu":
        _require(arm in ARMS[:2], "full-window CPU precision comparison is restricted to A/B")
    dirs = DIRECTIONS[:2] if precision == "Float64" else DIRECTIONS
    _require(index["directions"] == list(dirs), "direction inventory mismatch")
    _require(index["window_t_u_l"] == list(WINDOW) and index["sample_every"] == 8 and index["dual_width"] == 1, "full-window/sampling/Dual width mismatch; CPU dry runs are not scientific results")
    _require(index["block_limit"] == BLOCK_LIMIT and index["wall_factor"] == 8.0, "watchdog/wall threshold mismatch")
    _require(isinstance(index["qualification_flags"], dict) and set(index["qualification_flags"]) == set(FLAGS)
             and all(value is False for value in index["qualification_flags"].values()), "qualification_flags must remain false")
    _require(index["status"] in ("COMPLETE", "BLOCKED"), "arm did not complete its full inventory")
    _require(identity["spike_exit_code"] == (3 if index["status"] == "BLOCKED" else 0), "runner exit/index status mismatch")
    preflight = index["preflight"]
    _require(isinstance(preflight, dict) and preflight.get("pass") is True and preflight.get("steps") == 20, "preflight failed or absent")
    if arm == "quick":
        _require(preflight.get("primal_u_bit_equal") is True and preflight.get("primal_p_bit_equal") is True, "quick preflight is not primal bit-equal")
    if arm == "vanLeer_safe":
        _require(all(preflight.get(f"vanLeer_primal_{c}_bit_equal") is True for c in ("u", "p")), "vanLeer_safe preflight is not primal bit-equal to vanLeer")
    expected_lambda = LAMBDA_TYPES[arm]
    _require(index["lambda_type"] == expected_lambda, "lambda_type is not the selected convection scheme")
    _require(index["input_sha256"] == INPUT_SHA256, "registered input_sha256 mismatch")
    _require(set(index["epsilon_m"]) == set(DIRECTIONS) and set(index["by_direction"]) == set(dirs), "epsilon/by_direction inventory mismatch")
    for direction in DIRECTIONS:
        epsilon = _number(index["epsilon_m"][direction], f"{direction} epsilon_m", positive=True)
        _require(epsilon <= 5e-3 and epsilon == reference["directions"][direction]["epsilon_m"], f"{direction}: epsilon differs from reference or exceeds 5 mm")
    preflight_arms = preflight.get("arms")
    expected_preflight = {"selected_dual", "selected_plain"} | ({"quick"} if arm == "quick" else {"vanLeer_plain"} if arm == "vanLeer_safe" else set())
    _require(isinstance(preflight_arms, dict) and set(preflight_arms) == expected_preflight, "preflight arm inventory missing")
    for label, values in preflight_arms.items():
        _require(values.get("lambda_type") == (LAMBDA_TYPES["quick"] if label == "quick" else LAMBDA_TYPES["vanLeer"] if label == "vanLeer_plain" else expected_lambda), "preflight lambda routing mismatch")
        _require(all(values.get(k) is True for k in ("primal_finite", "tangent_u_finite", "tangent_p_finite")), "preflight primal/tangent not finite")
        for component in ("u", "p"):
            _require(re.fullmatch(r"[a-f0-9]{64}", str(values.get(f"primal_{component}_sha256", ""))) is not None, "preflight primal field SHA missing")
            _number(values.get(f"max_abs_tangent_{component}"), "preflight maximum tangent", minimum=0)
            if arm == "quick":
                _require(preflight_arms["quick"][f"primal_{component}_sha256"] == preflight_arms["selected_dual"][f"primal_{component}_sha256"], "quick preflight bit hashes disagree")
    if arm == "vanLeer_safe":
        for component in ("u", "p"):
            _require(preflight_arms["vanLeer_plain"][f"primal_{component}_sha256"] == preflight_arms["selected_plain"][f"primal_{component}_sha256"], "vanLeer_safe/vanLeer plain preflight bit hashes disagree")
    _require("preflight.json" in inventory and _read_json(out_dir / "preflight.json") == preflight, "preflight index/artifact mismatch")
    order = ["plain", *(label for d in dirs for label in (d, d + "__plus", d + "__minus"))]
    g2 = _read_json(out_dir / "g2_run_index.json")
    _require(g2.get("run_order") == order and set(g2.get("runs", {})) == set(order) and set(index["runs"]) == set(order), "run inventory differs from the declared 13 (or precision 7) runs")
    _require(g2.get("status") == index["status"], "g2/grad00 status mismatch")
    _require({p.name for p in out_dir.glob("*.history.csv")} == {f"{label}.history.csv" for label in order}, "unexpected history inventory")
    _require({p.name for p in out_dir.glob("*.watchdog.csv")} == {f"{label}.watchdog.csv" for label in dirs}, "unexpected watchdog inventory")
    runs = {}
    for label in order:
        entry = index["runs"][label]
        _require(isinstance(entry, dict), f"{label}: run entry missing")
        is_dual = label in dirs
        paths = {}
        for key in (("summary", "history", "watchdog") if is_dual else ("summary", "history")):
            name, digest = entry.get(key + "_path"), entry.get(key + "_sha256")
            _require(name == f"{label}.{key}.{'json' if key == 'summary' else 'csv'}", f"{label}: unexpected {key} artifact path")
            path = _relative_file(out_dir, name)
            _require(name in inventory and inventory[name] == digest and sha256(path) == digest, f"{label}: {key} SHA mismatch")
            paths[key] = path
        summary = _read_json(paths["summary"])
        _require(all(entry.get(k) == v for k, v in summary.items()), f"{label}: index differs from authenticated summary")
        _require(summary.get("label") == label and summary.get("lambda_type") == expected_lambda, f"{label}: label/lambda mismatch")
        _require(g2.get("run_status", {}).get(label) == summary.get("status"), f"{label}: g2 run_status mismatch")
        _require(type(summary.get("steps")) is int and summary["steps"] > 0, f"{label}: steps missing or invalid")
        _number(summary.get("total_seconds"), f"{label} wall", minimum=0)
        _number(summary.get("peak_vram_bytes"), f"{label} VRAM", minimum=0)
        run = {**summary, **(_watchdog(paths["watchdog"], summary) if is_dual else {"watchdog_max_tangent": 0.0, "watchdog_nonfinite": []})}
        direction = label if is_dual else next((d for d in dirs if label in (d + "__plus", d + "__minus")), None)
        amplitude = index["epsilon_m"][direction] * (1 if label.endswith("__plus") else -1) if direction and not is_dual else 0.0
        _require(summary.get("input_phi_storage_type") == precision and summary.get("input_phi_sha256") == expected_field_hash(precision, direction if amplitude else None, amplitude), f"{label}: actual stored phi input SHA mismatch")
        if is_dual:
            _require(summary.get("input_tangent_sha256") == expected_field_hash(precision, direction, tangent=True), f"{label}: actual Dual tangent input SHA mismatch")
            terminal = summary.get("terminal_tangent")
            _require(isinstance(terminal, dict), f"{label}: terminal tangent record missing")
            _require(all(k in terminal and (terminal[k] is None or type(terminal[k]) in (int, float) and math.isfinite(terminal[k]) and terminal[k] >= 0)
                         for k in ("tan_max_u", "tan_max_p")), f"{label}: invalid terminal tangent maxima")
            finite_terminal = [value for k, value in terminal.items() if k in ("tan_max_u", "tan_max_p") and type(value) in (float, int) and math.isfinite(value)]
            run["watchdog_max_tangent"] = max([run["watchdog_max_tangent"], *finite_terminal])
            if summary.get("status") == "COMPLETE":
                for key in ("tan_max_u", "tan_max_p"):
                    value = _number(terminal.get(key), f"{label} terminal {key}", minimum=0)
                    _require(value <= BLOCK_LIMIT, f"{label}: COMPLETE terminal tangent exceeds watchdog limit")
            _require(summary.get("watchdog_onset") == summary.get("blocked"), f"{label}: watchdog onset mismatch")
            for field in ("u", "p"):
                saved_max = _number(summary.get(f"watchdog_max_abs_tangent_{field}_finite"), f"{label} maximum {field} tangent", minimum=0)
                terminal_value = terminal.get(f"tan_max_{field}")
                observed_max = max(run[f"watchdog_sampled_max_{field}"], terminal_value if type(terminal_value) in (int, float) and math.isfinite(terminal_value) else 0.0)
                _require(V.close(saved_max, observed_max), f"{label}: watchdog/terminal maximum differs from summary")
        rows = _history(paths["history"], summary, blocked=run.get("status") == "BLOCKED")
        if run.get("status") == "BLOCKED":
            _require(is_dual, f"{label}: only a Dual tangent may be BLOCKED")
            boundedness(run)
            blocked = run["blocked"]
            _require(blocked["onset_step"] == summary["steps"], f"{label}: BLOCKED onset does not match terminal step")
            if blocked.get("reason") == "tangent_non_finite_or_above_limit":
                _require(run["watchdog_onset_step"] == blocked["onset_step"], f"{label}: BLOCKED onset not detected in watchdog")
            elif blocked.get("reason") == "non_finite_tangent_in_force_sample":
                _require(rows and rows[-1]["step"] == blocked["onset_step"] and any(not math.isfinite(rows[-1][k]) for k in W.HEADER if k.endswith("_tan")), f"{label}: BLOCKED force-sample onset missing")
            else:
                raise ValueError(f"{label}: unknown BLOCKED reason")
            blocked_file = f"{label}.blocked.json"
            _require(blocked_file in inventory and _read_json(out_dir / blocked_file) == run["blocked"], f"{label}: BLOCKED onset artifact mismatch")
        else:
            _require(not run["watchdog_nonfinite"], f"{label}: COMPLETE watchdog contains nonfinite tangents")
            boundedness(run)
            _require(summary.get("fields_finite_incl_partials") is True, f"{label}: fields are not finite")
            real_type = summary.get("real_type", "")
            _require(isinstance(real_type, str) and (re.fullmatch(rf"(ForwardDiff\.)?Dual\{{.+,\s*{precision},\s*1\}}", real_type) is not None if is_dual else real_type == precision), f"{label}: real_type mismatch")
            if not is_dual:
                _require(all(r[k] == 0 for r in rows for k in W.HEADER if k.endswith("_tan")), f"{label}: primal history contains tangents")
            means = {}
            for component in ("fx", "fz"):
                for variant, time_tangent in (("dual_time", True), ("frozen_time", False)):
                    value, tangent = W.window_mean(rows, component, *WINDOW, time_tangent=time_tangent)
                    key = f"window_mean_{component}_{variant}"
                    saved = summary.get(key, {})
                    _require(V.close(value, _number(saved.get("value"), f"{label} {key} value")) and V.close(tangent, _number(saved.get("tangent"), f"{label} {key} tangent")), f"{label}: host window recomputation mismatch")
                    means[key] = {"value": value, "tangent": tangent}
            run.update(means)
        runs[label] = run
    _require((index["status"] == "BLOCKED") == any(r["status"] == "BLOCKED" for r in runs.values()), "arm BLOCKED status does not match runs")
    for direction in dirs:
        epsilon = _number(index["epsilon_m"][direction], f"{direction} epsilon_m", positive=True)
        _require(epsilon == reference["directions"][direction]["epsilon_m"], f"{direction}: epsilon differs from reference")
        _require(index["by_direction"][direction] == {"plain": "plain", "dual": direction, "plus": direction + "__plus", "minus": direction + "__minus", "epsilon_m": epsilon}, f"{direction}: run routing/epsilon mismatch")
        if runs[direction]["status"] == "COMPLETE":
            for component in ("fx", "fz"):
                key = f"window_mean_{component}_dual_time"
                _require(V.rel(runs[direction][key]["value"], runs["plain"][key]["value"]) <= V.PRIMAL_GATE, f"{direction}: same-arm Dual/plain primal gate failed")
    return {"index": index, "runs": runs, "source_commit": identity["source_commit"], "index_sha256": sha256(out_dir / "grad00_index.json")}


def _mean(run, component, field="value"):
    return run[f"window_mean_{component}_dual_time"][field] * W.FORCE_SCALE_N_PER_SOLVER


def _fd(checked, direction, component):
    return (_mean(checked["runs"][direction + "__plus"], component) - _mean(checked["runs"][direction + "__minus"], component)) / (2 * checked["index"]["epsilon_m"][direction])


def _identity(checked):
    index = checked["index"]
    return tuple(index[k] for k in ("arm", "real_type", "waterlily", "backend"))


def _runtime(checked):
    return {k: checked["index"].get(k) for k in ("backend", "julia", "waterlily", "forwarddiff", "cuda_jl", "gpu_name")}


def analyze_campaign(root: Path, reference: dict) -> dict:
    validate_reference(reference)
    root = Path(root)
    _require(root.is_dir(), "campaign output root is missing")
    _require(not (root / "vanLeer_safe").exists() or (root / "vanLeer_safe").is_dir(), "vanLeer_safe output must be a directory")
    # A present output directory is evidence to authenticate, even without an
    # index. In particular an empty/failed D′ directory must not become NOT_RUN.
    outputs = sorted(p for p in root.iterdir() if p.is_dir())
    _require(outputs, "no arm grad00_index.json outputs found")
    verified = {out.name: verify_output(out, reference) for out in outputs}
    _require("vanLeer_safe" not in verified or verified["vanLeer_safe"]["index"]["arm"] == "vanLeer_safe", "vanLeer_safe output directory contains a different arm")
    identities = [_identity(v) for v in verified.values()]
    _require(len(set(identities)) == len(identities), "duplicate arm/precision/version/backend identity")
    _require({(arm, "Float32", "1.8.0", "cuda") for arm in PRIMARY_ARMS}.issubset(identities), "all four primary CUDA/T4 A-D arms are required before final analysis")
    classes = {v["index"]["evidence_class"] for v in verified.values()}
    _require(len(classes) == 1, "synthetic and measured evidence classes cannot be mixed")
    control = next(v for v in verified.values() if _identity(v) == ("quick", "Float32", "1.8.0", "cuda"))
    _require(sha256(SCOPE_RECORD) == SCOPE_RECORD_SHA256, "historical FD-08 scope record SHA mismatch")
    historical = {(r["direction_id"], "fx" if r["response_id"] == "drag" else "fz"): (1 if r["response_id"] == "drag" else -1) * r["g_hat_n_per_m"] for r in _read_json(SCOPE_RECORD)["rows"]}
    arms, allowed = {}, []
    for name, checked in verified.items():
        index, runs = checked["index"], checked["runs"]
        directions = {}
        for direction in index["directions"]:
            run = runs[direction]
            state = boundedness(run)
            entry = {"boundedness": state, "agreement": None, "comparison_reason": "tangent_blocked" if state == "BLOCKED" else None, "blocked": run.get("blocked"),
                     "watchdog_max_tangent": run["watchdog_max_tangent"], "wall_seconds": run["total_seconds"], "peak_vram_bytes": run["peak_vram_bytes"]}
            rows = {}
            for c in ("fx", "fz"):
                fd = _fd(checked, direction, c)
                spread = reference["directions"][direction]["spread_n_per_m"][c]
                compared = compare_row(_mean(run, c, "tangent"), fd, spread) if state == "BOUNDED" else {
                    "tangent_n_per_m": None, "fd_n_per_m": fd, "spread_n_per_m": spread, "label": None, "reason": "tangent_blocked"}
                rows[c] = {**compared, "fd08_model_a_n_per_m_descriptive": historical[(direction, c)]}
            entry["rows"] = rows
            if state == "BOUNDED":
                labels = [r["label"] for r in rows.values()]
                entry["agreement"] = "NOT_EVALUABLE" if "NOT_EVALUABLE" in labels else "AGREE" if all(v == "AGREE" for v in labels) else "DISAGREE"
            directions[direction] = entry
        count = sum(v["boundedness"] == "BOUNDED" for v in directions.values())
        label = "BOUNDED_ALL" if count == len(directions) else "BLOCKED_ALL" if not count else "PARTIAL"
        agree_count = sum(v["agreement"] == "AGREE" for v in directions.values())
        eligible = index["arm"] in NEXT_STEP_ARMS and index["real_type"] == "Float32" and index["waterlily"] == "1.8.0" and index["backend"] == "cuda" and len(directions) == 4
        if eligible and label == "BOUNDED_ALL" and agree_count >= 3:
            allowed.append(name)
        arms[name] = {"arm": index["arm"], "real_type": index["real_type"], "waterlily": index["waterlily"], "label": label,
                      "backend": index["backend"], "runtime": _runtime(checked),
                      "agree_count": agree_count, "direction_count": len(directions), "next_step_eligible": eligible, "directions": directions,
                      "plain_minus_arm_a_n": {c: _mean(runs["plain"], c) - _mean(control["runs"]["plain"], c) for c in ("fx", "fz")},
                      "plain_comparison_arm_a_source_commit": control["source_commit"], "plain_comparison_same_runtime": _runtime(checked) == _runtime(control),
                      "index_sha256": checked["index_sha256"], "source_commit": checked["source_commit"],
                      "wall_seconds_all_runs": sum(r["total_seconds"] for r in runs.values()), "peak_vram_bytes": max(r["peak_vram_bytes"] for r in runs.values())}
    if not any(v["index"]["arm"] == "vanLeer_safe" for v in verified.values()):
        arms["vanLeer_safe"] = {"arm": "vanLeer_safe", "label": "NOT_RUN", "reason": "output_directory_absent",
                               "agree_count": 0, "direction_count": 0, "directions": {}, "next_step_eligible": False}
    precision_differences = {}
    for arm in ARMS[:2]:
        f32 = next((v for v in verified.values() if _identity(v) == (arm, "Float32", "1.8.0", "cpu")), None)
        f32 = f32 or next((v for v in verified.values() if _identity(v) == (arm, "Float32", "1.8.0", "cuda")), None)
        f64 = next((v for v in verified.values() if _identity(v) == (arm, "Float64", "1.8.0", "cpu")), None)
        if f32 and f64:
            paired = {}
            for d in DIRECTIONS[:2]:
                both_bounded = f32["runs"][d]["status"] == f64["runs"][d]["status"] == "COMPLETE"
                paired[d] = {"float32_status": f32["runs"][d]["status"], "float64_status": f64["runs"][d]["status"],
                             "tangent_f64_minus_f32_n_per_m": {c: _mean(f64["runs"][d], c, "tangent") - _mean(f32["runs"][d], c, "tangent") if both_bounded else None for c in ("fx", "fz")},
                             "fd_f64_minus_f32_n_per_m": {c: _fd(f64, d, c) - _fd(f32, d, c) for c in ("fx", "fz")}}
            precision_differences[arm] = {"plain_f64_minus_f32_n": {c: _mean(f64["runs"]["plain"], c) - _mean(f32["runs"]["plain"], c) for c in ("fx", "fz")},
                                         "backend_pair": {"float32": f32["index"]["backend"], "float64": f64["index"]["backend"]},
                                         "runtime_pair": {"float32": _runtime(f32), "float64": _runtime(f64)},
                                         "cross_backend_confound": f32["index"]["backend"] != f64["index"]["backend"], "directions": paired,
                                         "interpretation": "descriptive CPU Float64 minus Float32; any backend/runtime differences remain confounded with precision"}
    return {"kind": "grad00_lambda_analysis", "analysis_runs": 1, "evidence_class": "SYNTHETIC_TEST_FIXTURE" if all(v["index"].get("evidence_class") == "SYNTHETIC_TEST_FIXTURE" for v in verified.values()) else "EXPLORATORY_COMMITTED",
            "arms": arms, "precision_differences": precision_differences,
            "next_step": "GRAD01_DRAFT_ALLOWED" if allowed else "GRAD01_DRAFT_NOT_ALLOWED", "eligible_arms_passing_next_rule": allowed,
            "reference": reference, "historical_fd08_model_a_scope_record_sha256": SCOPE_RECORD_SHA256,
            "rules": {"relative_error": RELATIVE_ERROR, "spread_multiple": SPREAD_MULTIPLE, "block_limit": BLOCK_LIMIT, "blocks_strictly_above_limit": True,
                      "window_t_u_l": list(WINDOW), "same_arm_primal_gate": V.PRIMAL_GATE, "next_step_arms": list(NEXT_STEP_ARMS)},
            "units": {"force": "N", "tangent_and_fd_and_spread": "N/m", "fz": "raw force on body; downforce=-fz"},
            "meaning": "exploratory sampled-watchdog boundedness and same-scheme central difference; not grid/physical/gradient qualification",
            "qualification_flags": {k: False for k in FLAGS}}


def write_analysis(path: Path, result: dict) -> None:
    """Exclusive create: never overwrite either evidence file or SHA sidecar."""
    path = Path(path)
    sidecar = path.with_name(path.name + ".sha256")
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {path}")
    data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(data)
    with sidecar.open("x") as handle:
        handle.write(hashlib.sha256(data).hexdigest() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--reference", type=Path, help="explicit plateau epsilon/spread definition with source hashes")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", type=Path, metavar="ANALYSIS_JSON")
    args = parser.parse_args()
    if args.write is not None and (args.write.exists() or args.write.with_name(args.write.name + ".sha256").exists()):
        parser.exit(1, "refusing to overwrite evidence\n")
    if args.reference is None:
        parser.exit(1, "explicit --reference epsilon/spread definition is required; no scientific labels or analysis are written\n")
    try:
        reference = load_reference(args.reference)
        result = analyze_campaign(args.out_dir, reference)
        result["reference_sha256"] = sha256(args.reference)
        if args.write is not None:
            write_analysis(args.write, result)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"GRAD-00 prerequisite/integrity failure: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
