"""Host-side analysis for the preregistered FD-07 continuous replacement probe."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY_JL = Path("/Users/sota/.julia/packages/WaterLily/yOkji/src/Body.jl")
BODY_SHA256 = "aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee"
EVIDENCE = Path("docs/evidence/sdf_native_fd07_continuous_replacement_2026_10")
EXPECTED_MODES = ("UPSTREAM", "NO_SIGN_CORRECTION", "A_THRESHOLD", "B_CENTER_SIGN", "C_MOMENT_BLEND")
SEEDS = (1, 11, 2026)
AMPLITUDES = ("1e-08", "1e-07")
FORCE_SCALE = 1.0 / 900.0
FORCE_COLUMNS = ("pressure_fx_solver", "pressure_fz_solver", "viscous_fx_solver", "viscous_fz_solver")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def verify_registration(outdir: Path) -> str:
    plan_path = outdir / "plan.json"
    plan_sha = sha(plan_path)
    expected = (outdir / "plan.sha256").read_text().split()[0]
    if plan_sha != expected:
        raise ValueError("plan hash differs from preregistration")
    if sha(BODY_JL) != BODY_SHA256:
        raise ValueError("pinned WaterLily Body.jl SHA-256 mismatch")
    for manifest_name in ("repository_sources.sha256", "input_files.sha256"):
        for line in (outdir / manifest_name).read_text().splitlines():
            digest, relative = line.split("  ", 1)
            path = BODY_JL if relative == "pinned_WaterLily_Body.jl" else ROOT / relative
            if sha(path) != digest:
                raise ValueError(f"registered source/input changed: {relative}")
    return plan_sha


def l2(values) -> float:
    return math.sqrt(sum(float(value) ** 2 for value in values))


def coefficient_screen(outdir: Path) -> dict:
    fields = read_csv(outdir / "coefficient_field_hashes.csv")
    metrics = read_csv(outdir / "coefficient_metrics.csv")
    pairs = read_csv(outdir / "coefficient_pair_responses.csv")
    expected = {(mode, case) for mode in EXPECTED_MODES for case in
                ["baseline"] + [f"seed_{seed}_{sign}_{amp}" for seed in SEEDS
                for amp in AMPLITUDES for sign in ("plus", "minus")]}
    if {(r["mode"], r["case_id"]) for r in fields} != expected:
        raise ValueError("coefficient field-hash case matrix is incomplete or unexpected")
    if {(r["mode"], r["case_id"]) for r in metrics} != expected:
        raise ValueError("coefficient metric case matrix is incomplete or unexpected")
    if len(pairs) != len(EXPECTED_MODES) * len(SEEDS) * len(AMPLITUDES):
        raise ValueError("coefficient odd/even response matrix is incomplete")

    by_mode = {mode: [r for r in metrics if r["mode"] == mode] for mode in EXPECTED_MODES}
    pair_by = defaultdict(dict)
    for row in pairs:
        pair_by[row["mode"]][(int(row["seed"]), row["amplitude_m"])] = row
    ground = read_csv(outdir / "moving_ground_identity.csv")
    ground_by_mode = defaultdict(list)
    for row in ground:
        ground_by_mode[row["mode"]].append(row["bitwise_equal"].lower() == "true")
    analytic = read_csv(outdir / "analytic_fixture_coefficients.csv")
    reflection = read_csv(outdir / "analytic_reflection_symmetry.csv")
    translation = {(r["mode"], r["sweep"]): r
                   for r in read_csv(outdir / "analytic_translation_continuity.csv")}
    exact_fixtures = {"plane_center_aligned", "plane_face_aligned", "plane_face_offset_1e-4",
                      "plane_near_center_offset_1e-4",
                      "sphere", "one_cell_plate", "two_cell_plate"}

    candidate_results = {}
    for mode in EXPECTED_MODES:
        rows = by_mode[mode]
        perturb = [r for r in rows if r["case_id"] != "baseline"]
        base = next(r for r in rows if r["case_id"] == "baseline")
        coeff_pairs = pair_by[mode]
        amp_ratios = []
        monotone = True
        for seed in SEEDS:
            small, large = coeff_pairs[(seed, "1e-08")], coeff_pairs[(seed, "1e-07")]
            monotone &= large["monotone_10x_response"].lower() == "true"
            for key in ("mu0_plus_l2", "mu0_minus_l2", "mu1_plus_l2", "mu1_minus_l2"):
                denominator = float(small[key])
                numerator = float(large[key])
                amp_ratios.append(numerator / denominator if denominator else (float("inf") if numerator else 1.0))
        exact_rows = [r for r in analytic if r["mode"] == mode and r["fixture"] in exact_fixtures]
        reflection_rows = [r for r in reflection if r["mode"] == mode]
        center_sweep = translation[(mode, "center_sign")]
        face_sweep = translation[(mode, "face_threshold")]
        candidate_results[mode] = {
            "baseline_max_abs_mu0_vs_upstream": float(base["mu0_max_abs_vs_upstream_same_case"]),
            "baseline_count_mu0_gt_1e_3_vs_upstream": int(base["mu0_count_gt_1e-3_vs_upstream_same_case"]),
            "baseline_max_abs_mu1_vs_upstream": float(base["mu1_max_abs_vs_upstream_same_case"]),
            "max_perturb_mu0_vs_own_baseline": max(float(r["mu0_max_abs_vs_mode_baseline"]) for r in perturb),
            "max_perturb_mu1_vs_own_baseline": max(float(r["mu1_max_abs_vs_mode_baseline"]) for r in perturb),
            "max_perturb_mu0_count_gt_1e_3": max(int(r["mu0_count_gt_1e-3_vs_mode_baseline"]) for r in perturb),
            "max_perturb_mu1_count_gt_1e_3": max(int(r["mu1_count_gt_1e-3_vs_mode_baseline"]) for r in perturb),
            "max_support_changes_vs_upstream": max(
                max(int(r["mu0_support_changes_vs_upstream_same_case"]),
                    int(r["mu1_support_changes_vs_upstream_same_case"])) for r in rows),
            "nonfinite_count": sum(int(r["nonfinite_count"]) for r in rows),
            "all_pair_responses_monotone_10x": bool(monotone),
            "amplitude_l2_ratio_min": min(amp_ratios),
            "amplitude_l2_ratio_max": max(amp_ratios),
            "moving_ground_bitwise_identity": all(ground_by_mode[mode]),
            "analytic_exact_fixture_max_abs_mu0_delta": max(
                float(r["max_abs_delta_mu0"]) for r in exact_rows),
            "analytic_thin_plate_max_abs_mu0_delta": max(
                float(r["max_abs_delta_mu0"]) for r in exact_rows
                if r["fixture"] in {"one_cell_plate", "two_cell_plate"}),
            "analytic_legal_half_cell_crossing_max_abs_mu0_delta": max(
                float(r["legal_half_cell_crossing_max_abs_delta_mu0"]) for r in exact_rows),
            "analytic_legal_half_cell_crossing_changed_mu0_count": sum(
                int(r["legal_half_cell_crossing_changed_mu0_count"]) for r in exact_rows),
            "analytic_exact_fixture_center_inside_samples": sum(
                int(r["center_inside_count"]) for r in exact_rows),
            "analytic_exact_fixture_center_outside_samples": sum(
                int(r["center_outside_count"]) for r in exact_rows),
            "analytic_reflection_geometry_max_abs_residual": max(
                float(r["geometry_max_abs_residual"]) for r in reflection_rows),
            "analytic_reflection_mu0_max_abs_residual": max(
                float(r["mu0_reflection_max_abs_residual"]) for r in reflection_rows),
            "analytic_reflection_mu1_max_abs_residual": max(
                float(r["mu1_reflection_max_abs_residual"]) for r in reflection_rows),
            "synthetic_center_translation_max_adjacent_mu0_delta": float(
                center_sweep["max_adjacent_delta"]),
            "synthetic_center_translation_nondecreasing":
                center_sweep["nondecreasing"].lower() == "true",
            "synthetic_face_threshold_max_adjacent_mu0_delta": float(
                face_sweep["max_adjacent_delta"]),
            "synthetic_face_threshold_nonincreasing":
                face_sweep["nonincreasing"].lower() == "true",
            "analytic_legal_half_cell_crossings_preserved": max(
                float(r["legal_half_cell_crossing_max_abs_delta_mu0"]) for r in exact_rows) == 0.0,
            "analytic_thin_plate_mu0_matches_upstream": max(
                float(r["max_abs_delta_mu0"]) for r in exact_rows
                if r["fixture"] in {"one_cell_plate", "two_cell_plate"}) == 0.0,
            "analytic_reflection_residuals_below_1e_6": max(
                max(float(r["mu0_reflection_max_abs_residual"]),
                    float(r["mu1_reflection_max_abs_residual"])) for r in reflection_rows) < 1e-6,
        }
    return {
        "case_count_per_mode": len({row["case_id"] for row in fields}),
        "mode_count": len(EXPECTED_MODES),
        "coefficient_field_hash_row_count": len(fields),
        "coefficient_metric_row_count": len(metrics),
        "coefficient_pair_response_row_count": len(pairs),
        "analytic_fixture_row_count": len(analytic),
        "analytic_reflection_row_count": len(reflection),
        "analytic_translation_row_count": len(translation),
        "candidate_results": candidate_results,
    }


def exact_window_mean(times, values, start=2.0, end=3.0) -> float:
    if len(times) < 2 or times[0] > start or times[-1] < end:
        raise ValueError("force history does not bracket the registered [2,3] interval")
    for a, b in zip(times, times[1:]):
        if b <= a:
            raise ValueError("force history times are not strictly increasing")
    inner = [(t, v) for t, v in zip(times, values) if start < t < end]
    points = [(start, _interp(times, values, start)), *inner, (end, _interp(times, values, end))]
    area = sum((t1 - t0) * (v0 + v1) * 0.5 for (t0, v0), (t1, v1) in zip(points, points[1:]))
    return area / (end - start)


def _interp(times, values, target):
    for index in range(1, len(times)):
        if times[index] >= target:
            t0, t1 = times[index - 1], times[index]
            v0, v1 = values[index - 1], values[index]
            return v0 + (v1 - v0) * ((target - t0) / (t1 - t0))
    return values[-1]


def read_force(path: Path) -> dict:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"empty force history: {path}")
    times = [float(row["t_u_l"]) for row in rows]
    comps = {
        name.removesuffix("_solver"): exact_window_mean(times, [float(row[name]) for row in rows]) * FORCE_SCALE
        for name in FORCE_COLUMNS
    }
    force = {
        "drag": comps["pressure_fx"] + comps["viscous_fx"],
        "downforce": -(comps["pressure_fz"] + comps["viscous_fz"]),
    }
    stored_drag = exact_window_mean(times, [float(row["drag_solver"]) for row in rows]) * FORCE_SCALE
    stored_downforce = exact_window_mean(times, [float(row["downforce_solver"]) for row in rows]) * FORCE_SCALE
    closure = max(abs(force["drag"] - stored_drag), abs(force["downforce"] - stored_downforce))
    sample_closure = max(
        max(abs(float(r["drag_solver"]) - float(r["pressure_fx_solver"]) - float(r["viscous_fx_solver"])) * FORCE_SCALE,
            abs(float(r["downforce_solver"]) + float(r["pressure_fz_solver"]) + float(r["viscous_fz_solver"])) * FORCE_SCALE)
        for r in rows
    )
    return {
        "window_mean_n": {**comps, **force},
        "stored_total_n": {"drag": stored_drag, "downforce": stored_downforce},
        "window_closure_max_abs_n": closure,
        "sample_closure_max_abs_n": sample_closure,
        "sample_count": len(rows),
        "time_bounds_u_l": [min(times), max(times)],
        "history_sha256": sha(path),
    }


def force_summary(outdir: Path) -> dict | None:
    execution_path = outdir / "stage3_execution.txt"
    if not execution_path.exists():
        return None
    text = execution_path.read_text()
    line = next((row for row in text.splitlines() if row.startswith("candidate_modes=")), None)
    if line is None:
        raise ValueError("Stage 3 record is missing candidate mode identity")
    candidates = [name for name in line.split("=", 1)[1].split(",") if name]
    modes = ["UPSTREAM", "NO_SIGN_CORRECTION", *candidates]
    cases = ["baseline"] + [f"seed_{seed}_{sign}_{amp}" for seed in SEEDS
             for amp in AMPLITUDES for sign in ("plus", "minus")]
    data = {}
    per_run = []
    for mode in modes:
        for case in cases:
            path = outdir / "solved" / mode.lower() / f"{case}.csv"
            data[(mode, case)] = read_force(path)
            record = data[(mode, case)]
            per_run.append({"mode": mode, "case_id": case, **record})
    pair_rows = []
    mode_findings = {}
    for mode in modes:
        baseline = data[(mode, "baseline")]["window_mean_n"]
        upstream = data[("UPSTREAM", "baseline")]["window_mean_n"]
        mode_findings[mode] = {
            "baseline_drag_n": baseline["drag"],
            "baseline_downforce_n": baseline["downforce"],
            "baseline_drag_delta_vs_upstream_n": baseline["drag"] - upstream["drag"],
            "baseline_downforce_delta_vs_upstream_n": baseline["downforce"] - upstream["downforce"],
            "max_sample_closure_abs_n": max(data[(mode, case)]["sample_closure_max_abs_n"] for case in cases),
            "max_window_closure_abs_n": max(data[(mode, case)]["window_closure_max_abs_n"] for case in cases),
        }
        for seed in SEEDS:
            for amp in AMPLITUDES:
                plus = data[(mode, f"seed_{seed}_plus_{amp}")]["window_mean_n"]
                minus = data[(mode, f"seed_{seed}_minus_{amp}")]["window_mean_n"]
                for quantity in ("drag", "downforce", "pressure_fx", "pressure_fz", "viscous_fx", "viscous_fz"):
                    base_value = baseline[quantity]
                    odd = (plus[quantity] - minus[quantity]) / 2
                    even = (plus[quantity] + minus[quantity]) / 2 - base_value
                    pair_rows.append({"mode": mode, "seed": seed, "amplitude_m": amp,
                        "quantity": quantity, "plus_delta_n": plus[quantity] - base_value,
                        "minus_delta_n": minus[quantity] - base_value, "odd_n": odd, "even_n": even})
    # Compare odd/even response sizes at 10x input amplitude without a pass threshold.
    for mode in modes:
        ratios = []
        for seed in SEEDS:
            for quantity in ("drag", "downforce"):
                small = next(r for r in pair_rows if r["mode"] == mode and r["seed"] == seed and
                             r["amplitude_m"] == "1e-08" and r["quantity"] == quantity)
                large = next(r for r in pair_rows if r["mode"] == mode and r["seed"] == seed and
                             r["amplitude_m"] == "1e-07" and r["quantity"] == quantity)
                for key in ("odd_n", "even_n"):
                    denominator = abs(small[key])
                    numerator = abs(large[key])
                    ratios.append(numerator / denominator if denominator else (math.inf if numerator else 1.0))
        mode_findings[mode]["force_10x_amplitude_ratio_min"] = min(ratios)
        mode_findings[mode]["force_10x_amplitude_ratio_max"] = max(ratios)

    for filename, rows in (("force_response_long.csv", per_run), ("force_pair_response.csv", pair_rows)):
        keys = list(rows[0])
        with (outdir / filename).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader(); writer.writerows(rows)
    return {"run_count": len(per_run), "pair_quantity_row_count": len(pair_rows), "modes": mode_findings,
            "maximum_independent_sample_force_closure_n": max(r["sample_closure_max_abs_n"] for r in per_run),
            "maximum_independent_window_force_closure_n": max(r["window_closure_max_abs_n"] for r in per_run)}


def sha_manifest(outdir: Path, filename: str) -> None:
    lines = []
    for path in sorted(p for p in outdir.rglob("*") if p.is_file() and p.name != filename):
        lines.append(f"{sha(path)}  {path.relative_to(outdir).as_posix()}\n")
    (outdir / filename).write_text("".join(lines))


def analyze(outdir: Path) -> dict:
    plan_sha = verify_registration(outdir)
    screen = coefficient_screen(outdir)
    forces = force_summary(outdir)
    summary = {
        "kind": "fd07_continuous_replacement_diagnostic_result",
        "evidence_class": "bounded_diagnostic_only",
        "plan_sha256": plan_sha,
        "pinned_waterlily_body_jl_sha256": sha(BODY_JL),
        "coefficient_screen": screen,
        "short_cpu_force_comparison": forces,
        "qualification_flags": {
            "formal_fd_qualified": False,
            "production_replacement_adopted": False,
            "gradient_qualified": False,
            "optimizer_allowed": False,
            "shape_update_allowed": False,
        },
    }
    with (outdir / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")
    sha_manifest(outdir, "artifact_manifest.sha256")
    return summary


if __name__ == "__main__":
    output = analyze(ROOT / EVIDENCE)
    print(json.dumps({"plan_sha256": output["plan_sha256"],
                      "short_cpu_force_comparison_present": output["short_cpu_force_comparison"] is not None},
                     sort_keys=True))
