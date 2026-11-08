#!/usr/bin/env python3
"""Register FORCE-00's phase-zero parent boxes once; CPU geometry only.

Run with no arguments to write docs/harness/force00_boxes.json. --toml reads
the existing registration for Julia entrypoints without adding a dependency.
Normal face indices are lo and hi+1; pressure cells are inclusive lo:hi.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/harness/force00_boxes.json"
GRIDS = {"flow_24", "flow_32"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def boxes_from_support(support, genesis):
    """Largest domain-inset box excluding ground, with certified support margin.

    On each axis, enlargement away from the enclosed support increases its
    clearance. Therefore the largest box reaches the allowed domain inset,
    except its bottom face: loc(3,I)=I[3]-2 must clear the ground by four cells.
    The parent's mu0<1 support must independently clear every normal face by
    five cells; otherwise this registration fails rather than clipping a body.
    """
    require(support["schema"] == "force00_box_support_v1", "unknown support schema")
    require(support["phase_shift_m"] == [0.0] * 3, "support must be measured at phase zero")
    require(support["field_type"] == "Float32" and support["waterlily_version"] == "1.8.0",
            "support must use the registered Float32 WaterLily 1.8.0 moments")
    plane = support["ground_plane_solver"]
    require(isinstance(plane, (int, float)) and not isinstance(plane, bool) and math.isfinite(plane),
            "non-finite ground plane")
    require(set(support["grids"]) == GRIDS, "exactly flow_24 and flow_32 support required")
    grids = {}
    for name, item in sorted(support["grids"].items()):
        dims, s_lo, s_hi = (item[key] for key in ("flow_dims", "mu0_support_lower", "mu0_support_upper"))
        require(all(isinstance(v, list) and len(v) == 3 for v in (dims, s_lo, s_hi)), "invalid support dimensions")
        require(all(type(n) is int for values in (dims, s_lo, s_hi) for n in values), "support indices must be integers")
        count = item["mu0_support_count"]
        require(type(count) is int and count > 0, "empty parent moment support")
        require(all(3 <= a <= b <= n for a, b, n in zip(s_lo, s_hi, dims)), "invalid parent support extent")
        lower = [4, 4, max(4, math.ceil(plane + 4 + 2))]
        upper = [n - 1 for n in dims]
        require(all(b - a >= 5 and d + 1 - c >= 5
                    for a, b, c, d in zip(lower, s_lo, s_hi, upper)),
                f"{name}: no five-cell parent-support clearance in largest allowed box")
        grids[name] = {**item, "lower": lower, "upper": upper,
                       "domain_inset_cells": 2, "body_clearance_cells": 5}
    return {"schema": "force00_boxes_v1", "parent_state_sha256": genesis["state"]["state_sha256"],
            "parent_phi_fortran_sha256": genesis["state"]["phi_fortran_order_sha256"],
            "phase_shift_m": support["phase_shift_m"], "field_type": support["field_type"],
            "waterlily_version": support["waterlily_version"], "ground_plane_solver": plane,
            "definition": "largest axis-aligned pressure-cell box at domain inset 2; scene-face SDF >=4; parent mu0<1 support clearance >=5",
            "grids": grids, "source_sha256": support["source_sha256"]}


def measure_support():
    result = subprocess.run(["julia", "--project=julia/CFDSDFWaterLily", "-O1",
                             "scripts/force00_uniform_pressure.jl", "--box-support"],
                            cwd=ROOT, check=True, capture_output=True, text=True)
    return tomllib.loads(result.stdout)


def register(output=REGISTRY, *, measure=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite registered FORCE-00 boxes: {output}")
    # The measurement path verifies the registered raw and NPZ via the existing
    # v18 loader before it reports moment support. Never replace that with SDF bounds.
    support = (measure or measure_support)()
    genesis_path = ROOT / "docs/evidence/v18_genesis_2026_10_19/genesis.json"
    record = boxes_from_support(support, json.loads(genesis_path.read_text()))
    record["source_sha256"]["scripts/force00_boxes.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        handle.write(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return record


def print_toml(path=REGISTRY):
    record = json.loads(Path(path).read_text())
    require(record["schema"] == "force00_boxes_v1", "unknown box registration")
    for key in ("schema", "parent_state_sha256", "parent_phi_fortran_sha256"):
        print(f"{key} = {json.dumps(record[key])}")
    print(f'registry_sha256 = "{hashlib.sha256(Path(path).read_bytes()).hexdigest()}"')
    for name, item in sorted(record["grids"].items()):
        print(f"\n[grids.{name}]")
        for key in ("lower", "upper", "flow_dims"):
            print(f"{key} = {json.dumps(item[key])}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REGISTRY)
    parser.add_argument("--toml", action="store_true")
    args = parser.parse_args(argv)
    if args.toml:
        print_toml(args.output)
    else:
        result = register(args.output)
        print(json.dumps({"status": "REGISTERED", "grids": result["grids"]}, sort_keys=True))


if __name__ == "__main__":
    main()
