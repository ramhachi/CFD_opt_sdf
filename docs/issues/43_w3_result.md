# Issue #43: W3 v17 primal 結果 (2026-09-30)

エビデンス種別: capability / numerical。登録した有限ボックス primal 契約 (W3 v16 round 4 と同じ測定契約) を v17 で満たしたことだけを示す。
物理 profile の等価性、格子・領域収束、絶対値の downforce、勾配、最適化の claim はしない。

- criteria: `docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json` (SHA `00af9ed9…e608`、source `39a8360`、登録は実行前)。
  ラベルの訂正: `…_semantic_clarification.json` (測定、gate、閾値の変更はなし)。
- 実行: Kaggle private kernel `ramhachi888/cfd-opt-sdf-w3-v17-primal/1`。dataset は `ramhachi888/cfd-opt-sdf-v17-genesis-state` (remote の hash 照合済み)。
- host 検証: 登録した source commit `39a8360` を取り出した worktree で、`scripts/verify_kaggle_w3_v16_host_compat.py` を使って実行した。
  これは verifier の `HOST_VERIFIER` 未定義という既存の不具合を回避する、v16 round 4 と同じ手順である。
  判定は **PASS** で、T0〜T10 がすべて true。
- 結果: `docs/evidence/kaggle_w3_v17_primal_result_2026_09.json` (+ sidecar)。

| 指標 (窓 t = 80〜120 の時間平均、solver 単位) | v16 round 4 | v17 | 差 |
|---|---|---|---|
| drag | 134.41 | 89.27 | -33.6% |
| downforce | 141.35 | 101.39 | -28.3% |
| drag の半窓ドリフト | 8.2e-6 | 2.6e-6 | |
| downforce の半窓ドリフト | 4.2e-6 | 6.3e-6 | |

N 換算では、drag 0.2232 N / downforce 0.2535 N (v16 は 0.3360 / 0.3534)。解析時間 35 s、4816 step、margin 0.35 m。

v16 との差は参考値で、gate ではない。短時間のローカル計算で見えた約 3 割の低下が、登録窓 (t = 80〜120) でも再現した。
どちらが body-fitted の参照解に近いかは、この結果からは判断できない。
次の候補は W4 (v17 の sensitivity) と、FD-05 (#37: v17 を使った新しい摂動契約での FD)。

## 追記: 圧力と粘性の内訳、および drag に関する仮説 (未検証)

登録窓 t = 80〜120 の平均、単位 N。力の CSV から計算した (v16 は kernel `w3-v16-primal/5`、v17 は `w3-v17-primal/1`)。

| | 圧力 drag | 粘性 drag | 合計 drag | 圧力 downforce | 合計 downforce |
|---|---|---|---|---|---|
| v16 | 0.228 | 0.108 | 0.336 | 0.362 | 0.353 |
| v17 | 0.139 | 0.084 | 0.223 | 0.263 | 0.253 |
| Stage V (OpenFOAM、境界条件は非等価) | — | — | 0.374 | — | 0.242 |

仮説 (未検証): v16 の薄板は内部が phi = 0 の層なので、BDIM の平滑化によって実際より太く見え、圧力による力が水増しされる。
一方で、正しい形状 (v17) でも、flow 格子が 0.05 m で板の厚さが 1 セルしかないため、次の二つで drag が不足する。

- 平滑化の幅より薄い物体を BDIM が完全には止められない (透過)。
- 境界層 (約 2 セル) の解像度が足りない。

v16 の drag が Stage V に近いのは、この水増しと不足が偶然打ち消し合った結果と考える。
v16 から v17 への減少が圧力成分に集中している (drag −39%、downforce −27%、粘性 drag は −22%) ことは、この仮説と整合する。

方針: v17 を採用する。drag の絶対値は主張の範囲外のままとし、drag を拘束条件に使う前に、flow 解像度 24 / 32 で drag の不足を測る (W4 の v17 版で確認する)。
