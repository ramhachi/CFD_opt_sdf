# GRID-02 (#56) 事前登録メモ — 4 つの flow grid での downforce 応答の slope / curvature と、解析格子の位置ずらし対照

実行前に固定する。結果を見た後に state・閾値・分類・判定を追加・変更しない。正本の計画は `docs/grid02_plan_2026_10_15.md`（v2、3 角度の敵対的レビュー後）で、この note はその登録要約である。
権限: ユーザーの 2026-10-13 の「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」と 2026-10-15 の「前に進めることが大事だよ」を**解釈**として読む（GRID-02 個別の許可ではない）。手続き（登録・凍結・hash・独立レビュー・fail-closed）は省略しない。

## 問い
OPT-01 v1 Stage B（`OPT01_V1_REJECT`）の同一 7 geometry の downforce 応答は、flow_24 と flow_32 で slope・curvature の符号が同じで大きさが違う（保存データの solver-free な 2 次フィット: flow_24 b≈+1.0e-4 N/mm, a≈-2.3e-4 N/mm²、zero crossing ≈0.4 mm、到達可能な gain ≈1e-5 N（床 3e-5 N 未満）／flow_32 b≈+4.8e-4, a≈-0.8e-4〜-1.4e-4、zero crossing 3〜6 mm、到達可能な gain ≈8e-4 N）。この grid 依存が、解像度によるものか、設計格子（h = 0.025 m）に対する flow grid の位置（整列）によるものかを、同じ geometry で測る。

## 登録する run（新規 20 run、5 kernel、T4、各 1 回の投入）
geometry は OPT-01 v1 Stage B の 7 state（parent = OPT-01 v1 の parent、generation 1、phi Fortran SHA `2f23be78…`、正方向 0.3125/0.625/0.9375/1.25 mm、reverse 0.625/1.25 mm）。inventory 行は hash 束縛した `opt01b_stage_b_2026_10_15/inventory.json` から**そのまま**複写し、再生成・再 gate はしない。

| kernel | case | 位置 | state | job |
| --- | --- | --- | --- | --- |
| s24 | flow_24 | shifted | 7 | `waterlily_xfid_candidate_c_job.jl`（変更なし） |
| s32 | flow_32 | shifted | 7 | `waterlily_lowdim02_flow32_job.jl`（変更なし） |
| f48a | flow_48 | native | parent, +0.3125, +0.625, +0.9375 | 新規 `waterlily_grid02_job.jl`（`grid02_case.jl`） |
| f48b | flow_48 | native | parent（再実行）, +1.25, reverse 1.25 | 同上 |
| f16 | flow_16 | native | 7 + parent 再実行 | 同上 |

native の flow_24 / flow_32 は再実行しない（`opt01b_analysis.json` の `state_forces_n`、SHA 束縛）。shifted = body を flow grid に対して (h/2, h/2, 0) だけ剛体平行移動（既存の pin 値 `W4_CANONICAL_ORIGIN_M` = (-0.9875, -0.7875, -0.6)、phi bytes は同一）。**z は動かさない**（車高を変えない）ので z 面の整列は一部しか反転せず、これは**部分的な対照**である。
solver・測定は不変: Re 80、Candidate C、Float32 T4、[80,120] tU/L の endpoint-clipped time-weighted force、Julia thread 1、物理 index 0 の GPU と singleton UUID の probe、grid ごとの host 換算 ρU²dx²。新 job は flow_32 job の行差分テスト済みの複製で、case 選択と検証表（flow_16 → (100,48,36)、flow_48 → (300,144,108)、粘性 n/80）とメッセージだけが違う。
予算（見積もりであって測定ではない）: flow_48 は 1 state ≈ 2,000 s（1,850–2,400 s）、per-state timeout 4,500 s、aggregate cap 18,000 s（f48a）/ 13,500 s（f48b）、kernel timeout 21,600 s。s24/s32/f16 は 900 s/state、kernel 10,800 s。timeout 超過は integrity failure（修復・再投入なし）。

## 登録する量
各 kernel の parent を基準に dL, dD（N）。分解能 = max(3e-5 N, その grid で観測した parent pair の最大差)。3e-5 N は flow_24 の名目 floor で、他 grid では未測定、byte 一致の pair は再現性であってノイズではない。native flow_24/32 の parent pair 差は 0 とする（opt01b の parent が retained 参照と byte 一致）。
各セル {16n, 24n, 24s, 32n, 32s, 48n} で正方向点に dL = b s + a s²（s は mm、最小二乗）をフィットし、b, a, 最大残差、切片チェック c、zero crossing b/|a|、到達可能な gain b²/(2|a|)（a < 0 かつ b > 0 のとき）、全 dL の符号状態（`positive_resolved` / `negative_resolved` / `unresolved`）を報告する。n = 16/24/32/48 の b, a と parent 力の表、placement effect（shifted − native の parent 力）、OPT-01 の both-grid 規則（> 3e-5 N の downforce 増かつ drag 変化 ≤ 0）の (24n,32n)・(24s,32s)・(32n,48n)・48n 単独での記述的評価も出す。どの組も、この結果だけで採用しない（dual-grid 規則の改定は別の登録）。

