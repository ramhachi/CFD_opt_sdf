#!/usr/bin/env python3
"""Independent saved-artifact Round3 audit; imports no extractor/evaluator helpers."""

import gzip
import hashlib
import io
import json
from pathlib import Path
import numpy as np
import trimesh
from verify_xfid45_round3 import topology, orientation, distance, fidelity, volume

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def load_field(path):
    with np.load(path) as z:
        m = json.loads(str(z["metadata"]))
        return z["phi"].copy(), np.array(m["origin_m"]), float(m["spacing_m"])


def load_surface(folder, stl=False):
    if stl:
        mesh = trimesh.load(
            io.BytesIO(gzip.decompress((folder / "surface.stl.gz").read_bytes())),
            file_type="stl",
            process=False,
        )
        return np.asarray(mesh.vertices), np.asarray(mesh.faces)
    with np.load(folder / "surface.npz") as z:
        return z["vertices"], z["faces"]


def gate_map(s, ori, d, lineage):
    return dict(
        lineage=bool(lineage),
        edge_manifold=s["edge_incidence_not_two_count"] == 0,
        vertex_link_manifold=s["vertex_link_bad_count"] == 0,
        watertight=s["watertight"],
        winding=s["winding_consistent"],
        duplicate_free=s["duplicate_face_count"] == 0,
        degenerate_free=s["zero_area_face_count"] == 0
        and s["repeated_index_face_count"] == 0,
        orientation=ori["status"],
        positive_total_volume=s["signed_volume_m3"] > 0
        if ori["status"] == "PASS"
        else "N/A",
        absolute_geometry=d["within_limit"],
        clearance=s["minimum_stage_v_clearance_m"] >= 0.25,
    )


