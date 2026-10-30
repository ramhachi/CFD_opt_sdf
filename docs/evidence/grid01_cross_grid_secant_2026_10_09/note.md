# #26 GRID-01 結果: `FEASIBLE_CONE_FOUND`（固定4方向の一次モデルで、両 flow grid の制約を満たす提案を記録）

flow_32 の新規9 state（baseline 1 + 4方向 × ±2.5 mm）を、freeze に固定した flow_24 の STEP-01 secant と比較した。Kaggle kernel `ramhachi888/cfd-opt-sdf-grid01-a/2` は `COMPLETE`、runner の `DONE` があり `ERROR.txt` はない。全9 state が完了し、output manifest の43ファイルの path 集合と SHA-256 が一致した。host で再計算した力と Julia summary は登録した相対 1e-9 の条件で一致し、baseline force CSV は W4 v17 round-2 flow_32 と byte 同一だった。

`--check` が `integrity.pass=true` を返した後、`--write` を1回だけ実行し、`grid01_analysis.json` を保存した。解析の integrity verdict は `GRID01_SECANT_RECORDED`、solver-free proposal の事前登録判定は **`FEASIBLE_CONE_FOUND`**。実験の基準・state・閾値・解析コードは変更していない。

これは固定4方向・±2.5 mm・Re=80・時間窓 tU/L=[80,120] の数値観察と、1.25 mm での一次予測である。新しい proposal の実 CFD、geometry gate の評価、受理 step は実行していない。格子収束、物理的な downforce、full-field gradient、OPT-01 (#30) の資格化には使わない。#26 は open のまま、最初の最適化 step に使う grid は未決。δ、GRAD-03 verdict、FD-08 verdict、6 qualification flag、`shape_update_allowed=false` は不変。

## 9 state の結果（flow_32、N）

力は host の時間重み付き再計算値。Δ は同じ kernel の baseline との差。全 state の完了・有限性・source/runtime/state identity を確認した。

| state | downforce | drag | Δdownforce | Δdrag |
| --- | ---: | ---: | ---: | ---: |
| baseline | 0.3612783599 | 0.3500267344 | +0.00000000e+00 | +0.00000000e+00 |
| D0_interface_offset +2.5 mm | 0.3625233442 | 0.3497165179 | +1.24498430e-03 | -3.10216550e-04 |
| D0_interface_offset −2.5 mm | 0.3578455310 | 0.3487670641 | -3.43282887e-03 | -1.25967036e-03 |
| D1_filtered_seed11 +2.5 mm | 0.3612578509 | 0.3496271144 | -2.05089530e-05 | -3.99620053e-04 |
| D1_filtered_seed11 −2.5 mm | 0.3609744405 | 0.3501716970 | -3.03919385e-04 | +1.44962578e-04 |
| D2_filtered_seed2026 +2.5 mm | 0.3607367914 | 0.3495176297 | -5.41568457e-04 | -5.09104756e-04 |
| D2_filtered_seed2026 −2.5 mm | 0.3614646334 | 0.3502520100 | +1.86273495e-04 | +2.25275549e-04 |
| P1_upstream_lobe +2.5 mm | 0.3598557854 | 0.3496886159 | -1.42257453e-03 | -3.38118577e-04 |
| P1_upstream_lobe −2.5 mm | 0.3622516258 | 0.3499674609 | +9.73265899e-04 | -5.92735552e-05 |

登録済み8 perturbation state の hard geometry gate はすべて通過している（STEP-01 state の固定記録）。これは新しい combined proposal の geometry gate 通過を意味しない。

## 方向別の中心 secant（N/m）

`g_sec=[R(+s)−R(−s)]/(2s)`、s=0.0025 m。比は flow_32 / flow_24。GRID-01 の分解条件は `|R(+s)−R(−s)| > 3e-5 N` で、各 grid・各応答の8成分すべてが分解された。`sign_preserved_resolved` / `sign_flipped_resolved` / `unresolved` はこの規則で判定する。D1/D2 downforce の STEP-01 の historical `source_step01_resolved=false` は別欄に保持し、過去の判定を変更していない。

| 方向 | g_L^24 | g_L^32 | L 比 | L 符号 | g_D^24 | g_D^32 | D 比 | D 符号 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| D0_interface_offset | +0.780711018 | +0.935562635 | +1.198347 | `sign_preserved_resolved` | -0.112482291 | +0.189890761 | -1.688184 | `sign_flipped_resolved` |
| D1_filtered_seed11 | -0.108387627 | +0.056682086 | -0.522957 | `sign_flipped_resolved` | -0.067548209 | -0.108916526 | +1.612427 | `sign_preserved_resolved` |
| D2_filtered_seed2026 | -0.096135998 | -0.145568390 | +1.514192 | `sign_preserved_resolved` | -0.168798771 | -0.146876061 | +0.870125 | `sign_preserved_resolved` |
| P1_upstream_lobe | -0.382309588 | -0.479168086 | +1.253351 | `sign_preserved_resolved` | -0.213037399 | -0.055769004 | +0.261780 | `sign_preserved_resolved` |

| raw coefficient vector | cos(flow_24, flow_32) | ‖flow_32‖₂ / ‖flow_24‖₂ |
| --- | ---: | ---: |
| downforce | 0.9839039751 | 1.2058290485 |
| drag | 0.2787729381 | 0.8927667711 |

downforce 全体の向きは近いが、D1 の符号が反転した。drag は D0 の符号が反転し、方向全体の cos も小さい。両者を同じ程度に grid へ転写できるとは解釈しない。flow_32 の全8 secant の偶関数部は負であり、D1 downforce の正の中心 secant にもかかわらず ±2.5 mm の両 state は baseline を下回る。中心 secant の符号と片側の実際の改善は区別する。

## 制約付き4D提案（実 CFD を行わない一次モデル）

主問題は `max t`、`g_L^k·c >= t`、`g_D^k·c <= 0`（k=24,32）、`‖c‖₂ <= 1`。感度版は各 lift に `−ε‖c‖₁`、各 drag に `+ε‖c‖₁` を加える。固定した ε=0.006 N/m は名目 floor 3e-5 N を 2s で割った値で、flow_32 の noise の実測値や統計的な信頼区間ではない。全6解の有限 active-set / orthant 列挙と primal-dual KKT 証明書は保存済み、すべて検証に通過した。

| 提案 | t* (N/m) | m（空間場の max 絶対値） | flow_24 ΔL @1.25 mm (N) | flow_32 ΔL @1.25 mm (N) | flow_24 ΔD (N) | flow_32 ΔD (N) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 主問題（raw） | 0.5002609628 | 1.6686280669 | +3.747546958e-04 | +4.944377702e-04 | -6.568734790e-05 | +3.118831890e-20 |
| 感度版（L 下限 / D 上限） | 0.4561908302 | 1.6562277259 | +3.442995965e-04 | +4.597037306e-04 | -6.149181615e-05 | -4.713274340e-20 |

約 1e-20 N の drag 予測は数値ゼロ。主問題の flow_32 drag の raw 予測はゼロだが、その方向を感度モデルで評価した drag 上限は +8.856977188e-6 N になる。感度モデルで drag 非増加を満たすのは感度版の提案である。

係数順は `(D0,D1,D2,P1)`。SDF への実 step は `Δφ = (s/m) Σ c_i d_i` で、c のノルムと空間場の max ノルムを混同しない。

- 主問題 c*: `(+0.5385287019, +0.3695763206, +0.5983823516, -0.4640460558)`。
- 主問題 per-unit-step c/m: `(+0.3227374108, +0.2214851397, +0.3586073874, -0.2781003538)`。
- 感度版 c*: `(+0.5088319704, +0.3741305630, +0.6314648863, -0.4498538041)`。
- 感度版 per-unit-step c/m: `(+0.3072234346, +0.2258931891, +0.3812669456, -0.2716134968)`。

各 grid 単独の保持率と cross-grid objective 比を区別する。以下の「単独保持率」は各 grid の drag 制約付き t* / unconstrained downforce vector のノルム。「cross/単独」は worst-grid objective t_cross* / t_single* で、flow_32 で達成する個別の slope の保持率ではない。

| grid | 単独主 t* (N/m) | 単独主保持率 | 単独感度 t* (N/m) | 単独感度保持率 | 主 cross/単独 | 感度 cross/単独 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| flow_24 | 0.8794433120 | 99.791% | 0.8687551503 | 98.578% | 56.884% | 52.511% |
| flow_32 | 0.6820336842 | 64.181% | 0.6333677603 | 59.601% | 73.348% | 72.026% |

元の LOWDIM-01 proposal を同じ一次 secant で評価すると次になる。実際の LOWDIM-01 / LOWDIM-02A 結果を置き換える数値ではない。

| grid | LOWDIM-01 一次 drag slope (N/m) | drag 予測 @1.25 mm (N) |
| --- | ---: | ---: |
| flow_24 | +0.0194932820 | +1.737007239e-05 |
| flow_32 | +0.2218311714 | +1.976693051e-04 |

flow_24 の +0.019493 N/m、+1.737e-5 N に対し、flow_32 は +0.221831 N/m、+1.977e-4 N。この差は両 grid の drag を制約に入れる理由になる。ただし combined-direction の加法性と曲率は別問題であり、一次予測だけで実際の drag 変化を保証しない。

## Amendment 1・証拠範囲・停止位置

最初の kernel v1 は CUDA probe の `JSON3` 未導入により、solver state を1つも走らせず fail-closed になった。Amendment 1 は probe の JSON 出力を Julia Base に置き換えただけで、測定・状態・閾値・提案の規則は不変。失敗は `failed_attempt1/` に保存済み。解析には `prerun_freeze_amend1.json` だけを使用し、元の freeze と全 historical evidence を変更していない。

CLI の status/output は current session を参照する。GetKernel metadata の `current_version_number=2`、pull した current source の frozen runner SHA 一致、output の source/pins/runner identity、および未コミットで受け取った `kaggle_submission_v2.json` を合わせて v2 を束縛した。`kernels pull .../2` は 403 で取得できず、その失敗も `postrun_execution.json` に記録した。

flow_32 の noise は測定していない。3e-5 N は flow_24 由来の名目 floor。secant、L1 感度モデル、combined-direction の一次予測は有限 step の仮説であり、実 primal の受理条件を代替しない。独立した read-only review では raw CSV の9状態の平均力・8 secant、43 manifest hash、全68 branch の KKT 証明書を直接確認し、blocker はなかった（平均力の差 <=5.56e-16 N、secant の差 <=8.89e-14 N/m）。

**ここで停止する。** `FEASIBLE_CONE_FOUND` の場合の判断分岐は、両 grid で reverse control を伴う actual-primal line-search を別 issue として事前登録するかどうか。候補 step・drag 受理条件・曲率の grid 依存は先に決める必要がある。`NO_FEASIBLE_CONE_IN_4D` の場合の分岐は GEOM-01 の状況を確認してから8–12D basis 拡張を検討することだったが、今回その分岐ではない。いずれもユーザー判断前には新 issue、CFD、basis 拡張、曲率モデル、reinitialization、#30 supersession、Stage B を実行しない。issue29-geom01 の未コミット作業も本件では変更しない。

## コマンドと artifact

`postrun_execution.json` に status/download/source-identity、`--check` → 1回の `--write` のコマンド・exit code を記録した。再現検証は `tests/test_grid01_evidence.py` による raw CSV の独立算術再構成と保存済み証明書の検証で行い、production analyzer を再実行しない。全 suite は **2114 passed / 37 failed / 23 skipped**、事前の37 failure ID と完全一致し新規失敗0件（全件 PASS ではない）。追加 evidence テスト6件、compileall は通過した。diff check と比較結果は `validation/postrun_validation.json` および同 directory の log/XML に保存する。raw instantiate log と postrun pytest 証拠の末尾空白は scoped `.gitattributes` でそのまま保持し、source の whitespace check は有効なままとした。

| artifact | SHA-256 |
| --- | --- |
| `prerun_freeze_amend1.json` | `522b409b75e9ab8579603770850683bde336fc010977a3916147fab7cdadf431` |
| `grid01_analysis.json` | `ec00ed9afe4f44926dd40ff1e87f303dd9baf89195b19cb550103606beedb69c` |
| `kernel_output/grid01_a/output_manifest.json` | `c145843c414998ff0b1d0613b73fafcec9dd6cd4a1a7e427906e24c9a4cbacac` |
| baseline force CSV | `032ef1cfae320ada28d05a3ad5785fc1fd770b202d4f0d2e9ed8490c6ab61753` |
| frozen analyzer | `808c6bea08ce69f3bc4296968e8c69271b8989067a30588861609a0bf1e705c1` |

source commit: `ea320dc5a95e9b98dc501b62574ea6ee26eaa211`。solver process wall time 合計 3858.256818 s（登録上限8100 s）。全 artifact の path/SHA は `SHA256SUMS`。実行・integrity は provenance evidence、測定・proposal は `bounded_cross_grid_finite_step_observation`、テストは software/evidence verification であり、物理資格化を意味しない。
