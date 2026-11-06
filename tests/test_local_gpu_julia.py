"""Protect the registered force contract in the checkpoint-enabled local copy.

Numerical restart coverage is scripts/checkpoint_selftest.jl (CPU only).
"""

import difflib
import json
from pathlib import Path

import pytest

from cfd_harness import campaign_build as CB, campaign_schema as SC


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = "julia/CFDSDFWaterLily/gen01/Checkpoint.jl"


def test_gen01_module_preserves_the_registered_src_directory_pin():
    # Read the registered hash instead of manufacturing a new historical value.
    freeze = json.loads(
        (ROOT / "docs/harness/job02_gate_campaign.prerun_freeze.json").read_text()
    )
    src = "julia/CFDSDFWaterLily/src"
    for pins in freeze["pins"].values():
        assert SC.sha256_path(ROOT / src) == pins[src]
    assert (ROOT / CHECKPOINT).is_file()
    assert not (ROOT / src / "Checkpoint.jl").exists()


def test_checkpoint_is_explicitly_included_and_pinned_outside_src():
    paths = {
        "julia/CFDSDFWaterLily/src",
        "scripts/waterlily_local_gpu_job.jl",
        CHECKPOINT,
    }
    CB.check_include_closure(ROOT, paths)
    with pytest.raises(ValueError, match="gen01/Checkpoint.jl.*not pinned"):
        CB.check_include_closure(ROOT, paths - {CHECKPOINT})
    for script in ("scripts/waterlily_local_gpu_job.jl", "scripts/checkpoint_selftest.jl"):
        text = (ROOT / script).read_text()
        assert CHECKPOINT in CB.julia_includes(script, text)
        assert 'Base.include(CFDSDFWaterLily,' in text


def test_checkpoint_job_diff_is_the_complete_actual_delta():
    original_name = "scripts/waterlily_lowdim02_flow32_job.jl"
    local_name = "scripts/waterlily_local_gpu_job.jl"
    original = (ROOT / original_name).read_text()
    local = (ROOT / local_name).read_text()
    expected = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            local.splitlines(keepends=True),
            fromfile="a/" + original_name,
            tofile="b/" + local_name,
        )
    )
    assert (ROOT / "scripts/waterlily_local_gpu_job.diff").read_text() == expected


def test_checkpoint_copy_preserves_the_registered_force_and_window_contract():
    original = (ROOT / "scripts/waterlily_lowdim02_flow32_job.jl").read_text()
    local = (ROOT / "scripts/waterlily_local_gpu_job.jl").read_text()
    # Windows, interpolation and CSV bytes remain shared with the registered job.
    boundaries = [
        ("json_number(x)", "function run_case_measurement("),
        ("        if step % SAMPLE_EVERY == 0", "        if step % 50 == 0"),
        ("    CUDA.synchronize()\n    wall_seconds", "\nfunction run_case("),
        ("function run_case(", "\nmain()"),
    ]
    for first, last in boundaries:
        assert original[original.index(first) : original.index(last)] == local[
            local.index(first) : local.index(last)
        ]
