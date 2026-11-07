"""Deterministic coefficient tables for WP4 software tests, never CFD evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def write_reference_bundle(folder):
    """WP5 digitize_cp manifest/CSV shape, with planted delta=1 and sum error=.01.

    The two element reading differences have opposite signs. Summing totals
    first would give .002 rather than the registered conservative .01.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    source = {"citation": "Synthetic test only", "url": "https://example.invalid/synthetic",
              "location": "Synthetic Table15 and Cp", "observable": "centre_section_pressure_integrated",
              "transition": "synthetic no physical evidence"}
    elements = []
    artifacts = []
    for index, sensitivity in enumerate((.006, -.004)):
        surfaces = {}
        for reader, direction in (("A", -1), ("B", 1)):
            surfaces[reader] = {}
            for surface, cp in (("upper", .8 + direction * sensitivity / 4),
                                ("lower", -.2 - direction * sensitivity / 4)):
                name = f"digitization_e{index}_{reader}_{surface}.csv"
                path = folder / name
                path.write_text("x/c,Cp\n" + "".join(f"{index + i / 10!r},{cp!r}\n" for i in range(11)))
                surfaces[reader][surface] = name
                artifacts.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "method": f"synthetic reader {reader}, {index}/{surface}"})
        elements.append({"id": f"element{index}", "abscissa_chord_m": .2234,
                         "x_extent": [index, index + 1], "coverage_note": "full synthetic contour", "surfaces": surfaces})
    common = {"height_m": .1, "height_mapping_note": "synthetic 100mm", "source": source}
    manifest = {"kind": "topo2d00_cp_manifest_v1", "reference_chord_m": .2234,
        "configs": [dict(common, config="E1_sharp", method="tabulated_cl", Cl=1., coefficient_chord_m=.2234,
                         coefficient_sign="downforce=-Fz", reading_sensitivity_abs=0., reading_sensitivity_note="exact planted scalar"),
                    dict(common, config="E2_sharp", method="cp", abscissa_direction="global_streamwise",
                         independence_note="different synthetic tools, no experiment", elements=elements,
                         digitizers=[{"id": "A", "operator": "reader A", "tool": "tool A"},
                                     {"id": "B", "operator": "reader B", "tool": "tool B"}])],
        "increments": [{"from": "E1_sharp", "to": "E2_sharp"}]}
    path = folder / "digitization_manifest.json"
    path.write_text(json.dumps(manifest))
    manifest_record = {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "method": "WP5-format synthetic manifest; E1 scalar extraction and E2 raw CSVs"}
    return {"manifest": manifest_record, "artifacts": [manifest_record, *artifacts]}


def input_table():
    runs = []
    for re in (1000, 3000):
        for k in (1, 2, 3):
            for phase in range(16):
                value = k + 0.2 + 0.001 * (phase - 7.5)
                runs.append(run(f"E{k}", re, phase, value))
    for k in (1, 2):
        for phase in range(4):
            runs.append(run(f"E{k}", 3000, phase, k + 0.2 + 0.001 * (phase - 1.5), "confirmation", "confirmation"))
    repeated = deepcopy(runs[0])
    repeated["role"] = "determinism"
    runs.append(repeated)
    cells = []
    for model in ("SA-WF", "SST-WF"):
        for family in ("fine30", "second"):
            realisations = []
            for i in range(8):
                names = ("E1", "E2", "E3", "E1_sharp", "E2_sharp")
                realisations.append({
                    "id": str(i), "mesh_sha256": {name: f"{i + 1:064x}" for name in names},
                    "status": {name: "SETTLED" for name in names},
                    "forces": {name: {"observable": "pressure_cl" if name.endswith("_sharp") else "total_cl",
                                      "downforce": (1, 2, 3, 1, 2)[j] + i * 0.001,
                                      "drag": (1, 2, 3, 1, 2)[j] * 0.1 + i * 0.0001}
                               for j, name in enumerate(names)},
                })
            cells.append({"model": model, "family": family, "realisations": realisations})
    return {"schema": "topo2d00-input-v1", "identity_valid": True, "cap_hit": False,
            "waterlily": runs, "rans": {"schema": "topo2d00-rans-results-v1",
            "coefficient_reference": {"chord_mm": 223.4, "height_mm": 100, "h_over_c1": 100 / 223.4, "h_over_c": 100 / 380},
            "reference": {"delta_cl": 1.0, "digitizing_uncertainty": 0.01, "observable": "pressure_cl"}, "cells": cells}, "controls": {}}


def run(config, reynolds, phase, downforce, grid="main", role="primary"):
    drag = downforce * 0.1
    return {"configuration": config, "height_mm": 100.0, "reynolds": reynolds,
            "observable": "total_cl",
            "grid": grid, "phase": str(phase), "role": role,
            "ok": True, "finite": True, "complete": True, "scene_sha256": "a" * 64,
            "readouts": {"cur": {"observable": "total_cl", "downforce": downforce, "drag": drag,
                "batches": [{"downforce": downforce + offset, "drag": drag + offset * 0.1}
                            for offset in (-0.001, 0.001, -0.001, 0.001)]}, "nds": None, "cv": None}}


def set_force(payload, config, value, re=None, include_confirmation=True):
    for row in payload["waterlily"]:
        if row["configuration"] == config and (re is None or row["reynolds"] == re) and (include_confirmation or row["grid"] == "main"):
            set_readout(row, "downforce", value)


def set_readout(row, response, value, readout="cur"):
    """Shift a synthetic mean and its equal-duration batches consistently."""
    old = row["readouts"][readout]
    delta = value - old[response]
    old[response] = value
    for batch in old["batches"]:
        batch[response] += delta


def add_auxiliary_coefficients(payload):
    """WP5-shaped software diagnostics; pressure/total effects intentionally differ."""
    for cell in payload["rans"]["cells"]:
        for rep in cell["realisations"]:
            rep["diagnostics"] = {}
            for config, force in rep["forces"].items():
                sharp = config.endswith("_sharp")
                pressure = {"Cl": force["downforce"] + (0 if sharp else 3), "Cd": force["drag"] + (0 if sharp else .2)}
                total = {"Cl": force["downforce"] - (7 if sharp else 0), "Cd": force["drag"] - (.4 if sharp else 0)}
                rep["diagnostics"][config] = {
                    "config": config, "model": cell["model"], "family": cell["family"],
                    "mesh_msh_sha256": rep["mesh_sha256"][config], "status": "COMPLETED", "usable": True,
                    "observable": force["observable"], "coefficients": {"total": total},
                    "pressure_coefficients": {"total": pressure},
                    "convergence": {"state": "settled"}, "pressure_convergence": {"state": "settled"},
                }
    return payload
