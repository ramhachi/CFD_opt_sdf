"""Independent host-side verification of a downloaded Kaggle replay artifact."""

import hashlib
import json
import math
import re
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(f"FAIL: {message}")


def scalar_list(body: str, expected_faces: int) -> list[float]:
    match = re.search(r"nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;", body, re.S)
    if match:
        values = [float(value) for value in re.findall(r"[-+0-9.eE]+", match.group(2))]
        require(len(values) == int(match.group(1)) == expected_faces, "phi list length differs from patch nFaces")
        return values
    match = re.search(r"\b(?:value\s+)?uniform\s+([-+0-9.eE]+)\s*;", body)
    require(match is not None, "missing uniform phi")
    return [float(match.group(1))] * expected_faces


def patch_blocks(text: str) -> dict[str, str]:
    start = text.find("boundaryField")
    require(start >= 0, "missing phi boundaryField")
    text = text[start:]
    found = {}
    depth = 0
    current = None
    body = []
    pending = None
    for line in text.splitlines():
        if depth == 1 and current is None:
            match = re.match(r'^\s*(?:"([^"]+)"|([\w.+-]+))\s*\{', line)
            if match:
                current = match.group(1) or match.group(2)
                body = [line]
            else:
                match = re.match(r'^\s*(?:"([^"]+)"|([\w.+-]+))\s*$', line)
                if match:
                    pending = match.group(1) or match.group(2)
                elif pending and line.strip() == "{":
                    current, body, pending = pending, [line], None
        elif current is not None:
            body.append(line)
        delta = line.count("{") - line.count("}")
        if current is not None and depth + delta == 1:
            found[current] = "\n".join(body)
            current = None
            body = []
        depth += delta
        if depth <= 0 and "{" in line:
            break
    return found


def mesh_boundary_face_counts(text: str) -> dict[str, int]:
    marker = re.search(r"\bobject\s+boundary\s*;", text)
    require(marker is not None, "mesh boundary header is missing")
    text = text[marker.end():]
    opening = re.search(r"(?m)^\s*\d+\s*$\s*\(", text)
    require(opening is not None, "mesh boundary patch list is missing")
    lines = iter(text[opening.end():].splitlines())
    faces = {}
    for line in lines:
        name = line.strip().strip('"')
        if not name:
            continue
        if name == ")":
            break
        require(re.fullmatch(r"[\w.+-]+", name) is not None, "invalid mesh patch name")
        require(next(lines, "").strip() == "{", f"missing mesh patch block for {name}")
        body, depth = [], 1
        for body_line in lines:
            depth += body_line.count("{") - body_line.count("}")
            if depth <= 0:
                break
            body.append(body_line)
        match = re.search(r"\bnFaces\s+(\d+)\s*;", "\n".join(body))
        require(match is not None, f"missing nFaces for patch {name}")
        faces[name] = int(match.group(1))
    return faces


