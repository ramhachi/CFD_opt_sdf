#!/usr/bin/env python3
"""Run the immutable FD-08 fresh-33 set with the verified XFID-C harness."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy

INPUT_ROOT = Path(os.environ.get("XC_INPUT", "/kaggle/input"))
matches = sorted(INPUT_ROOT.rglob("xfidc_criteria.json"))
if len(matches) != 1:
    raise RuntimeError(f"expected one attached FD-08 formal criteria file, found {len(matches)}")
criteria_path = matches[0]
sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
criteria_sha = hashlib.sha256(criteria_path.read_bytes()).hexdigest()
if not sidecar.is_file() or sidecar.read_text().strip() != criteria_sha:
    raise RuntimeError("FD-08 formal criteria SHA-256 sidecar mismatch")
criteria = json.loads(criteria_path.read_text())
if (criteria.get("kind") != "fd08_candidate_c_formal"
        or criteria.get("immutable") is not True
        or criteria.get("registered_before_computation") is not True
        or criteria.get("status") != "registered_not_run"):
    raise RuntimeError("attached criteria are not an immutable premeasurement FD-08 formal round")

core_path = Path(__file__).with_name("runner_base.py")
source_inputs = criteria.get("source_inputs", {})
wrapper_binding = source_inputs.get("formal_kernel_wrapper", {})
core_binding = source_inputs.get("formal_kernel_base_runner", {})
if (not isinstance(wrapper_binding, dict) or not isinstance(core_binding, dict)
        or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != wrapper_binding.get("sha256")
        or hashlib.sha256(core_path.read_bytes()).hexdigest() != core_binding.get("sha256")):
    raise RuntimeError("uploaded FD-08 formal kernel wrapper or core runner hash mismatch")
namespace = runpy.run_path(core_path, run_name="fd08_xfid_runner_core")
namespace["CRITERIA_SHA256"] = criteria_sha
namespace["INPUT_ROOT"] = INPUT_ROOT
namespace["OUT"] = Path(os.environ.get("FD08_OUT_ROOT", "/kaggle/working")) / "fd08_formal"
namespace["main"]()
