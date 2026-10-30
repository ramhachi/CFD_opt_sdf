# Codex への指示: #26 GRID-01 個別 basis の cross-grid secant ＋ cross-grid 制約付き 4D proposal（solver-free）

作成: 2026-10-09（Claude）。integration HEAD `32e64715dc20a9ac2dd78e3c011bcb48f311b98e`（`codex/kaggle-batch-migration`）から作業する。
リポジトリ作業の前に `AGENTS.md` が指す 5 文書（`docs/opencode_handoff_2026_09.md`、`docs/README.md`、`docs/phase_plan.md`、`docs/problem_register_2026_09.md`、`docs/problem_resolution_plan_2026_09.md`）と `docs/git_branching_strategy.md` を読むこと。主張は常に evidence-scope に収める（本作業は gradient の適格性・格子収束・物理的 downforce・OPT-01 のいずれでもない）。

## 0. 現状（事実。すべて main 上の evidence から検証できる）
- #49 LOWDIM-02A Stage A は事前登録どおり **`STAGE_A_CONSTRAINT_FAIL`**（`docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09/`、`lowdim02a_analysis.json`、`note.md`）。flow_32 で受理 step（4 方向 basis の downforce-only proposal に沿う +1.25 mm）は downforce **+7.31e-4 N**（flow_24: +4.05e-4）、reverse control −1.09e-3 N、gate 通過。ただし drag **+5.40e-5 N** が登録許容 3e-5 N を超えた。baseline と baseline repeat は W4 v17 の flow_32 baseline と byte 同一（SHA `032ef1cf…`）で、決定論性は確立済み。
- 奇偶分解（±1.25 mm）: downforce の奇関数部は flow_24 の 1.13 倍、偶関数部（曲率）は 0.45 倍。drag の奇関数部は flow_32 で ≈ +1.86e-4 N（正＝一次では drag 増側）、flow_24 は ≈ +2.7e-5 N。+2.5 mm では flow_32 の drag は −8.3e-5 N に戻る（二次以上の曲率）ので、「step を縮めれば drag 制約を満たす」とは言えない（小 step 極限では一次項が支配）。
- 帰結: downforce だけから作った 4D 方向は、grid を跨ぐ drag feasibility を保証しない。**drag の分解能測定は主課題にしない**（repeat が byte 同一で、離散 objective R = [80,120] tU/L の time-weighted force としては +5.4e-5 N は再現可能な差）。**#49 の Stage A contract は FAIL のまま終了。閾値を緩めない、結果を見て Stage B を生やさない**。
- 探索的な事前確認（Claude、flow_24 の既存 STEP-01 データのみ、freeze 前。**この結果に合わせて登録内容を調整してはならない**）: STEP-01 の ±2.5 mm centered secant（flow_24）で g_L = (+0.781, −0.108, −0.096, −0.382)、g_D = (−0.112, −0.068, −0.169, −0.213) N/m。LOWDIM-01 の proposal 単位ベクトル c の一次 drag 勾配は g_D·c = +0.0195 N/m（わずかに非 feasible。1.25 mm での一次予測は +1.7e-5 N）。flow_24 だけで「g_D·c ≤ 0, ‖c‖₂ ≤ 1」の下の downforce 最大化をすると、制約なしの ‖g_L‖ = 0.881 に対して 0.879 を保てる（downforce をほとんど失わず drag 制約を満たせる余地がある）。flow_32 の g はまだ無い。

## 1. 目的と範囲
1. **#26 GRID-01（FD-only の bounded な cross-grid 特性化）**: D0/D1/D2/P1 の 4 方向を flow_32 で STEP-01 と**全く同じ ±2.5 mm**（同じ phi）で測り、flow_24 の既存 secant（`step01_analysis.json`、hash 束縛）と、downforce・drag の両方で比較する。
2. **solver-free の cross-grid 制約付き 4D proposal**（§4）を、同じ analyzer が記録値だけから計算する（記述的。次の issue の入力）。
3. **やらないこと**: basis 拡張（8–12D）、曲率モデル、reinitialization（#28 は formal Round3 FAIL のまま）、#30 の supersession、#49 の Stage B、実 CFD での line-search（proposal の実評価は結果を見た上でユーザーが決める別 issue）、δ の選択、GRAD-03 verdict、flag の変更（6 個 false のまま）、FD-08 verdict の変更、AD/tangent の使用。**#26 の Done にある「最初の最適化 step にどの flow grid を使うか」の決定は、この結果だけでは行わない**（入力として記録するだけ）。

