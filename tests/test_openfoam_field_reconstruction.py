from __future__ import annotations

import gzip
from pathlib import Path
import re

import numpy as np
import pytest

from cfd_sdf.openfoam_field_reconstruction import (
    GLOBAL_CELL_LABEL_ORDER,
    reconstruct_final_decomposed_openfoam_fields,
)


_RUNTIME_G2_STRAIGHT_CASE = (
    Path(__file__).resolve().parents[1]
    / "examples/g2_openfoam_compile/runs/compiled_cases/flow_straight"
)


def _write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)


def _field(name: str, values: list[float], dimensions: str = "[0 0 0 0 0 0 0]") -> str:
    return (
        "FoamFile\n{\n    class volScalarField;\n"
        f"    object {name};\n}}\n\n"
        f"dimensions {dimensions};\ninternalField nonuniform List<scalar> {len(values)}\n(\n"
        + "\n".join(str(value) for value in values)
        + "\n);\n"
    )


def _uniform_alpha(value: float) -> str:
    return (
        "FoamFile\n{\n    class volScalarField;\n    object alpha;\n}\n\n"
        "dimensions [0 0 0 0 0 0 0];\n"
        f"internalField uniform {value};\n"
    )


def _labels(values: list[int]) -> str:
    return (
        "FoamFile\n{\n    class labelList;\n    object cellProcAddressing;\n}\n\n"
        f"{len(values)}\n(\n" + "\n".join(str(value) for value in values) + "\n);\n"
    )


def _top_ovars(value: float) -> str:
    return (
        "FoamFile\n{\n    class topO;\n    object topOVars;\n}\n\n"
        f"alpha uniform {value};\n"
    )


def _top_ovars_nonuniform(values: list[float]) -> str:
    return (
        "FoamFile\n{\n    class topO;\n    object topOVars;\n}\n\n"
        f"alpha nonuniform List<scalar> {len(values)}\n(\n"
        + "\n".join(str(value) for value in values)
        + "\n);\n"
    )


def _build_case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    # Local processor order deliberately differs from global labels.
    data = {
        0: {"labels": [2, 0], "sens": [20.0, 0.0], "alpha_tilda": [0.2, 0.0], "beta": [0.8, 0.6]},
        1: {"labels": [3, 1], "sens": [30.0, 10.0], "alpha_tilda": [0.3, 0.1], "beta": [0.9, 0.7]},
    }
    for processor, item in data.items():
        root = case / f"processor{processor}"
        _write_gz(root / "constant/polyMesh/cellProcAddressing.gz", _labels(item["labels"]))
        _write_gz(root / "1/topOSensresp_force.gz", _field("topOSensresp_force", item["sens"], "[1 1 -2 0 0 0 0]"))
        _write_gz(root / "1/alphaTilda.gz", _field("alphaTilda", item["alpha_tilda"]))
        _write_gz(root / "1/beta.gz", _field("beta", item["beta"]))
        _write_gz(root / "0/alpha.gz", _uniform_alpha(0.15 + processor * 0.05))
    return case


def test_reconstructs_multiple_processors_in_global_label_order_with_provenance(tmp_path: Path) -> None:
    case = _build_case(tmp_path)
    result = reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")

    assert result.global_cell_labels.tolist() == [0, 1, 2, 3]
    assert result.top_o_sensitivity == pytest.approx([0.0, 10.0, 20.0, 30.0])
    assert result.alpha_tilda == pytest.approx([0.0, 0.1, 0.2, 0.3])
    assert result.beta == pytest.approx([0.6, 0.7, 0.8, 0.9])
    # No final topOVars exists, so initial uniform alpha is reconstructed per processor.
    assert result.raw_alpha == pytest.approx([0.15, 0.2, 0.15, 0.2])
    assert result.provenance["ordering"] == GLOBAL_CELL_LABEL_ORDER
    assert result.provenance["final_time"] == "1"
    assert result.provenance["fields"]["top_o_sensitivity"] == {
        "openfoam_field_name": "topOSensresp_force",
        "openfoam_object": "topOSensresp_force",
        "openfoam_dimensions": "1 1 -2 0 0 0 0",
        "time": "1",
        "ordering": GLOBAL_CELL_LABEL_ORDER,
        "cell_count": 4,
        "processor_count": 2,
        "representation": "nonuniform_volScalarField",
        "source_files": result.provenance["fields"]["top_o_sensitivity"]["source_files"],
    }
    for source in result.provenance["fields"]["top_o_sensitivity"]["source_files"]:
        assert source["path"].endswith(".gz")
        assert len(source["sha256"]) == 64
    assert result.provenance["fields"]["raw_alpha"]["source_stage"] == "initial_time_alpha"


def test_final_topovars_uniform_alpha_is_preferred_and_replicated(tmp_path: Path) -> None:
    case = _build_case(tmp_path)
    for processor, value in ((0, 0.4), (1, 0.6)):
        _write_gz(case / f"processor{processor}/1/uniform/topOVars.gz", _top_ovars(value))

    result = reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")
    assert result.raw_alpha == pytest.approx([0.4, 0.6, 0.4, 0.6])
    raw = result.provenance["fields"]["raw_alpha"]
    assert raw["source_stage"] == "final_topOVars_uniform_alpha"
    assert raw["time"] == "1"
    assert raw["openfoam_dimensions"] is None


