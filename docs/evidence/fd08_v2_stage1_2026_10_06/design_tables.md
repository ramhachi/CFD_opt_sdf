# FD-08 v2 Stage 1 設計表（未登録）

証拠区分: `solver_free_design_and_simulation_unregistered`。全 qualification flag は false。B-3〜B-7、ladder、baseline 数、予算は未決。R5 FAIL は固定。

計算式: `2×方向数×ε点数 + baseline数 + 2×方向数`。jitter は 1 つのずらした ε における ±sign pair（2 state/方向）の費用。

solver は 108.7 s/state、overhead は約 74 s/state。上限は solver 5,400 s、kernel 10,800 s。R5 手書き実測 5,109.38 s / 47 = 108.710212766 s/state、経過 8,596.5 s / 47、差は 74.1940425532 s/state。表は指示の丸めた定数を使う予算目安であり、新方向や上端拡張に対する runtime 保証ではない。

出典: `docs/issues/46_fd08_v2_stage1_instruction_2026_10_06.md §4`、`docs/phase_plan.md:6257-6258`、solver 上限 `docs/evidence/xfid_candidate_c_2026_10_04/xfidc_criteria.json:100`、kernel 上限 `docs/phase_plan.md:6053-6054`。スクリプトは R5 artifact を読まず、数値は手書き定数。

| 方向 | ε点 | baseline | jitter | 合計state | solver s | 経過目安 s | solver超過 | kernel超過 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| 3 | 6 | 1 | 6 | 43 | 4674.1 | 7856.1 | NO | NO |
| 3 | 6 | 5 | 6 | 47 | 5108.9 | 8586.9 | NO | NO |
| 3 | 7 | 1 | 6 | 49 | 5326.3 | 8952.3 | NO | NO |
| 3 | 7 | 5 | 6 | 53 | 5761.1 | 9683.1 | YES | NO |
| 3 | 8 | 1 | 6 | 55 | 5978.5 | 10048.5 | YES | NO |
| 3 | 8 | 5 | 6 | 59 | 6413.3 | 10779.3 | YES | NO |
| 4 | 6 | 1 | 8 | 57 | 6195.9 | 10413.9 | YES | NO |
| 4 | 6 | 5 | 8 | 61 | 6630.7 | 11144.7 | YES | YES |
| 4 | 7 | 1 | 8 | 65 | 7065.5 | 11875.5 | YES | YES |
| 4 | 7 | 5 | 8 | 69 | 7500.3 | 12606.3 | YES | YES |
| 4 | 8 | 1 | 8 | 73 | 7935.1 | 13337.1 | YES | YES |
| 4 | 8 | 5 | 8 | 77 | 8369.9 | 14067.9 | YES | YES |
| 5 | 6 | 1 | 10 | 71 | 7717.7 | 12971.7 | YES | YES |
| 5 | 6 | 5 | 10 | 75 | 8152.5 | 13702.5 | YES | YES |
| 5 | 7 | 1 | 10 | 81 | 8804.7 | 14798.7 | YES | YES |
| 5 | 7 | 5 | 10 | 85 | 9239.5 | 15529.5 | YES | YES |
| 5 | 8 | 1 | 10 | 91 | 9891.7 | 16625.7 | YES | YES |
| 5 | 8 | 5 | 10 | 95 | 10326.5 | 17356.5 | YES | YES |

4 方向以上は jitter を含めると全案が solver 上限を超える。baseline 1 と 5 の選択、budget 増額・kernel 分割は承認事項。baseline 反復で jitter variance を代用する選択はしない。

## 登録済みコードの変更候補（編集していない）

全 location はスクリプト実行で当該 source anchor を確認した。新契約で必要なら別の v2 実装に分離し、保護済み source binding を維持する。

