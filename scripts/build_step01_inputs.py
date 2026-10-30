#!/usr/bin/env python3
"""Host registrar of the STEP-01 (#47) input states (solver-free): the combined directions, and the inventory of all 47 runs (3 kernels, each with its own baseline).

Every state is generated twice and the two results must be byte identical: by the numpy function the Kaggle runner uses (scripts/step01_states.py) and by
`cfd_sdf.fd08_v2_campaign.construct_state` (the FD-08 construction, with its geometry gates).  Writes inventory.json and the two combined-direction raws.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import step01_states as S  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.fd08_v2_campaign import MARGIN_GATE_M, construct_state, state_identity  # noqa: E402

E = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
IN = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
BASELINE_RAW = ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
BASELINE_SHA = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
CANONICAL_NPZ = Path("/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v17/sdf_design_state.npz")
CANONICAL_NPZ_SHA = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
MANIFEST = IN / "inputs_manifest.json"
MARGIN_TOLERANCE_M = 1e-6
FORMAL_CRITERIA = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
FD08_BASELINE_CSV_SHA = S.FD08_BASELINE_CSV_SHA256
FD08_BASELINE_FORCES_N = {"drag_n": 0.3239039699743226, "downforce_n": 0.3316344583180616}
FORMAL_CRITERIA_SHA = "31b29cccc9d3fd6912a910b09694a8230f9ee0aa84e6a418161881ffbcf907be"


def load_inputs() -> tuple[np.ndarray, dict[str, np.ndarray], dict]:
    manifest = json.loads(MANIFEST.read_text())
    assert S.sha256_bytes(BASELINE_RAW.read_bytes()) == BASELINE_SHA == manifest["baseline_phi"]["sha256"]
    dirs = {}
    for name in S.SINGLE_DIRECTIONS:
        entry = manifest["directions"][name]
        raw = (IN / entry["file"]).read_bytes()
        assert S.sha256_bytes(raw) == entry["sha256_fortran_raw"], name
        d = S.read_f4(IN / entry["file"])
        assert float(np.max(np.abs(d))) == 1.0, name
        dirs[name] = d
    return S.read_f4(BASELINE_RAW), dirs, manifest


def build(canonical: Path, write_combo_raws: bool) -> dict:
    phi, dirs, manifest = load_inputs()
    parent = SDFDesignState.load(canonical)
    assert S.sha256_bytes(canonical.read_bytes()) == CANONICAL_NPZ_SHA
    assert S.to_raw(parent.phi) == S.to_raw(phi), "the canonical NPZ phi differs from the baseline raw"
    base_id = state_identity(parent)
    combos = {}
    for pair in S.COMBOS:
        d, m = S.combo_direction(dirs[pair[0]], dirs[pair[1]])
        key = "+".join(pair)
        raw = S.to_raw(d)
        path = E / "inputs" / f"combo_{pair[0].split('_')[0]}_{pair[1].split('_')[0]}.dir_f4_fortran.raw"
        if write_combo_raws:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        else:
            assert path.read_bytes() == raw, f"committed combined direction differs: {path.name}"
        combos[key] = {"direction": d, "m_max_abs_sum": m, "file": str(path.relative_to(ROOT)), "sha256_fortran_raw": S.sha256_bytes(raw),
                       "component_step_mm": S.COMBO_STEP_MM / m, "pair": list(pair)}
    rows: list[dict] = []
    seen: set[bytes] = set()
    for kernel, plan in S.all_plans().items():
        for item in plan:
            row = {"kernel": kernel, **item}
            if item["kind"] == "baseline":
                child, audit = parent, {"changed_node_count": 0, "maximum_pointwise_change_m": 0.0, "zero_level_margin_m": base_id["margin_m"]}
                raw = S.to_raw(phi)
            else:
                if item["kind"] == "single":
                    d = dirs[item["directions"][0]]
                else:
                    d = combos["+".join(item["directions"])]["direction"]
                raw_np = S.perturb(phi, d, item["step_mm"], item["sign"])
                child, audit = construct_state(parent, d, item["step_mm"], item["sign"])
                raw = S.to_raw(child.phi)
                assert raw == S.to_raw(raw_np), f"runner-style numpy generation differs from construct_state: {item['name']}"
                assert audit["zero_level_margin_m"] >= MARGIN_GATE_M
                row["requested_max_change_m"] = item["step_mm"] / 1000.0
                row["realized_over_requested"] = audit["maximum_pointwise_change_m"] / (item["step_mm"] / 1000.0)
                if item["kind"] == "combo":
                    pair = combos["+".join(item["directions"])]
                    row["combo_m_max_abs_sum"] = pair["m_max_abs_sum"]; row["component_step_mm"] = pair["component_step_mm"]
            if item["kind"] == "baseline":
                assert raw == S.to_raw(phi)
            else:
                assert raw not in seen and raw != S.to_raw(phi), f"a perturbed state repeats another state or the baseline: {item['name']}"
                seen.add(raw)
            ident = state_identity(child)
            with tempfile.TemporaryDirectory() as tmp:
                p1, p2 = Path(tmp) / "a.npz", Path(tmp) / "b.npz"
                child.save(p1); child.save(p2)
                npz1, npz2 = S.sha256_bytes(p1.read_bytes()), S.sha256_bytes(p2.read_bytes())
            assert npz1 == npz2, "NPZ serialisation is not deterministic"
            row.update({"phi_fortran_order_sha256": ident["phi_fortran_order_sha256"], "phi_c_order_sha256": ident["phi_c_order_sha256"], "state_sha256": ident["state_sha256"],
                        "npz_sha256": npz1, "changed_node_count": int(audit["changed_node_count"]), "maximum_pointwise_change_m": float(audit["maximum_pointwise_change_m"]),
                        "zero_level_margin_m": float(audit["zero_level_margin_m"]), "margin_tolerance_m": MARGIN_TOLERANCE_M})
            rows.append(row)
    assert len(rows) == 47 and sum(1 for r in rows if r["kind"] == "baseline") == 3
    criteria_bytes = FORMAL_CRITERIA.read_bytes()
    assert S.sha256_bytes(criteria_bytes) == FORMAL_CRITERIA_SHA
    canonical = json.loads(criteria_bytes)["canonical_state"]
    job_env_common = {"W4_CANONICAL_STATE_LABEL": "v17", "W4_SOURCE_SURFACE_SHA256": canonical["source_surface_sha256"], "W4_POINT_SHAPE": ",".join(map(str, canonical["shape"])),
                      "W4_CELL_SHAPE": ",".join(str(int(v) - 1) for v in canonical["shape"]), "W4_CANONICAL_ORIGIN_M": ",".join(map(str, canonical["origin_m"])),
                      "W4_CANONICAL_DESIGN_SPACING_M": str(canonical["spacing_m"]), "W4_MARGIN_TOLERANCE_M": "1e-6", "W4_MARGIN_GATE_M": "0.15"}
    return {"kind": "step01_state_inventory", "job_env_common": job_env_common, "formal_criteria_sha256": FORMAL_CRITERIA_SHA, "fd08_baseline_reference": {"forces_csv_sha256": FD08_BASELINE_CSV_SHA, "host_recomputed_n": FD08_BASELINE_FORCES_N, "source": "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_kernel_output.tar.gz (member ...baseline_v17__flow_24.forces.csv); a reference for the byte-identity gate only, not a reused record"}, "baseline": {"phi_fortran_sha256": BASELINE_SHA, "canonical_npz_sha256": CANONICAL_NPZ_SHA, "state_sha256": base_id["state_sha256"],
                                                          "margin_m": base_id["margin_m"], "path": str(BASELINE_RAW.relative_to(ROOT))},
            "directions": {n: {"file": manifest["directions"][n]["file"], "sha256_fortran_raw": manifest["directions"][n]["sha256_fortran_raw"]} for n in S.SINGLE_DIRECTIONS},
            "combined_directions": {k: {x: v for x, v in c.items() if x != "direction"} for k, c in combos.items()},
            "h_m": S.SPACING_M, "step_mm": list(S.STEP_MM), "fractions_h": list(S.FRACTIONS_H), "combo_step_mm": S.COMBO_STEP_MM, "margin_gate_m": MARGIN_GATE_M,
            "perturbation": "float32(float64(phi) + (sign*eps_m)*float64(direction)), eps_m = step_mm/1000 (cfd_sdf.fd08_v2_campaign.construct_state)",
            "kernels": {k: [r["name"] for r in rows if r["kernel"] == k] for k in S.KERNELS}, "states": rows}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--canonical", type=Path, default=CANONICAL_NPZ)
    p.add_argument("--check", action="store_true", help="re-derive and compare with the committed inventory and combined directions; writes nothing")
    args = p.parse_args()
    inv = build(args.canonical, write_combo_raws=not args.check)
    data = (json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()
    out = E / "inventory.json"
    if args.check:
        assert out.read_bytes() == data, "the committed inventory differs from the re-derivation"
        print("inventory reproduced", hashlib.sha256(data).hexdigest())
        return
    if out.exists():
        sys.exit("refusing to overwrite the inventory")
    E.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data); out.with_name("inventory.json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
