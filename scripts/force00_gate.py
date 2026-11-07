#!/usr/bin/env python3
"""Write the FORCE-00 engineering gate once, without running a solver.

Usage: python scripts/force00_gate.py --evidence-root docs/evidence/force00_2026_11

Inputs are uniform_pressure.json and force00_runs.json (schema
``force00_runs_v1``, ``runs`` list). Each run has exactly ``run``, ``phase_id``,
``state``, ``grid``, ``forces_csv`` and ``summary_json``; file paths are relative
to the evidence directory. SHA256SUMS uses repository-relative paths, as do the
existing evidence manifests. The job CSV is the original 13 columns followed
by cur/nds/cv × (fx,fy,fz,drag,downforce)_solver. All means use the registered
endpoint-clipped, trapezoidal [80,120] tU/L window and physical force scale.

F1 explicitly combines UNC-01 U01 k0/half and U2 k1..k6; it does not invent
eight U01 rows. F2 k13/14 are in f32a and k15/16 in f32b. F3 is the FID tier-A
camber_m19.7 pair at k7..k10. Existing evidence and verdicts are never modified.
C4 uses the current user's explicit 15% band; the draft's conflicting 10%
sentence is reported as well. C5 needs UNC-01's exact mode sigma: its absence
is INCOMPLETE, never a pitch proxy or an unlabelled FID substitute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fd08_v2_campaign_io import FORCE_COLUMNS, clipped_window, time_weighted_mean


ROOT = Path(__file__).resolve().parents[1]
PARENT = "v18__parent"
CANDIDATE = "v18__camber_m19.7"
READOUTS = ("R_cur", "R_nds", "R_cv")
QUANTITIES = ("fx", "fy", "fz", "drag", "downforce")
ALL_COLUMNS = FORCE_COLUMNS + tuple(f"{r}_{q}_solver" for r in ("cur", "nds", "cv") for q in QUANTITIES)
F1_PHASES = ("k0", "half", *(f"k{i}" for i in range(1, 7)))
F2_PHASES = tuple(f"k{i}" for i in range(13, 17))
F3_PHASES = tuple(f"k{i}" for i in range(7, 11))
U2_PHASES = tuple(f"z{i}{s}" for i in range(65, 69) for s in ("p", "m"))
U1_PHASES = tuple(f"{i}{s}" for i in range(49, 65) for s in ("m", "p")) + U2_PHASES
EXPECTED_RUNS = tuple(("F1", p, PARENT) for p in F1_PHASES) + tuple(
    ("F2", p, PARENT) for p in F2_PHASES) + tuple(
    ("F3", p, s) for p in F3_PHASES for s in (PARENT, CANDIDATE))
IDENTITY_KEYS = ("case_id", "flow_dims", "flow_spacing_m", "density_kg_m3", "freestream_mps",
                 "state_sha256", "phi_fortran_sha256", "canonical_sdf_origin_m")
UNIFORM_LOCAL_SOURCES = ("scripts/force00_uniform_pressure.jl", "scripts/force00_uniform_inputs.py",
    "julia/CFDSDFWaterLily/Project.toml", "julia/CFDSDFWaterLily/Manifest.toml",
    "julia/CFDSDFWaterLily/gen01/Force00.jl", *(
        "julia/CFDSDFWaterLily/src/" + name for name in (
            "CFDSDFWaterLily.jl", "Runtime.jl", "Forces.jl", "Simulation.jl", "GridSDFBody.jl", "WaterLilyBody.jl",
            "WaterLilyNormalFloorBody.jl", "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl")))
WATERLILY_SOURCE_FILES = ("Metrics.jl", "Flow.jl", "Body.jl", "AutoBody.jl", "util.jl")
_UNSET = object()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"nonfinite/invalid {label}")
    return float(value)


def read_json(path):
    def object_without_duplicates(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"nonfinite JSON value {value}")

    return json.loads(Path(path).read_text(), object_pairs_hook=object_without_duplicates, parse_constant=reject_constant)


def relative_path(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute(), "expected a relative evidence path")
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()), f"path escapes evidence directory: {name}")
    return path


class Manifest:
    """The existing SHA256SUMS format; verify only the files actually consumed."""

    def __init__(self, path, repo):
        self.repo = Path(repo).resolve()
        self.path = Path(path)
        self.hashes = {}
        for line in self.path.read_text().splitlines():
            parts = line.split(maxsplit=1)
            require(len(parts) == 2, f"malformed checksum line in {path}")
            digest, name = parts[0], parts[1].removeprefix("*")
            require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid SHA-256")
            target = relative_path(self.repo, name)
            require(target not in self.hashes, f"duplicate checksum path: {name}")
            self.hashes[target] = digest

    def check(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        require(path in self.hashes, f"unlisted artifact in {self.path}: {path}")
        require(sha256(path) == self.hashes[path], f"SHA-256 mismatch: {path}")
        return path

    def json(self, path):
        return read_json(self.check(path))


def registered_references(repo_root=ROOT):
    """Read identities and hashes from immutable evidence, never copied numbers."""
    repo = Path(repo_root)
    unc = repo / "docs/evidence/unc01_2026_10_20"
    screen = repo / "docs/evidence/screen01_2026_10_30"
    fid = repo / "docs/evidence/fid01_2026_10_21"
    manifests = {"unc": Manifest(unc / "SHA256SUMS", repo), "screen": Manifest(screen / "SHA256SUMS", repo),
                 "fid": Manifest(fid / "SHA256SUMS", repo)}
    refs, provenance = {}, {"reference_artifacts": [], "reference_matrix": {
        "F1": "UNC-01 U01 smoke k0, U01 formal half, U2 k1..k6",
        "F2": "SCREEN-01 f32a k13/14 and f32b k15/16", "F3": "FID-01 tier-A k7..k10"}}
    tables = {}
    for run, phase, state in EXPECTED_RUNS:
        if run == "F3":
            continue
        if run == "F1":
            owner, kernel, grid = "unc", "f24", "flow_24"
            if phase == "k0":
                table = unc / "u01/smoke/smoke_verify_table.json"
                directory = unc / "u01/smoke/unc01_u01_f24"
            elif phase == "half":
                table = unc / "u01/state_force_table.json"
                directory = unc / "u01/kernel_output/unc01_u01_f24"
            else:
                table = unc / "u2/verify/table_f24.json"
                directory = unc / "u2/kernel_output/unc01_u2_f24"
            campaign_path = repo / ("docs/harness/unc01_u2_campaign.json" if phase not in ("k0", "half") else "docs/harness/unc01_u01_campaign.json")
        else:
            owner, kernel, grid = "screen", ("f32a" if phase in ("k13", "k14") else "f32b"), "flow_32"
            table = screen / f"wl/verify/table_{kernel}.json"
            directory = screen / f"wl/kernel_output/screen01_f_{kernel}"
            campaign_path = repo / "docs/harness/screen01_f_campaign.json"
        if table not in tables:
            tables[table] = manifests[owner].json(table)
            require(tables[table].get("integrity", {}).get("pass") is True, f"unverified registered table: {table}")
            require(sha256(campaign_path) == tables[table]["campaign_sha256"], f"registered campaign mismatch: {campaign_path}")
            provenance["reference_artifacts"].append({"path": str(table.relative_to(repo)), "sha256": sha256(table)})
        name = f"{state}__{phase}"
        row = tables[table]["state_forces_n"][kernel][name]
        csv, summary = directory / "states" / name / f"{grid}.forces.csv", directory / "states" / name / f"{grid}.summary.json"
        manifests[owner].check(csv); manifests[owner].check(summary)
        require(sha256(csv) == row["forces_csv_sha256"] and sha256(summary) == row["summary_sha256"], "registered CSV/summary does not match verified table")
        refs[(run, phase, state)] = {"legacy": csv.read_bytes(), "summary": read_json(summary), "grid": grid,
                                     "reference_csv": str(csv.relative_to(repo)), "reference_csv_sha256": row["forces_csv_sha256"]}
    d_set = manifests["fid"].json(fid / "d_set.json")
    campaign_path = repo / "docs/harness/fid01_campaign.json"
    require(sha256(campaign_path) == d_set["campaign_sha256"], "FID campaign SHA-256 mismatch")
    campaign = read_json(campaign_path)
    for phase in F3_PHASES:
        kernel = campaign["kernels"][f"f32{phase}"]
        for state in (PARENT, CANDIDATE):
            matches = [r for r in kernel["runs"] if r["name"] == f"{state}__{phase}"]
            require(len(matches) == 1, "FID paired phase not uniquely registered")
            source_state = campaign["states"][state]
            expected = {key: kernel["case"][key] for key in ("flow_dims", "flow_spacing_m", "density_kg_m3", "freestream_mps")}
            expected.update(case_id="flow_32", state_sha256=source_state["state_sha256"],
                            phi_fortran_sha256=source_state["phi_fortran_order_sha256"],
                            canonical_sdf_origin_m=[float(v) for v in matches[0]["env"]["W4_CANONICAL_ORIGIN_M"].split(",")])
            refs[("F3", phase, state)] = {"summary": expected, "grid": "flow_32"}
    analysis = manifests["unc"].json(unc / "analysis.json")
    sigma_row = analysis["grids"]["flow_32"]["differences"].get(CANDIDATE)
    sigma = None if sigma_row is None else finite(sigma_row["downforce"]["sigma_d_n"], "UNC-01 sigma_d_n")
    if sigma is None:
        provenance["sigma_d_missing"] = f"UNC-01 analysis.json grids.flow_32.differences has no {CANDIDATE}; no mode transfer permitted"
    provenance["sigma_d_source"] = {"path": str((unc / "analysis.json").relative_to(repo)), "sha256": sha256(unc / "analysis.json"), "unit": "N", "mode": CANDIDATE}
    provenance["manifest_sha256"] = {str(v.path.relative_to(repo)): sha256(v.path) for v in manifests.values()}
    return refs, sigma, provenance


def window_mean(rows, column):
    return time_weighted_mean(clipped_window(rows, 80.0, 120.0), column)


def validate_uniform_provenance(uniform, repo, references):
    """Bind CPU rows to the same verified geometry and registered shift reader."""
    from force00_uniform_inputs import inputs

    require(repo.resolve() == ROOT.resolve(), "production closure validation uses this checkout's registered inputs")
    unc = repo / "docs/evidence/unc01_2026_10_20"
    frozen = Manifest(unc / "SHA256SUMS", repo).json(unc / "freeze1.json")["file_sha256"]
    for name in ("docs/evidence/v18_genesis_2026_10_19/genesis.json", "scripts/mode01_v18_prescreen.py",
                 "scripts/prepare_kaggle_xfid_gridphase_x3.py"):
        require(sha256(repo / name) == frozen[name], f"uniform-pressure frozen source changed: {name}")
    data = inputs()
    require(uniform.get("waterlily_version") == "1.8.0" and uniform.get("field_type") == "Float64", "uniform-pressure backend/field type mismatch")
    expected_hashes = dict(data["source_sha256"])
    for name in UNIFORM_LOCAL_SOURCES:
        expected_hashes[name] = sha256(repo / name)
    require(uniform.get("source_sha256") == expected_hashes, "uniform-pressure geometry/source SHA-256 mismatch")
    package_hashes = uniform.get("waterlily_source_sha256", {})
    require(isinstance(package_hashes, dict) and set(package_hashes) == set(WATERLILY_SOURCE_FILES), "incomplete WaterLily source hash record")
    require(all(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
                for value in package_hashes.values()), "malformed WaterLily source hash")
    # Package-file hashes are provenance reported by the CPU run. The locked
    # Project/Manifest and repository sources are checked above. Analysis of
    # archived evidence must not depend on this host's Julia package depot.
    shifts = {"U1": {r["phase_id"]: r["shift_m"] for r in data["placements"]},
              "U2": {r["phase_id"]: r["shift_m"] for r in data["sphere_placements"]}}
    spacing = {"flow_24": references[("F1", "k0", PARENT)]["summary"]["flow_spacing_m"],
               "flow_32": references[("F2", "k13", PARENT)]["summary"]["flow_spacing_m"]}
    for row in uniform["rows"]:
        kind, phase = row["run"], row["phase_id"]
        require(kind in shifts and phase in shifts[kind], "unregistered uniform-pressure placement")
        require(row.get("shift_m") == shifts[kind][phase], "uniform-pressure physical shift differs from registered/generator value")
        if kind == "U1":
            require(row.get("grid") in spacing, "unknown uniform-pressure grid")
            h = spacing[row["grid"]]
            area = data["planform_area_m2"] / h**2
            require(math.isclose(finite(row["projected_area"], "projected area"), area, rel_tol=1e-12), "U1 projected area differs from verified v18 genesis")
        else:
            require(row.get("radius_cells") in (8, 16, 32), "unknown sphere radius")
            # W2a physical radius: Simulation.jl:20; that exact source is hashed
            # above. A changed fixture requires a reviewed reader update.
            h = 0.5 / row["radius_cells"]
        require(isinstance(row.get("shift_cells"), list) and len(row["shift_cells"]) == 3, "missing placement shift in solver cells")
        require(all(math.isclose(finite(value, "cell shift"), shift / h, rel_tol=1e-12, abs_tol=1e-15)
                    for value, shift in zip(row["shift_cells"], shifts[kind][phase])), "uniform-pressure cell shift differs")


def read_run(item, evidence, manifest, reference):
    csv = relative_path(evidence, item["forces_csv"])
    summary_path = relative_path(evidence, item["summary_json"])
    summary = manifest.json(summary_path)
    raw = manifest.check(csv).read_bytes()
    require(summary.get("force_csv_sha256") == hashlib.sha256(raw).hexdigest(), "job summary CSV hash mismatch")
    for key in IDENTITY_KEYS:
        require(summary.get(key) == reference["summary"][key], f"run identity mismatch: {key}")
    require(item["grid"] == summary["case_id"] == reference["grid"], "run grid mismatch")
    expected = {"waterlily_version": "1.8.0", "waterlily_backend": "KernelAbstractions", "gpu_name": "Tesla T4",
                "burn_in_t_u_l": 80.0, "t_end_target": 120.0, "sample_every_solver_steps": 8,
                "finite_u": True, "finite_p": True, "finite_forces": True}
    for key, value in expected.items():
        require(summary.get(key) == value, f"run backend/window mismatch: {key}")
    lower, upper = summary.get("force00_cv_box_lower"), summary.get("force00_cv_box_upper")
    require(all(isinstance(v, list) and len(v) == 3 and all(type(i) is int for i in v) for v in (lower, upper)), "missing/invalid CV box index record")
    # Flow allocates two ghost cells: two physical cells of inset require
    # lower>=4 and upper<=size(p)-3==flow_dims-1, as in Force00.jl.
    require(all(4 <= lo <= hi <= dim - 1 for lo, hi, dim in zip(lower, upper, summary["flow_dims"])), "CV box violates ordered two-cell domain inset")
    lines = raw.splitlines(keepends=True)
    require(lines and tuple(lines[0].decode().strip().split(",")) == ALL_COLUMNS, "FORCE-00 CSV schema mismatch")
    rows, projected = [], []
    for line_number, line in enumerate(lines):
        require(line.endswith(b"\n"), "CSV needs newline-terminated rows")
        fields = line.rstrip(b"\r\n").split(b",")
        require(len(fields) == len(ALL_COLUMNS), "CSV row width mismatch")
        ending = b"\r\n" if line.endswith(b"\r\n") else b"\n"
        projected.append(b",".join(fields[:len(FORCE_COLUMNS)]) + ending)
        if line_number == 0:
            continue
        row = {key: finite(float(value), key) for key, value in zip(ALL_COLUMNS, fields)}
        require(all(fields[ALL_COLUMNS.index(f"cur_{q}_solver")] == fields[FORCE_COLUMNS.index(f"{q}_solver")] for q in QUANTITIES), "cur columns differ from original force bytes")
        for readout in ("", "cur_", "nds_", "cv_"):
            require(row[f"{readout}drag_solver"] == row[f"{readout}fx_solver"] and row[f"{readout}downforce_solver"] == -row[f"{readout}fz_solver"], "force projection identity failed")
        require(all(math.isclose(row[f"{axis}_solver"], row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"], rel_tol=1e-6, abs_tol=1e-8) for axis in ("fx", "fy", "fz")), "legacy force component identity failed")
        rows.append(row)
    require(len(rows) >= 4, "insufficient force history")
    require(all(b["step"] > a["step"] and b["t_u_l"] > a["t_u_l"] for a, b in zip(rows, rows[1:])), "force step/time is not strictly increasing")
    steps, samples = summary.get("steps"), summary.get("force_samples")
    require(type(steps) is int and steps > 0, "invalid final solver step")
    require(type(samples) is int and samples == len(rows) == (steps + 7) // 8,
            "force sample count/cadence differs from completed steps")
    # Every regular sample is required, followed only by a final off-cadence
    # endpoint when needed. F3 cannot rely on C1's legacy-byte comparison.
    require(all(row["step"] == min(8 * (index + 1), steps) for index, row in enumerate(rows)),
            "force sampling cadence differs")
    require(rows[-1]["t_u_l"] == finite(summary.get("t_end_reached"), "t_end_reached") >= 120.0
            and all(row["t_u_l"] < 120.0 for row in rows[:-1]), "force final time/horizon mismatch")
    scale = finite(summary["density_kg_m3"], "density") * finite(summary["freestream_mps"][0], "velocity") ** 2 * finite(summary["flow_spacing_m"], "spacing") ** 2
    require(scale > 0, "nonpositive physical force scale")
    means = {}
    for readout in READOUTS:
        prefix = readout.removeprefix("R_") + "_"
        # Reuse the frozen window helper, whose endpoint interpolator expects
        # the legacy13 columns; remap this readout into that schema.
        remapped = [{key: row[key] for key in FORCE_COLUMNS} | {f"{q}_solver": row[f"{prefix}{q}_solver"] for q in QUANTITIES} for row in rows]
        means[readout] = {q: window_mean(remapped, f"{q}_solver") * scale for q in QUANTITIES}
    return means, b"".join(projected), {"csv_sha256": sha256(csv), "summary_sha256": sha256(summary_path),
        "force_scale_n_per_solver_force": scale, "force00_cv_box_lower": lower, "force00_cv_box_upper": upper}


def closure(uniform):
    require(uniform.get("schema") == "force00_uniform_pressure_v1", "unknown uniform-pressure schema")
    expected = {("U1", g, p) for g in ("flow_24", "flow_32") for p in U1_PHASES} | {("U2", r, p) for r in (8, 16, 32) for p in U2_PHASES}
    rows = {}
    for row in uniform["rows"]:
        kind = row["run"]
        require(kind in ("U1", "U2"), "unknown uniform-pressure run")
        key = (kind, row["grid"] if kind == "U1" else row["radius_cells"], row["phase_id"])
        require(key in expected and key not in rows, "unknown/duplicate uniform-pressure placement")
        require(row["body"] == ("v18_parent" if kind == "U1" else "w2a_sphere"), "uniform-pressure body mismatch")
        area = finite(row["projected_area"], "projected area")
        require(area > 0, "nonpositive projected area")
        if kind == "U2":
            require(math.isclose(area, math.pi * row["radius_cells"] ** 2, rel_tol=1e-12), "sphere projected area mismatch")
        norms = {}
        for readout in READOUTS:
            vector = row[readout.removeprefix("R_")]
            require(isinstance(vector, list) and len(vector) == 3, "uniform force must have three components")
            norms[readout] = math.hypot(*(finite(v, "uniform force") for v in vector))
        rows[key] = (area, norms)
    missing = sorted(expected - rows.keys(), key=str)
    result = {}
    for readout in READOUTS:
        groups = {}
        for kind, grid in (("U1", "flow_24"), ("U1", "flow_32"), ("U2", 8), ("U2", 16), ("U2", 32)):
            values = [(area, norms) for (k, g, _), (area, norms) in rows.items() if (k, g) == (kind, grid)]
            norms = [v[readout] for _, v in values]
            ratios = [v[readout] / a for a, v in values]
            cur_max = max((v["R_cur"] for _, v in values), default=0.0)
            maximum = max(norms, default=0.0)
            threshold = 1e-4 if kind == "U1" else 1e-3  # FORCE-00 rev0 §4 C2.
            groups[f"{kind}/{grid}"] = {"count": len(values), "max_norm": maximum,
                "rms_norm": math.sqrt(statistics.mean(v * v for v in norms)) if norms else None,
                "max_relative_to_projected_area": max(ratios, default=None), "relative_threshold": threshold,
                "reduction_factor_vs_cur": cur_max / maximum if maximum > 0 else None,
                "hundredfold_reduction_descriptive": maximum <= cur_max / 100.0,
                "pass": bool(values) and all(v <= threshold for v in ratios)}
        status = "INCOMPLETE" if missing else "PASS" if all(g["pass"] for g in groups.values()) else "FAIL_CLOSURE"
        result[readout] = {"status": status, "groups": groups}
    return result, [f"uniform placement {key}" for key in missing]


def evaluate(evidence_root, *, repo_root=ROOT, references=None, sigma_d_n=_UNSET):
    """Pure analysis; optional verified-catalog injection is for synthetic tests."""
    evidence, repo = Path(evidence_root).resolve(), Path(repo_root).resolve()
    provenance = {}
    production = references is None
    if references is None:
        references, registered_sigma, provenance = registered_references(repo)
        require(sigma_d_n is _UNSET, "production sigma must come from registered evidence")
        sigma_d_n = registered_sigma
    require(sigma_d_n is not _UNSET, "synthetic analysis must declare sigma or its absence")
    if sigma_d_n is not None:
        require(finite(sigma_d_n, "sigma_d_n") >= 0, "sigma_d must be nonnegative")
    result = {"schema": "force00_gate_v1", "evidence_class": "engineering_capability_gate", "status": "INCOMPLETE",
              "adopted_readout": "NONE", "criteria": {}, "readouts": {}, "missing": [], "provenance": provenance}
    criteria, missing = result["criteria"], result["missing"]
    try:
        manifest = Manifest(evidence / "SHA256SUMS", repo)
    except FileNotFoundError:
        result["missing"] = ["FORCE-00 SHA256SUMS"]
        result["criteria"] = {key: {"status": "INCOMPLETE"} for key in ("C1", "C2", "C3", "C4", "C5")}
        result["readouts"] = {r: "INCOMPLETE" for r in READOUTS[1:]}
        return result
    provenance["input_manifest_sha256"] = sha256(manifest.path)
    try:
        uniform = manifest.json(evidence / "uniform_pressure.json")
        if production:
            validate_uniform_provenance(uniform, repo, references)
            provenance["uniform_pressure_sha256"] = sha256(evidence / "uniform_pressure.json")
            provenance["uniform_waterlily_source_sha256_as_reported"] = uniform["waterlily_source_sha256"]
        criteria["C2"], absent = closure(uniform); missing.extend(absent)
    except FileNotFoundError:
        missing.append("uniform_pressure.json")
        criteria["C2"] = {r: {"status": "INCOMPLETE"} for r in READOUTS}
    try:
        run_manifest = manifest.json(evidence / "force00_runs.json")
        require(run_manifest.get("schema") == "force00_runs_v1", "unknown FORCE-00 run schema")
        items = run_manifest["runs"]
    except FileNotFoundError:
        items = []
    found, means, regressions, artifacts = set(), {}, [], []
    for item in items:
        require(set(item) == {"run", "phase_id", "state", "grid", "forces_csv", "summary_json"}, "unknown/missing FORCE-00 run fields")
        key = (item["run"], item["phase_id"], item["state"])
        require(key in EXPECTED_RUNS and key not in found, f"unknown/duplicate FORCE-00 run: {key}")
        found.add(key)
        try:
            reference = references[key]
            force, projected, hashes = read_run(item, evidence, manifest, reference)
        except (FileNotFoundError, KeyError) as error:
            missing.append(f"{key}: missing artifact/reference {error}")
            continue
        means[key] = force
        artifacts.append({"run": key, **hashes})
        if key[0] in ("F1", "F2"):
            regressions.append({"run": key, "pass": projected == reference["legacy"],
                                "projected_csv_sha256": hashlib.sha256(projected).hexdigest(),
                                "registered_csv_sha256": hashlib.sha256(reference["legacy"]).hexdigest()})
    missing.extend(f"missing run {key}" for key in EXPECTED_RUNS if key not in found)
    provenance["run_artifacts"] = artifacts
    c1_complete = all(key in means for key in EXPECTED_RUNS if key[0] in ("F1", "F2"))
    criteria["C1"] = {"status": "FAIL" if any(not r["pass"] for r in regressions) else "PASS" if c1_complete else "INCOMPLETE", "rows": regressions}
    if criteria["C1"]["status"] == "FAIL":
        result.update(status="FAIL", readouts={r: "FAIL_REGRESSION" for r in READOUTS[1:]})
        return result  # C1 specifies stop on a changed registered harness path.
    f1_complete = all(("F1", p, PARENT) in means for p in F1_PHASES)
    criteria["C3"], criteria["C4"] = {}, {"adoption_relative_band": 0.15,
        "draft_conflict": "rev0 PASS sentence says10%; current user and C4 table specify15%; both reported"}
    if f1_complete:
        f1 = {r: [means[("F1", p, PARENT)][r]["downforce"] for p in F1_PHASES] for r in READOUTS}
        cur_sd, cur_mean = statistics.stdev(f1["R_cur"]), statistics.mean(f1["R_cur"])
        criteria["C3"]["R_cur"] = {"phase_sd_n": cur_sd, "phase_mean_n": cur_mean}
        for r in READOUTS[1:]:
            sd, mean = statistics.stdev(f1[r]), statistics.mean(f1[r])
            criteria["C3"][r] = {"status": "PASS" if sd <= cur_sd else "FAIL_PHASE", "phase_sd_n": sd, "phase_mean_n": mean, "cur_phase_sd_n": cur_sd}
            same_sign = mean * cur_mean > 0
            relative = abs(mean - cur_mean) / abs(cur_mean) if cur_mean != 0 else None
            within15 = same_sign and relative <= 0.15
            criteria["C4"][r] = {"status": "FAIL_SIGN" if not same_sign else "PASS" if within15 else "HOLD",
                "same_sign": same_sign, "relative_shift": relative, "within_15_percent": within15,
                "within_10_percent": same_sign and relative <= 0.10, "phase_mean_n": mean, "cur_phase_mean_n": cur_mean}
    else:
        for r in READOUTS[1:]:
            criteria["C3"][r] = criteria["C4"][r] = {"status": "INCOMPLETE"}
    criteria["C5"] = {"descriptive_only": True, "sigma_d_n": sigma_d_n, "sigma_mode": CANDIDATE}
    f3_complete = all(("F3", p, s) in means for p in F3_PHASES for s in (PARENT, CANDIDATE))
    if sigma_d_n is None:
        missing.append(f"UNC-01 sigma_d_n for {CANDIDATE}")
    if f3_complete:
        differences = {r: [means[("F3", p, CANDIDATE)][r]["downforce"] - means[("F3", p, PARENT)][r]["downforce"] for p in F3_PHASES] for r in READOUTS}
        cur_difference = statistics.mean(differences["R_cur"])
        criteria["C5"]["R_cur"] = {"paired_differences_n": differences["R_cur"], "mean_difference_n": cur_difference}
        for r in READOUTS[1:]:
            shift = abs(statistics.mean(differences[r]) - cur_difference)
            criteria["C5"][r] = {"status": "COMPLETE" if sigma_d_n is not None else "INCOMPLETE",
                "paired_differences_n": differences[r], "mean_difference_n": statistics.mean(differences[r]),
                "difference_shift_n": shift, "below_sigma_d": shift < sigma_d_n if sigma_d_n is not None else None}
    else:
        for r in READOUTS[1:]:
            criteria["C5"][r] = {"status": "INCOMPLETE"}
    for r in READOUTS[1:]:
        statuses = [criteria[k][r]["status"] for k in ("C2", "C3", "C4")]
        result["readouts"][r] = next((s for s in statuses if s.startswith("FAIL")), "INCOMPLETE" if missing else "HOLD" if "HOLD" in statuses else "PASS")
    if missing:
        return result
    passing = [r for r in READOUTS[1:] if result["readouts"][r] == "PASS"]
    result["adopted_readout"] = "R_cv" if "R_cv" in passing else "R_nds" if "R_nds" in passing else "NONE"
    result["status"] = "PASS" if passing else "HOLD" if "HOLD" in result["readouts"].values() else "FAIL"
    return result


def write_gate(evidence_root, **kwargs):
    output = Path(evidence_root) / "gate.json"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite write-once gate: {output}")
    result = evaluate(evidence_root, **kwargs)
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with output.open("x") as handle:
        handle.write(encoded)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "docs/evidence/force00_2026_11")
    args = parser.parse_args(argv)
    result = write_gate(args.evidence_root)
    print(json.dumps({"status": result["status"], "adopted_readout": result["adopted_readout"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
