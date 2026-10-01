from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preflight_kaggle_sdf_directional_fd_v16_cpu import (  # noqa: E402
    check_metadata,
    check_queue_output_separation,
    check_summary_schema,
)


def test_registered_kernel_slug_and_dataset_binding():
    metadata = {
        "id": "ramhachi888/cfd-opt-sdf-v17-nfloor-fd-oracle",
        "title": "CFD Opt SDF v17 NFloor FD Oracle",
        "dataset_sources": ["ramhachi888/cfd-opt-sdf-v17-nfloor-directional-fd-oracle"],
    }
    assert check_metadata(metadata, metadata["dataset_sources"][0])["slug_length"] <= 40
    with pytest.raises(ValueError, match="slug or dataset binding"):
        check_metadata({**metadata, "dataset_sources": ["wrong/dataset"]}, metadata["dataset_sources"][0])


@pytest.mark.parametrize("kernel_id,title", [
    ("/valid-title", "Valid Title"),
    ("owner/white space", "White Space"),
    ("owner/" + "a" * 41, "Long Slug"),
    ("owner/different-title", "Other Title"),
])
def test_kernel_id_rejects_invalid_owner_slug_length_and_title(kernel_id, title):
    metadata = {"id": kernel_id, "title": title, "dataset_sources": ["owner/input"]}
    with pytest.raises(ValueError, match="slug or dataset binding"):
        check_metadata(metadata, "owner/input")


def test_queue_input_cannot_alias_julia_snapshot(tmp_path):
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="must not be the Julia output snapshot"):
        check_queue_output_separation(output / "run_queue.tsv", output)
    check_queue_output_separation(tmp_path / "input" / "run_queue.tsv", output)


def test_python_runner_summary_fields_exist_in_julia_job():
    result = check_summary_schema(
        ROOT / "infra/kaggle/kernel_sdf_directional_fd_v17_flow24_normalfloor/runner.py",
        ROOT / "scripts/waterlily_sdf_directional_fd_v16_job.jl",
    )
    assert result["missing_from_julia"] == []
    assert "normal_floor" in result["julia_keys"]
