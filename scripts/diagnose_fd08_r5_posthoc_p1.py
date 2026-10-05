#!/usr/bin/env python3
"""Create an unregistered, solver-free diagnostic of immutable FD-08 R5 data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from statistics import median
from typing import Any

EXPECTED_CRITERIA_SHA256 = "928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c"
EXPECTED_ANALYSIS_SHA256 = "dc769d6f2b5a2d6dfa45c6a5aeddfde726dd75f6e44ac564b128effecce3fb8b"
EXPECTED_MANIFEST_SHA256 = "1b04c3c2243459d2889dc16aa0f3c02c2ff6a5555a64406bb8177b9ee0b8600e"
EXPECTED_SOURCE_COMMIT = "95bd9cbf8e67f0c718e346f7edca3f343ed1091f"
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
RESPONSES = ("drag", "downforce")
EXPECTED_EPSILON_M = (5e-5, 1.5e-4, 5e-4, 1.5e-3, 5e-3, 1.5e-2, 5e-2)
EVIDENCE_RELATIVE = Path("docs/evidence/fd08_candidate_c_calibration_2026_10_04_r5")
OUTPUT_RELATIVE = EVIDENCE_RELATIVE / "post_hoc_p1"
FIGURE_FILES = (
    "q_by_epsilon.png",
    "q_vs_epsilon_squared_tail_fits.png",
    "centered_response_residual.png",
    "float32_realized_perturbation.png",
    "stationarity_half_window_drift.png",
    "paired_response_half_window_sensitivity.png",
)
PLOT_TEXT = {
    "en": {
        "font_family": None,
        "response_names": {"drag": "Drag", "downforce": "Downforce"},
        "direction": "Direction",
        "x_epsilon": "Registered nominal epsilon, mm",
        "q_y": "Centered-response slope q(epsilon), N/m",
        "q_title": "R5 raw-recomputed q(epsilon) — post-hoc diagnostic; R5 remains FAIL",
        "x_epsilon_squared": "Nominal epsilon squared, (mm)^2",
        "q_fit_y": "q(epsilon), N/m",
        "tail4": "last 4 points",
        "tail3": "last 3 points",
        "q_fit_title": "Exploratory suffix fits q = q0 + c epsilon²; no fit is selected as a gate",
        "residual_y": "S - q_ref epsilon, N",
        "residual_title": "Signed centered-response residual; q_ref is the first-three-epsilon median",
        "metric_max": "Maximum |delta phi|, mm",
        "metric_rms_all": "RMS delta phi over all nodes, mm",
        "metric_rms_changed": "RMS delta phi over changed nodes, mm",
        "metric_count": "Changed Float32 phi nodes",
        "metric_projection": "Projected realized epsilon / nominal epsilon",
        "max_title": "Maximum pointwise phi change",
        "rms_all_title": "RMS over entire phi grid",
        "rms_changed_title": "RMS over changed nodes",
        "count_title": "Actual changed-node count",
        "projection_title": "Direction-projected scale",
        "grid_epsilon_y": "Nominal epsilon / spacing",
        "grid_epsilon_title": "Perturbation size in grid units",
        "epsilon_lattice": "epsilon / SDF lattice",
        "epsilon_cell": "epsilon / flow cell",
        "lattice_annotation": "SDF lattice 25 mm",
        "cell_annotation": "flow cell 33.3 mm",
        "perturbation_title": "Float32-realized perturbations; error bars span plus/minus states",
        "stationarity_x": "R5 registered state order (47 states)",
        "stationarity_y": "Relative half-window drift, [80,100] vs [100,120]",
        "stationarity_axis_title": "Independent stationarity recomputation from raw force histories",
        "stationarity_title": "Stationarity cross-check; not a new qualification",
        "drag_short": "drag",
        "downforce_short": "downforce",
        "paired_y": "|S_first - S_second| / |S_full|, %",
        "paired_title": "Paired-response sensitivity to [80,100] vs [100,120] windows — descriptive, no gate",
        "d1_max": "D1 max {value:.1f}% @ {epsilon:g} mm",
    },
    "ja": {
        "font_family": "Hiragino Sans",
        "response_names": {"drag": "抗力", "downforce": "ダウンフォース"},
        "direction": "方向",
        "x_epsilon": "登録済み名目 ε [mm]",
        "q_y": "中心差分応答の傾き q(ε) [N/m]",
        "q_title": "R5 生データから再計算した q(ε)（事後診断、R5判定はFAILのまま）",
        "x_epsilon_squared": "名目 ε² [mm²]",
        "q_fit_y": "q(ε) [N/m]",
        "tail4": "末尾4点",
        "tail3": "末尾3点",
        "q_fit_title": "探索的な末尾点 fit: q = q₀ + c ε²（判定gateには不使用）",
        "residual_y": "S − q_ref ε [N]",
        "residual_title": "符号付き中心応答残差（q_ref は最初の3つの ε の中央値）",
        "metric_max": "最大 |Δφ| [mm]",
        "metric_rms_all": "全φ格子上の RMS Δφ [mm]",
        "metric_rms_changed": "変更ノード上の RMS Δφ [mm]",
        "metric_count": "変更された Float32 φ ノード数",
        "metric_projection": "方向射影による実現 ε / 名目 ε",
        "max_title": "最大点のφ変化量",
        "rms_all_title": "全φ格子上の RMS",
        "rms_changed_title": "変更ノード上の RMS",
        "count_title": "実際に変化したノード数",
        "projection_title": "方向への射影比",
        "grid_epsilon_y": "名目 ε / 格子幅",
        "grid_epsilon_title": "格子幅を単位とした摂動量",
        "epsilon_lattice": "ε / SDF格子幅",
        "epsilon_cell": "ε / 流体セル幅",
        "lattice_annotation": "SDF格子幅 25 mm",
        "cell_annotation": "流体セル幅 33.3 mm",
        "perturbation_title": "Float32で実現した摂動（誤差棒は±状態間の範囲）",
        "stationarity_x": "R5の登録状態順（47状態）",
        "stationarity_y": "半窓間の相対ドリフト（[80,100] と [100,120]）",
        "stationarity_axis_title": "生の力履歴から独立再計算した時間窓内の定常性",
        "stationarity_title": "時間窓ドリフトの照合（新たな適格性判定ではない）",
        "drag_short": "抗力",
        "downforce_short": "ダウンフォース",
        "paired_y": "|S前半 − S後半| / |S全窓| [%]",
        "paired_title": "半窓ごとのペア応答感度（記述診断、合否gateではない）",
        "d1_max": "D1 最大 {value:.1f}%（ε={epsilon:g} mm）",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"refusing to replace different historical artifact: {path}")
        return
    path.write_bytes(data)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def line_fit(x_values: list[float], y_values: list[float]) -> dict[str, float]:
    import numpy as np

    x = np.asarray(x_values, dtype=np.float64)
    y = np.asarray(y_values, dtype=np.float64)
    design = np.column_stack((np.ones_like(x), x))
    intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - (intercept + slope * x)
    centered = y - float(np.mean(y))
    ss_total = float(np.dot(centered, centered))
    return {
        "intercept": float(intercept),
        "slope": float(slope),
        "rmse": float(np.sqrt(np.mean(residual * residual))),
        "r_squared": 1.0 - float(np.dot(residual, residual)) / ss_total if ss_total else 1.0,
        "max_absolute_residual": float(np.max(np.abs(residual))),
    }


def local_intervals(epsilon_mm: list[float], q: list[float]) -> dict[str, Any]:
    """Enumerate all contiguous >=3-point windows within 5% of local median."""
    intervals = []
    for start in range(len(q)):
        for stop in range(start + 3, len(q) + 1):
            sample = q[start:stop]
            center = float(median(sample))
            if center == 0.0:
                continue
            maximum = max(abs(value - center) / abs(center) for value in sample)
            if maximum <= 0.05:
                intervals.append({
                    "epsilon_mm": epsilon_mm[start:stop],
                    "first_epsilon_mm": epsilon_mm[start],
                    "last_epsilon_mm": epsilon_mm[stop - 1],
                    "point_count": stop - start,
                    "local_median_n_per_m": center,
                    "maximum_relative_deviation": maximum,
                })
    longest_size = max((row["point_count"] for row in intervals), default=0)
    return {
        "rule": "all contiguous windows of at least 3 points with q within +/-5% of that window's median; unregistered description only",
        "all_qualifying_intervals": intervals,
        "longest_point_count": longest_size,
        "longest_intervals": [row for row in intervals if row["point_count"] == longest_size],
    }


def make_figures(
    output: Path,
    eps_mm: list[float],
    eps_m: list[float],
    series: dict[str, Any],
    realized: dict[str, Any],
    stationarity: list[dict[str, Any]],
    paired_half_window: dict[str, Any],
    sdf_spacing_mm: float,
    flow_spacing_mm: float,
    plot_language: str,
) -> dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    text = PLOT_TEXT[plot_language]
    if text["font_family"]:
        plt.rcParams["font.family"] = text["font_family"]
    plt.rcParams["axes.unicode_minus"] = False
    colors = {DIRECTIONS[0]: "#2463a6", DIRECTIONS[1]: "#d17a00", DIRECTIONS[2]: "#18835d"}
    labels = {DIRECTIONS[0]: "D0", DIRECTIONS[1]: "D1", DIRECTIONS[2]: "D2"}
    names = text["response_names"]
    figures = {}

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), constrained_layout=True)
    for ax, response in zip(axes, RESPONSES):
        for direction in DIRECTIONS:
            q = [row["q_n_per_m"] for row in series[direction][response]]
            ax.plot(eps_mm, q, marker="o", markersize=5, linewidth=1.7,
                    color=colors[direction], label=labels[direction])
        ax.axhline(0, color="#555555", linewidth=0.8)
        ax.set_xscale("log")
        ax.set_xlabel(text["x_epsilon"])
        ax.set_ylabel(text["q_y"])
        ax.set_title(names[response])
        ax.grid(True, which="both", alpha=0.23)
    axes[1].legend(title=text["direction"], frameon=False)
    fig.suptitle(text["q_title"], fontsize=13)
    figures["q_epsilon"] = "q_by_epsilon.png"
    fig.savefig(output / figures["q_epsilon"], dpi=180, facecolor="white")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4), constrained_layout=True)
    x_all = [value * value for value in eps_mm]
    for ax, response in zip(axes, RESPONSES):
        for direction in DIRECTIONS:
            q = [row["q_n_per_m"] for row in series[direction][response]]
            ax.plot(x_all, q, marker="o", markersize=4, linewidth=1.4,
                    color=colors[direction], label=labels[direction])
            for start, style, suffix in ((3, "--", text["tail4"]), (4, ":", text["tail3"])):
                fit = line_fit(x_all[start:], q[start:])
                x_fit = np.linspace(x_all[start], x_all[-1], 80)
                y_fit = fit["intercept"] + fit["slope"] * x_fit
                ax.plot(x_fit, y_fit, style, linewidth=1.0, color=colors[direction],
                        alpha=0.8, label=f"{labels[direction]} fit ({suffix})")
        ax.set_xscale("log")
        ax.set_xlabel(text["x_epsilon_squared"])
        ax.set_ylabel(text["q_fit_y"])
        ax.set_title(names[response])
        ax.grid(True, which="both", alpha=0.23)
    axes[1].legend(fontsize=7.5, ncol=2, frameon=False)
    fig.suptitle(text["q_fit_title"], fontsize=12.5)
    figures["curvature"] = "q_vs_epsilon_squared_tail_fits.png"
    fig.savefig(output / figures["curvature"], dpi=180, facecolor="white")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), constrained_layout=True)
    for ax, response in zip(axes, RESPONSES):
        for direction in DIRECTIONS:
            residual = [row["response_residual_n"] for row in series[direction][response]]
            ax.plot(eps_mm, residual, marker="o", markersize=4.5, linewidth=1.6,
                    color=colors[direction], label=labels[direction])
        ax.set_xscale("log")
        ax.set_yscale("symlog", linthresh=1e-7)
        ax.set_xlabel(text["x_epsilon"])
        ax.set_ylabel(text["residual_y"])
        ax.axhline(0, color="#555555", linewidth=0.8)
        ax.set_title(names[response])
        ax.grid(True, which="both", alpha=0.23)
    axes[1].legend(title=text["direction"], frameon=False)
    fig.suptitle(text["residual_title"], fontsize=12.5)
    figures["response_residual"] = "centered_response_residual.png"
    fig.savefig(output / figures["response_residual"], dpi=180, facecolor="white")
    plt.close(fig)

    figure_metrics = (
        ("maximum_abs_change_mm", text["metric_max"], True),
        ("rms_all_nodes_mm", text["metric_rms_all"], True),
        ("rms_changed_nodes_mm", text["metric_rms_changed"], True),
        ("changed_node_count", text["metric_count"], True),
        ("projection_epsilon_over_nominal", text["metric_projection"], False),
    )
    fig, axes = plt.subplots(2, 3, figsize=(14.2, 8.2), constrained_layout=True)
    for ax, (key, ylabel, log_y) in zip(axes.flat, figure_metrics):
        for direction in DIRECTIONS:
            ys, lows, highs = [], [], []
            for epsilon in eps_m:
                values = list(realized[direction][f"{epsilon:.12g}"]["signs"].values())
                pair_values = [row[key] for row in values]
                center = float(np.mean(pair_values))
                ys.append(center)
                lows.append(center - min(pair_values))
                highs.append(max(pair_values) - center)
            ax.errorbar(eps_mm, ys, yerr=np.asarray([lows, highs]), marker="o",
                        markersize=4, linewidth=1.4, capsize=2, color=colors[direction],
                        label=labels[direction])
        ax.set_xscale("log")
        if log_y:
            ax.set_yscale("log")
        ax.set_xlabel(text["x_epsilon"])
        ax.set_ylabel(ylabel)
        ax.grid(True, which="both", alpha=0.23)
    for ax in axes.flat[:3]:
        ax.axvline(sdf_spacing_mm, color="#555555", linestyle="--", linewidth=1.0)
        ax.axvline(flow_spacing_mm, color="#888888", linestyle=":", linewidth=1.1)
    axes[0, 0].set_title(text["max_title"])
    axes[0, 1].set_title(text["rms_all_title"])
    axes[0, 2].set_title(text["rms_changed_title"])
    axes[1, 0].set_title(text["count_title"])
    axes[1, 1].axhline(1.0, color="#555555", linewidth=0.8)
    axes[1, 1].set_ylim(0.95, 1.05)
    axes[1, 1].set_yticks([0.95, 1.0, 1.05], labels=["0.95", "1.00", "1.05"])
    axes[1, 1].set_title(text["projection_title"])
    axes[1, 2].plot(eps_mm, [value / sdf_spacing_mm for value in eps_mm],
                    marker="o", linewidth=1.4, color="#2463a6", label=text["epsilon_lattice"])
    axes[1, 2].plot(eps_mm, [value / flow_spacing_mm for value in eps_mm],
                    marker="s", linewidth=1.4, color="#d17a00", label=text["epsilon_cell"])
    axes[1, 2].axhline(1.0, color="#555555", linewidth=0.8)
    axes[1, 2].set_xscale("log")
    axes[1, 2].set_yscale("log")
    axes[1, 2].set_xlabel(text["x_epsilon"])
    axes[1, 2].set_ylabel(text["grid_epsilon_y"])
    axes[1, 2].set_title(text["grid_epsilon_title"])
    axes[1, 2].grid(True, which="both", alpha=0.23)
    axes[1, 2].legend(frameon=False, fontsize=8)
    axes[0, 0].annotate(text["lattice_annotation"], (sdf_spacing_mm, 0.98),
                        xycoords=("data", "axes fraction"), xytext=(3, -2),
                        textcoords="offset points", fontsize=8, rotation=90,
                        va="top", ha="left", color="#555555")
    axes[0, 0].annotate(text["cell_annotation"], (flow_spacing_mm, 0.98),
                        xycoords=("data", "axes fraction"), xytext=(3, -2),
                        textcoords="offset points", fontsize=8, rotation=90,
                        va="top", ha="left", color="#777777")
    axes[0, 1].legend(title=text["direction"], frameon=False)
    fig.suptitle(text["perturbation_title"], fontsize=13)
    figures["realized_perturbation"] = "float32_realized_perturbation.png"
    fig.savefig(output / figures["realized_perturbation"], dpi=180, facecolor="white")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12.7, 4.7), constrained_layout=True)
    x = list(range(len(stationarity)))
    for response, marker, response_label in (
        ("drag", "o", text["drag_short"]),
        ("downforce", "s", text["downforce_short"]),
    ):
        y = [row[f"{response}_relative_drift"] for row in stationarity]
        ax.plot(x, y, marker=marker, markersize=2.5, linewidth=0.8, label=response_label)
    for boundary in (4.5, 18.5, 32.5):
        ax.axvline(boundary, color="#888888", linestyle=":", linewidth=0.8)
    ax.set_yscale("log")
    ax.set_xlabel(text["stationarity_x"])
    ax.set_ylabel(text["stationarity_y"])
    ax.set_title(text["stationarity_axis_title"])
    ax.grid(True, which="both", alpha=0.23)
    ax.legend(frameon=False)
    fig.suptitle(text["stationarity_title"], fontsize=13)
    figures["stationarity"] = "stationarity_half_window_drift.png"
    fig.savefig(output / figures["stationarity"], dpi=180, facecolor="white")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.0), constrained_layout=True)
    for ax, response in zip(axes, RESPONSES):
        for direction in DIRECTIONS:
            rows = paired_half_window[direction][response]
            ax.plot(
                [row["epsilon_mm"] for row in rows],
                [row["relative_half_window_response_difference"] * 100.0 for row in rows],
                marker="o", markersize=4.5, linewidth=1.5,
                color=colors[direction], label=labels[direction],
            )
        ax.set_xscale("log")
        ax.set_yscale("symlog", linthresh=1.0)
        ax.set_ylim(bottom=0.0)
        ax.set_xlabel(text["x_epsilon"])
        ax.set_ylabel(text["paired_y"])
        ax.set_title(names[response])
        ax.grid(True, which="both", alpha=0.23)
        highlighted = max(
            paired_half_window[DIRECTIONS[1]][response],
            key=lambda row: row["relative_half_window_response_difference"],
        )
        ax.annotate(
            text["d1_max"].format(
                value=highlighted["relative_half_window_response_difference"] * 100.0,
                epsilon=highlighted["epsilon_mm"],
            ),
            xy=(highlighted["epsilon_mm"],
                highlighted["relative_half_window_response_difference"] * 100.0),
            xytext=(8, -16), textcoords="offset points", fontsize=8,
            color=colors[DIRECTIONS[1]],
        )
    axes[1].legend(title=text["direction"], frameon=False)
    fig.suptitle(text["paired_title"], fontsize=12.5)
    figures["paired_response_half_window_sensitivity"] = "paired_response_half_window_sensitivity.png"
    fig.savefig(output / figures["paired_response_half_window_sensitivity"], dpi=180, facecolor="white")
    plt.close(fig)
    return {name: sha256(output / filename) for name, filename in figures.items()}


def main() -> int:
    script = Path(__file__).resolve()
    default_repo = script.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=default_repo)
    parser.add_argument("--dataset-root", required=True, type=Path,
                        help="freshly downloaded immutable R5 dataset")
    parser.add_argument("--output-dir", type=Path,
                        help="defaults to the R5 evidence directory's post_hoc_p1 child")
    parser.add_argument("--plot-language", choices=tuple(PLOT_TEXT), default="en",
                        help="language for plot titles, labels, legends, and annotations")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    dataset_root = args.dataset_root.resolve()
    evidence = repo / EVIDENCE_RELATIVE
    final_output = (args.output_dir or repo / OUTPUT_RELATIVE).resolve()
    output = final_output.with_name(final_output.name + ".building")
    if final_output.exists() and any(final_output.iterdir()):
        raise SystemExit(f"Refusing to replace completed or partial output: {final_output}")
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Refusing to replace an earlier partial build: {output}")
    output.mkdir(parents=True, exist_ok=True)
    criteria_path = evidence / "xfidc_criteria.json"
    analysis_path = evidence / "calibration_analysis.json"
    runner_root = evidence / "result" / "fd08_calibration"
    runner_result_path = runner_root / "result.json"

    sys.path.insert(0, str(repo / "src"))
    from cfd_sdf.fd08_calibration import (
        FORCE_COLUMNS,
        clipped_time_mean_from_rows,
        recompute_force_history,
        verify_output_manifest,
        verify_registered_dataset,
    )

    criteria_sha = sha256(criteria_path)
    analysis_sha = sha256(analysis_path)
    if criteria_sha != EXPECTED_CRITERIA_SHA256 or analysis_sha != EXPECTED_ANALYSIS_SHA256:
        raise SystemExit("The immutable R5 criteria or analysis SHA-256 does not match this diagnostic.")
    criteria = json.loads(criteria_path.read_text())
    analysis = json.loads(analysis_path.read_text())
    if (analysis.get("calibration_criteria_sha256") != criteria_sha
            or analysis.get("source_commit") != EXPECTED_SOURCE_COMMIT
            or analysis.get("calibration_verdict") != "FAIL"
            or analysis.get("formal_phase_allowed") is not False
            or analysis.get("formal_qualification") is not False
            or any(value is not False for value in analysis.get("qualification_flags", {}).values())):
        raise SystemExit("R5 analysis no longer matches the immutable fail-closed contract.")
    if (criteria.get("source_commit") != EXPECTED_SOURCE_COMMIT
            or len(criteria.get("state_order", [])) != 47
            or len(criteria.get("dataset_files", {})) != 89):
        raise SystemExit("R5 criteria does not match the expected source and state inventory.")
    dataset_audit = verify_registered_dataset(criteria, criteria_sha, dataset_root)
    if dataset_audit["inventory_sha256"] != analysis["registered_dataset_audit"]["inventory_sha256"]:
        raise SystemExit("Downloaded R5 dataset differs from the host-verified dataset inventory.")
    manifest_audit = verify_output_manifest(runner_root, runner_result_path)
    if (manifest_audit["manifest_sha256"] != EXPECTED_MANIFEST_SHA256
            or manifest_audit["inventory_sha256"] != analysis["runner_output_manifest"]["inventory_sha256"]):
        raise SystemExit("R5 runner output does not match the immutable manifest and host audit.")

    states = {row["run_id"]: row for row in criteria["state_order"]}
    if len(states) != 47 or set(states) != set(analysis["calibration_run_ids"]):
        raise SystemExit("R5 criteria and analysis state inventories differ.")
    force = {}
    stationarity_rows = []
    force_mean_max_diff = 0.0
    for state in criteria["state_order"]:
        run_id = state["run_id"]
        state_dir = runner_root / "states" / run_id
        force_path = state_dir / "flow_24.forces.csv"
        raw = recompute_force_history(
            force_path,
            force_scale_n_per_solver_force=analysis["force_scale_n_per_solver_force"],
        )
        summary = json.loads((state_dir / "state_result.json").read_text())
        prior = analysis["raw_force_history_inventory"][run_id]
        if (raw["sha256"] != prior["sha256"]
                or raw["sha256"] != summary["force_csv_sha256"]
                or summary.get("status") != "COMPLETED"):
            raise SystemExit(f"R5 force history or terminal state mismatch: {run_id}")
        if summary.get("phi_fortran_sha256") not in (None, state["phi_fortran_sha256"]):
            raise SystemExit(f"R5 state phi hash mismatch: {run_id}")
        for response in RESPONSES:
            difference = abs(raw["force_n"][response] - prior["host_recomputed_force_n"][response])
            force_mean_max_diff = max(force_mean_max_diff, difference)
            if not math.isclose(raw["force_n"][response], prior["host_recomputed_force_n"][response],
                                rel_tol=2e-14, abs_tol=1e-15):
                raise SystemExit(f"Raw force mean differs from prior R5 analysis: {run_id}/{response}")
        drift = raw["stationarity_relative_half_window_drift"]
        max_drift = max(drift.values())
        if not math.isclose(max_drift, summary["stationarity_drift_max"],
                            rel_tol=2e-10, abs_tol=1e-12):
            raise SystemExit(f"Stationarity differs from runner record: {run_id}")
        with force_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            history = [{key: float(row[key]) for key in FORCE_COLUMNS} for row in reader]
        scale = float(analysis["force_scale_n_per_solver_force"])
        half_window_forces = {}
        for half_name, start, end in (("first", 80.0, 100.0), ("second", 100.0, 120.0)):
            half_window_forces[half_name] = {
                response: clipped_time_mean_from_rows(
                    history, f"{response}_solver", start_t_u_l=start, end_t_u_l=end,
                ) * scale
                for response in RESPONSES
            }
        for response in RESPONSES:
            reproduced_drift = abs(
                half_window_forces["first"][response] - half_window_forces["second"][response]
            ) / max(abs(raw["force_n"][response]), sys.float_info.epsilon)
            if not math.isclose(reproduced_drift, drift[response], rel_tol=2e-10, abs_tol=1e-12):
                raise SystemExit(f"Raw half-window force means differ from stationarity audit: {run_id}/{response}")
        force[run_id] = raw
        raw["half_window_force_n"] = half_window_forces
        stationarity_rows.append({
            "run_id": run_id,
            "role": state["role"],
            "direction_id": state.get("direction_id"),
            "epsilon_m": state.get("epsilon_m"),
            "drag_relative_drift": drift["drag"],
            "downforce_relative_drift": drift["downforce"],
            "runner_recorded_max_relative_drift": summary["stationarity_drift_max"],
            "recomputed_max_relative_drift": max_drift,
            "runner_gate": summary.get("stationarity_within_registered_limit"),
        })

    eps_m = list(criteria["calibration_epsilon_ladder_m"])
    if tuple(eps_m) != EXPECTED_EPSILON_M:
        raise SystemExit(f"Unexpected immutable epsilon ladder: {eps_m}")
    eps_mm = [value * 1000.0 for value in eps_m]
    series: dict[str, Any] = {}
    intervals: dict[str, Any] = {}
    curvature: dict[str, Any] = {}
    paired_half_window: dict[str, Any] = {}
    resolved_count = 0
    for direction in DIRECTIONS:
        series[direction], intervals[direction], curvature[direction] = {}, {}, {}
        paired_half_window[direction] = {}
        for response in RESPONSES:
            input_rows = analysis["direction_response_pairs"][direction][response]
            rows = []
            for row in input_rows:
                epsilon = float(row["epsilon_m"])
                plus = force[row["plus_run_id"]]["force_n"][response]
                minus = force[row["minus_run_id"]]["force_n"][response]
                centered = (plus - minus) / 2.0
                q = centered / epsilon
                plus_half = force[row["plus_run_id"]]["half_window_force_n"]
                minus_half = force[row["minus_run_id"]]["half_window_force_n"]
                centered_first = (plus_half["first"][response] - minus_half["first"][response]) / 2.0
                centered_second = (plus_half["second"][response] - minus_half["second"][response]) / 2.0
                if not math.isclose(
                    (centered_first + centered_second) / 2.0, centered,
                    rel_tol=2e-12, abs_tol=1e-15,
                ):
                    raise SystemExit(
                        f"Half-window responses do not average to full-window S: {direction}/{response}/{epsilon}"
                    )
                if (not row["resolved"]
                        or not math.isclose(centered, row["centered_response_n"], rel_tol=2e-14, abs_tol=1e-15)
                        or not math.isclose(q, row["centered_slope_n_per_m"], rel_tol=2e-14, abs_tol=1e-14)):
                    raise SystemExit(f"R5 paired response does not reproduce analysis: {direction}/{response}/{epsilon}")
                floor = analysis["baseline_resolution_floors"][response]["response_floor_n"]
                resolved_count += int(abs(centered) > floor)
                rows.append({
                    "epsilon_m": epsilon,
                    "epsilon_mm": epsilon * 1000.0,
                    "response_plus_n": plus,
                    "response_minus_n": minus,
                    "centered_response_s_n": centered,
                    "q_n_per_m": q,
                    "response_floor_n": floor,
                    "resolved_above_floor": abs(centered) > floor,
                    "plus_run_id": row["plus_run_id"],
                    "minus_run_id": row["minus_run_id"],
                    "plus_force_history_sha256": force[row["plus_run_id"]]["sha256"],
                    "minus_force_history_sha256": force[row["minus_run_id"]]["sha256"],
                    "centered_response_first_half_n": centered_first,
                    "centered_response_second_half_n": centered_second,
                    "slope_first_half_n_per_m": centered_first / epsilon,
                    "slope_second_half_n_per_m": centered_second / epsilon,
                    "absolute_half_window_response_difference_n": abs(centered_first - centered_second),
                    "relative_half_window_response_difference": (
                        abs(centered_first - centered_second) / abs(centered)
                    ),
                })
            q_values = [row["q_n_per_m"] for row in rows]
            q_ref = float(median(q_values[:3]))
            for row in rows:
                row["q_ref_first3_median_n_per_m"] = q_ref
                row["reference_response_s_n"] = q_ref * row["epsilon_m"]
                row["response_residual_n"] = row["centered_response_s_n"] - row["reference_response_s_n"]
            series[direction][response] = rows
            paired_half_window[direction][response] = [
                {
                    "epsilon_m": row["epsilon_m"],
                    "epsilon_mm": row["epsilon_mm"],
                    "centered_response_first_half_n": row["centered_response_first_half_n"],
                    "centered_response_second_half_n": row["centered_response_second_half_n"],
                    "centered_response_full_window_n": row["centered_response_s_n"],
                    "slope_first_half_n_per_m": row["slope_first_half_n_per_m"],
                    "slope_second_half_n_per_m": row["slope_second_half_n_per_m"],
                    "relative_half_window_response_difference": row[
                        "relative_half_window_response_difference"
                    ],
                }
                for row in rows
            ]
            intervals[direction][response] = local_intervals(eps_mm, q_values)
            suffixes = []
            for start in range(len(q_values) - 2):
                fit = line_fit([x * x for x in eps_mm[start:]], q_values[start:])
                suffixes.append({
                    "first_epsilon_mm": eps_mm[start],
                    "last_epsilon_mm": eps_mm[-1],
                    "point_count": len(q_values[start:]),
                    "q0_n_per_m": fit["intercept"],
                    "coefficient_n_per_m_per_mm_squared": fit["slope"],
                    "rmse_n_per_m": fit["rmse"],
                    "r_squared_descriptive_only": fit["r_squared"],
                    "max_absolute_residual_n_per_m": fit["max_absolute_residual"],
                    "q0_minus_first3_median_n_per_m": fit["intercept"] - q_ref,
                })
            curvature[direction][response] = {
                "model": "q(epsilon) = q0 + c * (epsilon_mm)^2",
                "units": {"q0": "N/m", "c": "N/m/mm^2"},
                "suffix_fits_from_each_registered_index": suffixes,
                "interpretation": "Exploratory fits only; not an inferential test or gate.",
            }
    if resolved_count != 42:
        raise SystemExit(f"Expected 42 resolved response samples, observed {resolved_count}.")

    baseline_summary = {}
    for response in RESPONSES:
        values = [force[run_id]["force_n"][response] for run_id in analysis["baseline_repeat_ids"]]
        baseline_summary[response] = {
            "repeat_count": len(values),
            "minimum_n": min(values),
            "maximum_n": max(values),
            "median_n": float(median(values)),
            "span_n": max(values) - min(values),
            "registered_response_floor_n": analysis["baseline_resolution_floors"][response]["response_floor_n"],
        }

    import numpy as np

    shape = tuple(criteria["geometry"]["point_shape"])
    canonical = np.fromfile(dataset_root / "baseline_v17.phi_f4_fortran.raw", dtype="<f4")
    if canonical.size != math.prod(shape):
        raise SystemExit("Canonical phi Float32 array has an incorrect size.")
    canonical = canonical.reshape(shape, order="F").astype(np.float64)
    realized: dict[str, Any] = {}
    for direction in DIRECTIONS:
        direction_meta = criteria["direction_inventory"][direction]
        direction_data = np.fromfile(dataset_root / direction_meta["dataset_path"], dtype="<f4")
        if direction_data.size != math.prod(shape):
            raise SystemExit(f"Direction Float32 array has an incorrect size: {direction}")
        direction_data = direction_data.reshape(shape, order="C").astype(np.float64)
        direction_norm_sq = float(np.vdot(direction_data.ravel(), direction_data.ravel()))
        if direction_norm_sq <= 0.0:
            raise SystemExit(f"Registered direction is empty: {direction}")
        realized[direction] = {}
        for epsilon in eps_m:
            pair = {"signs": {}}
            for sign in (-1, 1):
                state = next(
                    item for item in criteria["state_order"]
                    if item.get("direction_id") == direction
                    and item.get("epsilon_m") == epsilon
                    and item.get("sign") == sign
                )
                values = np.fromfile(dataset_root / state["raw_file"], dtype="<f4")
                if values.size != math.prod(shape):
                    raise SystemExit(f"Perturbed phi Float32 array has an incorrect size: {state['run_id']}")
                phi = values.reshape(shape, order="F").astype(np.float64)
                delta = phi - canonical
                flat = delta.ravel()
                changed_mask = flat != 0.0
                changed = int(np.count_nonzero(changed_mask))
                max_abs = float(np.max(np.abs(flat)))
                rms_all = float(np.sqrt(np.mean(flat * flat)))
                rms_changed = float(np.sqrt(np.mean(flat[changed_mask] ** 2))) if changed else 0.0
                signed_direction = sign * direction_data
                projected_epsilon = float(np.vdot(flat, signed_direction.ravel()) / direction_norm_sq)
                expected_delta = epsilon * signed_direction
                expected_norm = float(np.linalg.norm(expected_delta.ravel()))
                residual_norm = float(np.linalg.norm((delta - expected_delta).ravel()))
                c_order_sha = hashlib.sha256(np.asarray(phi, dtype="<f4").tobytes(order="C")).hexdigest()
                if (c_order_sha != state["phi_c_order_sha256"]
                        or changed != state["changed_node_count"]
                        or not math.isclose(max_abs, state["maximum_pointwise_change_m"], rel_tol=0.0, abs_tol=1e-12)):
                    raise SystemExit(f"Float32 perturbation realization differs from criteria: {state['run_id']}")
                pair["signs"][str(sign)] = {
                    "run_id": state["run_id"],
                    "phi_fortran_sha256": state["phi_fortran_sha256"],
                    "changed_node_count": changed,
                    "maximum_abs_change_m": max_abs,
                    "maximum_abs_change_mm": max_abs * 1000.0,
                    "rms_all_nodes_m": rms_all,
                    "rms_all_nodes_mm": rms_all * 1000.0,
                    "rms_changed_nodes_m": rms_changed,
                    "rms_changed_nodes_mm": rms_changed * 1000.0,
                    "direction_projection_equivalent_epsilon_m": projected_epsilon,
                    "projection_epsilon_over_nominal": projected_epsilon / epsilon,
                    "relative_l2_error_vs_nominal_direction": residual_norm / expected_norm,
                }
            pair["summary"] = {}
            for key in ("changed_node_count", "maximum_abs_change_m", "rms_all_nodes_m",
                        "maximum_abs_change_mm", "rms_all_nodes_mm", "rms_changed_nodes_m",
                        "direction_projection_equivalent_epsilon_m", "projection_epsilon_over_nominal"):
                values = [pair["signs"][str(sign)][key] for sign in (-1, 1)]
                pair["summary"][key] = {
                    "minimum_plus_minus": min(values),
                    "maximum_plus_minus": max(values),
                    "mean_plus_minus": float(np.mean(values)),
                }
            realized[direction][f"{epsilon:.12g}"] = pair

    stationarity_summary = {}
    for response in RESPONSES:
        values = [row[f"{response}_relative_drift"] for row in stationarity_rows]
        stationarity_summary[response] = {
            "state_count": len(values),
            "maximum_relative_drift": max(values),
            "median_relative_drift": float(median(values)),
            "p95_relative_drift": float(np.quantile(values, 0.95)),
        }
    max_drifts = [row["recomputed_max_relative_drift"] for row in stationarity_rows]
    stationarity_summary["all_state_response_max"] = {
        "state_count": len(max_drifts),
        "maximum_relative_drift": max(max_drifts),
        "median_relative_drift": float(median(max_drifts)),
        "p95_relative_drift": float(np.quantile(max_drifts, 0.95)),
        "runner_comparison": "all 47 recomputed maxima matched state_result.json",
    }

    paired_half_window_summary = {}
    for direction in DIRECTIONS:
        paired_half_window_summary[direction] = {}
        for response in RESPONSES:
            rows = paired_half_window[direction][response]
            maximum = max(rows, key=lambda row: row["relative_half_window_response_difference"])
            paired_half_window_summary[direction][response] = {
                "sample_count": len(rows),
                "median_relative_difference": float(median(
                    row["relative_half_window_response_difference"] for row in rows
                )),
                "maximum_relative_difference": maximum["relative_half_window_response_difference"],
                "maximum_at_epsilon_mm": maximum["epsilon_mm"],
                "maximum_first_half_response_n": maximum["centered_response_first_half_n"],
                "maximum_second_half_response_n": maximum["centered_response_second_half_n"],
                "maximum_full_window_response_n": maximum["centered_response_full_window_n"],
            }

    try:
        base_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        base_head = None
    sdf_spacing_mm = float(criteria["geometry"]["design_lattice_spacing_m"]) * 1000.0
    flow_spacing_mm = float(criteria["case"]["flow_spacing_m"]) * 1000.0
    figures = make_figures(
        output, eps_mm, eps_m, series, realized, stationarity_rows,
        paired_half_window, sdf_spacing_mm, flow_spacing_mm, args.plot_language,
    )
    import matplotlib

    script_sha = sha256(script)
    result = {
        "schema": "fd08_r5_posthoc_p1_diagnostic_v2",
        "evidence_class": "solver_free_post_hoc_calibration_diagnostic_unregistered",
        "verdict_effect": "none; immutable R5 verdict remains FAIL",
        "formal_phase_allowed": False,
        "fresh33_registered_or_run": False,
        "qualification_flags": analysis["qualification_flags"],
        "base_integration_head": base_head,
        "diagnostic_script": {"path": script.relative_to(repo).as_posix(), "sha256": script_sha},
        "input_bindings": {
            "criteria_path": criteria_path.relative_to(repo).as_posix(),
            "criteria_sha256": criteria_sha,
            "source_commit": EXPECTED_SOURCE_COMMIT,
            "existing_analysis_path": analysis_path.relative_to(repo).as_posix(),
            "existing_analysis_sha256": analysis_sha,
            "runner_manifest_sha256": manifest_audit["manifest_sha256"],
            "runner_inventory_sha256": manifest_audit["inventory_sha256"],
            "runner_verified_file_count": manifest_audit["verified_file_count"],
            "downloaded_dataset_path": str(dataset_root),
            "dataset_inventory_sha256": dataset_audit["inventory_sha256"],
            "dataset_verified_file_count": dataset_audit["verified_file_count"],
            "recomputed_raw_force_history_count": len(force),
            "registered_source_inputs": analysis["verified_source_inputs"],
        },
        "candidate_and_case": {
            "candidate": criteria["geometry"]["state_label"],
            "candidate_identity_sha256": criteria["geometry"]["canonical_state_identity_sha256"],
            "canonical_phi_sha256": criteria["geometry"]["canonical_phi_fortran_sha256"],
            "flow_id": criteria["case"]["case_id"],
            "reynolds": criteria["case"]["reynolds"],
            "time_window_t_u_l": analysis["window_t_u_l"],
            "design_lattice_spacing_m": criteria["geometry"]["design_lattice_spacing_m"],
            "flow_spacing_m": criteria["case"]["flow_spacing_m"],
            "force_scale_n_per_solver_force": analysis["force_scale_n_per_solver_force"],
        },
        "method": {
            "centered_response": "S(epsilon) = (R(+epsilon) - R(-epsilon)) / 2",
            "slope": "q(epsilon) = S(epsilon) / epsilon",
            "local_interval_rule": "All contiguous windows of at least 3 registered points with q within +/-5% of that window's median; descriptive only.",
            "curvature_model": "q(epsilon) = q0 + c * (epsilon_mm)^2; fit every suffix of at least 3 points.",
            "response_residual_reference": "q_ref is the median q of the first 3 registered epsilon points for each direction and response.",
            "response_residual": "S_residual = S - q_ref * epsilon, in N.",
            "realized_epsilon": "Projection of actual Float32 phi change onto sign times the registered direction; max, RMS, and changed-node count are also reported.",
            "stationarity": "Recompute trapezoidal force means in [80,100] and [100,120] tU/L from all 47 raw histories.",
            "paired_response_half_window_sensitivity": "For each plus/minus pair, compare S computed separately on [80,100] and [100,120] tU/L against the full-window S; descriptive only, not a gate.",
            "descriptive_unregistered_only": True,
        },
        "baseline_repeatability_and_response_floor": baseline_summary,
        "force_mean_max_absolute_difference_from_existing_analysis_n": force_mean_max_diff,
        "resolved_response_count_above_registered_floor": resolved_count,
        "series": series,
        "local_5_percent_intervals": intervals,
        "epsilon_squared_tail_fits": curvature,
        "float32_realized_perturbations": {
            "nominal_epsilon_m": eps_m,
            "nominal_epsilon_mm": eps_mm,
            "design_lattice_spacing_mm": sdf_spacing_mm,
            "flow_spacing_mm": flow_spacing_mm,
            "nominal_epsilon_over_design_lattice": [value / sdf_spacing_mm for value in eps_mm],
            "nominal_epsilon_over_flow_cell": [value / flow_spacing_mm for value in eps_mm],
            "by_direction_and_epsilon": realized,
        },
        "stationarity": {
            "time_window_t_u_l": analysis["window_t_u_l"],
            "state_results": stationarity_rows,
            "summary": stationarity_summary,
        },
        "paired_response_half_window_sensitivity": {
            "definition": "S_half=(R_plus_half-R_minus_half)/2; relative difference=abs(S_first-S_second)/abs(S_full)",
            "first_window_t_u_l": [80.0, 100.0],
            "second_window_t_u_l": [100.0, 120.0],
            "summary": paired_half_window_summary,
            "series": paired_half_window,
            "interpretation": "Post-hoc temporal-window sensitivity diagnostic; no registered pass/fail threshold and no change to R5 verdict.",
        },
        "plotting_environment": {
            "matplotlib_version": matplotlib.__version__,
            "backend": "Agg",
            "figure_language": args.plot_language,
            "font_family": PLOT_TEXT[args.plot_language]["font_family"] or "Matplotlib default",
        },
        "figures": figures,
        "limitations": [
            "Post-hoc R5 diagnostics only; no registered criteria or new verdict.",
            "R5 FAIL and NO_COMMON_PLATEAU are preserved unchanged.",
            "No epsilon ladder, response floor, threshold, operator, direction, or FD-08 definition was changed.",
            "No new solver execution was performed; R5 data are not formal fresh33 evidence.",
            "This does not establish OpenFOAM absolute accuracy, high-Re accuracy, grid independence, full-field gradient correctness, reverse AD correctness, optimizer descent, or topology-change correctness.",
        ],
    }
    result_path = output / "diagnostic_result.json"
    write_immutable(result_path, json_bytes(result))
    result_sha = sha256(result_path)

    changed_rms_ratios = {}
    all_rms_ratios = {}
    projection_ratios = []
    max_ratios = []
    changed_counts = []
    for direction in DIRECTIONS:
        changed_rms_ratios[direction] = []
        all_rms_ratios[direction] = []
        for eps_text, pair in realized[direction].items():
            epsilon = float(eps_text)
            summary = pair["summary"]
            changed_rms_ratios[direction].append(
                summary["rms_changed_nodes_m"]["mean_plus_minus"] / epsilon
            )
            all_rms_ratios[direction].append(
                summary["rms_all_nodes_m"]["mean_plus_minus"] / epsilon
            )
            projection_ratios.extend(
                pair["signs"][sign]["projection_epsilon_over_nominal"] for sign in ("-1", "1")
            )
            max_ratios.extend(
                pair["signs"][sign]["maximum_abs_change_m"] / epsilon for sign in ("-1", "1")
            )
            changed_counts.extend(
                pair["signs"][sign]["changed_node_count"] for sign in ("-1", "1")
            )

    note = [
        "# FD-08 R5 P1 事後診断",
        "",
        "証拠区分: solver_free_post_hoc_calibration_diagnostic_unregistered。",
        "P2判断用の記述的解析であり、criteriaの登録、epsilon・gateの変更、formal ladderの選択、",
        "R5の確定FAILの変更は行っていない。",
        "",
        f"- R5 criteria SHA-256: {criteria_sha}",
        f"- 既存R5解析 SHA-256: {analysis_sha}",
        f"- runner manifest SHA-256: {manifest_audit['manifest_sha256']}（{manifest_audit['verified_file_count']} files）",
        f"- download dataset inventory SHA-256: {dataset_audit['inventory_sha256']}（{dataset_audit['verified_file_count']} files）",
        f"- 診断スクリプト SHA-256: {script_sha}",
        f"- 診断JSON SHA-256: {result_sha}",
        f"- 描画環境: Matplotlib {matplotlib.__version__}",
        f"- 図のタイトル・軸・凡例・注記の言語: {'日本語' if args.plot_language == 'ja' else 'English'}",
        f"- 基準 integration HEAD: {base_head}",
        "",
        "## P2向けの観測",
        "",
        f"R5 verdictはFAILのまま、登録済み5点selectorは{analysis['formal_ladder_selection']['status']}のまま。",
        f"42/42のdirectional responseは既登録response floorを上回るが、formal ladderは選択されていない。",
        "図はraw historyから再計算したq(epsilon)、探索的なepsilon² suffix fit、S残差、",
        "Float32実現変位、47 stateの半窓stationarity、±応答の半窓感度を示す。",
        "",
        "以下の±5%区間は、登録済み7 epsilonのうち3点以上からなる全連続窓について、",
        "窓ごとのq中央値に対する最大偏差を列挙した未登録の説明用集計である。",
        "登録済みの共通5点gateを置き換えるものではない。",
        "",
        "| Direction / response | 最長の説明用区間 (mm) |",
        "| --- | --- |",
    ]
    for direction in DIRECTIONS:
        for response in RESPONSES:
            longest = intervals[direction][response]["longest_intervals"]
            label = ", ".join(
                f"{row['first_epsilon_mm']:g}–{row['last_epsilon_mm']:g} ({row['point_count']} pts)"
                for row in longest
            ) or "該当なし"
            note.append(f"| {direction} / {response} | {label} |")
    note.extend([
        "",
        "この説明用定義でも6系列に共通する区間はない。D1 drag/downforceとD0 dragには",
        "3点以上の区間がなく、D0 downforceとD2の2系列には個別の区間がある。",
        "したがって、局所的な一致が一部に見えてもR5の共通5点失敗は解消しない。",
        "",
        "### 大epsilon側のq = q0 + c epsilon² fit（各系列の最後4点、記述値）",
        "",
        "| Direction / response | q0 (N/m) | c (N/m/mm²) | RMSE (N/m) | R² |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for direction in DIRECTIONS:
        for response in RESPONSES:
            fit = curvature[direction][response]["suffix_fits_from_each_registered_index"][-2]
            note.append(
                f"| {direction} / {response} | {fit['q0_n_per_m']:.5g} | "
                f"{fit['coefficient_n_per_m_per_mm_squared']:.5g} | "
                f"{fit['rmse_n_per_m']:.4g} | {fit['r_squared_descriptive_only']:.4f} |"
            )
    note.extend([
        "",
        "suffixは4点だけで、q0は大epsilon側からの外挿である。適合度は方向・responseで異なり、",
        "この表だけで滑らかな曲率やcut/mask切替の機構を判定しない。",
        "",
        "### 小epsilon側のS残差",
        "",
        "S_ref = q_ref epsilon、q_refは各系列の最初の3点のq中央値とした。",
        "最初の3点のうちqが中央値になる点の残差は定義上0 N（該当点は系列ごとに異なる）。",
        "最初の3点における絶対残差の最大はdragで",
        f"{max(abs(row['response_residual_n']) for rows in series.values() for row in rows['drag'][:3]):.4g} N、",
        "downforceで",
        f"{max(abs(row['response_residual_n']) for rows in series.values() for row in rows['downforce'][:3]):.4g} N。",
        "これは一つの固定参照からの差であり、quantizationの証拠やnoise floorとして登録した値ではない。",
        "",
        "### 実現変位と格子幅",
        "",
        f"SDF lattice spacingは{sdf_spacing_mm:g} mm、flow cell幅は{flow_spacing_mm:.4g} mm。",
        f"名目epsilonはSDF幅の{min(eps_mm)/sdf_spacing_mm:.4g}〜{max(eps_mm)/sdf_spacing_mm:g}倍、",
        f"flow cell幅の{min(eps_mm)/flow_spacing_mm:.4g}〜{max(eps_mm)/flow_spacing_mm:g}倍。",
        f"42個のplus/minus perturbationでchanged-node countは{min(changed_counts)}〜{max(changed_counts)}。",
        "maximum |delta phi| とdirectionへの射影epsilonは名目値にほぼ一致する一方、",
        "changed nodes上のRMS / 名目epsilonの平均は",
        f"D0 {sum(changed_rms_ratios[DIRECTIONS[0]])/7:.4f}, "
        f"D1 {sum(changed_rms_ratios[DIRECTIONS[1]])/7:.4f}, "
        f"D2 {sum(changed_rms_ratios[DIRECTIONS[2]])/7:.4f}。",
    ])
    note.extend([
        "全grid上のRMS/名目epsilonはそれぞれ",
        f"D0 {sum(all_rms_ratios[DIRECTIONS[0]])/7:.4f}, "
        f"D1 {sum(all_rms_ratios[DIRECTIONS[1]])/7:.4f}, "
        f"D2 {sum(all_rms_ratios[DIRECTIONS[2]])/7:.4f}。",
        f"direction射影比は{min(projection_ratios):.10f}〜{max(projection_ratios):.10f}、",
        f"最大点変位/名目epsilonは{min(max_ratios):.10f}〜{max(max_ratios):.10f}。",
        "したがってepsilon等価性は指標依存であり、RMS比をmax値や射影比と混同しない。",
        "ここでのmax/RMSはphi格子値の変化量であり、zero-isosurfaceの直接移動距離ではない。",
        "滑らかなSDF上では局所的にdelta n ≈ -delta phi/|grad phi|と関係するが、今回その距離場を",
        "別途計測・適格化してはいない。direction射影比だけで方向間RMS等価性は示せない。",
        "",
        "### Stationarity",
        "",
        f"47 stateの最大半窓driftはdrag {stationarity_summary['drag']['maximum_relative_drift']:.6g}、",
        f"downforce {stationarity_summary['downforce']['maximum_relative_drift']:.6g}。",
        "全stateでrunner記録と再計算値が一致した。これは半窓比較の確認であり、",
        "あらゆる時間依存誤差がないことを証明するものではない。各stateの力（約0.33 N）に対する",
        "相対driftが小さくても、plus/minusの差分S（µN級）への相対影響は大きくなり得る。",
        "次表は各epsilonでSを半窓ごとに計算し、|S_first-S_second|/|S_full|をとった事後診断である。",
        "これは新しいgateではなく、時間窓依存の大きさを見る感度指標である。",
        "",
        "| Direction / response | 最大相対差 | epsilon (mm) | median相対差 |",
        "| --- | ---: | ---: | ---: |",
    ])
    for direction in DIRECTIONS:
        for response in RESPONSES:
            summary = paired_half_window_summary[direction][response]
            note.append(
                f"| {direction} / {response} | {summary['maximum_relative_difference'] * 100:.3f}% | "
                f"{summary['maximum_at_epsilon_mm']:g} | {summary['median_relative_difference'] * 100:.3f}% |"
            )
    d1_downforce = min(
        paired_half_window[DIRECTIONS[1]]["downforce"],
        key=lambda row: abs(row["epsilon_mm"] - 0.05),
    )
    note.extend([
        "",
        f"特にD1 downforce ε=0.05 mmでは、S_first={d1_downforce['centered_response_first_half_n']:.9g} N、",
        f"S_second={d1_downforce['centered_response_second_half_n']:.9g} N、",
        f"S_full={d1_downforce['centered_response_full_window_n']:.9g} Nで、相対差は",
        f"{d1_downforce['relative_half_window_response_difference'] * 100:.3f}%だった。",
        "bit-identical baseline repeatsは同じ計算の再現性を示すが、決定論的な過渡応答や時間窓依存を",
        "除外しない。小epsilonの不規則さをcut切替だけに帰属させる根拠はない。",
    ])
    note.extend([
        "",
        "## P2で残る判断",
        "",
        "P1結果はB1/B1-prime/B2/B3のいずれかを自動選択しない。特にD1に3点の±5%区間が",
        "ないことだけでは、5%条件が構造的に達成不能とは証明できず、B1-primeのgate変更根拠",
        "にはならない。逆に一部系列の局所区間やtail fitだけで共通FD oracleを主張できない。",
        "R6登録・submit、gateやladderの変更、FD-08定義やdirectionの変更はP2のユーザー判断待ち。",
        "fresh33は未登録・未実行で、全qualification flagはfalseのまま。",
        "",
        "## 図",
        "",
    ])
    for name, filename in zip(figures, FIGURE_FILES):
        note.append(f"- {filename} — SHA-256 {figures[name]}")
    note.extend([
        "",
        "## P2での停止点",
        "",
        "この成果物の範囲はP2のユーザー判断まで。R6は未登録・未submit、fresh33は未登録・未実行。",
        "B1/B1-prime/B2/B3、およびladder・gate・FD-08定義・directionの変更は承認済み計画に従い",
        "ユーザー判断待ち。全qualification flagはfalseのまま。",
        "",
        "epsilonごとの値、hash、source binding、Float32変位、stationarity値はdiagnostic_result.jsonを参照。",
    ])
    note_path = output / "P1_diagnostic_note.md"
    write_immutable(note_path, ("\n".join(note) + "\n").encode())

    files = [result_path, note_path, *(output / filename for filename in FIGURE_FILES)]
    sums = "".join(
        f"{sha256(path)}  {path.name}\n"
        for path in sorted(files, key=lambda item: item.name)
    ).encode()
    write_immutable(output / "SHA256SUMS", sums)
    if final_output.exists():
        final_output.rmdir()
    output.rename(final_output)
    print(json.dumps({
        "status": "P1_DIAGNOSTIC_COMPLETE",
        "verdict": "R5_FAIL_UNCHANGED",
        "result": str(final_output / result_path.name),
        "result_sha256": result_sha,
        "note": str(final_output / note_path.name),
        "figures": figures,
        "maximum_half_window_drift": stationarity_summary["all_state_response_max"]["maximum_relative_drift"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
