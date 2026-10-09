# #49 LOWDIM-02A 結果: `STAGE_A_CONSTRAINT_FAIL`（downforce の符号は flow_32 で保たれたが、事前登録した drag の条件を満たさなかった）

事前登録（`prerun_freeze.json`、独立レビュー 2 本の指摘を反映済み）どおりに T4 の 1 kernel（flow_32、baseline + baseline repeat + 受理 step +1.25 mm + reverse control −1.25 mm + 記述的 +2.5 mm = 5 state）を 1 回実行し、解析器（freeze に SHA を固定）を 1 回だけ実行した（`lowdim02a_analysis.json`）。
source `972fcce9`、freeze `a3010966…`。baseline の flow_32 力 CSV は W4 v17 round-2 の flow_32 と byte 同一（SHA `032ef1cf…`）、baseline repeat も byte 同一、全 state 完了、host（flow_32 の換算 6.25e-4）再計算と Julia の summary が相対 1e-9 で一致、integrity pass。出力は `kernel_output/`。
**1 方向・1 step・1 窓の cross-grid 符号確認であり、#26 GRID-01 の完了でも、格子収束でも、grid-independent / 物理的な downforce でも、gradient の適格性でも OPT-01（#30）でもない**。δ 未決、GRAD-03 verdict なし、6 flag・FD-08 verdict は不変、reinitialization なし、AD なし。

## 結果（flow_32 baseline: downforce 0.361278 N、drag 0.350027 N。flow_24 baseline は 0.331634 N で +8.9%）
| state（max\|Δφ\|） | Δdownforce（N） | Δdrag（N） | flow_24（LOWDIM-01）の Δdownforce |
| --- | ---: | ---: | ---: |
| +1.25 mm（受理 step） | **+7.31e-4**（+0.20%） | **+5.40e-5** | +4.05e-4（+0.12%）、Δdrag −1.68e-4 |
| −1.25 mm（reverse control） | −1.09e-3 | −3.17e-4 | −1.21e-3 |
| +2.5 mm（記述的のみ） | +1.20e-3 | −8.32e-5 | −5.0e-5（分解能すれすれ） |

## 事前登録の判定
分解能は baseline repeat が byte 同一だったため名目 floor の 3e-5 N（flow_32 の noise の証拠ではない。flow_32 の半窓ドリフトは約 1e-5 N）。
- downforce gain +7.31e-4 N > 3e-5 N（分解された正の符号、`marginal` ではない）。
- reverse control −1.09e-3 N < −3e-5 N（分解された損失。純偶関数応答ではない）。
- geometry gate（LOWDIM-01 で評価済みの +1.25 mm）: 全通過。
- **drag(+1.25) − drag(baseline) = +5.40e-5 N > 許容 3e-5 N**（相対で +0.015%）→ 条件を満たさず `STAGE_A_CONSTRAINT_FAIL`。
登録した規則に従った判定であり、結果を見た後に drag の閾値を緩めて PASS に読み替えることはしない（その閾値は flow_24 の名目 floor で、flow_32 の drag の noise は repeat が byte 同一のため測れていない）。Stage B は登録していない。

## 記述的な観察（判定には使わない）
- flow_32 の奇関数部は +9.12e-4 N（flow_24 の 1.13 倍）、偶関数部（曲率）は −1.81e-4 N（flow_24 の 0.45 倍）。FD 提案の符号と大きさは flow_24 と flow_32 でほぼ同じで、曲率が約半分になっている。gain の拡大（1.8 倍）は主に曲率の減少による。
- 曲率が小さいので、flow_32 では +2.5 mm も gain（+1.20e-3 N）を持つ。flow_24 では +1.25 mm 付近が最大で 2.5 mm はゼロ交差だったので、step 幅の最適値が grid 依存である（flow_32 の方が大きい step が許される）。この step 幅は +2.5 mm の 1 点だけから読めるもので、最適値の推定ではない。
- drag は +1.25 mm で増え（+5.4e-5）、+2.5 mm と control では減る（−8.3e-5、−3.2e-4）。flow_24 は +1.25 mm でも減った（−1.7e-4）。drag の変化は小さく単調でない。

## 解釈と注意
- 実際の downforce の符号・奇関数部は flow_24 から flow_32 に保たれた。受理 step が flow_24 だけの過適合ではないことを支持する。ただし 1 方向・1 step で、drag 制約は flow_32 では（名目 floor の厳密な規則の下で）満たされていない。
- LOWDIM-01 の drag の許容 3e-5 N は FD-08 の名目 σ0 の 10 倍で、実測の noise ではない。5.4e-5 N がこの floor を超えることが物理的な drag 増加なのか floor の取り方なのかは、この結果からは決められない（baseline repeat が byte 同一で noise を測れていない）。
- 次は**ユーザー判断**: (a) CONSTRAINT_FAIL のまま Stage B を登録しない、(b) drag 条件を事前に明示し直した上で（これは結果を見た後の変更なので post hoc と記録する）Stage B を別登録する、(c) 先に flow_32 の drag の分解能を測る（例えば微小摂動で floor を実測）、(d) 別の方向（basis 拡張・曲率モデル・GEOM-01）を先にする。

## 再現
`PYTHONPATH=src:scripts .venv/bin/python scripts/analyze_lowdim02a.py --kernel-dir kernel_output/lowdim02a_a --freeze prerun_freeze.json --check`（書き込みは 1 回のみ）。テストは `tests/test_lowdim02a_evidence.py`。
