"""Fail-closed reconstruction of final decomposed OpenFOAM topology fields.

This reader deliberately has no mesh-coordinate or interpolation logic.  It
only restores processor-local scalar fields into ascending undecomposed cell
labels using ``cellProcAddressing``.  The resulting order is therefore an
OpenFOAM global-cell-label order, not a claim about a Cartesian/design-grid
order.  That distinction is retained in the returned provenance.

``topOSens<adjoint-solver>`` is the only sensitivity accepted as output.
Files named ``topologySens*`` are recorded as audit candidates when present,
but are never substituted: a raw-only result is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
from pathlib import Path
import re
from typing import Mapping

import numpy as np


GLOBAL_CELL_LABEL_ORDER = "openfoam-global-cell-label-ascending"
_PROCESSOR_RE = re.compile(r"^processor([0-9]+)$")
_TIME_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_OBJECT_RE = re.compile(r"\bobject\s+([^;\s]+)\s*;")
_CLASS_RE = re.compile(r"\bclass\s+([^;\s]+)\s*;")
_DIMENSIONS_RE = re.compile(r"\bdimensions\s+\[([^\]]+)\]\s*;")
_NONUNIFORM_RE = re.compile(
    r"\binternalField\s+nonuniform\s+List<scalar>\s+([0-9]+)\s*\(\s*(.*?)\s*\)\s*;",
    re.DOTALL,
)
_UNIFORM_RE = re.compile(r"\binternalField\s+uniform\s+([^;\s]+)\s*;")
# OpenFOAM v2512 writes labelList addressing files without a trailing
# semicolon, whereas scalar internalField lists retain one.  The list itself
# is still unambiguous because it follows the labelList FoamFile header.
_LABEL_LIST_RE = re.compile(r"\n\s*([0-9]+)\s*\(\s*(.*?)\s*\)\s*;?", re.DOTALL)
_TOP_OVARS_ALPHA_RE = re.compile(r"\balpha\s+uniform\s+([^;\s]+)\s*;")
_TOP_OVARS_ALPHA_NONUNIFORM_RE = re.compile(
    r"\balpha\s+nonuniform\s+List<scalar>\s+([0-9]+)\s*\(\s*(.*?)\s*\)\s*;",
    re.DOTALL,
)


@dataclass(frozen=True)
class ReconstructedOpenFoamFields:
    """Final fields reconstructed in ascending undecomposed cell-label order."""

    global_cell_labels: np.ndarray
    top_o_sensitivity: np.ndarray
    alpha_tilda: np.ndarray
    beta: np.ndarray
    raw_alpha: np.ndarray | None
    provenance: Mapping[str, object]


def reconstruct_final_decomposed_openfoam_fields(
    case_dir: str | Path,
    *,
    adjoint_solver_id: str,
    final_time: str | None = None,
) -> ReconstructedOpenFoamFields:
    """Read final G2 fields from all processors, or reject incomplete evidence.

    ``final_time`` is optional only to support an explicit audit/replay.  When
    omitted the greatest numeric time directory shared by every processor is
    selected.  ``alphaTilda``, ``beta``, and ``topOSens<adjoint_solver_id>``
    must all be nonuniform ``volScalarField`` files at that exact time.
    """

    root = Path(case_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"OpenFOAM case directory does not exist: {root}")
    if not isinstance(adjoint_solver_id, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", adjoint_solver_id):
        raise ValueError("adjoint_solver_id must be a valid OpenFOAM identifier")
    processors = _processor_dirs(root)
    selected_time = _select_final_time(processors, final_time)
    labels_by_processor, label_sources = _processor_labels(root, processors)

    final_sensitivity_name = f"topOSens{adjoint_solver_id}"
    audit_candidates = _raw_topology_sensitivity_candidates(processors, selected_time)
    try:
        top_o_sensitivity, labels, sensitivity_provenance = _reconstruct_nonuniform_field(
            root, processors, labels_by_processor, selected_time, final_sensitivity_name
        )
    except ValueError as exc:
        if audit_candidates:
            raise ValueError(
                f"Final {final_sensitivity_name!r} is required; raw topologySens audit candidates cannot substitute it"
            ) from exc
        raise
    alpha_tilda, alpha_tilda_labels, alpha_tilda_provenance = _reconstruct_nonuniform_field(
        root, processors, labels_by_processor, selected_time, "alphaTilda"
    )
    beta, beta_labels, beta_provenance = _reconstruct_nonuniform_field(
        root, processors, labels_by_processor, selected_time, "beta"
    )
    if not (np.array_equal(labels, alpha_tilda_labels) and np.array_equal(labels, beta_labels)):
        raise ValueError("Reconstructed final fields do not share the same global cell-label ordering")
    raw_alpha, raw_alpha_provenance = _reconstruct_raw_alpha(
        root, processors, labels_by_processor, selected_time
    )
    provenance: dict[str, object] = {
        "kind": "openfoam_decomposed_field_reconstruction",
        "ordering": GLOBAL_CELL_LABEL_ORDER,
        "final_time": selected_time,
        "processor_count": len(processors),
        "cell_count": int(labels.size),
        "fields": {
            "top_o_sensitivity": sensitivity_provenance,
            "alpha_tilda": alpha_tilda_provenance,
            "beta": beta_provenance,
            "raw_alpha": raw_alpha_provenance,
        },
        "cell_proc_addressing": label_sources,
        "raw_topology_sensitivity_audit_candidates": audit_candidates,
    }
    for array in (labels, top_o_sensitivity, alpha_tilda, beta):
        array.setflags(write=False)
    if raw_alpha is not None:
        raw_alpha.setflags(write=False)
    return ReconstructedOpenFoamFields(
        global_cell_labels=labels,
        top_o_sensitivity=top_o_sensitivity,
        alpha_tilda=alpha_tilda,
        beta=beta,
        raw_alpha=raw_alpha,
        provenance=provenance,
    )


def _processor_dirs(root: Path) -> list[tuple[int, Path]]:
    processors = sorted(
        (int(match.group(1)), item)
        for item in root.iterdir()
        if item.is_dir() and (match := _PROCESSOR_RE.fullmatch(item.name))
    )
    if not processors or [index for index, _ in processors] != list(range(len(processors))):
        raise ValueError("OpenFOAM processors must be contiguous processor0..processorN")
    return processors


def _select_final_time(processors: list[tuple[int, Path]], requested: str | None) -> str:
    if requested is not None:
        if not isinstance(requested, str) or not _TIME_RE.fullmatch(requested):
            raise ValueError("final_time must be a canonical non-negative numeric OpenFOAM time directory")
        if any(not (processor / requested).is_dir() for _, processor in processors):
            raise ValueError(f"final_time {requested!r} is not present on every processor")
        return requested
    common: set[str] | None = None
    for _, processor in processors:
        times = {item.name for item in processor.iterdir() if item.is_dir() and _is_numeric_time(item.name)}
        common = times if common is None else common & times
    if not common:
        raise ValueError("OpenFOAM processors have no shared numeric time directory")
    return max(common, key=_time_sort_key)


def _is_numeric_time(value: str) -> bool:
    if _TIME_RE.fullmatch(value) is None:
        return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def _time_sort_key(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # Defensive after _is_numeric_time.
        raise ValueError(f"Invalid OpenFOAM time directory: {value!r}") from exc


def _processor_labels(
    root: Path, processors: list[tuple[int, Path]]
) -> tuple[dict[int, np.ndarray], dict[str, object]]:
    labels_by_processor: dict[int, np.ndarray] = {}
    source_files: list[dict[str, object]] = []
    for index, processor in processors:
        path = _single_file(processor / "constant" / "polyMesh" / "cellProcAddressing")
        text = _read_text(path)
        _require_foam_header(text, path, expected_class="labelList", expected_object="cellProcAddressing")
        match = _LABEL_LIST_RE.search(text)
        if match is None:
            raise ValueError(f"cellProcAddressing has no label list: {path}")
        values = _numbers(match.group(2), count=int(match.group(1)), path=path, integer=True)
        labels_by_processor[index] = values.astype(np.int64, copy=False)
        source_files.append(_source_file(index, root, path))
    global_labels = np.concatenate(list(labels_by_processor.values()))
    if np.any(global_labels < 0) or np.unique(global_labels).size != global_labels.size:
        raise ValueError("cellProcAddressing must provide unique non-negative global labels")
    expected = np.arange(global_labels.size, dtype=np.int64)
    if not np.array_equal(np.sort(global_labels), expected):
        raise ValueError("cellProcAddressing must cover contiguous global labels starting at zero")
    return labels_by_processor, {
        "ordering": GLOBAL_CELL_LABEL_ORDER,
        "cell_count": int(global_labels.size),
        "source_files": source_files,
    }


def _reconstruct_nonuniform_field(
    root: Path,
    processors: list[tuple[int, Path]],
    labels_by_processor: Mapping[int, np.ndarray],
    time_name: str,
    field_name: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    entries: list[tuple[np.ndarray, np.ndarray]] = []
    dimensions: str | None = None
    source_files: list[dict[str, object]] = []
    for index, processor in processors:
        path = _single_file(processor / time_name / field_name)
        values, current_dimensions = _read_nonuniform_scalar_field(path, field_name)
        labels = labels_by_processor[index]
        if values.size != labels.size:
            raise ValueError(
                f"{field_name} on processor{index} has {values.size} values but {labels.size} cell addresses"
            )
        if dimensions is None:
            dimensions = current_dimensions
        elif dimensions != current_dimensions:
            raise ValueError(f"{field_name} has inconsistent dimensions across processors")
        entries.append((labels, values))
        source_files.append(_source_file(index, root, path))
    labels, values = _sort_by_global_labels(entries, field_name)
    return values, labels, {
        "openfoam_field_name": field_name,
        "openfoam_object": field_name,
        "openfoam_dimensions": dimensions,
        "time": time_name,
        "ordering": GLOBAL_CELL_LABEL_ORDER,
        "cell_count": int(values.size),
        "processor_count": len(processors),
        "representation": "nonuniform_volScalarField",
        "source_files": source_files,
    }


def _reconstruct_raw_alpha(
    root: Path,
    processors: list[tuple[int, Path]],
    labels_by_processor: Mapping[int, np.ndarray],
    final_time: str,
) -> tuple[np.ndarray | None, dict[str, object]]:
    final_paths = [_maybe_single_file(processor / final_time / "uniform" / "topOVars") for _, processor in processors]
    if any(path is not None for path in final_paths):
        if any(path is None for path in final_paths):
            raise ValueError("final topOVars raw alpha is present on only some processors")
        entries: list[tuple[np.ndarray, np.ndarray]] = []
        sources: list[dict[str, object]] = []
        representations: list[str] = []
        for (index, _), path in zip(processors, final_paths):
            assert path is not None
            text = _read_text(path)
            # v2512 writes this uniform object with ``class topO`` (not a
            # generic dictionary), which is part of the provenance contract.
            _require_foam_header(text, path, expected_class="topO", expected_object="topOVars")
            labels = labels_by_processor[index]
            uniform = _TOP_OVARS_ALPHA_RE.search(text)
            nonuniform = _TOP_OVARS_ALPHA_NONUNIFORM_RE.search(text)
            if uniform is not None and nonuniform is not None:
                raise ValueError(f"final topOVars has ambiguous alpha entries: {path}")
            if uniform is not None:
                values = np.full(labels.size, _finite_scalar(uniform.group(1), path))
                representations.append("uniform")
            elif nonuniform is not None:
                values = _numbers(nonuniform.group(2), count=int(nonuniform.group(1)), path=path, integer=False)
                if values.size != labels.size:
                    raise ValueError(
                        f"final topOVars alpha on processor{index} has {values.size} values but {labels.size} cell addresses"
                    )
                representations.append("nonuniform")
            else:
                raise ValueError(f"final topOVars has no alpha entry: {path}")
            entries.append((labels, values))
            sources.append(_source_file(index, root, path))
        labels, values = _sort_by_global_labels(entries, "raw alpha")
        stage = (
            "final_topOVars_uniform_alpha"
            if set(representations) == {"uniform"}
            else "final_topOVars_nonuniform_alpha"
            if set(representations) == {"nonuniform"}
            else "final_topOVars_mixed_alpha"
        )
        return values, _raw_alpha_provenance(stage, final_time, labels.size, len(processors), sources, None)

    initial_paths = [_maybe_single_file(processor / "0" / "alpha") for _, processor in processors]
    if not any(path is not None for path in initial_paths):
        return None, {
            "status": "not_present",
            "reason": "no_final_topOVars_or_initial_alpha",
            "ordering": GLOBAL_CELL_LABEL_ORDER,
        }
    if any(path is None for path in initial_paths):
        raise ValueError("initial raw alpha is present on only some processors")
    entries = []
    sources = []
    dimensions: str | None = None
    for (index, _), path in zip(processors, initial_paths):
        assert path is not None
        values, current_dimensions = _read_scalar_field_allow_uniform(path, "alpha", labels_by_processor[index].size)
        if dimensions is None:
            dimensions = current_dimensions
        elif dimensions != current_dimensions:
            raise ValueError("initial raw alpha has inconsistent dimensions across processors")
        entries.append((labels_by_processor[index], values))
        sources.append(_source_file(index, root, path))
    labels, values = _sort_by_global_labels(entries, "raw alpha")
    return values, _raw_alpha_provenance("initial_time_alpha", "0", labels.size, len(processors), sources, dimensions)


def _raw_alpha_provenance(
    source_stage: str, time_name: str, cell_count: int, processors: int, sources: list[dict[str, object]], dimensions: str | None
) -> dict[str, object]:
    return {
        "status": "reconstructed",
        "openfoam_field_name": "alpha",
        "source_stage": source_stage,
        "time": time_name,
        "openfoam_dimensions": dimensions,
        "ordering": GLOBAL_CELL_LABEL_ORDER,
        "cell_count": int(cell_count),
        "processor_count": processors,
        "source_files": sources,
    }


def _raw_topology_sensitivity_candidates(processors: list[tuple[int, Path]], time_name: str) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for index, processor in processors:
        directory = processor / time_name
        for path in sorted(directory.iterdir() if directory.is_dir() else (), key=lambda item: item.name):
            name = path.name.removesuffix(".gz")
            if path.is_file() and name.startswith("topologySens"):
                candidates.append({"processor": index, "path": f"processor{index}/{time_name}/{path.name}", "sha256": _sha256(path), "field_name": name, "status": "audit_only_not_output"})
    return candidates


def _read_nonuniform_scalar_field(path: Path, expected_object: str) -> tuple[np.ndarray, str]:
    text = _read_text(path)
    _require_foam_header(text, path, expected_class="volScalarField", expected_object=expected_object)
    dimensions = _dimensions(text, path)
    match = _NONUNIFORM_RE.search(text)
    if match is None:
        raise ValueError(f"{expected_object} must have a nonuniform scalar internalField: {path}")
    return _numbers(match.group(2), count=int(match.group(1)), path=path, integer=False), dimensions


def _read_scalar_field_allow_uniform(path: Path, expected_object: str, count: int) -> tuple[np.ndarray, str]:
    text = _read_text(path)
    _require_foam_header(text, path, expected_class="volScalarField", expected_object=expected_object)
    dimensions = _dimensions(text, path)
    nonuniform = _NONUNIFORM_RE.search(text)
    if nonuniform is not None:
        return _numbers(nonuniform.group(2), count=int(nonuniform.group(1)), path=path, integer=False), dimensions
    uniform = _UNIFORM_RE.search(text)
    if uniform is None:
        raise ValueError(f"{expected_object} has no scalar internalField: {path}")
    return np.full(count, _finite_scalar(uniform.group(1), path), dtype=np.float64), dimensions


def _sort_by_global_labels(entries: list[tuple[np.ndarray, np.ndarray]], field_name: str) -> tuple[np.ndarray, np.ndarray]:
    labels = np.concatenate([labels for labels, _ in entries]).astype(np.int64, copy=False)
    values = np.concatenate([values for _, values in entries]).astype(np.float64, copy=False)
    if labels.size == 0 or values.size != labels.size:
        raise ValueError(f"{field_name} reconstruction has an invalid cell count")
    if np.any(labels < 0) or np.unique(labels).size != labels.size:
        raise ValueError(f"{field_name} reconstruction has duplicate or negative global cell labels")
    order = np.argsort(labels, kind="stable")
    labels, values = labels[order], values[order]
    if not np.array_equal(labels, np.arange(labels.size, dtype=np.int64)):
        raise ValueError(f"{field_name} reconstruction does not cover contiguous global cell labels")
    if not np.isfinite(values).all():
        raise ValueError(f"{field_name} reconstruction contains non-finite values")
    return labels, values


def _require_foam_header(text: str, path: Path, *, expected_class: str, expected_object: str) -> None:
    class_match = _CLASS_RE.search(text)
    object_match = _OBJECT_RE.search(text)
    if class_match is None or class_match.group(1) != expected_class:
        raise ValueError(f"OpenFOAM file has invalid class for {expected_object}: {path}")
    if object_match is None or object_match.group(1) != expected_object:
        raise ValueError(f"OpenFOAM file object does not match {expected_object!r}: {path}")


def _dimensions(text: str, path: Path) -> str:
    match = _DIMENSIONS_RE.search(text)
    if match is None:
        raise ValueError(f"OpenFOAM scalar field has no dimensions: {path}")
    return " ".join(match.group(1).split())


def _numbers(text: str, *, count: int, path: Path, integer: bool) -> np.ndarray:
    dtype = np.int64 if integer else np.float64
    values = np.fromstring(text, sep=" ", dtype=dtype)
    if values.size != count:
        raise ValueError(f"OpenFOAM list expected {count} values but found {values.size}: {path}")
    if not integer and not np.isfinite(values).all():
        raise ValueError(f"OpenFOAM scalar values are non-finite: {path}")
    return values


def _finite_scalar(value: str, path: Path) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"OpenFOAM scalar value is invalid: {path}") from exc
    if not np.isfinite(result):
        raise ValueError(f"OpenFOAM scalar value is non-finite: {path}")
    return result


def _single_file(base: Path) -> Path:
    path = _maybe_single_file(base)
    if path is None:
        raise ValueError(f"Required OpenFOAM source file is missing: {base}")
    return path


def _maybe_single_file(base: Path) -> Path | None:
    candidates = [path for path in (base, base.with_name(base.name + ".gz")) if path.is_file()]
    if len(candidates) > 1:
        raise ValueError(f"OpenFOAM source file is ambiguous (plain and gzip): {base}")
    return candidates[0] if candidates else None


def _read_text(path: Path) -> str:
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8", errors="strict") as handle:
                return handle.read()
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Unable to read OpenFOAM source file: {path}") from exc


def _source_file(processor: int, root: Path, path: Path) -> dict[str, object]:
    return {"processor": processor, "path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "GLOBAL_CELL_LABEL_ORDER",
    "ReconstructedOpenFoamFields",
    "reconstruct_final_decomposed_openfoam_fields",
]
