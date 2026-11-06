"""Read registered FORCE-00 geometry/placements; bridge JSON and stdlib TOML.

The pinned Julia project has only WaterLily as a direct dependency. This small
CPU helper reuses the existing Python NPZ loader and Halton generator without
adding a Julia JSON dependency or copying registered placement numbers.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]


def verified(path: Path, expected: str) -> str:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return actual


def inputs() -> dict:
    import mode01_v18_prescreen
    from prepare_kaggle_xfid_gridphase_x3 import phase_cases

    genesis = ROOT / "docs/evidence/v18_genesis_2026_10_19"
    fid = ROOT / "docs/evidence/fid01_2026_10_21"
    g = json.loads((genesis / "genesis.json").read_text())
    state, _ = mode01_v18_prescreen.load_parent()
    raw = genesis / "v18_parent.phi_f4_fortran.raw"
    npz = genesis / "v18_parent.npz"
    hashes = {
        raw.relative_to(ROOT).as_posix(): verified(raw, g["state"]["phi_fortran_order_sha256"]),
        npz.relative_to(ROOT).as_posix(): verified(npz, g["state"]["npz_sha256"]),
    }
    frozen = {}
    for line in (fid / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        frozen[path.lstrip("*")] = digest
    placements = {}
    for i in range(1, 5):
        path = fid / f"of/criteria/v1_{i}.json"
        rel = path.relative_to(ROOT).as_posix()
        hashes[rel] = verified(path, frozen[rel])
        record = json.loads(path.read_text())
        registered_tags = record["shift_design"]["shift_tags"]
        for case in record["case_order"]:
            if case["state"] == "v18__parent":
                tag = case["id"].rsplit("_", 1)[1]
                if tag not in registered_tags or tag in placements:
                    raise ValueError("duplicate or unregistered FID placement")
                placements[tag] = case["shift_m"]
    if len(placements) != 32:
        raise ValueError("FID V1 must supply exactly 32 registered shifts")
    rows = [{"phase_id": tag, "kind": "registered_fid_v1", "shift_m": placements[tag]}
            for tag in sorted(placements, key=lambda t: (int(t[:-1]), t[-1]))]
    # Additional z-only phases: the same generator, next four mirror pairs.
    start = max(int(tag[:-1]) for tag in placements) + 1
    spheres = []
    for case in phase_cases("sphere", "z", 4, start=start):
        tag = "z" + case["id"].rsplit("_", 1)[1].lstrip("0")
        shift = case["shift_m"]
        rows.append({"phase_id": tag, "kind": "additional_z_only", "shift_m": [0.0, 0.0, shift[2]]})
        spheres.append({"phase_id": tag, "shift_m": shift})
    for path in (genesis / "genesis.json", ROOT / "scripts/mode01_v18_prescreen.py",
                 ROOT / "scripts/prepare_kaggle_xfid_gridphase_x3.py"):
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "raw_path": str(raw), "shape": list(state.phi.shape),
        "origin_m": list(state.origin_m), "spacing_m": state.spacing_m,
        "margin_m": 0.15, "planform_area_m2": g["measurements"]["planform_area_m2"],
        "placements": rows, "sphere_placements": spheres, "source_sha256": hashes,
    }


def print_inputs(data: dict) -> None:
    # Only scalar/array values and array-of-table records cross this boundary.
    for key, value in data.items():
        if key not in ("placements", "sphere_placements", "source_sha256"):
            print(f"{key} = {json.dumps(value, allow_nan=False)}")
    for group in ("placements", "sphere_placements"):
        for row in data[group]:
            print(f"\n[[{group}]]")
            for key, value in row.items():
                print(f"{key} = {json.dumps(value, allow_nan=False)}")
    print("\n[source_sha256]")
    for key, value in sorted(data["source_sha256"].items()):
        print(f"{json.dumps(key)} = {json.dumps(value)}")


if __name__ == "__main__":
    if sys.argv[1:] == ["inputs"]:
        print_inputs(inputs())
    elif len(sys.argv) == 3 and sys.argv[1] == "json":
        import tomllib  # Python 3.11+ is needed only for the Julia output bridge.

        data = tomllib.loads(sys.stdin.read())
        encoded = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        with Path(sys.argv[2]).open("xb") as output:
            output.write(encoded)
    else:
        raise SystemExit("usage: force00_uniform_inputs.py inputs | json <new-output.json>")
