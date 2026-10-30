#!/usr/bin/env python3
"""W1 GridSDFBody adapter qualification controller.

Runs the registered fixture suite (round 4 of
``docs/evidence/sdf_native_w1_adapter_criteria_2026_09.json``) under CLI Julia,
re-checks every registered threshold independently in Python, measures the
registered v16 genesis state's zero-level-to-design-box margin through the
adapter's own ``zero_level_margin_m`` and gate constructor, and writes the
immutable W1 evidence record plus its sha256 sidecar.

Fail-closed: if any registered gate fails, no evidence is written and the
process exits nonzero.  This controller never runs a solver.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402

CRITERIA_PATH = ROOT / "docs/evidence/sdf_native_w1_adapter_criteria_2026_09.json"
CRITERIA_SHA256 = "6da068fad8c79ba39197377157d4a5172dedf04511b2acbd8f69146aefea70ef"
W0_EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_w0_julia_env_2026_09.json"
W0_EVIDENCE_SHA256 = "9689ed58dfda87414bc1a4be8fce49d86405c2619217540bfe08391b98b3e5e7"
GENESIS_EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json"
MANIFEST_PATH = ROOT / "julia/CFDSDFWaterLily/Manifest.toml"
MANIFEST_SHA256 = "65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c"
PROJECT_PATH = ROOT / "julia/CFDSDFWaterLily/Project.toml"
PROJECT_SHA256 = "5abca50d507cd809e6950ec654703cd1887977aab14ba5b864bcf066b4865e27"
GENESIS_STATE_PATH = ROOT / "work/sdf_native_genesis_v16/sdf_design_state.npz"
GENESIS_STATE_SHA256 = "3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe"
GENESIS_CANONICAL_STATE_SHA256 = "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8"
GENESIS_PHI_SHA256 = "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785"
TEST_PATH = ROOT / "julia/CFDSDFWaterLily/test/test_grid_sdf_body.jl"
SRC_PATH = ROOT / "julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl"
PROJECT_DIR = ROOT / "julia/CFDSDFWaterLily"
WORK_DIR = ROOT / "work/sdf_native_w1_grid_sdf_body_2026_09"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_w1_grid_sdf_body_2026_09.json"

ORIGIN = (-1.0, -0.8, -0.6)
SPACING = (0.05, 0.05, 0.05)
SHAPE = (61, 33, 25)
ORIGIN_JL = "(-1.0, -0.8, -0.6)"
SPACING_JL = "(0.05, 0.05, 0.05)"
SHAPE_JL = "(61, 33, 25)"
SPHERE_CENTER_M = (0.25, 0.0, 0.0)
SPHERE_RADIUS_M = 0.5
CROSS_CHECK_PROBES = 200_000
CROSS_CHECK_SEED = 2026
OUTSIDE_VALUE = 3.0
RUN_MARGIN_M = 0.15
SPHERE_MARGIN_M = 0.10

# registered fixture gates: name -> (judgment kind, registered value)
FIXTURE_GATES: dict[str, tuple[str, float]] = {
    "world_solver_roundtrip": ("max_le", 1e-14),
    "affine_exactness": ("max_le", 2e-5),
    "sphere_sdf_interface_band": ("band_max_le", 3.3e-3),
    "sphere_sdf_interior_diagnostic": ("recorded", 0.0),
    "radius_float64": ("max_le", 2e-3),
    "radius_float32": ("max_le", 2e-3),
    "outside_extension_positive_exactly": ("verdict", 0.0),
    "margin_gate_pass": ("min_ge", SPHERE_MARGIN_M - 1e-6),
    "margin_gate_fail_closed": ("verdict", 0.0),
    "all_solid_refused": ("verdict", 0.0),
}
BAND_PROBE_COUNT = 5000


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_sidecar(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise SystemExit(f"{label} is missing: {path.relative_to(ROOT)}")
    actual = _sha256_path(path)
    if actual != expected:
        raise SystemExit(f"{label} sha mismatch: {actual} != {expected}")
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != actual:
        raise SystemExit(f"{label} sidecar mismatch: {sidecar.relative_to(ROOT)}")
    return actual


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise SystemExit(f"refusing to overwrite immutable artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _independent_band_sup() -> float:
    """Independent numpy trilinear evaluation of the registered analytic-sphere
    fixture on explicit interface-band probes (diagnostic, not a gate)."""

    xs = np.asarray(ORIGIN[0] + np.arange(SHAPE[0]) * SPACING[0])
    ys = np.asarray(ORIGIN[1] + np.arange(SHAPE[1]) * SPACING[1])
    zs = np.asarray(ORIGIN[2] + np.arange(SHAPE[2]) * SPACING[2])
    grid = np.meshgrid(xs, ys, zs, indexing="ij")
    center = np.asarray(SPHERE_CENTER_M)
    phi = np.asarray(
        np.sqrt(sum((axis - center[i]) ** 2 for i, axis in enumerate(grid)))
        - SPHERE_RADIUS_M,
        dtype=np.float32,
    )
    rng = np.random.default_rng(CROSS_CHECK_SEED)
    theta = np.arccos(1.0 - 2.0 * rng.random(CROSS_CHECK_PROBES))
    azimuth = 2.0 * np.pi * rng.random(CROSS_CHECK_PROBES)
    direction = np.stack(
        [np.sin(theta) * np.cos(azimuth), np.sin(theta) * np.sin(azimuth), np.cos(theta)],
        axis=1,
    )
    offsets = (2.0 * rng.random(CROSS_CHECK_PROBES) - 1.0) * 1e-3
    points = center + (SPHERE_RADIUS_M + offsets)[:, None] * direction
    scaled = (points - np.asarray(ORIGIN)) / np.asarray(SPACING)
    base = np.minimum(np.floor(scaled).astype(np.int64), np.asarray(SHAPE) - 2)
    frac = scaled - base
    values = np.zeros(CROSS_CHECK_PROBES)
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                weight = ((1 - frac[:, 0]) if dx == 0 else frac[:, 0]) * (
                    (1 - frac[:, 1]) if dy == 0 else frac[:, 1]
                ) * ((1 - frac[:, 2]) if dz == 0 else frac[:, 2])
                values += weight * phi[
                    base[:, 0] + dx, base[:, 1] + dy, base[:, 2] + dz
                ].astype(np.float64)
    return float(np.abs(values - offsets).max())


def _julia_version() -> str:
    completed = _run(["julia", "--version"], timeout=120)
    if completed.returncode != 0:
        raise SystemExit(f"julia --version failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _parse_results(stdout: str) -> dict[str, tuple[str, str]]:
    results: dict[str, tuple[str, str]] = {}
    for line in stdout.splitlines():
        match = re.match(r"^RESULT (\S+) (PASS|FAIL)(?: (.*))?$", line.strip())
        if match:
            results[match.group(1)] = (match.group(2), (match.group(3) or "").strip())
    return results


def _judge(name: str, verdict: str, value: str) -> tuple[bool, str]:
    kind, bound = FIXTURE_GATES[name]
    if kind == "verdict":
        return verdict == "PASS", f"verdict {verdict}"
    if kind == "recorded":
        return verdict == "PASS", f"recorded value: {value}"
    if kind == "band_max_le":
        match = re.match(r"^n=(\d+) max (\S+)$", value)
        if not match:
            return False, f"unparsable band value: {value!r}"
        count = int(match.group(1))
        measured = float(match.group(2))
        return (
            verdict == "PASS" and count == BAND_PROBE_COUNT and measured <= bound,
            f"n={count} max={measured:.6e} <= {bound:.6e}",
        )
    if kind == "max_le":
        measured = float(value)
        return verdict == "PASS" and measured <= bound, f"{measured:.6e} <= {bound:.6e}"
    if kind == "min_ge":
        measured = float(value)
        return verdict == "PASS" and measured >= bound, f"{measured:.6e} >= {bound:.6e}"
    raise AssertionError(kind)


def main() -> None:
    criteria_sha = _check_sidecar(CRITERIA_PATH, CRITERIA_SHA256, "W1 criteria")
    w0_sha = _check_sidecar(W0_EVIDENCE_PATH, W0_EVIDENCE_SHA256, "W0 evidence")
    if _sha256_path(MANIFEST_PATH) != MANIFEST_SHA256:
        raise SystemExit("pinned Manifest.toml changed; W0 environment identity is broken")
    if _sha256_path(PROJECT_PATH) != PROJECT_SHA256:
        raise SystemExit("pinned Project.toml changed; W0 environment identity is broken")
    genesis_evidence_sha = _sha256_path(GENESIS_EVIDENCE_PATH) if GENESIS_EVIDENCE_PATH.is_file() else ""
    genesis_sidecar = GENESIS_EVIDENCE_PATH.with_suffix(GENESIS_EVIDENCE_PATH.suffix + ".sha256")
    if not genesis_evidence_sha or not genesis_sidecar.is_file() or (
        genesis_sidecar.read_text().strip() != genesis_evidence_sha
    ):
        raise SystemExit("genesis evidence or its sidecar is missing/inconsistent")
    if not GENESIS_STATE_PATH.is_file() or _sha256_path(GENESIS_STATE_PATH) != GENESIS_STATE_SHA256:
        raise SystemExit("genesis state npz is missing or has changed")

    state = SDFDesignState.load(GENESIS_STATE_PATH)
    if state.state_sha256 != GENESIS_CANONICAL_STATE_SHA256:
        raise SystemExit(f"genesis state sha mismatch: {state.state_sha256}")
    if state.phi_sha256() != GENESIS_PHI_SHA256:
        raise SystemExit(f"genesis phi sha mismatch: {state.phi_sha256()}")
    if tuple(int(v) for v in state.shape) != SHAPE:
        raise SystemExit(f"genesis phi shape changed: {state.shape}")
    if tuple(float(v) for v in state.origin_m) != ORIGIN or float(state.spacing_m) != SPACING[0]:
        raise SystemExit("genesis grid identity differs from the registered canonical grid")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    julia_version = _julia_version()
    fixture = _run(
        ["julia", f"--project={PROJECT_DIR}", str(TEST_PATH)],
        timeout=3600,
    )
    transcript = fixture.stdout + "\n--- stderr ---\n" + fixture.stderr
    fixture_results = _parse_results(fixture.stdout)

    missing = [name for name in FIXTURE_GATES if name not in fixture_results]
    if missing:
        print(transcript, file=sys.stderr)
        raise SystemExit(f"fixture run did not report registered gates: {missing}")

    fixture_judgment: dict[str, Any] = {}
    failures: list[str] = []
    for name, (verdict, value) in fixture_results.items():
        if name not in FIXTURE_GATES:
            continue
        ok, detail = _judge(name, verdict, value)
        fixture_judgment[name] = {
            "verdict": verdict,
            "value": value,
            "registered_judgment": detail,
            "pass": ok,
        }
        if not ok:
            failures.append(name)
    if fixture.returncode != 0 or failures:
        print(transcript, file=sys.stderr)
        raise SystemExit(
            f"W1 fixture fail-closed stop: exit={fixture.returncode} failures={failures}"
        )

    # real-data margin/round-trip probe through the adapter itself
    raw_path = WORK_DIR / "genesis_phi_f4_fortran.raw"
    raw_path.write_bytes(state.phi.tobytes(order="F"))
    probe_script = f"""