def passed(g):
    return all(v is True or v == "PASS" for v in g.values())


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main():
    reg = json.loads((OUT / "preregistration.json").read_text())
    reference = json.loads((OUT / "result.json").read_text())
    for spec in reg["sources"].values():
        assert (
            hashlib.sha256((ROOT / spec["path"]).read_bytes()).hexdigest()
            == spec["sha256"]
        )
    report = dict(
        evidence_class="independent_saved_NPZ_STL_recomputation",
        qualification_flags=reg["qualification_flags"],
        cases=[],
        fidelity_pairs=[],
        source_volumes={},
        selected_r=None,
    )
    for case, spec in reg["inputs"].items():
        path = ROOT / spec["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]
        phi, o, h = load_field(path)
        vals = {str(n): volume(phi, o, h, n) for n in (16, 32, 64)}
        expected = reference["source_volume_quadrature"][case][
            "gauss_xy_exact_linear_z"
        ]
        report["source_volumes"][case] = dict(
            values_m3=vals,
            match=all(
                np.isclose(vals[k], expected[k], rtol=1e-8, atol=h**3 * 1e-9)
                for k in vals
            ),
        )
    for ref in reference["cases"]:
        r, case = ref["r"], ref["case"]
        folder = OUT / "surfaces" / f"r{r}" / case
        phi, o, h = load_field(ROOT / reg["inputs"][case]["path"])
        # Independently verify artifact hashes and extraction provenance attestation.
        npz_ok = (
            hashlib.sha256((folder / "surface.npz").read_bytes()).hexdigest()
            == ref["surface_npz_sha256"]
        )
        stl_bytes = gzip.decompress((folder / "surface.stl.gz").read_bytes())
        stl_ok = hashlib.sha256(stl_bytes).hexdigest() == ref["raw_stl_sha256"]
        provenance = json.loads(
            gzip.decompress((folder / "lineage_orientation.json.gz").read_bytes())
        )
        lineage = bool(
            npz_ok
            and stl_ok
            and provenance["source_phi_unmodified"]
            and provenance["float32_cast_lineage_pass"]
            and ref["deterministic_repeat_match"]
            and ref["repeat_array_sha256"] == ref["raw_array_sha256"]
        )
        row = dict(r=r, case=case, individual_gate_agreement=True)
        for key, is_stl in [("double", False), ("float32", True)]:
            v, f = load_surface(folder, is_stl)
            s = topology(v, f)
            ori = orientation(v, f, phi, o, h)
            d, bounds = distance(v, f, phi, o, h)
            np.savez_compressed(
                folder / f"independent_{key}_certificates.npz", triangle_bounds=bounds
            )
            g = gate_map(s, ori, d, lineage)
            row[key] = dict(
                statistics=s,
                orientation=ori,
                identity=d,
                gates=g,
                individual_matches={k: g[k] == ref[key + "_gates"][k] for k in g},
                volume_match=bool(
                    np.isclose(
                        s["signed_volume_m3"],
                        ref[
                            "statistics" if key == "double" else "serialized_statistics"
                        ]["signed_volume_m3"],
                        rtol=1e-8,
                        atol=h**3 * 1e-9,
                    )
                ),
            )
            row["individual_gate_agreement"] &= all(
                row[key]["individual_matches"].values()
            )
        row["surface_gates_pass"] = passed(row["double"]["gates"]) and passed(
            row["float32"]["gates"]
        )
        row["aggregate_agreement"] = (
            row["surface_gates_pass"] == ref["surface_gates_pass"]
        )
        report["cases"].append(row)
        dump(OUT / "independent_result.json", report)
        print(r, case, "independent", row["individual_gate_agreement"], flush=True)
    for ref in reference["fidelity_pairs"]:
        r, case = ref["r"], ref["case"]
        basefolder = OUT / "surfaces" / f"r{r}" / "baseline"
        folder = OUT / "surfaces" / f"r{r}" / case
        bp, o, h = load_field(ROOT / reg["inputs"]["baseline"]["path"])
        tp, _, _ = load_field(ROOT / reg["inputs"][case]["path"])
        row = dict(r=r, case=case)
        for key, is_stl in [("double", False), ("float32", True)]:
            v, f = load_surface(basefolder, is_stl)
            tv, tf = load_surface(folder, is_stl)
            row[key] = fidelity(v, f, tv, tf, bp, tp, o, h)
        base = next(
            c for c in report["cases"] if c["r"] == r and c["case"] == "baseline"
        )
        target = next(c for c in report["cases"] if c["r"] == r and c["case"] == case)
        prereq = base["surface_gates_pass"] and target["surface_gates_pass"]
        row["status"] = (
            "PASS"
            if prereq
            and row["double"]["within_limit"]
            and row["float32"]["within_limit"]
            else "FAIL"
            if prereq
            else "N/A"
        )
        row["individual_gate_agreement"] = (
            all(
                row[k]["within_limit"] == ref[k]["within_limit"]
                for k in ("double", "float32")
            )
            and row["status"] == ref["status"]
        )
        report["fidelity_pairs"].append(row)
        dump(OUT / "independent_result.json", report)
        print(
            r,
            case,
            "independent fidelity",
            row["individual_gate_agreement"],
            flush=True,
        )
    report["all_individual_gates_agree"] = all(
        c["individual_gate_agreement"]
        for c in report["cases"] + report["fidelity_pairs"]
    )
    report["all_aggregate_gates_agree"] = all(
        c["aggregate_agreement"] for c in report["cases"]
    ) and all(
        c["status"] == ref["status"]
        for c, ref in zip(report["fidelity_pairs"], reference["fidelity_pairs"])
    )
    report["all_volumes_agree"] = all(
        v["match"] for v in report["source_volumes"].values()
    ) and all(
        c[k]["volume_match"] for c in report["cases"] for k in ("double", "float32")
    )
    report["candidate_pass"] = {
        str(r): all(c["surface_gates_pass"] for c in report["cases"] if c["r"] == r)
        and all(c["status"] == "PASS" for c in report["fidelity_pairs"] if c["r"] == r)
        and report["all_individual_gates_agree"]
        and report["all_volumes_agree"]
        for r in (1, 2, 4, 8)
    }
    report["selected_r"] = next(
        (
            r
            for r in (1, 2, 4, 8)
            if report["candidate_pass"][str(r)]
            and reference["candidate_pass_before_independent_verification"][str(r)]
        ),
        None,
    )
    dump(OUT / "independent_result.json", report)


if __name__ == "__main__":
    main()
