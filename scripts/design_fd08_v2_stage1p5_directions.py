#!/usr/bin/env python3
"""Canonical geometry diagnostics of fixed analytical lobe options (not directions).

Only protected D0/D1/D2 are regenerated. New expressions are evaluated in
temporary Float64 active-node vectors, never full-grid direction/state arrays.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.fd08_contract import CANONICAL_PHI_FORTRAN_F32_SHA256, CANONICAL_STATE_NPZ_SHA256
from cfd_sdf.gradients.directional_fd import direction_sha256, generate_directions, phi_sha256

DEFAULT_STATE = Path("/Users/sota/.codex/worktrees/issue45-root-certifier-integration/work/sdf_native_genesis_v17/sdf_design_state.npz")
DEFAULT_OUTPUT = ROOT / "docs/evidence/fd08_v2_stage1p5_2026_10_06"
EVIDENCE_CLASS = "solver_free_design_and_numeric_contract_unregistered"

# Frozen before any correlation/support diagnostic. Fractions use the active
# coordinate bounding box, not measured forces or directions. No tuning loop.
PRESETS = [
    {"id": "P1_upstream_lobe", "centers_fraction": [[0.25, 0.5, 0.5]],
     "widths_fraction": [0.6, 0.8, 0.8], "coefficients": [1.0]},
    {"id": "P2_downstream_lobe", "centers_fraction": [[0.75, 0.5, 0.5]],
     "widths_fraction": [0.6, 0.8, 0.8], "coefficients": [1.0]},
    {"id": "P3_vertical_signed_pair", "centers_fraction": [[0.5, 0.5, 0.75], [0.5, 0.5, 0.25]],
     "widths_fraction": [0.8, 0.8, 0.6], "coefficients": [1.0, -1.0]},
]


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_location(path: str, anchor: str) -> str:
    matches = [i for i, line in enumerate((ROOT / path).read_text().splitlines(), 1)
               if line.startswith(anchor)]
    if len(matches) != 1:
        raise ValueError(f"source anchor not unique: {path} {anchor!r}")
    return f"{path}:{matches[0]}"


def frozen_definition() -> dict:
    return {"presets": PRESETS, "coordinate_rule": "centers=active_min+fraction*active_span; widths=fraction*active_span",
        "a_rule": "sum coefficient*max(1-sum(((x-center)/width)^2),0)^3",
        "phi_rule": "raw=-a*norm(gradient_phi)*interface_taper; active_node_values=raw/max(abs(raw))",
        "gradient_rule": "second-order central differences on interior nodes; first-order one-sided at box edges; zero-gradient raw remains zero",
        "normal_convention": "n=+gradient_phi/norm(gradient_phi); negative phi is solid; delta_phi=-u dot gradient_phi",
        "recommendation_before_diagnostics": "P1 as simplest single localized normal mode, conditional on future approved artifact/float32/geometry gates; no change after correlations",
        "array_restriction": "temporary Float64 active-node expressions only; no new full-grid direction, Float32 array, candidate hash, signed state or dataset"}


def freeze_text(freeze: dict, freeze_sha: str) -> str:
    return "\n".join([
        "# B-6 analytical lobe design / canonical diagnostics (Stage 1.5, 未登録)", "",
        f"証拠区分: `{EVIDENCE_CLASS}`。全6 qualification flag は false。B-6 は未承認。", "",
        "この文書の以下の preset を cosine/support 診断実行前に固定した。旧 Stage 1 設計メモを具体化する設計診断であり、新 direction の生成・登録ではない。",
        f"解析定義 freeze SHA-256: `{freeze_sha}`。再現可能な定義は `direction_diagnostics.json` の `frozen_definition`。", "",
        "```json", json.dumps(freeze, indent=2, sort_keys=True, allow_nan=False), "```", "",
        "中心/幅は canonical の unconstrained active-node coordinate bbox の割合。診断を見た後に位置・幅・符号を変えない。P1 を低実装量の第一候補とする原理は単一の局在モードの簡単さであり、force または cosine の最良値による選択ではない。P2 はstreamwise位置を変える比較、P3 は上/下の signed低次モードの比較。ユーザーの採否は別判断。", "",
        "`a=max(1-r²,0)³` は境界で C²、各 width は bbox span の 0.6〜0.8倍。解析ローブは低周波だが mask/taper と canonical gradient の非滑らかさを乗じた後の場が同じ smoothness を持つとは限らない。最終 geometry/Float32 gate は将来の契約。", "",
        "負値が solid、n=+∇phi/|∇phi|。外向き変位 u=a*n に対し δphi≈−a|∇phi|。normalized scalar coefficient が max=1 であっても physical normal displacement の max/RMS は ε とは異なる。以下は active nodes だけにおける解析値の統計・離散内積であり、新しい full-grid Float32 direction を生成/保存しない。", "",
    ])


def active_gradient(state: SDFDesignState, indices: np.ndarray) -> np.ndarray:
    """Read canonical neighbors; create only an active-node gradient vector."""
    components = []
    for axis in range(3):
        left, right = indices.copy(), indices.copy()
        left[:, axis] = np.maximum(indices[:, axis] - 1, 0)
        right[:, axis] = np.minimum(indices[:, axis] + 1, state.shape[axis] - 1)
        denominator = (right[:, axis] - left[:, axis]) * state.spacing_m
        components.append((state.phi[tuple(right.T)].astype(np.float64)
                           - state.phi[tuple(left.T)].astype(np.float64)) / denominator)
    return np.stack(components, axis=1)


def scalar_stats(values: np.ndarray, total_nodes: int) -> dict:
    return {"l2_norm": float(np.linalg.norm(values)), "max_abs": float(np.max(np.abs(values))),
        "rms_active": float(np.sqrt(np.mean(values**2))),
        "rms_full_grid_zero_extension": float(np.sqrt(np.sum(values**2) / total_nodes)),
        "nonzero_active_nodes": int(np.count_nonzero(values))}


def diagnose(state_path: Path, freeze: dict, freeze_sha: str, initial_note_sha: str) -> dict:
    if not state_path.is_file():
        return {"status": "未実施", "reason": "canonical NPZ missing; stop without fabricated correlation", "path": str(state_path)}
    npz_sha = digest_bytes(state_path.read_bytes())
    if npz_sha != CANONICAL_STATE_NPZ_SHA256:
        raise ValueError("canonical NPZ SHA-256 mismatch")
    state = SDFDesignState.load(state_path)
    phi_sha = phi_sha256(state.phi, order="F")
    if phi_sha != CANONICAL_PHI_FORTRAN_F32_SHA256:
        raise ValueError("canonical Float32 Fortran phi SHA-256 mismatch")
    active = state.design_mask & ~state.fixed_solid_mask & ~state.forbidden_mask & ~state.root_mask
    indices = np.argwhere(active)
    xyz = np.asarray(state.origin_m) + indices * state.spacing_m
    low, high = xyz.min(axis=0), xyz.max(axis=0)
    span = high - low
    if np.any(span <= 0):
        raise ValueError("active coordinate bbox is degenerate")
    gradients = active_gradient(state, indices)
    magnitudes = np.linalg.norm(gradients, axis=1)
    radial = np.abs(state.phi[active].astype(np.float64)) / state.narrow_band_width_m
    taper = np.where(radial < 1, 0.5 * (1 + np.cos(np.pi * radial)), 0)
    protected = generate_directions(state)
    references = {name: values[active].astype(np.float64) for name, values in protected.items()}
    total = int(np.prod(state.shape))
    candidates = []
    for preset in PRESETS:
        centers = low + np.asarray(preset["centers_fraction"]) * span
        widths = np.asarray(preset["widths_fraction"]) * span
        a = np.zeros(len(indices), dtype=np.float64)
        for center, coefficient in zip(centers, preset["coefficients"], strict=True):
            radius_squared = np.sum(((xyz - center) / widths)**2, axis=1)
            a += coefficient * np.maximum(1 - radius_squared, 0)**3
        raw = -a * magnitudes * taper
        peak = float(np.max(np.abs(raw)))
        if not np.isfinite(peak) or peak <= 0:
            raise ValueError(f"analytical lobe {preset['id']} has no finite support")
        values = raw / peak
        physical = np.divide(-values, magnitudes, out=np.zeros_like(values), where=magnitudes > 0)
        comparisons = []
        for name, ref in references.items():
            intersection = int(np.count_nonzero((values != 0) & (ref != 0)))
            union = int(np.count_nonzero((values != 0) | (ref != 0)))
            inner = float(np.dot(values, ref))
            comparisons.append({"protected_id": name, "discrete_l2_inner_product": inner,
                "discrete_integral_inner_product_m3": inner * state.spacing_m**3,
                "cosine": inner / float(np.linalg.norm(values) * np.linalg.norm(ref)),
                "support_intersection": intersection, "support_union": union,
                "support_jaccard": intersection / union,
                "candidate_support_in_reference_fraction": intersection / int(np.count_nonzero(values)),
                "reference_support_in_candidate_fraction": intersection / int(np.count_nonzero(ref))})
        candidates.append({"id": preset["id"], "centers_m": centers.tolist(), "widths_m": widths.tolist(),
            "widths_in_grid_spacings": (widths / state.spacing_m).tolist(),
            "analytic_phi_coefficient_stats": scalar_stats(values, total),
            "physical_normal_displacement_per_nominal_epsilon_stats": scalar_stats(physical, total),
            "raw_phi_normalizer": peak, "comparison_to_protected_directions": comparisons,
            "new_direction_generated": False, "new_direction_sha256": None, "float32_audit_executed": False})
    source = "src/cfd_sdf/gradients/directional_fd.py"
    locations = [source_location(source, f"def {name}(") for name in
                 ("direction_sha256", "_active_mask", "interface_taper", "generate_directions", "validate_directions", "validate_direction")]
    locations += [source_location("src/cfd_sdf/fd08_contract.py", "CANONICAL_STATE_NPZ_SHA256 ="),
        source_location("src/cfd_sdf/fd08_contract.py", "CANONICAL_PHI_FORTRAN_F32_SHA256 ="),
        source_location("src/cfd_sdf/fd08_calibration.py", "def audit_float32_centered_pair("),
        source_location("src/cfd_sdf/fd08_calibration.py", "FLOAT32_DIRECTION_RELATIVE_L2_ERROR_LIMIT =")]
    return {"status": "canonical_geometry_diagnostics_completed_unregistered", "evidence_class": EVIDENCE_CLASS,
        "numpy_version": np.__version__, "frozen_definition": freeze, "preset_freeze_sha256": freeze_sha,
        "initial_pre_diagnostic_note_sha256": initial_note_sha,
        "canonical": {"path": str(state_path), "npz_sha256": npz_sha, "phi_float32_fortran_sha256": phi_sha,
            "state_content_sha256": state.state_sha256, "shape": list(state.shape), "total_nodes": total,
            "spacing_m": state.spacing_m, "origin_m": list(state.origin_m), "narrow_band_width_m": state.narrow_band_width_m,
            "active_node_count": len(indices), "active_bbox_min_m": low.tolist(), "active_bbox_max_m": high.tolist(),
            "gradient_magnitude_min": float(magnitudes.min()), "gradient_magnitude_max": float(magnitudes.max()),
            "zero_gradient_active_nodes": int(np.count_nonzero(magnitudes == 0))},
        "protected_direction_regeneration": [{"id": name, "sha256": direction_sha256(protected[name]),
            "dtype": str(protected[name].dtype), "C_contiguous": protected[name].flags.c_contiguous,
            "stats": scalar_stats(references[name], total)} for name in references],
        "protected_source_sha256": digest_bytes((ROOT / source).read_bytes()), "source_locations": locations,
        "candidates_analytical_diagnostics_only": candidates,
        "qualification_flags": {key: False for key in ("shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}}


def round_json(value):
    if isinstance(value, float):
        return float(f"{value:.12g}")
    if isinstance(value, dict):
        return {key: round_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [round_json(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if any((args.output_dir / name).exists() for name in ("direction_design.md", "direction_diagnostics.json")):
        parser.error("output exists: preserve evidence; use a new --output-dir for reproduction")
    freeze = frozen_definition()
    freeze_sha = digest_bytes(json.dumps(freeze, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    note = freeze_text(freeze, freeze_sha)
    note_path = args.output_dir / "direction_design.md"
    note_path.write_text(note)
    print(f"preset definitions frozen BEFORE diagnostic: {freeze_sha}", flush=True)
    result = round_json(diagnose(args.state, freeze, freeze_sha, digest_bytes(note.encode())))
    output = args.output_dir / "direction_diagnostics.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    note_path.write_text(note + report(result, output))
    print(f"diagnostics={result['status']}; no new direction arrays/hash/states; {output}")
    return 0 if result["status"] != "未実施" else 2


def report(result: dict, output: Path) -> str:
    if result["status"] == "未実施":
        return "\ncanonical NPZ が存在しないため相関計算は **未実施**。値を生成せず停止。\n"
    c = result["canonical"]
    lines = ["", "## 実行と入力の確認", "", f"canonical NPZ SHA-256: `{c['npz_sha256']}`。Float32 Fortran raw phi SHA-256: `{c['phi_float32_fortran_sha256']}`。両者は現 HEAD の fd08_contract 定数と照合済み。異なる hash の表記を混同しない。",
        f"shape={c['shape']}、spacing={c['spacing_m']} m、active nodes={c['active_node_count']}、gradient magnitude min/max={c['gradient_magnitude_min']:.9g}/{c['gradient_magnitude_max']:.9g}。",
        "旧 Stage 1 メモの4718 nodeは当時の設計入力の記述であり、本作業では上書きしない。今回のcanonical active maskは107415 node、再生成した保護済みD0/D1/D2の非ゼロsupportは各8339 node。active mask、taper後の非ゼロsupport、特定εのFloat32 signed状態で実際に変わるnode数は異なる集合。4718との同一性を仮定せず、signed stateを作らないため実現changed-node数は未測定。今後の生成契約ではsupportと実現変化集合を区別して固定する必要がある。",
        "", "```sh", "PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python scripts/design_fd08_v2_stage1p5_directions.py",
        "```", "", f"NumPy {result['numpy_version']}。protected direction generator source SHA-256: `{result['protected_source_sha256']}`。",
        f"診断 JSON SHA-256: `{digest_bytes(output.read_bytes())}`。初回計算前の freeze 文書 SHA-256: `{result['initial_pre_diagnostic_note_sha256']}`。定義の hash と初回文書 hash は内容が異なるため別値。",
        "", "既存 D0/D1/D2 は許可された正準 regenerate のみ。各 hash と support/RMS/max は JSON に記録し、新 direction の hash は null。R5 の force/result/analysis/dataset direction raw は読み込んでいない。source bytes と canonical state が同じ条件での再生成であり、R5 raw との照合を行ったという主張ではない。",
        "", "## 固定 preset の診断値", "", "| option | center(s) m | width m | phi max | active RMS | full-grid RMS | support | physical normal max/ε | physical normal RMS(active)/ε |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in result["candidates_analytical_diagnostics_only"]:
        s, p = row["analytic_phi_coefficient_stats"], row["physical_normal_displacement_per_nominal_epsilon_stats"]
        lines.append(f"| {row['id']} | {row['centers_m']} | {row['widths_m']} | {s['max_abs']:.8g} | {s['rms_active']:.8g} | {s['rms_full_grid_zero_extension']:.8g} | {s['nonzero_active_nodes']} | {p['max_abs']:.8g} | {p['rms_active']:.8g} |")
    lines += ["", "上表の physical displacement は `−δphi/|∇phi|` の一次近似であり、surface relocation 測定値ではない。例えば nominal ε を掛ければ同じ単位の予測変位になるが、signed phi を作って確認した値ではない。zero-gradient nodes は raw=0、physical係数=0。L2内積は node の離散内積、volume weighted は h³を掛けた離散体積積分。全格子 RMS は明示的 full-grid 配列を作らずゼロ延長のノルムと総node数から計算。", "", "| option | protected | L2 inner product | cosine | support intersection/union | Jaccard |", "| --- | --- | ---: | ---: | --- | ---: |"]
    for row in result["candidates_analytical_diagnostics_only"]:
        for comparison in row["comparison_to_protected_directions"]:
            lines.append(f"| {row['id']} | {comparison['protected_id']} | {comparison['discrete_l2_inner_product']:.9g} | {comparison['cosine']:.9g} | {comparison['support_intersection']}/{comparison['support_union']} | {comparison['support_jaccard']:.9g} |")
    lines += ["", "この幾何学的 cosine/support は scalar phi の方向類似性であり、force gradient の類似性、solver response magnitude、qualification を表さない。符号反転でも同じ一次空間なので重複判断は abs(cosine) を見る。診断の最大cosineに合わせてpresetを変更・再選択しない。", "", "## 将来承認時だけ実施する artifact / Float32 契約", "",
        "1. direction inventory と generator の数値的 arithmetic、中心/幅、narrow-band taper、gradient stencil、zero-gradient の扱いを事前登録する。既存 D0/D1/D2 と source/array hash は保護し、新ローブを採用するなら別契約にする。",
        "2. 初めて full-grid max=1 direction を作る際は little-endian float32 C順、support 外0、max after cast、finiteを検査。SHA-256 は既存 direction_sha256 と同じ C順 bytes に対して生成する。本作業ではその配列・hashを生成しない。",
        "3. nominal ε ごとに将来 `phi±=float32(phi0±ε*d)` を構成し、両符号の changed-node数/max/active RMS/full-grid RMS、support外byte同一、masks、marginを監査する。float32 roundaway は失敗として残し、力の結果でεを後から変更しない。",
        "4. effective centered direction `(phi+−phi−)/(2ε)` の requested とのcosine・relative L2、現行 limit 0.05を使うか、新contractの採否を事前に決める。実現 normal displacement はscalar SDF増分と別に零面/gradientを用いて測る。",
        "", "実在 source locations（現 HEAD で再検索）:", ""]
    lines += [f"- `{location}`" for location in result["source_locations"]]
    lines += ["", "## 判断と未実施事項", "", "P1 は単一局在ローブの実装量が小さいための条件付き第一候補。P2 は局在位置の別案、P3 は2つのsigned低次モードの別案。相関が高いものでもここで調整しない。どの方向を加えるか/加えないか、#23のcoverage、必要state数・予算・ladder・B-3〜B-7 はユーザー判断。新方向がsmoothだから gが安定・応答が十分大きいとは言えない。", "", "新方向、signed states、R6 criteria/dataset、formal、force応答、Float32 perturbation audit は生成/実行していない。solver/Kaggleを実行せず、R5/Stage1 evidenceとphase_planを変更せず停止。JSONは12有効数字、sort_keys=True、allow_nan=False。hashは同一環境再現用、機種間では参考値。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
