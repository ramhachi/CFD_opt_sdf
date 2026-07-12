from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .optimization import run_parametric_optimization
from .topology import run_topology_exploration


@dataclass(frozen=True)
class PracticalRunSummary:
    run_dir: Path
    mode: str
    evaluator: str
    status: str
    iterations: int
    accepted_count: int
    rejected_count: int
    failed_count: int
    best_candidate_dir: Path
    best_objective: float
    manifest_path: Path
    progress_path: Path
    summary_markdown: Path
    runner_summary_path: Path
    engine_summary_path: Path
    best_export_dir: Path
    failure_classes: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "run_dir",
            "best_candidate_dir",
            "manifest_path",
            "progress_path",
            "summary_markdown",
            "runner_summary_path",
            "engine_summary_path",
            "best_export_dir",
        ):
            data[key] = str(data[key])
        return data


def run_practical_optimization(
    base_project_yaml: Path,
    *,
    run_dir: Path,
    mode: str = "topology",
    iterations: int = 8,
    evaluator: str | None = None,
    seed: int = 1,
    voxel_size_m: float | None = 0.08,
    backend: str = "auto",
    timeout_seconds: int | None = None,
    resume: bool = True,
    reject_before_cfd: bool = True,
) -> PracticalRunSummary:
    normalized_mode = mode.lower()
    if normalized_mode not in {"parametric", "topology"}:
        raise ValueError(f"Unsupported optimization mode: {mode}")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    selected_evaluator = evaluator or ("mock" if normalized_mode == "parametric" else "low-fi")
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "run_manifest.json"
    progress_path = run_dir / "progress.json"
    summary_markdown = run_dir / "run_summary.md"
    runner_summary_path = run_dir / "runner_summary.json"
    best_export_dir = run_dir / "best_design"
    engine_dir = run_dir / normalized_mode

    manifest = _manifest(
        base_project_yaml,
        mode=normalized_mode,
        evaluator=selected_evaluator,
        iterations=iterations,
        seed=seed,
        voxel_size_m=voxel_size_m,
        backend=backend,
        timeout_seconds=timeout_seconds,
        reject_before_cfd=reject_before_cfd,
    )
    if not (resume and manifest_path.exists()):
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if normalized_mode == "parametric":
        engine_summary = run_parametric_optimization(
            base_project_yaml,
            run_dir=engine_dir,
            iterations=iterations,
            evaluator=selected_evaluator,
            seed=seed,
            voxel_size_m=voxel_size_m,
            backend=backend,
            resume=resume,
            reject_before_cfd=reject_before_cfd,
        )
        engine_summary_path = engine_dir / "optimization_summary.json"
    else:
        engine_summary = run_topology_exploration(
            base_project_yaml,
            run_dir=engine_dir,
            iterations=iterations,
            evaluator=selected_evaluator,
            seed=seed,
            voxel_size_m=voxel_size_m,
            backend=backend,
            timeout_seconds=timeout_seconds,
            resume=resume,
            reject_before_cfd=reject_before_cfd,
        )
        engine_summary_path = engine_dir / "topology_summary.json"

    candidate_dicts = [candidate.to_dict() for candidate in engine_summary.candidates]
    classifications = [classify_candidate(candidate) for candidate in candidate_dicts]
    failure_classes = Counter(item["class"] for item in classifications)
    accepted_count = int(failure_classes.get("accepted", 0))
    rejected_count = len(candidate_dicts) - accepted_count
    failed_count = int(sum(count for name, count in failure_classes.items() if name.startswith("failed")))
    best = engine_summary.best_candidate

    _export_best_design(best.candidate_dir, best_export_dir)
    summary = PracticalRunSummary(
        run_dir=run_dir,
        mode=normalized_mode,
        evaluator=selected_evaluator,
        status="complete_with_failures" if failed_count else "complete",
        iterations=iterations,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        failed_count=failed_count,
        best_candidate_dir=best.candidate_dir,
        best_objective=float(best.objective),
        manifest_path=manifest_path,
        progress_path=progress_path,
        summary_markdown=summary_markdown,
        runner_summary_path=runner_summary_path,
        engine_summary_path=engine_summary_path,
        best_export_dir=best_export_dir,
        failure_classes=dict(sorted(failure_classes.items())),
    )
    progress_path.write_text(json.dumps(_progress(summary, classifications), indent=2), encoding="utf-8")
    runner_summary_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    summary_markdown.write_text(_summary_markdown(summary, classifications), encoding="utf-8")
    return summary


