#!/usr/bin/env python3
"""Verify a version-specific Kaggle K0 download before accepting its evidence."""

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "docs/evidence/kaggle_k0_criteria_2026_09.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(a, b):
    require(math.isfinite(a) and math.isfinite(b) and a != 0 and b != 0,
            "response is zero or non-finite")
    return abs(a - b) / max(abs(a), abs(b))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_files(folder):
    require((folder / "DONE").is_file() and (folder / "outcome.json").is_file(),
            "completion marker or outcome missing")
    manifest = json.loads((folder / "sha256.json").read_text())
    names = {file.name for file in folder.iterdir() if file.is_file()}
    require(set(manifest) == names - {"sha256.json", "DONE"}, "artifact inventory mismatch")
    for name, expected in manifest.items():
        require(Path(name).name == name and sha256(folder / name) == expected,
                f"artifact SHA-256 mismatch: {name}")
    return len(manifest)


def verify(download):
    k0 = download / "k0"
    criteria = json.loads(CRITERIA.read_text())
    require(sha256(CRITERIA) == CRITERIA.with_suffix(".json.sha256").read_text().strip(),
            "K0 criteria hash mismatch")
    reference = ROOT / criteria["colab_reference"]["evidence_path"]
    require(sha256(reference) == criteria["colab_reference"]["evidence_sha256"],
            "Colab reference hash mismatch")
    verified_files = verify_files(k0)

    outcome = json.loads((k0 / "outcome.json").read_text())
    require(outcome["source_commit"] == criteria["source_commit"], "source commit drift")
    require(outcome["project_sha256"] == criteria["project_sha256"], "Julia Project drift")
    require(outcome["manifest_sha256"] == criteria["manifest_sha256"], "Julia Manifest drift")
    rows = json.loads((k0 / "fingerprint.json").read_text())["gpu_csv"]
    require(len(rows) == 2 and all("Tesla T4" in row for row in rows), "T4 inventory mismatch")
    ref_drag = criteria["colab_reference"]["window_mean_drag"]
    summaries = {"single": outcome["single"], **outcome["dual"]}
    require(set(summaries) == {"single", "gpu0", "gpu1"}, "case inventory mismatch")
    for name, summary in summaries.items():
        require(summary["mode"] == "analytic" and summary["steps"] == criteria["colab_reference"]["steps"],
                f"analytic completion mismatch: {name}")
        require(summary["t_end_reached"] >= 60, f"time horizon not reached: {name}")
        require(all(summary[key] is True for key in ("finite_u", "finite_p", "finite_forces")),
                f"non-finite fields or forces: {name}")
        require(summary["window_mean_drag"] > 0, f"drag sign invalid: {name}")
        require(relative(summary["first_half_mean_drag"], summary["second_half_mean_drag"]) <= 0.02,
                f"stationarity failed: {name}")
        require(relative(summary["window_mean_drag"], ref_drag) <= 0.0001,
                f"Colab agreement failed: {name}")
        require(0 < summary["peak_vram_bytes"] < summary["vram_total_bytes"],
                f"VRAM record invalid: {name}")
        require(sha256(k0 / f"{name}.forces.csv") == summary["csv_sha256"],
                f"force CSV hash mismatch: {name}")
        if name != "single":
            require(relative(summary["window_mean_drag"], outcome["single"]["window_mean_drag"]) <= 0.000001,
                    f"dual/single agreement failed: {name}")
    intervals = outcome["intervals"]
    require(set(intervals) == {"gpu0", "gpu1"}, "worker interval inventory mismatch")
    require(all(item["exit_code"] == 0 for item in intervals.values()), "Julia worker exit failure")
    require(max(item["start_monotonic"] for item in intervals.values()) < min(
        item["end_monotonic"] for item in intervals.values()), "Julia workers did not overlap")
    return {"verified_files": verified_files,
            "single_drag": outcome["single"]["window_mean_drag"],
            "colab_relative_difference": relative(outcome["single"]["window_mean_drag"], ref_drag),
            "dual_drags": {key: value["window_mean_drag"] for key, value in outcome["dual"].items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path, help="version-specific kaggle kernels output directory")
    print(json.dumps(verify(parser.parse_args().download), indent=2, sort_keys=True))