def main() -> None:
    artifact = Path(sys.argv[1]).resolve()
    criteria_path = Path(sys.argv[2]).resolve()
    lock_path = Path(sys.argv[3]).resolve()
    registration_path = Path(sys.argv[4]).resolve()
    criteria = json.loads(criteria_path.read_text())
    lock = json.loads(lock_path.read_text())
    registration = json.loads(registration_path.read_text())
    manifest_path = artifact / "artifact_manifest.json"
    done_path = artifact / "DONE"
    require(manifest_path.is_file() and done_path.is_file(), "PASS manifest or DONE sentinel missing")
    manifest = json.loads(manifest_path.read_text())
    done = json.loads(done_path.read_text())
    require(done.get("status") == "PASS" and manifest.get("status") == "PASS", "artifact status is not PASS")
    require(done.get("artifact_manifest_sha256") == digest(manifest_path), "DONE manifest hash mismatch")
    require(manifest.get("criteria_sha256") == digest(criteria_path), "criteria hash mismatch")
    require(manifest.get("package_lock_sha256") == digest(lock_path), "package lock hash mismatch")
    require(manifest.get("runner_sha256") == registration.get("runner_sha256"), "runner hash differs from parent registration manifest")
    require(registration.get("criteria_sha256") == digest(criteria_path), "parent registration criteria hash mismatch")
    require(registration.get("kernel_metadata_sha256") == digest(criteria_path.parent / "kernel-metadata.json"), "parent registration metadata hash mismatch")
    current_files = {path.relative_to(artifact).as_posix() for path in artifact.rglob("*") if path.is_file() and path.name not in {"artifact_manifest.json", "DONE"}}
    require(current_files == set(manifest["files"]), "output inventory differs from artifact manifest")
    for relative, expected in manifest["files"].items():
        require(digest(artifact / relative) == expected, f"output hash mismatch: {relative}")

    case = artifact / "case"
    for relative, expected in criteria["fixture"]["input_file_sha256"].items():
        if relative.startswith("case_template/"):
            case_file = case / relative.removeprefix("case_template/")
            require(digest(case_file) == expected, f"case input hash mismatch: {relative}")
    fixture_root = criteria_path.parent / "fixtures"
    for path, expected in ((fixture_root / "candidate_v16.stl", criteria["fixture"]["candidate_stl_sha256"]), (fixture_root / "design_domain.stl", criteria["fixture"]["design_domain_stl_sha256"]), (fixture_root / "physical_profile.yaml", criteria["fixture"]["input_file_sha256"]["fixtures/physical_profile.yaml"])):
        require(digest(path) == expected, f"registered historical fixture hash mismatch: {path.name}")
    require(digest(case / "constant/triSurface/design_candidate.stl") == criteria["fixture"]["candidate_stl_sha256"], "case candidate STL differs from historical fixture")
    require(digest(case / "constant/triSurface/allowed_design_domain.stl") == criteria["fixture"]["design_domain_stl_sha256"], "case domain STL differs from historical fixture")
    check = (case / "log.checkMesh").read_text(errors="replace")
    failures = [int(value) for value in re.findall(r"^[ \t]*Failed (\d+) mesh checks?\.[ \t]*$", check, re.M)]
    diagnostics = re.findall(r"^[ \t]*\*\*\*.*$", check, re.M)
    mesh_cfg = criteria["gates"]["mesh"]
    cell_matches = re.findall(r"^\s*cells:\s*(\d+)\s*$", check, re.M)
    concave_matches = re.findall(r"Concave cells \(using face planes\) found, number of cells:\s*(\d+)", check)
    require(failures == [1] and len(diagnostics) == 1 and re.fullmatch(r"\s*\*\*\*Concave cells .*number of cells:\s*\d+\s*", diagnostics[0]) is not None, "mesh failure is not exactly the registered concave-cell exception")
    require(cell_matches and concave_matches, "mesh cell counts missing")
    cells, concave = int(cell_matches[-1]), int(concave_matches[-1])
    require(cells > 0 and concave / cells <= mesh_cfg["maximum_concave_cell_fraction"], "concave-cell fraction exceeds criteria")

    log = (case / "log.simpleFoam").read_text(errors="replace")
    final_residuals = {}
    for field, ceiling in criteria["gates"]["residual_final_max"].items():
        values = re.findall(rf"Solving for {field}, Initial residual = [-+0-9.eE]+, Final residual = ([-+0-9.eE]+)", log)
        require(values, f"missing {field} residual")
        final_residuals[field] = float(values[-1])
        require(math.isfinite(final_residuals[field]) and 0 <= final_residuals[field] <= ceiling, f"{field} residual exceeds gate")

    latest = max((path for path in case.iterdir() if path.is_dir() and path.name.isdigit()), key=lambda path: int(path.name))
    patches = patch_blocks((latest / "phi").read_text(errors="replace"))
    face_counts = mesh_boundary_face_counts((case / "constant/polyMesh/boundary").read_text(errors="replace"))
    require(patches.keys() == face_counts.keys(), "phi and mesh patch inventories differ")
    flux = {name: scalar_list(body, face_counts[name]) for name, body in patches.items()}
    require({"inlet", "outlet", "sideMin", "sideMax", "top", "bottom", "design_candidate"} <= flux.keys(), "required phi patches missing")
    require(all(math.isfinite(value) for values in flux.values() for value in values), "non-finite flux")
    net = sum(sum(values) for values in flux.values())
    absolute = sum(sum(abs(value) for value in values) for values in flux.values())
    imbalance = abs(net) / (0.5 * absolute)
    require(math.isfinite(imbalance) and imbalance <= criteria["gates"]["normalized_mass_imbalance_max"], "mass imbalance exceeds gate")

    force_file = case / "postProcessing/forceCoeffs/0/coefficient.dat"
    rows, header = [], None
    for line in force_file.read_text().splitlines():
        if line.startswith("#"):
            header = line.lstrip("#").split()
        elif line.strip():
            values = [float(value) for value in line.split()]
            require(header is not None and len(values) == len(header) and all(math.isfinite(value) for value in values), "invalid force history row")
            rows.append(dict(zip(header, values)))
    stationarity_cfg = criteria["gates"]["force_stationarity"]
    require(len(rows) >= stationarity_cfg["minimum_rows"], "insufficient force history")
    tail_count = max(stationarity_cfg["minimum_rows"], math.ceil(len(rows) * stationarity_cfg["tail_fraction"]))
    tail = rows[-tail_count:]
    responses = {"Cd": [row["Cd"] for row in tail], "downforce_coefficient": [-row["Cl"] for row in tail]}
    means = {}
    for name, values in responses.items():
        mean = sum(values) / len(values)
        std = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
        center = (len(values) - 1) / 2
        slope = sum((i - center) * (value - mean) for i, value in enumerate(values)) / sum((i - center) ** 2 for i in range(len(values)))
        drift = abs(slope * (len(values) - 1))
        if name == "Cd":
            require(std / abs(mean) <= stationarity_cfg["relative_std_max"] and drift / abs(mean) <= stationarity_cfg["relative_drift_max"], "Cd stationarity gate failed")
        else:
            require(std <= stationarity_cfg["absolute_std_max"] and drift <= stationarity_cfg["absolute_drift_max"], "downforce stationarity gate failed")
        means[name] = mean
    reproduction = criteria["gates"]["reproduction"]
    require(abs(means["Cd"] - reproduction["drag_coefficient_reference"]) / abs(reproduction["drag_coefficient_reference"]) <= reproduction["drag_coefficient_relative_tolerance"], "Cd reference gate failed")
    require(abs(means["downforce_coefficient"] - reproduction["downforce_coefficient_reference"]) <= reproduction["downforce_coefficient_absolute_tolerance"], "downforce reference gate failed")

    result = json.loads((artifact / "result.json").read_text())
    environment = result["environment"]
    require(environment["os_id"] == "ubuntu" and environment["os_codename"] == lock["suite"] and environment["architecture"] == lock["architecture"], "runtime OS/architecture violates package lock")
    require(environment["foamVersion"] == criteria["environment"]["foam_version"], "foamVersion violates criteria")
    require(environment.get("os_version") and environment.get("observed_os_release") and environment.get("architecture"), "runtime OS/version evidence is incomplete")
    package_records = {record["name"]: record for record in environment["package_records"]}
    require(set(package_records) == set(lock["packages"]), "installed package evidence inventory mismatch")
    for name, expected_sha in lock["packages"].items():
        record = package_records[name]
        require(record["version"] == lock["version"] and record["sha256"] == expected_sha and record["architecture"] == lock["package_architectures"][name] and digest(artifact / record["deb"]) == expected_sha, f"package evidence mismatch: {name}")
    require(environment["installed_packages"] == sorted(f"{name}={lock['version']}" for name in lock["packages"]), "installed package version list mismatch")
    require(environment["official_installer_sha256"] == lock["official_installer_sha256"] and digest(artifact / "add-debian-repo.sh") == lock["official_installer_sha256"], "repository installer hash mismatch")
    index_records = {record["name"]: record for record in environment["apt_index_records"]}
    require(set(index_records) == set(lock["indexes"]), "apt-index evidence inventory mismatch")
    for name, expected in lock["indexes"].items():
        record = index_records[name]
        require(record["url"] == expected["url"] and record["sha256"] == expected["sha256"] and digest(artifact / name) == expected["sha256"], f"apt index evidence mismatch: {name}")
    require(result["responses"]["Cd"] == means["Cd"] and result["responses"]["downforce_coefficient"] == means["downforce_coefficient"], "result disagrees with raw force history")
    require(result["mass"]["normalized_imbalance"] == imbalance, "result disagrees with raw phi fields")
    print(json.dumps({"status": "PASS", "evidence_class": "independent_host_recomputation", "runner_sha256": manifest["runner_sha256"], "cells": cells, "concave_cells": concave, "mass_imbalance": imbalance, "responses": {"Cd": means["Cd"], "downforce_coefficient": means["downforce_coefficient"], "drag_N": means["Cd"] * 0.32, "downforce_N": means["downforce_coefficient"] * 0.32}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
