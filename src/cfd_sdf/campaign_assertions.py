"""Fail-closed assertions for the PQ3.3b campaign runner (manifest v3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

REQUIRED_MANIFEST_HASH_FIELDS: tuple[str, ...] = (
    "input_checkpoint",
    "problem_spec",
    "compiled_problem_hash",
    "canonical_grid",
    "openfoam_image",
    "template_tree_hash",
    "solver_controls_hash",
    "filter_radius_m",
    "registered_target",
    "v_max_projected",
    "b_q_schedule",
    "move_limit",
    "objective_alpha_ladder",
    "volume_tolerance",
    "path_b_epsilon",
    "noise_calibration",
    "iteration_bounds",
    "convergence_thresholds",
    "reject_stop_count",
    "checkpoint_resume_rule",
    "fresh_output_rule",
    "preflight_v4",
    "state_lineage",
)

ALLOWED_PHASE1_BACKENDS = ("projected-volume-restoration-oc",)
ALLOWED_PHASE2_BACKENDS = ("volume-corrected-objective-oc",)
FORBIDDEN_BACKENDS = ("volume-target-oc", "projected-volume-target-oc")

STATUS_AWAITING_GO = "registered_preflight_pass_awaiting_user_go"
STATUS_BLOCKED = "registered_blocked"


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compiled_problem_sha256(compiled) -> str:
    """Hash the compiled algebra and declared volume budget, not a placeholder."""
    payload = json.dumps(asdict(compiled), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tree_sha256(root) -> str:
    """Deterministic hash over a template directory tree."""
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        if path.is_file():
            digest.update(
                hashlib.sha256(path.read_bytes()).hexdigest().encode("utf-8")
            )
    return digest.hexdigest()


def python_source_tree_sha256(root) -> str:
    """Hash source code without generated __pycache__ and bytecode files."""
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def manifest_sha_of(manifest_path) -> str:
    return sha256_file(manifest_path)


def assert_manifest_complete(manifest: dict[str, Any]) -> None:
    for key in REQUIRED_MANIFEST_HASH_FIELDS:
        value = manifest.get(key)
        if value is None or (isinstance(value, (str, int, float)) and value == ""):
            raise ValueError(f"manifest v3 is missing the required field: {key}")


def assert_manifest_sha(manifest_path, expected_sha: str) -> None:
    observed = manifest_sha_of(manifest_path)
    if observed != str(expected_sha):
        raise ValueError(
            "manifest SHA-256 mismatch: registered manifest was modified after "
            "registration"
        )


def assert_preflight_v4_pass(evidence_path) -> bool:
    if not Path(evidence_path).is_file():
        raise ValueError(f"preflight v4 evidence missing: {evidence_path}")
    artifact = load_json(evidence_path)
    summary = artifact.get("summary") or {}
    if summary.get("preflight_pass") is not True:
        raise ValueError("preflight v4 did not pass; campaign start is blocked")
    return True


def assert_backend_ids(manifest: dict[str, Any]) -> None:
    phase1 = (manifest.get("phase_1_backend") or {}).get("id")
    phase2 = (manifest.get("phase_2_backend") or {}).get("id")
    if phase1 not in ALLOWED_PHASE1_BACKENDS:
        raise ValueError(
            f"Phase 1 backend {phase1!r} is not the registered restoration backend"
        )
    if phase2 not in ALLOWED_PHASE2_BACKENDS:
        raise ValueError(
            f"Phase 2 backend {phase2!r} is refused; only the registered "
            "volume-corrected objective backend is allowed"
        )


def assert_no_forbidden_backend(manifest: dict[str, Any]) -> None:
    for key in ("phase_1_backend", "phase_2_backend"):
        backend_id = (manifest.get(key) or {}).get("id")
        if backend_id in FORBIDDEN_BACKENDS:
            raise ValueError(
                f"refusing the legacy multiplicative OC backend {backend_id!r}; "
                "no silent fallback to the old backends"
            )


def assert_compiled_objective_sense(manifest: dict[str, Any]) -> None:
    objective = manifest.get("objective") or {}
    if objective.get("sense") != "maximize" or objective.get("canonical") != "J = -downforce":
        raise ValueError(
            "compiled objective sense is not the registered maximize-downforce "
            "contract; refusing to run"
        )


def assert_fresh_output_directory(path) -> None:
    if Path(path).exists():
        raise ValueError(f"output directory already exists; refusing to run: {path}")


def assert_level_exact_rho_lineage(
    previous_level_accepted_rho_sha256: str, next_level_input_rho_sha256: str
) -> None:
    if previous_level_accepted_rho_sha256 != next_level_input_rho_sha256:
        raise ValueError(
            "level lineage broken: the previous level's accepted rho does not "
            "match the next level's input rho"
        )


def assert_path_b_bracket(bracket: dict) -> bool:
    if not bool(bracket.get("ok")):
        raise ValueError(f"Path B bracket failed: {bracket.get('reason')}")
    if not (bracket.get("d_adj", 0.0) < 0.0 and bracket.get("d_fd", 0.0) < 0.0):
        raise ValueError("Path B bracket sign contracts violated")
    return True


def assert_real_trial_primal(trial_result: dict) -> dict:
    if trial_result.get("primal_converged") is not True:
        raise ValueError("real trial primal did not converge; refusing")
    return trial_result


def assert_canonical_objective_improvement(parent_objective: float, trial_objective: float, noise: float) -> bool:
    if not float(trial_objective) < float(parent_objective) - float(noise):
        raise ValueError(
            "canonical objective did not improve beyond the noise threshold"
        )
    return True


def assert_raw_downforce_improvement(parent_downforce: float, trial_downforce: float, noise: float) -> bool:
    if not float(trial_downforce) > float(parent_downforce) + float(noise):
        raise ValueError(
            "raw downforce did not improve beyond the noise threshold"
        )
    return True


def assert_projected_volume_upper_bound(phi: float, v_max: float) -> bool:
    if not float(phi) <= float(v_max):
        raise ValueError("projected volume exceeded the upper bound")
    return True


def assert_mask_invariance(drift: float) -> bool:
    if not float(drift) <= 1e-12:
        raise ValueError("mask drift violated the invariance contract")
    return True


def assert_checkpoint_resume_lineage(previous: str, current: str) -> None:
    if previous != current:
        raise ValueError("checkpoint lineage mismatch; refusing to resume")


def checkpoint_rule_note() -> str:
    return (
        "Phase 1 records restoration_feasible states only; objective_accepted "
        "requires the full Phase 2 gate set including the real trial primal, "
        "Path B bracket and downforce improvement. Resume asserts the accepted "
        "rho sha256 chain."
    )





def assert_no_legacy_backend(manifest: dict[str, Any]) -> None:
    for key in ("phase_1_backend", "phase_2_backend"):
        backend_id = (manifest.get(key) or {}).get("id")
        if backend_id in FORBIDDEN_BACKENDS:
            raise ValueError(
                f"refusing the legacy multiplicative OC backend {backend_id!r}; "
                "no silent fallback to the old backends"
            )
