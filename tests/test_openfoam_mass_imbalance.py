from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cfd_sdf.openfoam_mass_imbalance import (
    MASS_IMBALANCE_FORMULA,
    NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME,
    produce_openfoam_normalized_mass_imbalance,
    render_openfoam_mass_imbalance_function_dict,
    validate_normalized_mass_imbalance_artifact,
)


def test_function_dict_measures_signed_and_absolute_phi_on_each_open_patch() -> None:
    text = render_openfoam_mass_imbalance_function_dict(("outlet", "inlet"))

    assert "object      cfdSdfMassImbalanceDict;" in text
    assert "cfdSdfMassSigned0" in text
    assert "cfdSdfMassMagnitude0" in text
    assert "operation       sum;" in text
    assert "operation       sumMag;" in text
    assert "name            inlet;" in text
    assert "name            outlet;" in text
    assert "fields          (phi);" in text


def test_producer_uses_surface_fluxes_and_writes_a_revalidated_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case_with_contract(tmp_path)
    _write_function_rows(case, "cfdSdfMassSigned0", "1 -5.760000000000e+01\n")
    _write_function_rows(case, "cfdSdfMassMagnitude0", "1 5.760000000000e+01\n")
    _write_function_rows(case, "cfdSdfMassSigned1", "1 5.759999992644e+01\n")
    _write_function_rows(case, "cfdSdfMassMagnitude1", "1 5.759999992644e+01\n")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("cfd_sdf.openfoam_mass_imbalance.subprocess.run", fake_run)
    artifact = produce_openfoam_normalized_mass_imbalance(case, backend="docker")

    assert artifact["formula"] == MASS_IMBALANCE_FORMULA
    assert artifact["measurements"][0]["net_signed_flux"] == pytest.approx(-7.356e-08)
    assert artifact["measurements"][0]["normalized_mass_imbalance"] == pytest.approx(
        abs(-7.356e-08) / 57.59999996322
    )
    assert "mpirun" not in captured["command"]
    written = json.loads((case / NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert validate_normalized_mass_imbalance_artifact(written) == pytest.approx(
        [artifact["measurements"][0]["normalized_mass_imbalance"]]
    )


def test_validator_rejects_formula_inconsistent_measurement() -> None:
    artifact = {
        "schema_version": 1,
        "kind": "openfoam_normalized_mass_imbalance",
        "flow_case_id": "straight",
        "open_patch_ids": ["inlet", "outlet"],
        "epsilon": 1e-30,
        "formula": MASS_IMBALANCE_FORMULA,
        "measurements": [
            {
                "time": 1.0,
                "signed_flux_by_patch": {"inlet": -10.0, "outlet": 9.0},
                "absolute_flux_by_patch": {"inlet": 10.0, "outlet": 9.0},
                "net_signed_flux": -1.0,
                "absolute_flux_sum": 19.0,
                "throughput": 9.5,
                "denominator": 9.5,
                "normalized_mass_imbalance": 0.0,
            }
        ],
    }

    with pytest.raises(ValueError, match="normalized mass-imbalance"):
        validate_normalized_mass_imbalance_artifact(artifact)


def test_parallel_processor_directories_select_parallel_postprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case_with_contract(tmp_path)
    for index in range(2):
        (case / f"processor{index}").mkdir()
    for name, value in (("cfdSdfMassSigned0", "-10"), ("cfdSdfMassMagnitude0", "10"), ("cfdSdfMassSigned1", "10"), ("cfdSdfMassMagnitude1", "10")):
        _write_function_rows(case, name, f"1 {value}\n")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "cfd_sdf.openfoam_mass_imbalance.subprocess.run",
        lambda command, **kwargs: captured.setdefault("command", command) and SimpleNamespace(returncode=0),
    )

    produce_openfoam_normalized_mass_imbalance(case, backend="docker")

    assert "mpirun -np 2" in captured["command"][-1]
    assert "-parallel" in captured["command"][-1]


def _case_with_contract(root: Path) -> Path:
    case = root / "case"
    (case / "system").mkdir(parents=True)
    (case / "system/cfdSdfMassImbalanceDict").write_text("dictionary\n", encoding="utf-8")
    (case / "generated_openfoam_physics.json").write_text(
        json.dumps(
            {
                "kind": "generated_openfoam_physics",
                "flow_case_id": "straight",
                "normalized_mass_imbalance": {
                    "artifact_name": NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME,
                    "function_dict": "system/cfdSdfMassImbalanceDict",
                    "open_patch_ids": ["inlet", "outlet"],
                    "formula": MASS_IMBALANCE_FORMULA,
                    "epsilon": 1e-30,
                },
            }
        ),
        encoding="utf-8",
    )
    return case


def _write_function_rows(case: Path, name: str, rows: str) -> None:
    path = case / "postProcessing" / name / "surfaceFieldValue_1.dat"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Time value\n" + rows, encoding="utf-8")
