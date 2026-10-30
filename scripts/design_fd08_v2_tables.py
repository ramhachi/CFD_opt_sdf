#!/usr/bin/env python3
"""Unregistered solver-free FD-08 v2 design tables; never load R5 artifacts."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/evidence/fd08_v2_stage1_2026_10_06"

# Hand-transcribed constants from instruction §4; no R5 artifact is opened.
# Raw R5 times are separately reported to expose the rounding assumption.
SOLVER_S_PER_STATE = 108.7
OVERHEAD_S_PER_STATE = 74.0
R5_SOLVER_S = 5109.38
R5_ELAPSED_S = 8596.5
R5_STATES = 47
SOLVER_LIMIT_S = 5400.0
KERNEL_LIMIT_S = 10800.0


def location(path: str, anchor: str) -> str:
    """Verify each source anchor exists and report its current one-based line."""
    matches = [i for i, line in enumerate((ROOT / path).read_text().splitlines(), 1)
               if line.startswith(anchor)]
    if len(matches) != 1:
        raise ValueError(f"expected one source anchor: {path}: {anchor!r}: {matches}")
    return f"{path}:{matches[0]}"


def source_changes() -> list[dict]:
    rows = []
    for name, reason in (
        ("FORMAL_EPSILON_COUNT", "formal の 5 点固定と calibration 部分集合条件"),
        ("FORMAL_DIRECTION_IDS", "D0/D1/D2 の固定 inventory。B-4/B-6 は未決"),
        ("MINIMUM_CALIBRATION_EPSILON_COUNT", "7 点以上と 6 点案の衝突"),
        ("MINIMUM_CALIBRATION_SPAN_RATIO", "100 倍以上と 10/16.7 倍案の衝突"),
        ("validate_calibration_ladder", "点数・span 制約と新 ladder の別契約"),
        ("validate_formal_epsilon_ladder", "5 点固定・calibration 部分集合から内部新点へ"),
        ("_plateau_metrics", "median-slope 5% から WLS と 6 項目への別契約"),
        ("select_formal_epsilon_ladder", "3 方向共通の連続 5 点窓、全 6 系列の gate"),
        ("classify_calibration_screen", "5 点窓を列挙する旧 gate の停止規則"),
        ("evaluate_formal_direction_response", "5 観測・floor・plateau 固定"),
        ("aggregate_formal_verdict", "全 6 系列固定。B-4 の被覆規則は未決"),
        ("derive_response_floor", "baseline span の床と jitter に基づく σ 推定は異なる"),
    ):
        anchor = f"{name} =" if name.isupper() else f"def {name}("
        rows.append({"location": location("src/cfd_sdf/fd08_calibration.py", anchor),
                     "change_needed_if_approved": reason})
    for name, reason in (
        ("FRESH_QUALIFICATION_RUNS", "33 state 固定と predict-then-run 24 state"),
        ("PLATEAU_RELATIVE_LIMIT", "5% 固定。新 tolerance は暫定案・未承認"),
        ("MINIMUM_PLATEAU_POINTS", "3 plateau 点と v2 gate の点数要件"),
        ("validate_fd08_design", "3 baseline + 3×5×2 の固定矩形"),
        ("validate_fd08_run_partition", "fresh33 固定。disjoint inventory は維持"),
    ):
        anchor = f"{name} =" if name.isupper() else f"def {name}("
        rows.append({"location": location("src/cfd_sdf/fd08_contract.py", anchor),
                     "change_needed_if_approved": reason})
    for path, name, reason in (
        ("scripts/register_fd08_formal.py", "build", "calibration の連続 5 点部分集合・旧 sources と gate の hash 結合"),
        ("scripts/verify_fd08_formal.py", "verify", "fresh33・3 方向・calibration の 5 baseline・全旧 gate の再計算"),
        ("scripts/register_fd08_calibration.py", "build", "旧 ladder 検証、D0/D1/D2、baseline 5、signed inventory、criteria 結合"),
        ("scripts/analyze_fd08_calibration.py", "analyze", "旧 pair 分母・baseline floor・共通 plateau selector・新 jitter roles"),
    ):
        rows.append({"location": location(path, f"def {name}("),
                     "change_needed_if_approved": reason})
    return rows


def epsilon_semantics() -> list[dict]:
    targets = {
        "src/cfd_sdf/gradients/directional_fd.py": ("perturbation_case_id", "perturbed_state", "classify_direction"),
        "src/cfd_sdf/fd08_calibration.py": ("validate_calibration_ladder", "validate_formal_epsilon_ladder",
            "audit_float32_centered_pair", "centered_pair", "_plateau_metrics", "select_formal_epsilon_ladder",
            "classify_calibration_screen", "evaluate_formal_direction_response"),
        "src/cfd_sdf/fd08_contract.py": ("validate_fd08_design", "audit_float32_perturbation", "evaluate_fd08_response"),
        "scripts/register_fd08_calibration.py": ("epsilon_tag", "build", "bind_cpu_rehearsal"),
        "scripts/register_fd08_formal.py": ("epsilon_tag", "build"),
        "scripts/analyze_fd08_calibration.py": ("analyze",),
        "scripts/verify_fd08_formal.py": ("verify",),
    }
    return [{"location": location(path, f"def {name}("), "function": name}
            for path, names in targets.items() for name in names]


def build_tables() -> dict:
    rows = []
    for directions, epsilons, baselines in itertools.product((3, 4, 5), (6, 7, 8), (1, 5)):
        signed = 2 * directions * epsilons
        jitter = 2 * directions
        states = signed + baselines + jitter
        solver = states * SOLVER_S_PER_STATE
        elapsed = states * (SOLVER_S_PER_STATE + OVERHEAD_S_PER_STATE)
        rows.append({"directions": directions, "epsilon_points": epsilons, "baseline_states": baselines,
            "signed_ladder_states": signed, "jitter_states": jitter, "total_states": states,
            "solver_s": solver, "overhead_s": states * OVERHEAD_S_PER_STATE, "estimated_elapsed_s": elapsed,
            "solver_margin_s": SOLVER_LIMIT_S - solver, "kernel_margin_s": KERNEL_LIMIT_S - elapsed,
            "solver_limit_exceeded": solver > SOLVER_LIMIT_S, "kernel_limit_exceeded": elapsed > KERNEL_LIMIT_S})
    assert len(rows) == 18 and rows[0]["total_states"] == 43 and rows[-1]["total_states"] == 95
    assert all(row["solver_limit_exceeded"] for row in rows if row["directions"] >= 4)
    return {
        "evidence_class": "solver_free_design_and_simulation_unregistered", "numpy_version": np.__version__,
        "qualification_flags": {key: False for key in ("shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")},
        "pending_decisions": ["B-3", "B-4", "B-5", "B-6", "B-7", "ladder", "baseline_count", "budget"],
        "runtime_assumptions": {"solver_s_per_state": SOLVER_S_PER_STATE, "overhead_s_per_state": OVERHEAD_S_PER_STATE,
            "solver_limit_s": SOLVER_LIMIT_S, "kernel_limit_s": KERNEL_LIMIT_S,
            "source": "docs/issues/46_fd08_v2_stage1_instruction_2026_10_06.md §4; docs/phase_plan.md:6257-6258",
            "budget_source": "docs/evidence/xfid_candidate_c_2026_10_04/xfidc_criteria.json:100; docs/phase_plan.md:6053-6054",
            "R5_handwritten_solver_s": R5_SOLVER_S, "R5_handwritten_elapsed_s": R5_ELAPSED_S, "R5_states": R5_STATES,
            "R5_raw_solver_s_per_state": R5_SOLVER_S / R5_STATES,
            "R5_raw_overhead_s_per_state": (R5_ELAPSED_S - R5_SOLVER_S) / R5_STATES},
        "state_formula": "2 * directions * epsilon_points + baseline_states + 2 * directions",
        "jitter_interpretation": "two signs at one shifted magnitude epsilon_mid*(1+0.001); one centered S contrast per direction/response",
        "runtime_rows": rows, "registered_code_changes_design_only": source_changes(),
        "epsilon_m_affected_functions_design_only": epsilon_semantics(),
        "epsilon_semantics_note": "Current epsilon_m is the nominal scalar coefficient of max=1 phi direction; realized float32 direction/physical normal displacement are audited separately. No effective-epsilon redefinition is made.",
    }


def round_json(value):
    if isinstance(value, float):
        return float(f"{value:.12g}")
    if isinstance(value, dict):
        return {key: round_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [round_json(item) for item in value]
    return value


def markdown(table: dict) -> str:
    lines = ["# FD-08 v2 Stage 1 設計表（未登録）", "", "証拠区分: `solver_free_design_and_simulation_unregistered`。全 qualification flag は false。B-3〜B-7、ladder、baseline 数、予算は未決。R5 FAIL は固定。", "",
        "計算式: `2×方向数×ε点数 + baseline数 + 2×方向数`。jitter は 1 つのずらした ε における ±sign pair（2 state/方向）の費用。", "",
        "solver は 108.7 s/state、overhead は約 74 s/state。上限は solver 5,400 s、kernel 10,800 s。R5 手書き実測 5,109.38 s / 47 = 108.710212766 s/state、経過 8,596.5 s / 47、差は 74.1940425532 s/state。表は指示の丸めた定数を使う予算目安であり、新方向や上端拡張に対する runtime 保証ではない。", "",
        "出典: `docs/issues/46_fd08_v2_stage1_instruction_2026_10_06.md §4`、`docs/phase_plan.md:6257-6258`、solver 上限 `docs/evidence/xfid_candidate_c_2026_10_04/xfidc_criteria.json:100`、kernel 上限 `docs/phase_plan.md:6053-6054`。スクリプトは R5 artifact を読まず、数値は手書き定数。", "",
        "| 方向 | ε点 | baseline | jitter | 合計state | solver s | 経過目安 s | solver超過 | kernel超過 |", "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |"]
    for r in table["runtime_rows"]:
        lines.append(f'| {r["directions"]} | {r["epsilon_points"]} | {r["baseline_states"]} | {r["jitter_states"]} | {r["total_states"]} | {r["solver_s"]:.1f} | {r["estimated_elapsed_s"]:.1f} | {"YES" if r["solver_limit_exceeded"] else "NO"} | {"YES" if r["kernel_limit_exceeded"] else "NO"} |')
    lines += ["", "4 方向以上は jitter を含めると全案が solver 上限を超える。baseline 1 と 5 の選択、budget 増額・kernel 分割は承認事項。baseline 反復で jitter variance を代用する選択はしない。", "", "## 登録済みコードの変更候補（編集していない）", "", "全 location はスクリプト実行で当該 source anchor を確認した。新契約で必要なら別の v2 実装に分離し、保護済み source binding を維持する。", "", "| file:line | 承認後に必要となる変更 |", "| --- | --- |"]
    lines += [f'| `{r["location"]}` | {r["change_needed_if_approved"]} |' for r in table["registered_code_changes_design_only"]]
    lines += ["", "## epsilon_m の意味が影響する関数（変更していない）", "", table["epsilon_semantics_note"], "", "`phi± = float32(phi0 ± epsilon_nominal_m*d)` の ε は SDF値の最大変位を指定する係数。実現 normal displacement は局所 `|∇phi|`、法線、float32 rounding に依存し、名目 ε と同一とみなさない。有効 ε を分母に入れると oracle と hash/ID の契約が変わるため、方向そのものの実現誤差と別に事前決定が要る。", ""]
    lines += [f'- `{r["location"]}` (`{r["function"]}`)' for r in table["epsilon_m_affected_functions_design_only"]]
    lines += ["", "JSON float は有効数字 12 桁、sort_keys=True、allow_nan=False。hash は同一環境内の再現確認用、機種間では参考値。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    table = round_json(build_tables())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "design_tables.json").write_text(json.dumps(table, indent=2, sort_keys=True, allow_nan=False) + "\n")
    (args.output_dir / "design_tables.md").write_text(markdown(table))
    print(f"18 designs written to {args.output_dir}; all source locations verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
