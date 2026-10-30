# #56 GRID-02 結果: `GRID02_RECORDED` — 4 つの flow grid での downforce 応答の slope／curvature と placement-shift 対照

事前登録（`prerun_freeze.json`、source `807157d0`、freeze SHA `67eab367…`、独立レビュー 5 本の指摘を反映済み）どおりに 5 kernel・29 state（f16 8、f48a 4、f48b 3、s24 7、s32 7）を各 1 回実行し、analyzer（freeze に SHA を固定）を `--check` で integrity 確認の後に 1 回だけ `--write` した（`grid02_analysis.json`）。5 kernel とも `COMPLETE`・`DONE`・`ERROR.txt` なし、全 summary が host 再計算（grid ごとの換算）と相対 1e-9 で一致、flow_16 / flow_48 の parent pair は byte 同一、shifted 親が native 親と異なる（shift は有効）、integrity pass。出力は `kernel_output/`。
**一つの parent・一つの方向・[80,120] tU/L の単一窓の記述**で、格子収束・GCI・真の grid・物理的な downforce／drag・勾配・optimizer・OPT-01 の再開や規則変更のいずれでもない。shift 対照は部分的（z 未移動）。分解能の床 3e-5 N は flow_24 の名目値で、他 grid では未測定。全 qualification flag false、`shape_update_allowed=false`、δ 未設定。

## 結果（dL = b s + a s²、s は mm、正方向 4 点の最小二乗、N 単位）
| セル | b (N/mm) | a (N/mm²) | 最大残差 | 参考: 中心差分 slope | parent downforce / drag (N) |
| --- | ---: | ---: | ---: | ---: | --- |
| 16 native | +4.12e-4 | +5.3e-5（凸） | 9e-6 | +4.67e-4 | 0.2549 / 0.2235 |
| 24 native | +9.4e-5 | −2.24e-4 | 4e-6 | +9.8e-5 | 0.3319 / 0.3237 |
| 24 shifted | +3.16e-4 | −2.26e-4 | 5e-6 | +3.32e-4 | 0.3374 / 0.3236 |
| 32 native | +4.90e-4 | −9.0e-5 | 1.1e-5 | +4.72e-4 | 0.3618 / 0.3500 |
| 32 shifted | +9.27e-4 | −1.1e-5 | 6e-6 | +9.48e-4 | 0.3269 / 0.3731 |
| 48 native | +4.92e-4 | −2.3e-5 | 3.7e-5 | +6.45e-4 | 0.3644 / 0.3595 |

dL(1.25 mm): flow_16 +5.97e-4、flow_24 −2.33e-4、flow_32 +4.68e-4、flow_48 +5.96e-4 N（drag は 16: +1.2e-4、24: −4.6e-4、32: −1.2e-4、48: −1.46e-3 N）。flow_24 を shift すると全 step で downforce が正（+7.8e-5〜+1.1e-4 N）になる。flow_48 の dL は 0.3125/0.625/0.9375/1.25 mm で +1.79e-4/+3.06e-4/+4.04e-4/+5.96e-4 N（単調だが増分は等間隔でなく、最大残差 3.7e-5 N は床 3e-5 N を超える）。
placement effect（shifted − native の parent）: flow_24 は downforce +5.5e-3 N（+1.7%）、drag −2.1e-4 N、b は +2.2e-4 N/mm。flow_32 は downforce **−3.46e-2 N（−9.6%）**、drag +2.35e-2 N（+6.7%）、b は +4.4e-4 N/mm。

## 事前登録の分類
- **Alignment 対照: `GRID02_ALIGNMENT_PARTIAL_OR_MIXED`**（G = b_32n − b_24n = 3.96e-4 N/mm、m24 = +0.56、m32 = −1.11、shift 後の gap 比 1.54）。shift で flow_24 の slope は flow_32（native）へ gap の 56% 動き、flow_32 の slope は逆に gap の 1.1 倍増えた。
- **Fine grid: `FINE_CONTINUES_TO_FLOW32`**（r = 1.007）、`STABLE_32_TO_48` = true（b_48n = 4.92e-4 vs b_32n = 4.90e-4）。ただし中心差分の slope で置き換えると b_48n = 6.45e-4 となり STABLE は false になる（alignment と fine の class は不変）。
- 登録した decision map では PARTIAL_OR_MIXED の分岐が適用される: **別の placement phase（x/y の別位相、z は車高許容を登録して）の研究を、規則改定の前に行う**。
- OPT-01 の both-grid 規則の記述的評価（この結果だけでは採用しない）: (24n, 32n) は通る step なし、(24s, 32s) は 0.9375 と 1.25 mm が通る、(32n, 48n) は 4 step すべてが通る。
- ヒンドキャスト（0.38–0.40 N）に対し flow_48 の parent downforce は 0.3644 N で範囲外（記述的）。

## 記述的な観察（解釈の上限つき）
- native の slope は n = 16、24、32、48 で +4.1e-4、+0.94e-4、+4.9e-4、+4.9e-4 N/mm と**単調ではない**。flow_24 だけが小さく、flow_32 と flow_48 は一致し、flow_16 も近い。flow_16 は flow_24 と同じ整列クラスなので、flow_24 の低い slope は「粗い grid の解像度効果」でも単純な「整列の効果」でもない（flow_24 固有の位相／離散化の効果を排除できない）。
- placement（解析格子と設計格子の相対位相）の効果は、slope で grid 間の差と同程度以上、flow_32 の parent downforce で −9.6% と大きい。sub-cell スケールの step（0.3〜1.25 mm）の accept／reject は、現状の離散モデルでは placement に対して頑健でない可能性が高い。flow_24 の応答の符号も shift で反転した。
- flow_48 は curvature がほぼ小さく（a = −2.3e-5）、slope は flow_32 と一致するが、残差が床を超えるので 4 点の 2 次近似の精度は他のセルより低い。到達可能な gain の外挿値（zero crossing 21 mm、peak 10.5 mm）は試験範囲（1.25 mm）の外で、解釈に使わない。
- 解釈の限界: shift 対照は z を動かしておらず（flow_24 shifted の位相は x, y で {1/2, 5/6, 1/6}、flow_32 shifted は x, y で node 整列）、「整列」だけの対照ではない。1 つの parent・1 つの方向。flow_32 shifted の 86 mm という zero crossing や 0.02 N の peak は外挿で意味を持たない。

## 次（ユーザー判断ではなく登録済み decision map に従う。ただしこの登録では実行しない）
PARTIAL_OR_MIXED: 別 placement phase の研究。具体案（次の登録で決める）: flow_32 と flow_24（と flow_48）に対し、x/y の複数の位相（例: 0, h/4, h/2, 3h/4）で parent と +1.25 mm と −1.25 mm の 3 state を測り、slope と parent force の placement 分散を、grid 間の差と同じ尺度で定量する。これは placement-robust な評価（位相平均）の設計の前提でもある。

## 再現
`PYTHONPATH=src:scripts .venv/bin/python scripts/analyze_grid02.py --kernel-root kernel_output --freeze prerun_freeze.json --check`（`--write` は 1 回のみ、既存なら拒否）。テストは `tests/test_grid02_evidence.py`。
