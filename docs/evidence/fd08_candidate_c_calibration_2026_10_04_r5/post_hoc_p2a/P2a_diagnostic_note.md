# FD-08 R5 P2a 事後記述診断

証拠区分: `solver_free_post_hoc_calibration_diagnostic_unregistered`

## 範囲と状態

この成果物は、登録済み R5 calibration の保存データに対するソルバー不要の記述診断です。R5 の既存 verdict は **FAIL** のままです。FD-08 / gradient / reverse / optimizer の qualification flags はすべて `false` のままです。gate、criteria、direction、epsilon ladder は変更しておらず、R6 / fresh33 の登録・実行はしていません。原因、達成可能性、gate の適否について結論しません。

A3 の LOO 指示は、数値誤差を出す一方で pass/fail の誤差境界を定めていません。このため、計算可能なケースも数値を併記したうえで3値 status は `undeterminable` としました。これは精度の判定ではなく、分類規則が未定義であることの記録です。

## 入力の固定と照合

- integration source: `8e736c1f01a617fe5a29eb7945ea1f1042bf45d1`; R5 source commit: `95bd9cbf8e67f0c718e346f7edca3f343ed1091f`
- criteria SHA-256: `928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c`
- 既存 analysis SHA-256: `dc769d6f2b5a2d6dfa45c6a5aeddfde726dd75f6e44ac564b128effecce3fb8b`
- runner manifest SHA-256: `1b04c3c2243459d2889dc16aa0f3c02c2ff6a5555a64406bb8177b9ee0b8600e`; runner inventory SHA-256: `6225f8f94f68ae1ba9c91fadc9f062e346416b1c7c4703c7f8eb3c6993b102d6`
- dataset: 89/89 files verified; inventory SHA-256 `593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954`
- force outputs: 47/47 histories verified against the registered manifest, existing analysis and state records
- runner directory inventory complete: `False`; missing non-input manifest files: `['instantiate.log']`
- signed Float32 phi: 42/42 saved raw and NPZ arrays exactly match deterministic `float32(base.astype(float64) ± epsilon_m * direction)` realization
- diagnostic script SHA-256: `a36be71bea2b4ef9f62938f88a885d7ae693e92eae0c1ec9f9b58a7b378d3ac2`

Inputs are read-only. `phi` is interpreted as metres with `phi < 0` denoting solid; baseline raw phi uses Fortran order, direction arrays use C order, and saved signed raw phi uses Fortran order. The three force responses use the existing host recomputation helper, exact clipped `[80,120] tU/L` endpoints and `1/900 N` per solver force unit.

## 固定した記述定義

- `R0`: 5 baseline repeat force means combined with `math.fsum / 5`; used only for `E`.
- `S=(R(+ε)-R(-ε))/2`, `q=S/ε` with ε converted from mm to m for `q [N/m]`; `E=(R(+ε)+R(-ε))/2-R0`.
- `q=g+c ε²`: unweighted least squares on the three fixed inclusive intervals `[0.5,5]`, `[0.5,15]`, `[1.5,15] mm`; full points and signal-selected columns are both recorded. Signal selections use 10/30/50 µN; 50 µN is the primary descriptive cut. These were chosen after P1 and the plan tables had exposed S and q, and are not described as preregistered thresholds.
- Plateau windows are the three consecutive five-point windows starting at 0.05, 0.15 and 0.5 mm. Maximum deviation uses the registered normalizer `max(|median(q)|, response_floor / epsilon_min)`; no pass/fail line is added.
- LOO includes points where `|S| >= X µN`; relative error is undefined when `|q_obs| < 1e-9 N/m`. Sigma scenarios `{2,3,4} µN` are assumptions, not measured noise.
- SDF proxies are `Σ clip(0.5 - phi/h,0,1) h³` for `h=25 mm` and `h=33.33 mm`. Seven R5 epsilon values are combined with 40 logarithmically spaced values from 0.05 to 50 mm; overlapping values `[0.05, 0.5, 5.0, 50.0]` are deduplicated with exact R5 values retained, giving 43 unique epsilon values. Trilinear zero-isosurface volume was omitted because a robust closed-mesh implementation is outside this bounded diagnostic; both specified soft-volume proxies are included.

The soft-volume functionals are SDF grid proxies. They are not the WaterLily fluid-cell cut/mask or its `normal_floor`; smoothness in these proxy curves does not establish absence of cut/mask changes. Functional units are shown in separate plot panels from force `q`.

## 数値要約（A5）

### 3窓のうち最大偏差が最小の窓

| 系列 | 窓 ε [mm] | 最大偏差 [%] |
|---|---:|---:|
| D0_interface_offset/drag | 0.05–5 | 23.73476 |
| D0_interface_offset/downforce | 0.05–5 | 5.0905306 |
| D1_filtered_seed11/drag | 0.05–5 | 8.1933588 |
| D1_filtered_seed11/downforce | 0.05–5 | 23.752657 |
| D2_filtered_seed2026/drag | 0.05–5 | 3.3182559 |
| D2_filtered_seed2026/downforce | 0.15–15 | 7.506237 |

### 3区間 g ずれ（大きい順）

| 順位 | 系列 | (max g − min g)/|median g| |
|---:|---|---:|
| 1 | D1_filtered_seed11/drag | 0.07762909 |
| 2 | D0_interface_offset/drag | 0.070718769 |
| 3 | D1_filtered_seed11/downforce | 0.039382484 |
| 4 | D2_filtered_seed2026/downforce | 0.014788234 |
| 5 | D0_interface_offset/downforce | 0.0086737699 |
| 6 | D2_filtered_seed2026/drag | 0.0012330867 |

LOO の数値・各閾値・各系列・各区間と `status` は JSON の `loo` に全件記録しました。`calculation_status=calculable` は数値を算出できたことだけを表し、3値 `status` は誤差境界がないため `undeterminable` です。

### D1 / D0 の SDF 奇数部微分中央値比

| 汎関数 | ε点数 | median(|D1|/|D0|) | D1が小さい桁数 = −log10(比) |
|---|---:|---:|---:|
| sdf_25_mm | 43 | 8.7794083e-11 | 10.056535 |
| flow_33_33_mm | 43 | 6.6660037e-11 | 10.176134 |

## 図と完全データ

- `plateau_windows.png`: 6系列・3窓の最大偏差。
- `sdf_functionals_D0.png` / `D1` / `D2`: 力 `q(ε)` と、各 h の奇数部・偶数部を別パネルで表示。日本語タイトル・軸ラベルを使用。
- `diagnostic_result.json`: A1–A5 の数値、force/dataset/source hashes、各入力との対応を含む完全な機械可読結果。PNG の SHA-256 は参照値として記録し、`SHA256SUMS` は JSON とこの note のみを固定。

## 変更・停止記録

作業ブランチは `codex/kaggle-batch-migration` から作成し、integration は `--no-ff` merge しました。これはユーザー指示による運用で、`docs/git_branching_strategy.md` の trunk 運用とは異なる点を明記します。ここで Step A を終え、結果を #46 に報告して停止します。B の gate / FD-08 定義の判断はユーザーに残します。