def classify_candidate(candidate: dict[str, object]) -> dict[str, object]:
    status = str(candidate.get("status", "accepted" if candidate.get("constraints_ok", False) else "rejected"))
    records = [dict(item) for item in candidate.get("constraint_records", [])]
    enforced_failures = [
        record
        for record in records
        if bool(record.get("enforced", False)) and not bool(record.get("satisfied", False))
    ]
    if status == "accepted" and not enforced_failures:
        return {
            "index": int(candidate.get("index", -1)),
            "status": status,
            "class": "accepted",
            "primary_reason": None,
            "candidate_dir": str(candidate.get("candidate_dir", "")),
        }

    if enforced_failures:
        primary = enforced_failures[0]
        category = str(primary.get("category", "unknown"))
        return {
            "index": int(candidate.get("index", -1)),
            "status": status,
            "class": f"rejected_{category}",
            "primary_reason": str(primary.get("name", "unknown")),
            "candidate_dir": str(candidate.get("candidate_dir", "")),
        }

    if status == "failed":
        reasons = [str(item) for item in candidate.get("rejection_reasons", [])]
        failure_class = "failed_cfd" if any(reason.startswith("openfoam_") for reason in reasons) else "failed_unknown"
    else:
        failure_class = "rejected_unknown"
    return {
        "index": int(candidate.get("index", -1)),
        "status": status,
        "class": failure_class,
        "primary_reason": ";".join(str(item) for item in candidate.get("rejection_reasons", [])) or None,
        "candidate_dir": str(candidate.get("candidate_dir", "")),
    }


def _manifest(
    base_project_yaml: Path,
    *,
    mode: str,
    evaluator: str,
    iterations: int,
    seed: int,
    voxel_size_m: float | None,
    backend: str,
    timeout_seconds: int | None,
    reject_before_cfd: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_project_yaml": str(base_project_yaml.resolve()),
        "mode": mode,
        "evaluator": evaluator,
        "iterations": iterations,
        "seed": seed,
        "voxel_size_m": voxel_size_m,
        "backend": backend,
        "timeout_seconds": timeout_seconds,
        "reject_before_cfd": reject_before_cfd,
    }


def _progress(summary: PracticalRunSummary, classifications: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": summary.status,
        "mode": summary.mode,
        "evaluator": summary.evaluator,
        "iterations": summary.iterations,
        "accepted_count": summary.accepted_count,
        "rejected_count": summary.rejected_count,
        "failed_count": summary.failed_count,
        "best_candidate_dir": str(summary.best_candidate_dir),
        "best_objective": summary.best_objective,
        "failure_classes": summary.failure_classes,
        "classifications": classifications,
    }


def _summary_markdown(summary: PracticalRunSummary, classifications: list[dict[str, object]]) -> str:
    class_rows = "\n".join(
        f"| {name} | {count} |" for name, count in summary.failure_classes.items()
    )
    candidate_rows = "\n".join(
        f"| {item['index']} | {item['status']} | {item['class']} | {item['primary_reason'] or ''} |"
        for item in classifications
    )
    return f"""# Practical Optimization Run

| Field | Value |
| --- | --- |
| Status | {summary.status} |
| Mode | {summary.mode} |
| Evaluator | {summary.evaluator} |
| Iterations | {summary.iterations} |
| Accepted | {summary.accepted_count} |
| Rejected | {summary.rejected_count} |
| Failed | {summary.failed_count} |
| Best objective | {summary.best_objective:.8g} |
| Best candidate | `{summary.best_candidate_dir}` |
| Best export | `{summary.best_export_dir}` |

## Failure Classes

| Class | Count |
| --- | ---: |
{class_rows}

## Candidates

| Index | Status | Class | Primary reason |
| ---: | --- | --- | --- |
{candidate_rows}
"""


def _export_best_design(best_candidate_dir: Path, best_export_dir: Path) -> None:
    if best_export_dir.exists():
        shutil.rmtree(best_export_dir)
    shutil.copytree(best_candidate_dir, best_export_dir)