def test_final_topovars_nonuniform_alpha_is_global_label_reconstructed(tmp_path: Path) -> None:
    case = _build_case(tmp_path)
    _write_gz(case / "processor0/1/uniform/topOVars.gz", _top_ovars_nonuniform([0.42, 0.40]))
    _write_gz(case / "processor1/1/uniform/topOVars.gz", _top_ovars(0.6))

    result = reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")
    assert result.raw_alpha == pytest.approx([0.40, 0.6, 0.42, 0.6])
    assert result.provenance["fields"]["raw_alpha"]["source_stage"] == "final_topOVars_mixed_alpha"


@pytest.mark.parametrize(
    "relative, replacement, message",
    [
        ("processor1/1/beta.gz", _field("beta", [0.9, 0.7], "[1 0 0 0 0 0 0]"), "inconsistent dimensions"),
        ("processor1/1/alphaTilda.gz", _field("wrongObject", [0.3, 0.1]), "object does not match"),
        ("processor1/constant/polyMesh/cellProcAddressing.gz", _labels([3, 2]), "unique non-negative"),
    ],
)
def test_missing_or_inconsistent_sources_are_rejected(tmp_path: Path, relative: str, replacement: str, message: str) -> None:
    case = _build_case(tmp_path)
    _write_gz(case / relative, replacement)
    with pytest.raises(ValueError, match=message):
        reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")


def test_missing_required_final_field_is_rejected(tmp_path: Path) -> None:
    case = _build_case(tmp_path)
    (case / "processor1/1/beta.gz").unlink()
    with pytest.raises(ValueError, match="Required OpenFOAM source file is missing"):
        reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")


def test_nonfinite_values_are_rejected(tmp_path: Path) -> None:
    case = _build_case(tmp_path)
    _write_gz(case / "processor0/1/topOSensresp_force.gz", _field("topOSensresp_force", [np.nan, 0.0]))
    with pytest.raises(ValueError, match="non-finite"):
        reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")


def test_raw_topology_sensitivity_never_substitutes_for_final_toposens(tmp_path: Path) -> None:
    case = _build_case(tmp_path)
    for processor in (0, 1):
        (case / f"processor{processor}/1/topOSensresp_force.gz").unlink()
        _write_gz(
            case / f"processor{processor}/1/topologySensresp_force.gz",
            _field("topologySensresp_force", [1.0, 2.0]),
        )
    with pytest.raises(ValueError, match="raw topologySens audit candidates cannot substitute"):
        reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")


def test_raw_topology_sensitivity_is_explicitly_audit_only(tmp_path: Path) -> None:
    case = _build_case(tmp_path)
    _write_gz(case / "processor0/1/topologySensresp_force.gz", _field("topologySensresp_force", [1.0, 2.0]))
    result = reconstruct_final_decomposed_openfoam_fields(case, adjoint_solver_id="resp_force")
    candidates = result.provenance["raw_topology_sensitivity_audit_candidates"]
    assert candidates[0]["status"] == "audit_only_not_output"
    assert candidates[0]["field_name"] == "topologySensresp_force"
    assert not hasattr(result, "topology_sensitivity")


@pytest.mark.skipif(
    not _RUNTIME_G2_STRAIGHT_CASE.is_dir(),
    reason="ignored G2 Docker runtime artifact is not available in this checkout",
)
def test_runtime_g2_straight_case_reconstructs_final_fields_with_audit_provenance() -> None:
    """Exercise the reader against the actual v2512 four-processor G2 run.

    The ignored artifact is intentionally optional for CI clones.  When it is
    present, this prevents synthetic fixtures from masking a parser drift in
    OpenFOAM's real labelList or topOVars serialization.
    """

    result = reconstruct_final_decomposed_openfoam_fields(
        _RUNTIME_G2_STRAIGHT_CASE,
        adjoint_solver_id="resp_rotated_force",
    )

    assert result.global_cell_labels.tolist() == list(range(8192))
    assert result.global_cell_labels.size == 8192
    provenance = result.provenance
    assert provenance["final_time"] == "1"
    assert provenance["ordering"] == GLOBAL_CELL_LABEL_ORDER
    for field_key, field_name in (
        ("top_o_sensitivity", "topOSensresp_rotated_force"),
        ("alpha_tilda", "alphaTilda"),
        ("beta", "beta"),
    ):
        field = provenance["fields"][field_key]
        assert field["openfoam_field_name"] == field_name
        assert field["time"] == "1"
        assert field["ordering"] == GLOBAL_CELL_LABEL_ORDER
        assert field["cell_count"] == 8192
        assert len(field["source_files"]) == 4
        assert all(len(item["sha256"]) == 64 for item in field["source_files"])

    raw = provenance["fields"]["raw_alpha"]
    assert raw["status"] == "reconstructed"
    assert raw["source_stage"] == "final_topOVars_mixed_alpha"
    assert result.raw_alpha is not None
    assert result.raw_alpha[0] == pytest.approx(0.0)
    # processor0's v2512 topOVars is the expected uniform alpha=0 source.
    with gzip.open(
        _RUNTIME_G2_STRAIGHT_CASE / "processor0/1/uniform/topOVars.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        assert re.search(r"\balpha\s+uniform\s+0\s*;", handle.read())

    audit = provenance["raw_topology_sensitivity_audit_candidates"]
    assert len(audit) == 4
    assert all(item["status"] == "audit_only_not_output" for item in audit)
