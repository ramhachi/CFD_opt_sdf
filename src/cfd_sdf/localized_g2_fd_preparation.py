"""Prepare, but never execute, localized G2 finite-difference cases.

The independent variable is the canonical localized ``rho_raw`` vector.  A
prepared directory is immutable evidence for a later execution/validation
step: it contains no OpenFOAM result and deliberately makes no FD claim.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal, Sequence

import numpy as np

from .localized_alpha_reference_binding import (
    load_and_verify_localized_alpha_reference_binding,
    calculate_localized_alpha_source,
)
from .localized_design_state_manifest import (
    LocalizedDesignStateManifest,
    create_localized_design_state_manifest,
    localized_design_state_manifest_sha256,
    read_localized_design_state_manifest,
    write_localized_design_state_manifest,
)
from .localized_design_transfer import LocalizedDesignToCfdTransfer
from .localized_filter_projection import (
    apply_localized_heaviside_projection,
    read_canonical_filter_config,
    read_canonical_projection_config,
    topology_solid_mask,
    write_localized_cone_filtered_npy,
)
from .localized_openfoam_alpha_case import stage_localized_openfoam_alpha_case
from .localized_reference_state_bundle import (
    LOCALIZED_REFERENCE_STATE_FILENAME,
    LocalizedReferenceStateBundle,
    verify_localized_reference_state_bundle,
)
from .localized_reference_topology import (
    LOCALIZED_REFERENCE_TOPOLOGY_KIND,
    LOCALIZED_REFERENCE_TOPOLOGY_SCHEMA_VERSION,
)
from .problem_spec import ProblemSpec, load_problem_spec, problem_spec_sha256


LOCALIZED_G2_FD_PREPARATION_SCHEMA_VERSION = 1
LOCALIZED_G2_FD_PREPARATION_KIND = "localized_g2_openfoam_fd_preparation"
LOCALIZED_G2_FD_PREPARATION_FILENAME = "localized_g2_openfoam_fd_preparation.json"


@dataclass(frozen=True)
class LocalizedG2FdPreparation:
    """A fully staged direction experiment, with execution explicitly absent."""

    path: Path
    report_json: Path
    status: str
    mode: str
    epsilon_ladder: tuple[float, float, float]
    plus_hmax: float
    minus_hmax: float
    cases: tuple[Path, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["path"] = str(self.path)
        data["report_json"] = str(self.report_json)
        data["epsilon_ladder"] = list(self.epsilon_ladder)
        data["cases"] = [str(item) for item in self.cases]
        return data


def prepare_localized_g2_openfoam_fd_direction(
    problem: ProblemSpec | str | Path,
    *,
    reference_bundle_path: str | Path,
    topology_report_path: str | Path,
    alpha_reference_binding_path: str | Path,
    compiled_case_dir: str | Path,
    direction: np.ndarray | str | Path,
    epsilon_ladder: Sequence[float],
    output_dir: str | Path,
    mode: Literal["one_sided", "central"] = "one_sided",
) -> LocalizedG2FdPreparation:
    """Atomically stage a local raw-density FD direction without running it.

    The fixed protocol accepts exactly ``[h, h/2, h/4]``.  ``central`` is
    accepted only when every requested negative raw perturbation is feasible;
    no density or alpha clipping is ever applied.
    """

    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    if not isinstance(spec, ProblemSpec):
        raise ValueError("problem must be a ProblemSpec or project YAML path")
    if mode not in {"one_sided", "central"}:
        raise ValueError("mode must be 'one_sided' or 'central'")
    ladder = _validate_epsilon_ladder(epsilon_ladder)
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite localized G2 FD preparation: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    bundle = verify_localized_reference_state_bundle(reference_bundle_path, problem=spec)
    reference_state = read_localized_design_state_manifest(bundle.path / "localized_design_state_manifest.json")
    _require_success_topology_report(topology_report_path, bundle=bundle, state=reference_state, spec=spec)
    binding = load_and_verify_localized_alpha_reference_binding(
        alpha_reference_binding_path, expected_problem_spec_sha256=problem_spec_sha256(spec)
    )
    if binding.reference_state.manifest.sha256 != bundle.state_manifest_sha256:
        raise ValueError("alpha reference binding does not bind the verified reference bundle state")
    if binding.reference_state.manifest.states["rho_projected"].byte_sha256 != reference_state.states["rho_projected"].byte_sha256:
        raise ValueError("alpha reference binding projected-state hash does not match reference bundle")

    masks = _load_masks(reference_state)
    raw = _load_state(reference_state, "rho")
    try:
        vector, direction_sha = _load_direction(direction, reference_state.grid.cell_count)
        _validate_direction(vector, masks)
        plus_hmax, minus_hmax = _raw_hmax(raw, vector, masks["active_design_mask"])
        if ladder[0] > plus_hmax:
            raise ValueError(f"epsilon h={ladder[0]:.17g} exceeds positive raw feasibility hmax={plus_hmax:.17g}")
        if mode == "central" and ladder[0] > minus_hmax:
            raise ValueError(f"epsilon h={ladder[0]:.17g} exceeds negative raw feasibility hmax={minus_hmax:.17g}")
        reference_predicate = topology_solid_mask(
            _load_state(reference_state, "rho_projected"), masks["active_design_mask"]
        )
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
        try:
            _copy_shared_contract(staging, reference_state)
            prepared_direction_path = staging / "direction.npy"
            np.save(prepared_direction_path, vector, allow_pickle=False)
            transfer = LocalizedDesignToCfdTransfer.build(
                cfd_grid=binding.binding.cfd_grid, design_grid=reference_state.grid
            )
            staged: dict[str, dict[str, Any]] = {}
            # A baseline case is staged explicitly, even though its alpha is the
            # binding's reference alpha; this prevents stale solver output from
            # masquerading as a baseline on the later execute step.
            baseline_source = calculate_localized_alpha_source(
                binding=binding, current_state=binding.reference_state, transfer=transfer
            )
            baseline_case = stage_localized_openfoam_alpha_case(
                compiled_case_dir=compiled_case_dir,
                output_case_dir=staging / "cases" / "reference",
                alpha_source=baseline_source,
                verified_alpha_binding=binding,
            )
            staged["reference"] = {
                "state_manifest_sha256": bundle.state_manifest_sha256,
                "case_relative_path": "cases/reference",
                "case_manifest_sha256": _sha256_file(baseline_case.manifest_json),
                "alpha_values_sha256": baseline_case.alpha_values_sha256,
            }
            for sign, allowed in (("plus", True), ("minus", mode == "central")):
                if not allowed:
                    continue
                for epsilon in ladder:
                    label = _label(sign, epsilon)
                    state = _materialize_perturbed_state(
                        root=staging,
                        label=label,
                        reference_state=reference_state,
                        active=masks["active_design_mask"],
                        raw=raw,
                        direction=vector,
                        epsilon=epsilon if sign == "plus" else -epsilon,
                    )
                    projected = _load_state(state, "rho_projected")
                    try:
                        if not np.array_equal(
                            topology_solid_mask(projected, masks["active_design_mask"]), reference_predicate
                        ):
                            raise ValueError(
                                f"topology predicate changes for {sign} perturbation at epsilon={epsilon:.17g}"
                            )
                    finally:
                        del projected
                    source = calculate_localized_alpha_source(binding=binding, current_state=state, transfer=transfer)
                    case = stage_localized_openfoam_alpha_case(
                        compiled_case_dir=compiled_case_dir,
                        output_case_dir=staging / "cases" / label,
                        alpha_source=source,
                        verified_alpha_binding=binding,
                    )
                    staged[label] = {
                        "sign": sign,
                        "epsilon": epsilon,
                        "state_manifest_relative_path": state.path.relative_to(staging).as_posix(),
                        "state_manifest_sha256": localized_design_state_manifest_sha256(state),
                        "rho_raw_sha256": state.states["rho"].byte_sha256,
                        "rho_filtered_sha256": state.states["rho_filtered"].byte_sha256,
                        "rho_projected_sha256": state.states["rho_projected"].byte_sha256,
                        "case_relative_path": case.case_dir.relative_to(staging).as_posix(),
                        "case_manifest_sha256": _sha256_file(case.manifest_json),
                        "alpha_values_sha256": case.alpha_values_sha256,
                    }
            status = "prepared_central" if mode == "central" else "prepared_one_sided"
            report = _report(
                spec=spec, bundle=bundle, reference_state=reference_state,
                topology_report_path=topology_report_path, binding_path=alpha_reference_binding_path,
                binding_sha256=binding.binding.sha256, compiled_case_dir=compiled_case_dir,
                direction_sha256=direction_sha, prepared_direction_sha256=_sha256_file(prepared_direction_path),
                epsilon_ladder=ladder, mode=mode,
                plus_hmax=plus_hmax, minus_hmax=minus_hmax, status=status, staged=staged,
            )
            _write_json(staging / LOCALIZED_G2_FD_PREPARATION_FILENAME, report)
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    finally:
        del raw

    cases = tuple(destination / str(item["case_relative_path"]) for item in staged.values())
    return LocalizedG2FdPreparation(
        path=destination,
        report_json=destination / LOCALIZED_G2_FD_PREPARATION_FILENAME,
        status=status,
        mode=mode,
        epsilon_ladder=ladder,
        plus_hmax=plus_hmax,
        minus_hmax=minus_hmax,
        cases=cases,
    )


def _materialize_perturbed_state(*, root: Path, label: str, reference_state: LocalizedDesignStateManifest,
                                  active: np.ndarray, raw: np.ndarray, direction: np.ndarray, epsilon: float) -> LocalizedDesignStateManifest:
    state_dir = root / "states" / label
    state_dir.mkdir(parents=True, exist_ok=False)
    candidate = np.asarray(raw + epsilon * direction, dtype=np.float64)
    if not np.isfinite(candidate).all() or np.any(candidate[active] < 0.0) or np.any(candidate[active] > 1.0) or np.any(candidate[~active] != 0.0):
        raise ValueError("raw perturbation is infeasible without clipping")
    raw_path = state_dir / "rho_raw.npy"
    np.save(raw_path, candidate, allow_pickle=False)
    filter_config = read_canonical_filter_config(root / "configs" / "filter_config.json")
    projection_config = read_canonical_projection_config(root / "configs" / "projection_config.json")
    filtered_path = write_localized_cone_filtered_npy(
        candidate, active, reference_state.grid, output_path=state_dir / "rho_filtered.npy", config=filter_config
    )
    filtered = np.load(filtered_path, mmap_mode="r", allow_pickle=False)
    projected_path = state_dir / "rho_projected.npy"
    projected = np.lib.format.open_memmap(projected_path, mode="w+", dtype=np.float64, shape=(reference_state.grid.cell_count,))
    try:
        apply_localized_heaviside_projection(filtered, active, config=projection_config, out=projected)
        projected.flush()
    finally:
        del projected
        del filtered
    manifest = create_localized_design_state_manifest(
        path=root / f"{label}_state_manifest.json",
        problem_spec_sha256=reference_state.problem_spec_sha256,
        grid=reference_state.grid,
        masks={name: root / "masks" / f"{name}.npy" for name in reference_state.masks},
        states={"rho": raw_path, "rho_filtered": filtered_path, "rho_projected": projected_path},
        filter_config_sha256=reference_state.filter_config_sha256,
        projection_config_sha256=reference_state.projection_config_sha256,
        filter_config_path=root / "configs" / "filter_config.json",
        projection_config_path=root / "configs" / "projection_config.json",
    )
    write_localized_design_state_manifest(manifest)
    return manifest


def _copy_shared_contract(root: Path, state: LocalizedDesignStateManifest) -> None:
    for name, artifact in state.masks.items():
        source = state.path.parent / artifact.relative_path
        destination = root / "masks" / f"{name}.npy"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if _sha256_file(destination) != artifact.byte_sha256:
            raise ValueError(f"copied {name} mask hash mismatch")
    assert state.filter_config is not None and state.projection_config is not None
    for name, artifact in (("filter", state.filter_config), ("projection", state.projection_config)):
        source = state.path.parent / artifact.relative_path
        destination = root / "configs" / f"{name}_config.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if _sha256_file(destination) != artifact.byte_sha256:
            raise ValueError(f"copied {name} config hash mismatch")


def _load_masks(state: LocalizedDesignStateManifest) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    for name, artifact in state.masks.items():
        values = np.load(state.path.parent / artifact.relative_path, mmap_mode="r", allow_pickle=False)
        if values.dtype != np.dtype(np.bool_) or values.shape != (state.grid.cell_count,):
            raise ValueError(f"reference {name} layout is invalid")
        result[name] = values
    return result


def _load_state(state: LocalizedDesignStateManifest, name: str) -> np.ndarray:
    artifact = state.states[name]
    values = np.load(state.path.parent / artifact.relative_path, mmap_mode="r", allow_pickle=False)
    if values.dtype != np.dtype(np.float64) or values.shape != (state.grid.cell_count,):
        raise ValueError(f"reference {name} layout is invalid")
    return values


def _load_direction(value: np.ndarray | str | Path, count: int) -> tuple[np.ndarray, str]:
    if isinstance(value, (str, Path)):
        path = Path(value)
        vector = np.load(path, allow_pickle=False)
        source_hash = _sha256_file(path)
    else:
        vector = value
        if not isinstance(vector, np.ndarray):
            raise ValueError("direction must be a float64 NPY vector or ndarray")
        source_hash = _sha256_array(vector)
    if not isinstance(vector, np.ndarray) or vector.dtype != np.dtype(np.float64) or not vector.dtype.isnative or vector.ndim != 1 or vector.shape != (count,):
        raise ValueError("direction must be a one-dimensional native float64 vector on the canonical x-fastest grid")
    return np.ascontiguousarray(vector), source_hash


def _validate_direction(direction: np.ndarray, masks: dict[str, np.ndarray]) -> None:
    active = masks["active_design_mask"]
    if not np.isfinite(direction).all() or not np.any(direction):
        raise ValueError("direction must be finite and nonzero")
    if np.any(direction[~active] != 0.0):
        raise ValueError("direction must be exactly zero outside active_design_mask")
    for name in ("fixed_solid_mask", "root_mask", "forbidden_mask"):
        if np.any(direction[masks[name]] != 0.0):
            raise ValueError(f"direction must be exactly zero on {name}")
    if float(np.max(np.abs(direction))) != 1.0:
        raise ValueError("direction must use declared L-infinity normalization (max(abs(direction)) == 1)")


def _raw_hmax(raw: np.ndarray, direction: np.ndarray, active: np.ndarray) -> tuple[float, float]:
    plus_terms = np.full(raw.shape, np.inf, dtype=np.float64)
    minus_terms = np.full(raw.shape, np.inf, dtype=np.float64)
    positive = direction > 0.0
    negative = direction < 0.0
    plus_terms[positive] = (1.0 - raw[positive]) / direction[positive]
    plus_terms[negative] = raw[negative] / -direction[negative]
    minus_terms[positive] = raw[positive] / direction[positive]
    minus_terms[negative] = (1.0 - raw[negative]) / -direction[negative]
    return float(np.min(plus_terms[active])), float(np.min(minus_terms[active]))


def _validate_epsilon_ladder(values: Sequence[float]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise ValueError("epsilon_ladder must contain exactly [h, h/2, h/4]")
    result = tuple(float(item) for item in values)
    if not all(np.isfinite(item) and item > 0.0 for item in result):
        raise ValueError("epsilon_ladder values must be positive finite numbers")
    if result[1] != result[0] / 2.0 or result[2] != result[0] / 4.0:
        raise ValueError("epsilon_ladder must be exactly [h, h/2, h/4]")
    return result  # type: ignore[return-value]


def _require_success_topology_report(path: str | Path, *, bundle: LocalizedReferenceStateBundle,
                                     state: LocalizedDesignStateManifest, spec: ProblemSpec) -> None:
    target = Path(path).resolve()
    try:
        report = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read localized topology report: {target}") from exc
    if not isinstance(report, dict) or report.get("schema_version") != LOCALIZED_REFERENCE_TOPOLOGY_SCHEMA_VERSION or report.get("kind") != LOCALIZED_REFERENCE_TOPOLOGY_KIND:
        raise ValueError("localized topology report has unsupported schema")
    if report.get("status") != "success":
        raise ValueError("localized topology report must have status='success'")
    if report.get("problem_spec_sha256") != problem_spec_sha256(spec) or report.get("grid_sha256") != state.grid_sha256:
        raise ValueError("localized topology report project or grid binding mismatch")
    if report.get("reference_state_manifest_sha256") != bundle.state_manifest_sha256 or report.get("rho_projected_sha256") != state.states["rho_projected"].byte_sha256:
        raise ValueError("localized topology report state binding mismatch")
    if (report.get("reference_bundle_geometry_snapshot_sha256") != bundle.geometry_snapshot.sha256
            or report.get("reference_bundle_raw_manifest_sha256") != bundle.raw_manifest_sha256
            or report.get("initial_design_stl_sha256") != bundle.initial_design_stl_sha256):
        raise ValueError("localized topology report exact-bundle provenance mismatch")
    try:
        report_bundle = Path(str(report["reference_bundle_path"])).resolve()
    except (KeyError, TypeError) as exc:
        raise ValueError("localized topology report bundle path is invalid") from exc
    if report_bundle != bundle.path.resolve():
        raise ValueError("localized topology report does not bind the exact reference bundle path")


def _report(*, spec: ProblemSpec, bundle: LocalizedReferenceStateBundle, reference_state: LocalizedDesignStateManifest,
            topology_report_path: str | Path, binding_path: str | Path, binding_sha256: str, compiled_case_dir: str | Path,
            direction_sha256: str, prepared_direction_sha256: str, epsilon_ladder: tuple[float, float, float], mode: str, plus_hmax: float,
            minus_hmax: float, status: str, staged: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": LOCALIZED_G2_FD_PREPARATION_SCHEMA_VERSION,
        "kind": LOCALIZED_G2_FD_PREPARATION_KIND,
        "status": status,
        "execution_status": "not_run",
        "validation_status": "not_run",
        "independent_variable": "rho_raw",
        "raw_chain_rule": "rho_raw -> active_cone_filter -> tanh_heaviside_projection -> E -> alpha",
        "mode": mode,
        "epsilon_ladder": list(epsilon_ladder),
        "raw_feasibility": {"plus_hmax": plus_hmax, "minus_hmax": minus_hmax, "clipping": "forbidden"},
        "topology_stability": {"operator": "rho_projected >= 0.5", "all_prepared_perturbations_unchanged": True},
        "provenance": {
            "problem_spec_sha256": problem_spec_sha256(spec),
            "reference_bundle_path": str(bundle.path),
            "reference_bundle_ledger_sha256": _sha256_file(bundle.path / LOCALIZED_REFERENCE_STATE_FILENAME),
            "reference_state_manifest_sha256": bundle.state_manifest_sha256,
            "reference_rho_projected_sha256": reference_state.states["rho_projected"].byte_sha256,
            "topology_report_path": str(Path(topology_report_path).resolve()),
            "topology_report_sha256": _sha256_file(Path(topology_report_path)),
            "alpha_reference_binding_path": str(Path(binding_path).resolve()),
            "alpha_reference_binding_sha256": binding_sha256,
            "compiled_case_dir": str(Path(compiled_case_dir).resolve()),
            "direction_input_sha256": direction_sha256,
            "prepared_direction_npy_sha256": prepared_direction_sha256,
            "direction_normalization": "L_infinity_exactly_1",
        },
        "cases": dict(sorted(staged.items())),
        "validation_protocol": {
            "baseline_repeats_minimum": 2,
            "ladder": "h,h/2,h/4",
            "noise_model": {
                "independent_fresh_runs": True,
                "per_run_response_noise": "homoskedastic_assumed",
                "sigmaJ_estimator": "baseline sample standard deviation with scale floor",
                "limitation": "perturbation-state noise is not independently replicated",
            },
            "baseline_statistics": "Jbar0=mean(J0); sJ=sample_standard_deviation(J0)",
            "scale_and_noise": "Jscale=max(rms(J0),max_k(abs(Jk-Jbar0))); sigmaJ=max(sJ,1e-12*Jscale)",
            "derivative_noise": "sigmaD,k=sigmaJ*sqrt(1+1/n0)/hk",
            "snr": "abs(Jk-Jbar0)/(sigmaJ*sqrt(1+1/n0)) >= 10",
            "adjacent_stability": "Mstab=abs(Dk-Dc)/(0.05*max(abs(Dk),abs(Dc))+2*sigmaDelta) <= 1; sigmaDelta=sigmaJ*sqrt(1/hk^2+1/hc^2+(1/hc-1/hk)^2/n0), hc=2*hk",
            "central_derivative_noise": "Ck=(Jplus,k-Jminus,k)/2; Dk=Ck/hk; sigmaD,k=sigmaJ/(sqrt(2)*hk)",
            "central_snr": "abs(Ck)/(sigmaJ/sqrt(2)) >= 10",
            "central_adjacent_stability": "Mstab=abs(Dk-Dc)/(0.05*max(abs(Dk),abs(Dc))+2*sigmaDelta) <= 1; sigmaDelta=sigmaJ/sqrt(2)*sqrt(1/hk^2+1/hc^2), hc=2*hk",
            "selection": "smallest of h/2,h/4 meeting its and coarse-neighbor SNR/stability; otherwise fd_ladder_unqualified",
            "final_gate": "abs(Dfd),abs(Dadj)>=5*sigmaD; equal nonzero signs; relative_error<=0.10; absolute_error<=5*sigmaD",
        },
        "limitations": [
            "prepared_cases_are_not_openfoam_execution_results",
            "no_fd_derivative_or_adjoint_comparison_has_run",
            "only_discrete_topology_predicate_stability_is_checked",
            "does_not_qualify_native_v2_or_continuous_manufacturability",
        ],
    }


def _label(sign: str, epsilon: float) -> str:
    return f"{sign}_h{epsilon:.17g}".replace("+", "p").replace("-", "m")


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_array(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")


__all__ = [
    "LOCALIZED_G2_FD_PREPARATION_FILENAME", "LOCALIZED_G2_FD_PREPARATION_KIND",
    "LOCALIZED_G2_FD_PREPARATION_SCHEMA_VERSION", "LocalizedG2FdPreparation",
    "prepare_localized_g2_openfoam_fd_direction",
]
