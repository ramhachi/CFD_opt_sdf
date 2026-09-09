"""Small cross-platform research commands, separate from production claims."""
from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(help="Runtime, geometry and bounded numerical research checks.")


def _emit(report: dict, output: Path | None) -> None:
    text = json.dumps(report, indent=2, allow_nan=False)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    typer.echo(text)


@app.command()
def doctor(output: Path | None = typer.Option(None, help="Write a JSON report.")) -> None:
    """Inspect this machine; tool availability is not CFD qualification."""
    from .runtime_diagnostics import collect_runtime_diagnostics
    _emit(collect_runtime_diagnostics(), output)


@app.command("preflight")
def preflight(
    problem: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path | None = typer.Option(None),
    minimum_cells_per_feature: float = typer.Option(3.0),
) -> None:
    """Check STL validity and declared feature resolution (bounded G3 subset)."""
    from .geometry_preflight import assess_geometry_preflight
    try:
        report = assess_geometry_preflight(
            problem, minimum_cells_per_feature=minimum_cells_per_feature,
        )
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit(report, output)
    if report["status"] != "pass":
        raise typer.Exit(1)


@app.command("lbm-benchmark")
def lbm_benchmark(
    backend: str = typer.Option("cpu", help="cpu or metal"),
    nx: int = typer.Option(32),
    ny: int = typer.Option(32),
    steps: int = typer.Option(100),
    viscosity: float = typer.Option(0.1, help="Kinematic viscosity in lattice units."),
    velocity: float = typer.Option(0.01, help="Low-Mach lattice velocity."),
    output: Path | None = typer.Option(None),
) -> None:
    """Measure periodic Taylor-Green decay; no walls or shape optimization."""
    from .lbm_benchmark import run_lbm_benchmark
    from .lbm_reference import LBMConfig
    try:
        report = run_lbm_benchmark(LBMConfig(nx, ny, steps, viscosity, velocity), backend)
    except (ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit(report, output)
    if report["status"] != "pass":
        raise typer.Exit(1)