## 2. 手順（これまでの workflow と同じ。各段で記録し、最後に必ずユーザー判断で止まる）
0. **issue 整理（先に実施）**
   - #26 に #49 Stage A の結果への cross-link コメント（現在は予告コメントしかない）: 結果の表、`STAGE_A_CONSTRAINT_FAIL`、奇偶 1.13×/0.45×、「個別 basis の cross-grid 特性化は #26 で行い、#49 は registered check の constraint failure として終了」。#26 は open のまま。
   - #49 を close（理由: Stage A contract 終了、Stage B は Stage A PASS 後の条件付きのため実行しない）。コメントに結果と本作業への参照を残す。
1. 作業 branch（例 `exp/issue26-grid01-cross-grid-secant-2026-10-09`）を integration HEAD から作る。`git status`/`git diff`/recent history を確認してから編集（AGENTS.md）。
2. **事前登録**: §3・§4 の内容を `prerun_note.md` に固定し、solver 入力（inventory）と analyzer・契約・runner・kernel を実装・テストし、source commit を切る（pin 対象を commit してから kernel を render）。
3. **独立レビュー 2 本**（read-only、別 agent）を freeze の前に実施し、指摘をすべて反映（pin 対象ファイルを変えたら source commit を切り直す）。(1) lineage / 入力 / runner / 時間予算 / byte-identity gate、(2) analyzer・定義・閾値・proposal の定式化・文言（結果を見た後に決めたと読める余地がないか）。`independent_reviews.md` に記録。
4. identity-free check（新 slug）→ freeze（`prerun_freeze.json`、clean tracked tree、source commit が HEAD の祖先）→ **branch を push**（Kaggle kernel が GitHub から pinned commit を clone するため、push 前に kernel を投入しない）。
5. T4 実行（Kaggle、1 kernel、9 run）。runner の `KERNEL_TIMEOUT_S` と `kaggle kernels push --timeout` は同じ値にする。Kaggle を操作できない場合は freeze と push までで止め、ユーザーに引き継ぐ。
6. host 検証 → analyzer を `--check` で確認 → **`--write` は 1 回だけ**。
7. 記録: `note.md`、evidence test、`SHA256SUMS`、`docs/phase_plan.md` に追記、全 pytest（`.venv/bin/python -m pytest -q`。**baseline の 37 失敗と同一であること**＝新規失敗 0）、`git diff --check`、branch を push、temp worktree で `--no-ff` merge（`git worktree add --detach … origin/codex/kaggle-batch-migration`、merge、`git push origin HEAD:codex/kaggle-batch-migration`、`git worktree remove`）、#26 に結果コメント、memory 更新。
8. **ここで止める**。結果に応じた次（新しい constrained LOWDIM iteration issue、basis 拡張など）は提案としてまとめるだけで、実行・登録しない。