| file:line | 承認後に必要となる変更 |
| --- | --- |
| `src/cfd_sdf/fd08_calibration.py:24` | formal の 5 点固定と calibration 部分集合条件 |
| `src/cfd_sdf/fd08_calibration.py:25` | D0/D1/D2 の固定 inventory。B-4/B-6 は未決 |
| `src/cfd_sdf/fd08_calibration.py:28` | 7 点以上と 6 点案の衝突 |
| `src/cfd_sdf/fd08_calibration.py:29` | 100 倍以上と 10/16.7 倍案の衝突 |
| `src/cfd_sdf/fd08_calibration.py:225` | 点数・span 制約と新 ladder の別契約 |
| `src/cfd_sdf/fd08_calibration.py:236` | 5 点固定・calibration 部分集合から内部新点へ |
| `src/cfd_sdf/fd08_calibration.py:530` | median-slope 5% から WLS と 6 項目への別契約 |
| `src/cfd_sdf/fd08_calibration.py:550` | 3 方向共通の連続 5 点窓、全 6 系列の gate |
| `src/cfd_sdf/fd08_calibration.py:608` | 5 点窓を列挙する旧 gate の停止規則 |
| `src/cfd_sdf/fd08_calibration.py:657` | 5 観測・floor・plateau 固定 |
| `src/cfd_sdf/fd08_calibration.py:699` | 全 6 系列固定。B-4 の被覆規則は未決 |
| `src/cfd_sdf/fd08_calibration.py:205` | baseline span の床と jitter に基づく σ 推定は異なる |
| `src/cfd_sdf/fd08_contract.py:17` | 33 state 固定と predict-then-run 24 state |
| `src/cfd_sdf/fd08_contract.py:18` | 5% 固定。新 tolerance は暫定案・未承認 |
| `src/cfd_sdf/fd08_contract.py:19` | 3 plateau 点と v2 gate の点数要件 |
| `src/cfd_sdf/fd08_contract.py:48` | 3 baseline + 3×5×2 の固定矩形 |
| `src/cfd_sdf/fd08_contract.py:27` | fresh33 固定。disjoint inventory は維持 |
| `scripts/register_fd08_formal.py:111` | calibration の連続 5 点部分集合・旧 sources と gate の hash 結合 |
| `scripts/verify_fd08_formal.py:87` | fresh33・3 方向・calibration の 5 baseline・全旧 gate の再計算 |
| `scripts/register_fd08_calibration.py:367` | 旧 ladder 検証、D0/D1/D2、baseline 5、signed inventory、criteria 結合 |
| `scripts/analyze_fd08_calibration.py:95` | 旧 pair 分母・baseline floor・共通 plateau selector・新 jitter roles |

## epsilon_m の意味が影響する関数（変更していない）

Current epsilon_m is the nominal scalar coefficient of max=1 phi direction; realized float32 direction/physical normal displacement are audited separately. No effective-epsilon redefinition is made.

`phi± = float32(phi0 ± epsilon_nominal_m*d)` の ε は SDF値の最大変位を指定する係数。実現 normal displacement は局所 `|∇phi|`、法線、float32 rounding に依存し、名目 ε と同一とみなさない。有効 ε を分母に入れると oracle と hash/ID の契約が変わるため、方向そのものの実現誤差と別に事前決定が要る。

- `src/cfd_sdf/gradients/directional_fd.py:160` (`perturbation_case_id`)
- `src/cfd_sdf/gradients/directional_fd.py:177` (`perturbed_state`)
- `src/cfd_sdf/gradients/directional_fd.py:297` (`classify_direction`)
- `src/cfd_sdf/fd08_calibration.py:225` (`validate_calibration_ladder`)
- `src/cfd_sdf/fd08_calibration.py:236` (`validate_formal_epsilon_ladder`)
- `src/cfd_sdf/fd08_calibration.py:461` (`audit_float32_centered_pair`)
- `src/cfd_sdf/fd08_calibration.py:516` (`centered_pair`)
- `src/cfd_sdf/fd08_calibration.py:530` (`_plateau_metrics`)
- `src/cfd_sdf/fd08_calibration.py:550` (`select_formal_epsilon_ladder`)
- `src/cfd_sdf/fd08_calibration.py:608` (`classify_calibration_screen`)
- `src/cfd_sdf/fd08_calibration.py:657` (`evaluate_formal_direction_response`)
- `src/cfd_sdf/fd08_contract.py:48` (`validate_fd08_design`)
- `src/cfd_sdf/fd08_contract.py:151` (`audit_float32_perturbation`)
- `src/cfd_sdf/fd08_contract.py:185` (`evaluate_fd08_response`)
- `scripts/register_fd08_calibration.py:89` (`epsilon_tag`)
- `scripts/register_fd08_calibration.py:367` (`build`)
- `scripts/register_fd08_calibration.py:140` (`bind_cpu_rehearsal`)
- `scripts/register_fd08_formal.py:97` (`epsilon_tag`)
- `scripts/register_fd08_formal.py:111` (`build`)
- `scripts/analyze_fd08_calibration.py:95` (`analyze`)
- `scripts/verify_fd08_formal.py:87` (`verify`)

JSON float は有効数字 12 桁、sort_keys=True、allow_nan=False。hash は同一環境内の再現確認用、機種間では参考値。