## 事前登録の分類と decision map（閾値は固定。調整しない）
Alignment 対照（b を使う。a は副次）: G = b_32n − b_24n、m24 = (b_24s − b_24n)/G、m32 = (b_32n − b_32s)/G。
- `GRID02_ALIGNMENT_DOMINANT`: m24 ≥ 0.5 かつ m32 ≥ 0.5
- `GRID02_ALIGNMENT_NEGLIGIBLE`: |m24| ≤ 0.2 かつ |m32| ≤ 0.2
- `GRID02_ALIGNMENT_PARTIAL_OR_MIXED`: それ以外
Fine grid: r = (b_48n − b_24n)/G。`FINE_CONTINUES_TO_FLOW32`: r ≥ 0.5、`FINE_REVERSES_TOWARD_FLOW24`: r ≤ 0.2、`FINE_INTERMEDIATE`: それ以外。`STABLE_32_TO_48` は |b_48n − b_32n| ≤ 0.3 |b_32n|。G = 0 や非有限値は分類せず INCOMPLETE。integrity failure は `GRID02_INCOMPLETE`（`--write` 禁止）。integrity が通れば全体判定は `GRID02_RECORDED`。
Decision map（次の一手の記録であり、この登録では実行しない）:
- ALIGNMENT_DOMINANT: dual-grid の不一致は placement の artifact。新しい accept 規則の前に placement-robust な評価（native と shifted の平均）を登録。basis 拡張はしない。
- ALIGNMENT_NEGLIGIBLE かつ STABLE_32_TO_48: flow_32 はこの応答の安定した作業地図。flow_32 での提案と flow_48 の finalist 確認、dual-grid 規則の別途登録の改定（1 候補あたりの費用: (24,32) ≈ 2+6 分、(32,48) ≈ 6+33 分でおよそ 6 倍、finalist のみの flow_48 確認は約 1.1 倍）。
- ALIGNMENT_NEGLIGIBLE かつ STABLE でない: 安価な grid では sub-5 mm の slope が安定しない。大きな step／粗い設計格子の研究（solver-free の準備が先）。
- ALIGNMENT_PARTIAL_OR_MIXED: 別の placement phase（x/y の別位相、z は車高許容を登録して）の研究を、規則改定の前に行う。

## 実行前の既知事項（開示）
OPT-01 v1 Stage B、GRID-01、W4 の履歴、上記の保存データのフィットは既知。ヒンドキャスト（精密な予測ではない）: n = 16/24/32 の baseline downforce 0.2545/0.3316/0.3613 N と 1/n〜1/n² の変化から、flow_48 の parent downforce は 0.38–0.40 N 付近。b_48, a_48 の予測は登録しない。FD-07 の位相ずらし（flow_24 で drag +11.9%、downforce +7.2%、再サンプリングで純粋な平行移動ではない）は placement が効く弱い先験的な根拠。3e-5 N の床は flow_16/32/48 で未測定。
v1 → v2 の変更（レビュー反映）: 主推定量を 2 点の符号分類から (b, a, zero crossing, 到達可能な gain) へ、実質ゼロだった solver-free の covariate を同じ研究内の平行移動対照へ、実行不能な n = 64 の後続を削除、分解能と parent 参照を kernel ごとに固定、費用モデル・cap・整列の算術を修正、claims と decision map を書き直し。

## できること・できないこと
言える: 各 grid・位置での登録 step への downforce 応答の slope・curvature・zero crossing・到達可能な gain、shift が flow_24 を flow_32 に近づけるか、flow_48 の slope が 24 → 32 の変化の延長か。
言えない: 格子収束・GCI、真の grid、物理的な downforce／drag、勾配、optimizer や 2 回目の iteration の適格性、OPT-01 の再開や規則変更、shift が整列の完全な対照であること（z 未移動）、他の parent・方向への一般化（parent 1 つ・方向 1 つ）。全 qualification flag は false、`shape_update_allowed=false`、δ 未設定、FD-08 / GRAD-03 の verdict は不変。

## 失敗時の扱いと停止位置
ERROR / CANCEL / integrity failure は `failed_attemptN/` に保存して原因を報告し、`--write`・自動修復・再投入はしない（analyzer 側の不備と分かった場合の amendment は、結果を読む前に結果と無関係な理由で直したことを記録して行う）。記録後に停止する: 規則改定・re-genesis・basis 研究・第 2 iteration は始めない。