## 3. 事前登録する内容（#26 の測定）
- **state（1 kernel、flow_32、9 run）**: baseline 1 本 ＋ `{D0_interface_offset, D1_filtered_seed11, D2_filtered_seed2026, P1_upstream_lobe} × {+2.5 mm, −2.5 mm}`。phi・state・NPZ の SHA、changed node 数、margin は **STEP-01 の `inventory.json`（`step01__<dir>__s2.5mm__{plus,minus}`）をそのまま hash 束縛**し、runner が numpy（`scripts/step01_states.py` の `perturb`、`construct_state` と同じ演算順）で再生成して SHA を照合する（方向 raw は `docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/*.dir_f4_fortran.raw`、各 SHA を pin）。baseline repeat は不要（#49 で byte 同一を確認済み）。
- **job**: `scripts/waterlily_lowdim02_flow32_job.jl` をそのまま使う（変更しない、pin する）。
- **baseline gate（fail closed）**: flow_32 baseline の力 CSV は W4 v17 round-2 retained の `flow_32.forces.csv`（SHA `032ef1cfae320ada28d05a3ad5785fc1fd770b202d4f0d2e9ed8490c6ab61753`）と byte 同一。不一致なら runner は他 state を走らせず停止、analyzer は INCOMPLETE。最初の登録 state が唯一の baseline であることを runner が実行時に確認する（#49 の実装をそのまま流用）。
- **測定契約**: [80,120] tU/L の endpoint-clipped time-weighted force。N への換算は host で flow_32（`flow_spacing_m = 0.025`、ρU²dx² = 6.25e-4）。**`recompute_force_n` は case の spacing で換算するので、flow_24 の `formal_criteria.json` をそのまま渡すと 0.0011111 倍になって誤る**。`cfd_sdf.lowdim02a_contract.FLOW32_CASE` と `analyze_lowdim02a.flow32_criteria` を再利用すること（W4 flow_32 baseline を再計算して 0.3612783598966907 N と一致するテストがある）。host 再計算と Julia summary は相対 1e-9 で一致。
- **量（各方向 i、応答 q ∈ {downforce, drag}）**: 
  - `g32_{q,i} = [R(+2.5) − R(−2.5)] / (2·0.0025)` N/m、偶関数部 `[R(+)+R(−)−2R(0)]/2`、η_even（STEP-01 と同じ定義）。
  - 分解条件: `|R(+) − R(−)| > 3e-5 N`（FD-08 の名目 σ0 の 10 倍＝flow_24 の名目 floor。flow_32 の noise 実測ではないと明記）。分解できない成分の符号は主張せず `unresolved` と報告（0 とは書かない）。
  - flow_24 側は `step01_analysis.json`（SHA を freeze に束縛）の `series["<dir>|<q>"].rows[0]`（step_mm = 2.5）の `g_sec_n_per_m`・`r_plus_n`・`r_minus_n`・`r0_n` を使う。**flow_24 の値を再計算・再利用で書き換えない**。
  - 比較: 成分ごとの `g32/g24`、符号一致（両方が分解できる場合のみ）、相対差、および係数空間（基底＝4 方向、単位 max-norm）での **cos(g_L^24, g_L^32)・cos(g_D^24, g_D^32)** とノルム比。
- **判定（記述的。物理の pass/fail ではない）**: `GRID01_SECANT_RECORDED`（integrity が通った場合。上の量をすべて記録）／`GRID01_SECANT_INCOMPLETE`。符号保存は方向ごとに `sign_preserved_resolved` / `sign_flipped_resolved` / `unresolved` と記述。格子収束・GCI・「受け入れ可能な grid」の判定はしない。
- **integrity gate（fail closed）**: baseline byte 同一、各 state の phi/state/NPZ SHA・margin・有限性・t_end ≥ 120・threads = 1、manifest、pin、GPU = Tesla T4、全 state 完了（1 つでも欠ければ DONE を書かず INCOMPLETE）、freeze の key・ファイル hash。analyzer に pin の空・NaN・欠落で fail-open する経路がないこと（#49・LOWDIM-01 のテストを参考に）。

## 4. 事前登録する内容（solver-free の cross-grid 制約付き 4D proposal。測定の**前**に定式化を固定し、同じ analyzer が記録値から計算する）
係数 c ∈ R⁴（基底 D0, D1, D2, P1。単位 max-norm の方向、c は LOWDIM-01 と同じく係数空間のユークリッド単位球で正規化）。Δφ への変換は `scripts/lowdim01_states.py::coefficient_direction` と同じ（v = Σ cᵢdᵢ、d = v / max|v|、step s では係数 cᵢ/m·s）。
- **主問題 P**: `max t  s.t.  t ≤ g_L^24·c,  t ≤ g_L^32·c,  g_D^24·c ≤ 0,  g_D^32·c ≤ 0,  ‖c‖₂ ≤ 1`。
- **感度版**: 分解能由来の不確かさ ε = 3e-5 / (2·0.0025) = 6e-3 N/m を全成分に与えた頑健版 `g_L·c − ε‖c‖₁ ≥ t`、`g_D·c + ε‖c‖₁ ≤ 0`（両 grid）。
- **併記する参照**: 各 grid 単独の制約付き最適解、制約なしの downforce 最適（‖g_L‖）に対する保持率、LOWDIM-01 の proposal 単位ベクトルの各 grid での一次 drag 勾配 g_D·c と 1.25 mm での一次予測、最適 c と対応する per-unit-step 係数。
- **判定（記述的）**: `FEASIBLE_CONE_FOUND` ＝ 主問題と感度版の両方で t* > 0 かつ、s = 1.25 mm での一次予測 downforce 増が**両 grid で ≥ 3e-5 N**。それ以外は `NO_FEASIBLE_CONE_IN_4D`（t* > 0 でも一次予測が 3e-5 N 未満の場合を含む。理由を併記）。解法は決定論的にすること（凸問題。SOCP/二次錐でも、線形計画＋多面体近似でもよいが、solver・近似・許容誤差を freeze に書き、解を制約で検証する）。
- **位置づけ**: 一次（secant）モデルによる仮説であり結果ではない。曲率は grid 感度が高い（偶関数部 0.45×）ので、実 CFD の line-search（両 grid・reverse control 付き）が受理の唯一の権威になる別 issue で扱う。一次モデルは proposal 生成、曲率は trust radius の参考値にとどめる。

