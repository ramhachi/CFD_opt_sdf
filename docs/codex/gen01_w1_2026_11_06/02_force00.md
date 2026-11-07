# WP2：FORCE-00 の実装（一様圧力で閉じる力の読み出しと、その gate）

最初に `docs/codex/gen01_w1_2026_11_06/00_README.md` を読み、その規則に従うこと。仕様は `docs/force00_force_readout_gate_2026_11_01.md`（FORCE-00、draft rev 0）。

## 目的

WaterLily 1.8.0 の `pressure_force`（`∮ p n ds` を `nds = n·kern(clamp(d,−1,1))` で近似）は一様圧力で閉じない（WaterLily issue #369）。本リポジトリの判定尺度（親の力の 0.1〜0.5 %）と同じ桁の、配置位相に依存する誤差を出す。閉じる読み出しを 2 つ（R_nds：#369 の μ₀ telescoping、R_cv：運動量の control volume）本プロジェクト側に実装し、一様圧力の閉包テスト（CPU）と、既存の親の力に対する回帰・比較を取る job フック、そして gate の判定スクリプトを作る。**GPU は回さない**（F1〜F3 はユーザーが後で回す）。

## 必ず読む（全文）

- `docs/force00_force_readout_gate_2026_11_01.md`
- `docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md` §2〜§3（1.8.0 の `nds`、`measure!` の μ₀、#369 の式、#293 の control volume の recipe）
- `julia/CFDSDFWaterLily/src/Forces.jl`、`WaterLilyBody.jl`、`GridSDFBody.jl`、`CandidateCWaterLilyBody.jl`、`WaterLilyNormalFloorBody.jl`、`SurfaceFluxQuadrature.jl`（既存の面積分の書き方）
- WaterLily 1.8.0 の source（`~/.julia/packages/WaterLily/<slug>/src/Metrics.jl`、`Flow.jl`、`Body.jl`、`AutoBody.jl`。無ければ `julia --project=julia/CFDSDFWaterLily -e 'using Pkg; Pkg.instantiate()'` で取得して読む）
- `scripts/waterlily_lowdim02_flow32_job.jl` の力のサンプリング（編集しない。フックの付け方の参考）
- `docs/evidence/unc01_2026_10_20/`（U01 smoke の親の値と位相）、`docs/evidence/screen01_2026_10_30/wl/verify/table_f32a.json`（F2 の回帰参照）

## 成果物

1. `julia/CFDSDFWaterLily/src/Forces.jl` に追加（既存の関数は変えない）：
   - `nds_telescoping(sim)`：`sim.flow.μ₀` から `nds[I] = Σᵢ eᵢ (μ₀[I+δ(i,I), i] − μ₀[I, i])` を作る（#369 の μ₀ 形。SDF の距離を使う版は使わない）。`pressure_force_nds(sim)`、`viscous_force_nds(sim)`（粘性項は既存の `−2ν S(I,u)` に同じ nds を掛ける）、`force_on_body_nds(sim) = −(…)`。
   - `control_volume_force(sim, box)`：box（セル index の範囲。領域境界から ≥ 2 セル、物体から ≥ 4 セル内側）の面上で `u`、`p` を補間し、粘性応力は `WaterLily.S`、蓄積項は `sim.flow.u⁰` と `Δt[end−1]` で（#293 の recipe）。2D と 3D の両方。GPU 配列でも動く書き方（`@loop`／KernelAbstractions）にし、CPU で検証する。
   - 3 つの読み出しを同じ呼び出しで返す `force_readouts(sim, box) -> NamedTuple(cur=…, nds=…, cv=…)`。
2. `scripts/force00_uniform_pressure.jl`（U1／U2、CPU）：
   - v18 の親（`docs/evidence/v18_genesis_2026_10_19/v18_parent.npz` か harness の raw。既存のローダを使う）を flow_24 と flow_32 の格子に `GridSDF` で載せ、FID-01 の 32 個の Halton shift（`docs/evidence/fid01_2026_10_21/` の登録値を読む。コピーしない）＋ z の shift（同じ生成規則で 8 個）で配置し、`p .= 1`、`u .= 0` として `∮ p nds` を R_cur と R_nds で計算する。流れは解かない。
   - W2a の球の fixture（既存の `tests/` か `docs/evidence/` の W2a の定義を探す）で R ∈ {8, 16, 32} セルの off-grid 球について同じことを行い、#369 の表（円 8.5e-3、2.7e-3、2.9e-2；球 R16 で 0.29）と並べて出す。
   - 出力は `uniform_pressure.json`（配置ごとの力ベクトル、最大・RMS、R_nds の閉包）。決定的であること（2 回走らせて byte 同一）。
