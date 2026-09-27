#!/usr/bin/env python3
"""W1g GPU GridSDF geometry qualification recorder.

Validates the captured Colab T4 fixture output against the registered W1g
criteria, verifies the backend identity with scripts/t4_backend_identity.py,
and writes the W1g evidence record plus its sha256 sidecar.  Fail-closed: on
any failed gate no evidence is written.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from t4_backend_identity import verify_backend_identity  # noqa: E402

CRITERIA_PATH = ROOT / "docs/evidence/sdf_native_w1g_gpu_gridsdf_criteria_2026_09.json"
W0B_RESULT = ROOT / "docs/evidence/sdf_native_w0b_t4_cuda_env_2026_09.json"
W2A_RESULT = ROOT / "docs/evidence/sdf_native_w2a_sphere_cpu_2026_09.json"
W2A_RESULT_SHA256 = "26b6a65f6a2f89dde7e9976b2209b776eeb90d895432707214a582e9192f920b"
WORK_DIR = ROOT / "work/sdf_native_w1g_gpu_gridsdf_2026_09"
RUN_STDOUT = WORK_DIR / "run_stdout.txt"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_w1g_gpu_gridsdf_2026_09.json"

VALUE_BOUND_M = 1e-5
NORMAL_BOUND = 1e-3
REGISTERED_BULK_BOX = 100_000
REGISTERED_BULK_BAND = 100_000
REGISTERED_REPRESENTATIVES = 12
REGISTERED_OUTSIDE = 6


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise SystemExit(f"refusing to overwrite immutable artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> None:
    criteria_sidecar = CRITERIA_PATH.with_suffix(CRITERIA_PATH.suffix + ".sha256")
    if not CRITERIA_PATH.is_file() or not criteria_sidecar.is_file():
        raise SystemExit("W1g criteria or sidecar is missing")
    criteria_sha = _sha256_path(CRITERIA_PATH)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise SystemExit("W1g criteria sidecar mismatch")
    if (
        not W2A_RESULT.is_file()
        or _sha256_path(W2A_RESULT) != W2A_RESULT_SHA256
    ):
        raise SystemExit("W2a result evidence is missing or inconsistent")
    if not W0B_RESULT.is_file():
        raise SystemExit("W0b result evidence is missing")
    if not RUN_STDOUT.is_file():
        raise SystemExit(f"captured W1g fixture output is missing: {RUN_STDOUT}")

    text = RUN_STDOUT.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"W1G_SUMMARY_BEGIN\s*(\{.*?\})\s*W1G_SUMMARY_END", text, re.S)
    if not match or "W1G_FIXTURE_DONE gpu" not in text:
        raise SystemExit("W1g fixture output does not contain a completed gpu summary")
    summary: dict[str, Any] = json.loads(match.group(1))

    gates: dict[str, Any] = {}
    failures: list[str] = []

    def record(name: str, passed: bool, detail: str) -> None:
        gates[name] = {"pass": passed, "detail": detail}
        if not passed:
            failures.append(name)

    record(
        "G1_device_copy_source_sha",
        summary["mode"] == "gpu"
        and summary["source_phi_sha256"] == summary["device_roundtrip_sha256"],
        f"source={summary['source_phi_sha256'][:16]} roundtrip={summary['device_roundtrip_sha256'][:16]}",
    )
    record(
        "G2_kernel_executes",
        summary["probe_count"] == REGISTERED_BULK_BOX + REGISTERED_BULK_BAND + REGISTERED_REPRESENTATIVES
        and summary["bulk_box"] == REGISTERED_BULK_BOX
        and summary["bulk_band"] == REGISTERED_BULK_BAND,
        f"probe_count={summary['probe_count']} box={summary['bulk_box']} band={summary['bulk_band']}",
    )
    record("G3_finite", bool(summary["all_finite"]), f"all_finite={summary['all_finite']}")
    record(
        "G4_sign_classification",
        int(summary["sign_violations"]) == 0 and int(summary["sign_gated_probes"]) > 0,
        f"violations={summary['sign_violations']} gated={summary['sign_gated_probes']}",
    )
    record(
        "G5_value_bound",
        float(summary["max_value_error_world_m"]) <= VALUE_BOUND_M,
        f"max_value_error={summary['max_value_error_world_m']} <= {VALUE_BOUND_M}",
    )
    record(
        "G6_normal_bound",
        float(summary["max_normal_error"]) <= NORMAL_BOUND and int(summary["normal_gated_probes"]) > 0,
        f"max_normal_error={summary['max_normal_error']} <= {NORMAL_BOUND} "
        f"(gated subset {summary['normal_gated_probes']})",
    )
    record(
        "G7_outside_extension",
        bool(summary["outside_exact"]) and int(summary["outside_probes"]) == REGISTERED_OUTSIDE,
        f"outside_exact={summary['outside_exact']} probes={summary['outside_probes']}",
    )
    record(
        "G8_no_scalar_fallback",
        summary["allowscalar"] is False,
        f"allowscalar={summary['allowscalar']}",
    )
    identity_check = verify_backend_identity(summary["backend_identity"])
    record(
        "G9_backend_identity",
        identity_check["pass"],
        f"mismatches={identity_check['mismatches']}",
    )

    if failures:
        print(json.dumps({"status": "fail_closed", "failures": failures, "gates": gates}, indent=2))
        raise SystemExit(1)

    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "sdf_native_w1g_gpu_gridsdf",
        "gate_id": json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))["gate_id"],
        "evidence_class": "contract_and_numerical",
        "immutable": True,
        "solver_started": False,
        "existing_evidence_modified": False,
        "generated_on": {
            "platform": "Colab T4 runtime (Linux x86_64) driven through the colab-mcp browser connection",
            "recording_host": platform.platform(),
            "python": sys.version.split()[0],
        },
        "registered_criteria": {
            "path": CRITERIA_PATH.relative_to(ROOT).as_posix(),
            "sha256": criteria_sha,
        },
        "inputs": {
            "w0b_result": {
                "path": W0B_RESULT.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(W0B_RESULT),
            },
            "w2a_result": {
                "path": W2A_RESULT.relative_to(ROOT).as_posix(),
                "sha256": W2A_RESULT_SHA256,
            },
        },
        "fixture_summary": summary,
        "backend_identity_check": identity_check,
        "artifacts": {
            "fixture_stdout": {
                "path": RUN_STDOUT.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(RUN_STDOUT),
            }
        },
        "gates": gates,
        "verdict": {
            "w1g_qualified": True,
            "fail_closed": False,
        },
        "claims_supported": [
            "the device GridSDF is a derived copy whose read-back sha256 equals the canonical CPU phi sha256",
            "the WaterLily body measurement path executes inside a CUDA kernel for all registered probes with no scalar fallback",
            "CPU/GPU geometry value, normal, sign classification and outside extension agree within the registered tolerances"
        ],
        "claims_not_supported": [
            "no CFD time step or force value (W2-T4b)",
            "no SDF gradient, reverse-mode or Enzyme capability",
            "no v16 geometry, topology or optimizer claim",
            "no change to the CPU-qualified W1 semantics or evidence"
        ],
        "flags": {
            "shape_update_allowed": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
        },
    }
    payload = (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    _write_immutable(EVIDENCE_PATH, payload)
    sidecar = EVIDENCE_PATH.with_suffix(EVIDENCE_PATH.suffix + ".sha256")
    digest = _sha256_path(EVIDENCE_PATH)
    if sidecar.exists() and sidecar.read_text().strip() != digest:
        raise SystemExit("W1g evidence sidecar mismatch")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))
    print(json.dumps({
        "status": "registered",
        "gate_id": document["gate_id"],
        "max_value_error_world_m": summary["max_value_error_world_m"],
        "max_normal_error": summary["max_normal_error"],
        "sign_violations": summary["sign_violations"],
        "outside_exact": summary["outside_exact"],
        "probe_count": summary["probe_count"],
        "gates_passed": len(gates),
        "evidence": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "evidence_sha256": digest,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
