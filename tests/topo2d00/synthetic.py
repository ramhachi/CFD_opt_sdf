"""Deterministic coefficient tables for WP4 software tests, never CFD evidence."""
from copy import deepcopy


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
