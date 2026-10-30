"""Fresh/reused provenance on OpenFOAM oracle artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import cfd_sdf.openfoam_oracle as module
from cfd_sdf.openfoam_oracle import OpenFoamOracle


def test_fresh_run_state_records_explicit_reused_false(tmp_path: Path, monkeypatch):
    oracle = OpenFoamOracle.__new__(OpenFoamOracle)
    oracle.config = SimpleNamespace(
        run_root=tmp_path / "runs",
        timeout_seconds=30,
        docker_image="test-image",
        work_root=tmp_path,
    )
    oracle.config.run_root.mkdir()
    oracle.transfer = SimpleNamespace(
        transfer_state_to_source=lambda beta: np.asarray(beta, dtype=np.float64)
    )
    oracle.provenance = {}
    oracle.mapping = np.array([0, 1], dtype=np.int64)
    oracle._base_contract = lambda: tmp_path / "base.json"

    monkeypatch.setattr(module, "write_candidate_sidecar", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "inject_canonical_state_into_fixed_grid_contract",
        lambda **kwargs: SimpleNamespace(
            topology_state_json=tmp_path / "topology.json",
            directory=tmp_path / "contract",
        ),
    )

    def prepare(_topology, *, case_dir, **_kwargs):
        case_dir.mkdir(parents=True)
        return SimpleNamespace(
            case_dir=case_dir,
            topology_state_json=tmp_path / "topology.json",
        )

    monkeypatch.setattr(module, "prepare_fixed_grid_primal_case", prepare)
    monkeypatch.setattr(
        module,
        "run_openfoam_case",
        lambda *args, **kwargs: SimpleNamespace(to_dict=lambda: {"returncode": 0}),
    )

    def summarize(case_dir, **_kwargs):
        summary = {
            "status": "converged",
            "convergence": {
                "primal_converged": True,
                "primal_iterations": 12,
                "downforce_adjoint_converged": False,
            },
        }
        (case_dir / "fixed_grid_primal_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        return summary

    monkeypatch.setattr(module, "summarize_fixed_grid_primal_case", summarize)

    artifact = oracle._run_state(
        SimpleNamespace(beta=np.array([0.2, 0.4])),
        tag="fresh",
        template=tmp_path / "template",
        require_adjoint=False,
    )

    assert artifact["reused"] is False
    assert artifact["summary_sha256"]

    reused = oracle._run_state(
        SimpleNamespace(beta=np.array([0.2, 0.4])),
        tag="fresh",
        template=tmp_path / "template",
        require_adjoint=False,
    )
    assert reused["reused"] is True
    assert reused["summary_sha256"] == artifact["summary_sha256"]
