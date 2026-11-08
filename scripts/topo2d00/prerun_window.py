"""Derive a write-once TOPO-2D parent window from the actual E1 force history.

Amendment 7 fixes the engineering estimator. Candidate 100-c1/U burn blocks
start every 50 c1/U from the first sample time. The earliest within +/-2 SE
of the remaining history's mean sets B=max(80, candidate start); SE uses the
remainder's complete 20-c1/U batch means. If none qualifies, B=130 is recorded
with BURN_IN_FALLBACK. S0 is the largest point estimate over complete 10, 20
and 40-c1/U batches after B. W rounds up to 50 c1/U and clips at 400 with
WINDOW_CAPPED. Endpoints are interpolated without extrapolation, and trailing
partial batches are omitted. These choices precede any formal data.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from cfd_harness import campaign_schema as SC
from cfd_harness.scene_campaign import parent_window, validate_observable

FORMULA = {
    "source": "TOPO-2D-00 Amendment 7 section 2",
    "horizon": 520,
    "minimum_burn_in": 80,
    "burn_block_length": 100,
    "burn_candidate_origin": "first sample time",
    "burn_candidate_step": 50,
    "burn_candidate_extent": "all complete 100 blocks ending at or before horizon",
    "burn_range": "mean([t+100,horizon]) +/- 2*SE(remainder complete batch means)",
    "burn_se_batch_length": 20,
    "minimum_remainder_batches": 2,
    "burn_in_rule": "max(80, earliest accepted candidate start); fallback 130",
    "burn_in_fallback": 130,
    "missing_candidate_endpoint": "never extrapolate",
    "batch_lengths": [10, 20, 40],
    "s0_rule": "max(length * sample_variance); point estimates only",
    "incomplete_trailing_batch": "omit",
    "window_multiple": 50,
    "target_se_fraction": 0.015,
    "window_cap": 400,
    "window_cap_rule": "clip and flag WINDOW_CAPPED; do not refuse",
    "density_kg_m3": 1.0,
    "freestream_mps": 1.0,
    "reference_chord_mm": 223.4,
}
UNITS = {"downforce": "N/m", "time": "c1/U", "s0": "(N/m)^2*c1/U"}


def estimate(rows):
    """Compute registered point B/S0/W with exact piecewise-linear integrals.

    All complete candidate blocks are listed, including those with too few
    remaining batches to estimate SE. The remainder mean includes its trailing
    partial batch; the batch-means SE omits that partial batch. A selected
    candidate earlier than 80 is raised to the registered minimum B=80.
    """
    SC.req(len(rows) >= 4, "nonfinite or short parent series")
    times, values = np.array([[SC.finite(row[k]) for k in ("t_u_l", "downforce_n_per_m")] for row in rows]).T
    spacing = np.diff(times)
    SC.req(np.all(spacing > 0), "parent sample times are not increasing")
    horizon = FORMULA["horizon"]
    SC.req(0 <= times[0] <= 80 and times[-1] >= horizon, "parent series does not bracket its 520 c1/U horizon")
    # One cumulative trapezoid, then exact quadratic integration inside an
    # endpoint's segment. Removing the DC level avoids cancellation in S0.
    centered = values - values[0]
    slopes = np.diff(centered) / spacing
    integrals = np.r_[0.0, np.cumsum((centered[:-1] + centered[1:]) * spacing / 2)]

    def integral(at):
        index = np.clip(np.searchsorted(times, at, side="right") - 1, 0, len(times) - 2)
        offset = at - times[index]
        return integrals[index] + centered[index] * offset + slopes[index] * offset ** 2 / 2

    def mean(start, end):
        SC.req(times[0] <= start < end <= times[-1], "parent history does not bracket window")
        return float(values[0] + (integral(end) - integral(start)) / (end - start))

    def batch_means(start, length):
        edges = start + np.arange(math.floor((horizon - start) / length) + 1) * length
        return values[0] + np.diff(integral(edges)) / length

    candidates, burn = [], None
    count = math.floor((horizon - times[0] - FORMULA["burn_block_length"]) / FORMULA["burn_candidate_step"]) + 1
    for index in range(count):
        start = float(times[0] + index * FORMULA["burn_candidate_step"])
        end = start + FORMULA["burn_block_length"]
        later = batch_means(end, FORMULA["burn_se_batch_length"])
        row = {"start": start, "remainder_batch_count": len(later), "accepted": False}
        if len(later) < FORMULA["minimum_remainder_batches"]:
            row["reason"] = "fewer than two remainder batches"
        else:
            candidate, center = mean(start, end), mean(end, horizon)
            se = float(np.std(later, ddof=1) / math.sqrt(len(later)))
            row.update(mean=candidate, remainder_mean=center, remainder_se=se,
                       accepted=abs(candidate - center) <= 2 * se)
        candidates.append(row)
        if row["accepted"] and burn is None:
            burn = max(FORMULA["minimum_burn_in"], start)
    fallback = burn is None
    if fallback:
        burn = FORMULA["burn_in_fallback"]
    estimates = []
    for length in FORMULA["batch_lengths"]:
        batches = batch_means(burn, length)
        SC.req(len(batches) >= 2, "not enough post-burn-in parent batches")
        variance = float(np.var(batches, ddof=1))
        estimates.append({"block_length": length, "batch_count": len(batches), "degrees_of_freedom": len(batches) - 1,
                          "batch_mean": float(np.mean(batches)), "sample_variance": variance,
                          "s0_point": length * variance})
    downforce, s0 = mean(burn, horizon), max(row["s0_point"] for row in estimates)
    SC.req(downforce > 0, "parent pre-run mean downforce must be positive")
    window = parent_window(downforce, s0, burn)
    uncapped = max(FORMULA["window_multiple"], FORMULA["window_multiple"] * math.ceil(s0 / (FORMULA["target_se_fraction"] * downforce) ** 2 / FORMULA["window_multiple"]))
    return {"units": UNITS, "formula": FORMULA, "burn_in": burn, "mean_downforce": downforce,
            "s0_point": s0, "window_width": window[1] - window[0], "window": window,
            "uncapped_window_width": uncapped,
            "flags": {"BURN_IN_FALLBACK": fallback, "WINDOW_CAPPED": uncapped > FORMULA["window_cap"]},
            "burn_candidates": candidates, "spectral_estimates": estimates}


def record_from_files(series_path, summary_path, *, repo=ROOT):
    """Bind calculated statistics to the full E1/main/phase-0 pre-run inputs."""
    repo, series_path, summary_path = Path(repo).resolve(), Path(series_path).resolve(), Path(summary_path).resolve()
    relative = lambda path: SC.safe_rel(path.relative_to(repo).as_posix()).as_posix()
    summary = SC.jload(summary_path)
    ident = summary.get("topo2d", {})
    SC.req(ident.get("configuration") == "E1" and ident.get("grid") == "main" and str(ident.get("phase")) == "0" and ident.get("role") == "prerun" and ident.get("reynolds") in (1000, 3000), "parent pre-run E1/main/phase-0 identity")
    SC.req(summary.get("smoke") is False and summary.get("runtime", {}).get("memory") == "CuArray", "a CPU smoke cannot produce a formal parent window")
    validate_observable(summary, SC.finite(ident.get("height_mm")))
    SC.req(summary.get("force_unit") == "N/m" and summary.get("reference_chord_mm") == 223.4 and summary.get("solver_length") == 120, "parent nominal force/common-c1 units")
    SC.req(summary.get("reynolds") == ident["reynolds"] and summary.get("flow_dims") == [840, 824] and summary.get("phase_shift_m") == [0, 0, 0] and summary.get("top_factor") == 1.0, "parent pre-run grid/phase/Re contract")
    SC.req(summary.get("window_t_u_l") == [80, 520] and SC.finite(summary.get("t_end_reached")) >= 520 and all(summary.get(key) is True for key in ("finite_u", "finite_p", "finite_forces")), "parent pre-run horizon/finite contract")
    SC.req(SC.is_sha(summary.get("scene_sha256")) and isinstance(summary.get("source_sha256"), dict) and summary["source_sha256"] and all(SC.is_sha(value) for value in summary["source_sha256"].values()), "parent pre-run source/scene hashes")
    digest = SC.sha256_path(series_path)
    SC.req(summary.get("force_csv_sha256") == digest, "parent pre-run series hash mismatch")
    with series_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        SC.req(tuple((reader.fieldnames or [])[:13]) == SC.FORCE_COLUMNS and len(set(reader.fieldnames)) == len(reader.fieldnames), "parent force CSV schema")
        rows = [{key: float(row[key]) for key in SC.FORCE_COLUMNS} for row in reader]
    SC.req(all(all(math.isfinite(value) for value in row.values()) for row in rows), "nonfinite parent force rows")
    SC.req(all(b["step"] > a["step"] for a, b in zip(rows, rows[1:])), "parent step order")
    for row in rows:
        SC.req(math.isclose(row["drag_solver"], row["fx_solver"], abs_tol=1e-9) and math.isclose(row["downforce_solver"], -row["fz_solver"], abs_tol=1e-9), "parent force sign projection")
        SC.req(all(math.isclose(row[f"{axis}_solver"], row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"], abs_tol=1e-9) for axis in ("fx", "fy", "fz")), "parent force component closure")
    force_scale = 0.2234 / 120  # rho=1 kg/m3, U=1 m/s, dx=c1/120 metres.
    stats = estimate([{**row, "downforce_n_per_m": row["downforce_solver"] * force_scale} for row in rows])
    return {"schema": "topo2d-parent-window-v1", "configuration": "E1", "reynolds": ident["reynolds"], "height_mm": ident["height_mm"],
            "grid": "main", "phase": "0", "role": "prerun", "observable": "total_cl",
            "series_path": relative(series_path), "series_sha256": digest, "summary_path": relative(summary_path),
            "summary_sha256": SC.sha256_path(summary_path), "scene_sha256": summary["scene_sha256"],
            "source_sha256": summary["source_sha256"], "runtime": summary["runtime"], **stats}


def write_record(series_path, summary_path, target, *, repo=ROOT):
    record = record_from_files(series_path, summary_path, repo=repo)
    text = json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with Path(target).open("x") as handle:
        handle.write(text)
    return record


def validate_record(path, *, repo=ROOT):
    """Refuse hand-entered statistics, changed raw bytes and derived-value forgery."""
    record = SC.jload(path)
    SC.req(record.get("schema") == "topo2d-parent-window-v1", "parent record schema absent; hand-entered statistics are forbidden")
    repo = Path(repo)
    for prefix in ("series", "summary"):
        source = repo / SC.safe_rel(record.get(prefix + "_path"))
        SC.req(SC.is_sha(record.get(prefix + "_sha256")) and SC.sha256_path(source) == record[prefix + "_sha256"], "parent raw series/summary hash mismatch")
    expected = record_from_files(repo / record["series_path"], repo / record["summary_path"], repo=repo)
    SC.req(record == expected, "parent window record differs from recomputed raw-series statistics")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series", type=Path)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    ident = SC.jload(args.summary)["topo2d"]
    target = args.out or args.repo / f"docs/harness/topo2d00_window_re{int(ident['reynolds'])}.json"
    write_record(args.series, args.summary, target, repo=args.repo)
    print(target)


if __name__ == "__main__":
    main()
