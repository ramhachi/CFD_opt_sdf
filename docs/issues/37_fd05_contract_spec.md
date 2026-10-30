# FD-05 (#37) 契約の設計判断 (2026-09-30、実行前に固定)

実装者 (Codex / Luna など) はこの仕様に従う。ここに書いていない判断が必要になったら、実装を止めてユーザーに確認する。
土台にするのは、FD-02 round 5 の criteria (`docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round5.json`、以下 R5)。

## 1. 位置づけ

- R5 の続き (round 6) としては扱わない。**v17 の状態に対する新しい FD の契約の round 1** として登録する。
  - `criteria_id` は `sdf_directional_fd_v17_flow24_2026_09`。
  - 理由: canonical state、flow 解像度、摂動の 3 つがすべて変わるため。
- 過去の R1〜R5 の criteria と証跡は変更しない。新しい criteria では、R5 を「先行する fail-closed の診断」として path と SHA で参照する。

## 2. 変える項目

| 項目 | 値 | 根拠 |
|---|---|---|
| canonical state | genesis v17 (state SHA `02f48f64…5dcb`、h = 0.025、121×65×49) | #43、`evidence/sdf_native_genesis_v17_2026_09.json` |
| flow case | `flow_24` (W4 v17 の登録済み case を再利用) | ユーザー決定 (#37 のコメント) |
| 前提条件 (prerequisites) | W3 v17 PASS (`kaggle_w3_v17_primal_result_2026_09.json`) と W4 v17 PASS (`kaggle_w4_v17_sensitivity_result_2026_09.json`) の path と SHA | v16 の W3 / W4 から差し替える |
| W4 との照合 (`w4_cross_check`) | W4 v17 の flow_24 の値 (drag 0.326317 N、downforce 0.331029 N)。参考値のみで gate にしない | R5 と同じ扱い |
| 方向 | 既存の生成器 (`generate_directions`) を v17 にそのまま適用する (D0、seed 11、seed 2026)。方向の hash と在庫は新しく登録する | narrow band = h = 0.025 なので、方向の台が R5 と異なる |
| 摂動 | 既存の `perturbed_state` で 30 本を作り直し、hash を登録する | |

## 3. 変えない項目 (R5 と機械的に同一であること)

- **ε ラダーの絶対値**: 0.5 / 1 / 2.5 / 5 / 10 mm。符号は ±、本数は 30、clipping・平滑化・再初期化はなし。
  - `epsilon_relative_to_design_spacing` は **0.02 / 0.04 / 0.1 / 0.2 / 0.4** に更新し、criteria に理由を明記する。
  - 理由: v17 のローカル CPU 診断 (`evidence/sdf_native_fd04_v17_*`) で、この絶対値の範囲が今の bridge で ε に比例していた。同じ物理的な変位幅で、v16 の診断とも比べられる。
- **run の構成**: baseline は A / B / C の 3 本で、R5 と同じ順序で差し込む。合計 33 本。
- **測定**: 窓は t = 80〜120、半窓は [80,100] と [100,120]、サンプリング間隔は 8 step、端点は線形補間、力の閉合と許容差、host 再計算の許容差 1e-9。
- **noise と plateau**: noise_floor、分解できたと見なす条件 (resolution_factor 20)、分解できた ε の最小本数 3、plateau の相対許容差 0.05、符号一致、「3 本の応答と方向の組がすべて pass」の条件。
- **定常性**: 半窓ドリフト ≤ 0.02。
- **gate**: T0〜T12 の構成。名前の中の v16 を v17 に変えるのは可。T0 は、v17 の W3 / W4 の前提を束縛するものに差し替える。
- **VRAM 上限**: 4 GiB。

## 4. 時間の上限 (事前に確認済み)

- flow_24 では 1 run あたり約 102 s (W4 v17)。33 本で約 1 時間なので、R5 の上限 (run ごと 1800 s、solver 合計 7200 s、kernel 14400 s) に収まる。**上限は変えない**。

## 5. 主張の範囲

- PASS した場合: 「v17・flow_24・この 3 方向について、中心差分 FD の oracle が qualified」。これだけ。
- 主張しないもの: 勾配の backend、格子収束、他の flow 解像度、物理的な妥当性、形状の更新。
- FAIL した場合: fail-closed の診断としてそのまま記録する。閾値を変えての再試行はしない。
