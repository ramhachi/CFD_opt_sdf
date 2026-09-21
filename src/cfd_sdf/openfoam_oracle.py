"""Real OpenFOAM oracle for the Stage T loop (PQ0.2 smoke).

Two solver invocations are distinguished:

- **parent**: one qualified full-template run per accepted parent. It produces
  the primal values *and* the adjoint fields; the gradient is then extracted
  from the same artifact (no second solver run, no duplicate primal). The loop
  reaches this through the optional ``evaluate_parent`` fast path.
- **trial**: a primal-only run with the adjoint solvers deactivated, used for
  trial values and for the Path B bracket.

The canonical design is ``rho_design``; the solver sees
``beta = transform.forward(rho).beta``; the source contract receives
``P @ beta``. Gradients are reconstructed from ``topOSens<solver>`` and mapped
to the canonical beta space with ``P.T`` before the compiled oracle pulls them
back to the design space.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .design_transform import DesignTransform, DesignTransformState
from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE, run_openfoam_case
from .fixed_grid_canonical_state_injection import (
    inject_canonical_state_into_fixed_grid_contract,
)
from .fixed_grid_primal import (
    load_fixed_grid_density_state,
    prepare_fixed_grid_primal_case,
    summarize_fixed_grid_primal_case,
)
from .openfoam_field_reconstruction import reconstruct_final_decomposed_openfoam_fields
from .openfoam_grid_transfer import ExactCartesianOverlapTransfer, UniformCartesianCellGrid


class OpenFoamOracleError(RuntimeError):
    """Fail-closed OpenFOAM oracle contract violation."""


def array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values))
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)},
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


def write_candidate_sidecar(
    base_provenance: dict[str, Any],
    rho_xfastest: np.ndarray,
    mapping: np.ndarray,
    *,
    npz_path: Path,
    provenance_path: Path,
) -> None:
    """Write a state NPZ with its own provenance sidecar (fail-closed pair)."""

    rho_global = np.empty_like(rho_xfastest)
    rho_global[mapping] = rho_xfastest
    np.savez(
        npz_path,
        source_rho_xfastest=rho_xfastest,
        source_rho_global_label=rho_global,
        source_global_cell_labels_by_xfastest=mapping.astype(np.int64),
    )
    provenance = copy.deepcopy(base_provenance)
    provenance["artifact_file"] = {
        "path": str(npz_path),
        "sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest(),
    }
    exported = provenance.get("exported_arrays")
    if not isinstance(exported, dict):
        raise OpenFoamOracleError("base provenance is missing exported_arrays")
    for name, record in exported.items():
        if name == "source_rho_xfastest":
            record["sha256"] = array_sha256(rho_xfastest)
            record["cell_count"] = int(rho_xfastest.size)
            record["range"] = [float(rho_xfastest.min()), float(rho_xfastest.max())]
        elif name == "source_rho_global_label":
            record["sha256"] = array_sha256(rho_global)
            record["cell_count"] = int(rho_global.size)
        elif name == "source_global_cell_labels_by_xfastest":
            expected = array_sha256(mapping.astype(np.int64))
            if record.get("sha256") != expected:
                raise OpenFoamOracleError(
                    "base provenance cell-order hash does not match the loaded mapping"
                )
        else:
            raise OpenFoamOracleError(f"unexpected exported array: {name}")
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class OpenFoamOracleConfig:
    work_root: Path
    canonical_topology_state_json: Path
    template_parent: Path
    template_trial: Path
    flow_case_id: str
    responses: tuple[str, ...]
    run_root: Path
    adjoint_solver_id: str = "downforce"
    timeout_seconds: int = 3600
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE


class OpenFoamOracle:
    """Split primal/adjoint evaluator for the reduced Stage T problem."""

    def __init__(self, config: OpenFoamOracleConfig, transform: DesignTransform) -> None:
        self.config = config
        self.transform = transform
        provenance_path = config.work_root / "source_state" / "provenance.json"
        self.provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        source = self.provenance["source"]
        target = self.provenance["target"]
        self.transfer = ExactCartesianOverlapTransfer.build(
            source_grid=UniformCartesianCellGrid(
                origin=source["origin"], spacing=source["spacing"], cell_shape=source["cell_shape"]
            ),
            target_grid=UniformCartesianCellGrid(
                origin=target["origin"], spacing=target["spacing"], cell_shape=target["cell_shape"]
            ),
        )
        self.mapping = np.load(
            config.work_root / "cell_order" / "source_global_cell_labels_by_xfastest.npy",
            allow_pickle=False,
        ).astype(np.int64)
        state = load_fixed_grid_density_state(config.canonical_topology_state_json)
        self.canonical_rho = np.asarray(state.arrays["rho"], dtype=np.float64)
        self.run_root.mkdir(parents=True, exist_ok=True)

    @property
    def run_root(self) -> Path:
        return self.config.run_root

    def _base_contract(self) -> Path:
        return self.config.work_root / "injected_contract" / "topology_state.json"

    def _values_from_summary(self, summary: dict[str, Any]) -> dict[tuple[str, str], float]:
        values: dict[tuple[str, str], float] = {}
        for response in self.config.responses:
            key = f"{response}_coefficient"
            value = summary.get(key)
            if value is None:
                raise OpenFoamOracleError(
                    f"primal summary is missing response {response!r} ({key})"
                )
            values[(self.config.flow_case_id, response)] = float(value)
        return values

    def _run_state(
        self,
        state: DesignTransformState,
        *,
        tag: str,
        template: Path,
        require_adjoint: bool,
    ) -> dict[str, Any]:
        source_rho = self.transfer.transfer_state_to_source(
            np.asarray(state.beta, dtype=np.float64)
        )
        run_dir = self.run_root / tag
        summary_path = run_dir / "case" / "fixed_grid_primal_summary.json"
        if run_dir.exists():
            if not summary_path.is_file():
                raise OpenFoamOracleError(
                    f"{run_dir} exists without a completed summary; refusing to reuse"
                )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            convergence = summary.get("convergence") or {}
            if require_adjoint and not bool(convergence.get("downforce_adjoint_converged")):
                raise OpenFoamOracleError(f"{tag}: cached run lacks a converged adjoint")
            return {
                "case_dir": str(run_dir / "case"),
                "contract_dir": str(run_dir / "contract"),
                "summary_json": str(summary_path),
                "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                "source_rho_sha256": array_sha256(source_rho),
                "primal_iterations": convergence.get("primal_iterations"),
                "adjoint_iterations": convergence.get("downforce_adjoint_iterations"),
                "summary": summary,
                "reused": True,
            }
        run_dir.mkdir(parents=True)
        npz_path = run_dir / "perturbed_source_state.npz"
        provenance_path = run_dir / "perturbed_source_state.provenance.json"
        write_candidate_sidecar(
            self.provenance,
            source_rho,
            self.mapping,
            npz_path=npz_path,
            provenance_path=provenance_path,
        )
        contract = inject_canonical_state_into_fixed_grid_contract(
            openfoam_source_state_npz=npz_path,
            source_state_provenance_json=provenance_path,
            topology_state_json=self._base_contract(),
            output_directory=run_dir / "contract",
        )
        prepared = prepare_fixed_grid_primal_case(
            contract.topology_state_json,
            case_dir=run_dir / "case",
            template_case_dir=template,
            density_variant="seed",
        )
        run_result = run_openfoam_case(
            prepared.case_dir,
            backend="auto",
            dry_run=False,
            timeout_seconds=self.config.timeout_seconds,
            docker_image=self.config.docker_image,
        )
        summary = summarize_fixed_grid_primal_case(
            prepared.case_dir,
            topology_state_json=prepared.topology_state_json,
            run_result=run_result.to_dict(),
            docker_image=self.config.docker_image,
        )
        convergence = summary.get("convergence") or {}
        if not bool(convergence.get("primal_converged")):
            raise OpenFoamOracleError(
                f"{tag}: primal did not converge; the run is not usable as an artifact"
            )
        if require_adjoint and not bool(convergence.get("downforce_adjoint_converged")):
            raise OpenFoamOracleError(
                f"{tag}: adjoint did not converge; parent gradients are fail-closed"
            )
        summary_path = prepared.case_dir / "fixed_grid_primal_summary.json"
        return {
            "case_dir": str(prepared.case_dir),
            "contract_dir": str(contract.directory),
            "summary_json": str(summary_path),
            "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            "source_rho_sha256": array_sha256(source_rho),
            "primal_iterations": convergence.get("primal_iterations"),
            "adjoint_iterations": convergence.get("downforce_adjoint_iterations"),
            "summary": summary,
        }

    def _reconstruct_gradients(self, artifact: dict[str, Any]) -> dict[tuple[str, str], np.ndarray]:
        case_dir = Path(artifact["case_dir"])
        reconstructed = reconstruct_final_decomposed_openfoam_fields(
            case_dir,
            adjoint_solver_id=self.config.adjoint_solver_id,
            allow_identity_profile=True,
        )
        labels = np.asarray(reconstructed.global_cell_labels)
        sensitivity_global = np.asarray(reconstructed.top_o_sensitivity)
        sensitivity_xfastest = np.empty_like(sensitivity_global)
        sensitivity_xfastest[labels] = sensitivity_global
        canonical_sensitivity = self.transfer.transfer_gradient_to_target(
            sensitivity_xfastest
        )
        return {
            (self.config.flow_case_id, self.config.adjoint_solver_id): canonical_sensitivity
        }

    # --- evaluator callbacks consumed by make_oracle_from_compiled -------------

    def primal_evaluator(self, state: DesignTransformState) -> dict[str, Any]:
        artifact = self._run_state(
            state,
            tag=f"trial_{array_sha256(np.asarray(state.beta))[:12]}",
            template=self.config.template_trial,
            require_adjoint=False,
        )
        return {
            "values": self._values_from_summary(artifact["summary"]),
            "primal_converged": True,
            "solver_status": str(artifact["summary"].get("status")),
            "response_hash": artifact["summary_sha256"],
            "artifact": artifact,
        }

    def parent_evaluator(self, state: DesignTransformState) -> dict[str, Any]:
        artifact = self._run_state(
            state,
            tag=f"parent_{array_sha256(np.asarray(state.beta))[:12]}",
            template=self.config.template_parent,
            require_adjoint=True,
        )
        return {
            "values": self._values_from_summary(artifact["summary"]),
            "gradients": self._reconstruct_gradients(artifact),
            "adjoint_converged": True,
            "primal_converged": True,
            "solver_status": str(artifact["summary"].get("status")),
            "response_hash": artifact["summary_sha256"],
            "artifact": artifact,
        }

    def adjoint_evaluator(
        self, state: DesignTransformState, primal_artifact: dict[str, Any]
    ) -> dict[str, Any]:
        """Pure-path adjoint: extraction only, from the accepted artifact."""

        artifact = primal_artifact.get("artifact")
        if not isinstance(artifact, dict):
            raise OpenFoamOracleError(
                "adjoint evaluation requires the accepted primal artifact"
            )
        return {
            "gradients": self._reconstruct_gradients(artifact),
            "adjoint_converged": True,
        }


__all__ = [
    "OpenFoamOracle",
    "OpenFoamOracleConfig",
    "OpenFoamOracleError",
    "array_sha256",
    "write_candidate_sidecar",
]
