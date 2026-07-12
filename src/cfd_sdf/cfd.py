from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CfdEvaluation:
    source: str
    latest: dict[str, float]
    drag_coefficient: float | None
    lift_coefficient: float | None
    downforce_coefficient: float | None
    efficiency: float | None
    efficiency_constraint: float | None

    @property
    def ok(self) -> bool:
        return self.drag_coefficient is not None and self.downforce_coefficient is not None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["ok"] = self.ok
        return data


def evaluate_openfoam_case(case_dir: Path, efficiency_min: float) -> CfdEvaluation:
    force_file = _find_force_coeffs(case_dir)
    values = _read_latest_force_coeffs(force_file)
    cd = values.get("Cd")
    cl = values.get("Cl")
    downforce = -cl if cl is not None else None
    efficiency = None
    efficiency_constraint = None
    if cd is not None and downforce is not None and abs(cd) > 1.0e-12:
        efficiency = downforce / cd
        efficiency_constraint = efficiency_min * cd - downforce
    return CfdEvaluation(
        source=str(force_file),
        latest=values,
        drag_coefficient=cd,
        lift_coefficient=cl,
        downforce_coefficient=downforce,
        efficiency=efficiency,
        efficiency_constraint=efficiency_constraint,
    )


def write_cfd_summary(case_dir: Path, efficiency_min: float) -> Path:
    evaluation = evaluate_openfoam_case(case_dir, efficiency_min)
    path = case_dir / "cfd_summary.json"
    path.write_text(json.dumps(evaluation.to_dict(), indent=2), encoding="utf-8")
    return path


def _find_force_coeffs(case_dir: Path) -> Path:
    files = sorted(case_dir.glob("postProcessing/forceCoeffs*/**/forceCoeffs.dat"))
    files.extend(sorted(case_dir.glob("postProcessing/forceCoeffs*/**/coefficient.dat")))
    if not files:
        raise FileNotFoundError(f"No force coefficient file found under {case_dir / 'postProcessing'}")
    return sorted(files)[-1]


def _read_latest_force_coeffs(path: Path) -> dict[str, float]:
    header: list[str] = []
    latest: list[str] | None = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            header = stripped.lstrip("#").split()
            continue
        latest = stripped.split()
    if latest is None:
        raise ValueError(f"No data rows found in {path}")
    if not header:
        header = [f"col_{index}" for index in range(len(latest))]
    return {name: float(value) for name, value in zip(header, latest)}