3. job フック：登録済みの job は編集できないので、**新しい job 変種** `scripts/waterlily_force00_job.jl` を `waterlily_lowdim02_flow32_job.jl` から **コピーして**作り、変更点を (a) 力のサンプルに `cur`、`nds`、`cv` の 3 組の列を足す、(b) box を環境変数で受ける、の 2 点に限る。既存の列名・順序・窓・位相の意味は変えない（R_cur の列が既存 job と byte 同一になるように）。差分を `scripts/waterlily_force00_job.diff` として添える。
4. `scripts/force00_gate.py`：仕様 §4 の C1〜C5 を `docs/evidence/force00_2026_11/` の出力から 1 回だけ計算（書き込み先が存在すれば拒否）。C1 は R_cur の byte 回帰（U01 smoke と f32a の登録 CSV と比較。SHA は evidence から読む）。C2 は閉包の閾値（仕様の 1e-4 × 投影面積、球は相対 1e-3）。C3 は位相 SD の比較（記述、両方報告）。C4 は符号と 15 % の帯。C5 は FID tier-A の対差分の差 vs UNC-01 の σ_d（evidence から読む）。欠け run は `INCOMPLETE`。採用規則（両方 PASS なら R_cv、片方なら それ、無ければ `NONE`）を `gate.json` に書く。
5. テスト：
   - Julia：`scripts/force00_selftest.jl`（CPU、数秒）。(a) 解析的な一様圧力場で R_nds が 1e-12 以下で閉じる（2D 円、3D 球、off-grid）、(b) 線形速度場で control volume の各項が解析値と一致、(c) `force_readouts` の cur 成分が `WaterLily.total_force` と byte 同一。
   - Python：`tests/test_force00_gate.py`（合成データで C1〜C5、採用規則、`INCOMPLETE`、書き込み拒否）。

## 受け入れ条件

- Julia の自己テストが CPU で通り、R_nds の一様圧力の閉包が 1e-12 以下。
- `force00_uniform_pressure.jl` が Mac で数分以内に終わり、決定的。
- `waterlily_force00_job.jl` の R_cur 列が既存 job と同じ定義であることを、CPU の小さい格子（flow_16 相当、短い窓）で既存 job と並べて確認する（両方を同じ入力で走らせ、`cur` 列が byte 同一）。
- `pytest -q tests/test_force00_gate.py` が通り、全体の失敗集合が base と同一。

## Amendment 1（2026-11-06。1 回目の試み（Draft PR #84、`21d1e8e7`）が「配置の決定待ち」で止まった点への回答。この節が上の本文より優先する）

1. **配置は A。** 新しい読み出しは **新規ファイル `julia/CFDSDFWaterLily/src/Force00.jl`** に置き、`Forces.jl` は **1 byte も変えない**（W2a の manifest が `Forces.jl` 全体を SHA で固定しているため。`test_candidate_c_w2a_source_manifest_and_criteria_hashes_resolve` が通ること）。用意済みの `reports/wp02_preserve_pins.proposed.diff` を適用し、`CFDSDFWaterLily.jl` への `include` の追加が他の pin（conftest の `_PINNED_SOURCE_*`、各 freeze の source SHA）を壊さないことを、全体 pytest の失敗集合が base と同一であることで示す。もし `CFDSDFWaterLily.jl` 自体が pin されていて `include` を足せないなら、`Force00.jl` を job 側から `Base.include` する（`quick_tie.jl` と同じ流儀）。
2. 「Julia 自己テストは数秒」は cold start の JIT を除いた話でよい。69〜161 秒は許容。報告にそう書く。
3. C4 は 15 %（本文の値）を採用し、10 % は診断値として報告する（既に実装済み。そのまま）。C5 で `camber_m19.7` の UNC-01 σ_d が登録 evidence に無い場合は `INCOMPLETE`（既に実装済み。そのまま）。
4. **道具の注意。** 今回の sandbox では共有の Git dir（`/Users/sota/projects/FomulaTMU/CFD2026_09/.git`）に書き込めるので、この worktree の branch `feat/gen01-w1-02-force00` で直接 commit・push する（一時 checkout は使わない）。worktree は remote の `21d1e8e7` に同期済み。1 回目の記録 `reports/wp02_design.md`・`wp02_report.md` はそのまま更新してよい（`wp02_preserve_pins.proposed.diff` は適用後に削除）。PR は既存の Draft PR #84 を `gh pr edit` で更新し、受け入れ条件を満たしたら `gh pr ready` にする（新しい PR は作らない）。
5. 全体 pytest の base の失敗集合は、開始 commit（`e3dcdf61`）を `git worktree add --detach` した別ディレクトリで **完走**させて取る（中断した記録は base にならない）。実装後も完走させ、両者の失敗 ID 集合を報告に載せる。

これで決定待ちは解消したので、今回は BLOCKED にせず完了して PR を ready にすること。

## 注意

- `nds` の符号と向き（外向き法線、物体が流体に及ぼす力の符号）は `Forces.jl` の docstring の約束に合わせる。
- `measure!` が μ₀ を書くのは band の中だけ（`d[I]^2 < (2+ε)^2`）で、外は 1、内は 0。telescoping はこれを前提にしてよいが、テストで確認する。
- 浮動小数点の和は Float64 で（1.8.0 の `promote_type(Float64, Tp)` と同じ）。
- 報告には、#293 の「組み込みと control volume は 7〜9 % ずれる」が本プロジェクトの親でどうかは **GPU 実行まで分からない**と明記する。