## 5. 実装の流用元と注意（#49 の経験）
- 流用: `scripts/lowdim02a_runner_template.py`・`build_lowdim02a_kernel.py`・`build_lowdim02a_inputs.py`・`analyze_lowdim02a.py`・`build_lowdim02a_freeze.py`・`src/cfd_sdf/lowdim02a_contract.py`、`tests/test_lowdim02a*.py`・`tests/lowdim02a_synthetic.py`、`scripts/check_fd08_v2_kaggle_identity_free.py`（kernel と dataset の slug は同じ namespace。title == slug）。runner は方向 4 本の raw を pin する点が #49 と違う（#49 は proposal 1 本）。
- 新しい kernel（例 `cfd-opt-sdf-grid01-a`）は identity-free check を通す。dataset は使わない。timeout の目安: setup ≈ 240 s ＋ 1 state ≈ 390–430 s × 9 ≈ 1 時間強、`--timeout 10800`。
- レビューで直した落とし穴を最初から入れる: (a) PASS 的な判定に純偶関数応答を通さない、(b) 分解できない量を 0 や符号として扱わない、(c) byte 同一な repeat は noise の証拠ではない旨を note と解釈文に書く、(d) 解釈文を verdict ごとに条件づける、(e) 境界テストは厳密な差で（float の偶然に頼らない）、(f) geometry gate 集合の検査を落とさない。
- macOS の注意: `sed -i` には `''` が要る／`timeout` コマンドがない／`kaggle` は 2.2.4／`.venv/bin/python` を使う／変数展開つき `rm -rf` は避ける。
- 編集は commit 単位で意図したファイルだけ add。force-push・reset・checkout で他の作業を上書きしない。

## 6. 並行トラック（別 branch・独立。T4 トラックを待たせない）: #29 GEOM-01
現在 3 gate pass・10 unmeasured、実際の zero-level / STL exporter は未適格。8–12D や multi-step の前に埋める:
min feature width、inter-component gap、connectivity policy（#31 と整合）、実 export integrity（surface/self-intersection）。まず #29 の現状と `src/cfd_sdf/design/{geometry_gates,topology_policy}.py` を読み、solver-free の測定器と defect fixture（クリーンな解析 fixture が通り、故意の欠陥が正しい理由で落ちる）を追加し、LOWDIM-01/02A の既存 state（baseline、+1.25、+2.5、+5、+7.5、reverse）に遡って記述的に適用する。**optimizer の受理は一切認可しない**（#29 の Non-goal）。成果は別 PR/branch・別の evidence dir に置き、本トラックの freeze と混ぜない。

## 7. 完了時の報告に含めること（ユーザーが次を判断できるように）
- 実行したコマンドと結果、artifact のパスと hash、evidence class を結論と分けて記録。
- 9 state の表: 各方向の g_L^24, g_L^32, g_D^24, g_D^32、比、符号保存、分解可否、cos と ‖·‖ 比。
- §4 の結果: `FEASIBLE_CONE_FOUND` か `NO_FEASIBLE_CONE_IN_4D`、t*、最適 c（per-unit-step 係数）、各 grid の保持率、LOWDIM-01 proposal の各 grid の一次 drag 勾配、感度版の結果。
- 判断分岐の提示のみ: feasible → 両 grid での actual-primal line-search（新 issue の事前登録案、候補 step・reverse control・受理条件）／ not feasible → 8–12D basis 拡張の動機づけ（その前に #29 の状況を確認）。いずれも**実行せずユーザー判断で止まる**。
- 開示: 登録前の探索的確認（§0）を使ったこと、flow_32 の noise は実測していないこと、一次モデルは仮説であること。