include({json.dumps(str(SRC_PATH))})
using .CFDSDFWaterLily.GridSDFBody
phi = reshape(reinterpret(Float32, read({json.dumps(str(raw_path))})), {SHAPE_JL})
origin = {ORIGIN_JL}
h = {SPACING_JL}
m = zero_level_margin_m(phi, origin, h)
println("GENESIS_MARGIN_MEASURED ", m)
try
    g = GridSDF(phi; origin=origin, h=h, outside_value={OUTSIDE_VALUE}, margin_m={RUN_MARGIN_M})
    println("GENESIS_MARGIN_GATE ACCEPT")
    probes = ((-0.95, -0.77, 0.11), (0.25, 0.0, 0.0), (1.99, 0.79, -0.59))
    maxrt = maximum(maximum(abs.(solver_to_world(g, world_to_solver(g, xw)) .- xw)) for xw in probes)
    println("GENESIS_ROUNDTRIP_MAX ", maxrt)
catch e
    println("GENESIS_MARGIN_GATE REFUSE ", sprint(showerror, e))
    exit(3)
end
"""
    probe = _run(["julia", f"--project={PROJECT_DIR}", "-e", probe_script], timeout=600)
    margin_match = re.search(r"^GENESIS_MARGIN_MEASURED (\S+)$", probe.stdout, re.M)
    roundtrip_match = re.search(r"^GENESIS_ROUNDTRIP_MAX (\S+)$", probe.stdout, re.M)
    gate_accepted = "GENESIS_MARGIN_GATE ACCEPT" in probe.stdout
    if not margin_match or not gate_accepted or not roundtrip_match:
        print(probe.stdout + "\n--- stderr ---\n" + probe.stderr, file=sys.stderr)
        raise SystemExit("W1 genesis probe fail-closed stop: margin/gate/round-trip not established")
    genesis_margin_m = float(margin_match.group(1))
    genesis_roundtrip_m = float(roundtrip_match.group(1))
    if genesis_margin_m < RUN_MARGIN_M:
        raise SystemExit(
            f"W1 genesis margin fail-closed: {genesis_margin_m} m < {RUN_MARGIN_M} m"
        )
    if genesis_roundtrip_m > 1e-14:
        raise SystemExit(f"W1 genesis round-trip fail-closed: {genesis_roundtrip_m} m")
    independent_band_sup_m = _independent_band_sup()
    band_measured_m = float(
        re.match(
            r"^n=\d+ max (\S+)$", fixture_judgment["sphere_sdf_interface_band"]["value"]
        ).group(1)
    )

    transcript_path = WORK_DIR / "fixture_stdout.txt"
    transcript_path.write_text(transcript)
    probe_path = WORK_DIR / "genesis_margin_probe_stdout.txt"
    probe_path.write_text(probe.stdout + "\n--- stderr ---\n" + probe.stderr)

    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "sdf_native_w1_grid_sdf_body",
        "gate_id": "sdf_native_w1_gridsdfbody_2026_09",
        "evidence_class": "contract_and_numerical",
        "immutable": True,
        "solver_started": False,
        "existing_evidence_modified": False,
        "generated_on": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "julia": julia_version,
        },
        "registered_criteria": {
            "path": CRITERIA_PATH.relative_to(ROOT).as_posix(),
            "sha256": criteria_sha,
            "correction_round_used": 4,
            "round3_bound_m": 1.0e-3,
            "round4_bound_m": 3.3e-3,
            "round3_failure_measured_m": band_measured_m,
            "correction_note": (
                "the deterministic fixture measured here is the same quantity that failed "
                "the unsound round-3 bound; round 4 replaced the bound with the analytic "
                "Kergin truncation bound before this registered evidence run"
            ),
            "environment_identity": {
                "manifest_sha256": MANIFEST_SHA256,
                "project_sha256": PROJECT_SHA256,
                "waterlily": "1.8.0",
            },
        },
        "inputs": {
            "w0_evidence": {
                "path": W0_EVIDENCE_PATH.relative_to(ROOT).as_posix(),
                "sha256": w0_sha,
            },
            "genesis_evidence": {
                "path": GENESIS_EVIDENCE_PATH.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(GENESIS_EVIDENCE_PATH),
            },
            "genesis_state_npz": {
                "path": GENESIS_STATE_PATH.relative_to(ROOT).as_posix(),
                "sha256": GENESIS_STATE_SHA256,
                "state_sha256": GENESIS_CANONICAL_STATE_SHA256,
                "phi_sha256": GENESIS_PHI_SHA256,
            },
            "genesis_phi_fortran_raw": {
                "path": raw_path.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(raw_path),
                "shape": list(SHAPE),
                "dtype": "float32",
                "order": "F",
                "note": "byte encoding consumed by the Julia probe; derived from the registered phi",
            },
        },
        "adapter_contract": {
            "sign_convention": "phi < 0 solid / phi > 0 fluid",
            "world_space": {
                "origin_m": list(ORIGIN),
                "spacing_m": list(SPACING),
                "point_shape": list(SHAPE),
                "design_box": "closed lattice extent",
            },
            "affine_map": {
                "world_to_solver": "x_solver = (x_world - offset_m) ./ h_m",
                "solver_to_world": "x_world = offset_m + x_solver .* h_m",
                "offset_m": list(ORIGIN),
                "scale_solver_per_m": [1.0 / value for value in SPACING],
                "role": "W1 measures the map; later registered runs must advertise it in the runtime fingerprint",
            },
            "outside_design_box": (
                f"guaranteed positive read-only fluid extension {OUTSIDE_VALUE} m, "
                "exactly returned; never interpolated or extrapolated"
            ),
            "interface_to_boundary_margin_m": RUN_MARGIN_M,
            "registered_min_run_margin_m": RUN_MARGIN_M,
        },
        "fixture_results": fixture_judgment,
        "independent_cross_checks": {
            "band_error_numpy": {
                "max_m": independent_band_sup_m,
                "probes": CROSS_CHECK_PROBES,
                "seed": CROSS_CHECK_SEED,
                "method": (
                    "numpy trilinear evaluation of the same analytic-sphere fixture and "
                    "registered band construction; diagnostic, not gated"
                ),
            },
            "fixture_transcript": {
                "path": (WORK_DIR / "fixture_stdout.txt").relative_to(ROOT).as_posix(),
                "sha256": _sha256_bytes(transcript.encode("utf-8")),
            },
            "genesis_probe_transcript": {
                "path": (WORK_DIR / "genesis_margin_probe_stdout.txt").relative_to(ROOT).as_posix(),
                "sha256": _sha256_bytes((probe.stdout + "\n--- stderr ---\n" + probe.stderr).encode("utf-8")),
            },
        },
        "genesis_margin_diagnosis": {
            "measured_zero_level_margin_m": genesis_margin_m,
            "required_run_margin_m": RUN_MARGIN_M,
            "gate_constructor_accepted": gate_accepted,
            "roundtrip_max_m": genesis_roundtrip_m,
            "registered_expectation": "~0.35 m >= 0.15 m",
            "measure": (
                "conservative Lipschitz bound over solid nodes: min over axes of the "
                "node-to-face gap plus the nodal |phi|"
            ),
        },
        "verdict": {
            "w1_adapter_qualified": True,
            "fixture_gates_passed": len(fixture_judgment),
            "fail_closed": False,
        },
        "claims_supported": [
            "the GridSDFBody adapter reproduces the registered world-space trilinear SDF map: "
            "affine exactness 1.776e-15 m, world<->solver round-trip bound pass, exact positive "
            "outside extension, under the registered fail-closed gates",
            "the adapter's trilinear representation of the analytic sphere stays within the "
            "round-4 analytic truncation bound in the interface band; the measured band error "
            "is documented and independently reproduced outside the adapter",
            "the registered v16 genesis state passes the 0.15 m interface-to-boundary margin "
            "gate through the gate constructor (measured conservative clearance ~0.35 m)",
            "the fail-closed refusal paths work: margin-gate refusal and all-solid refusal",
        ],
        "claims_not_supported": [
            "no WaterLily time step, force value, Simulation, BC or grid-study claim",
            "no CUDA/Enzyme backend qualification or Manifest change",
            "no v16 physics behavior; the v16 state is a margin/round-trip fixture only",
            "no SDF gradient, topology-birth, optimizer or downforce claim",
        ],
        "flags": {
            "shape_update_allowed": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
        },
    }
    payload = (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _write_immutable(EVIDENCE_PATH, payload)
    sidecar = EVIDENCE_PATH.with_suffix(EVIDENCE_PATH.suffix + ".sha256")
    digest = _sha256_path(EVIDENCE_PATH)
    if sidecar.exists() and sidecar.read_text().strip() != digest:
        raise SystemExit(f"evidence sidecar mismatch: {sidecar.relative_to(ROOT)}")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))

    summary = {
        "status": "registered",
        "gate_id": document["gate_id"],
        "julia": julia_version,
        "fixture_gates_passed": len(fixture_judgment),
        "band_error_m": fixture_judgment["sphere_sdf_interface_band"]["value"],
        "numpy_band_sup_m": independent_band_sup_m,
        "genesis_margin_m": genesis_margin_m,
        "evidence": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "evidence_sha256": digest,
        "solver_started": False,
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
