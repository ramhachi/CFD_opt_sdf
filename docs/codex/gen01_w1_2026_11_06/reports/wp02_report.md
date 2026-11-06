# WP2 FORCE-00 報告

## 状態

**BLOCKED：実装と CPU の個別検証は完了。既存 source pin と指定されたファイル配置が衝突しており、全体 pytest の失敗集合を base と同一にする受け入れ条件は未達。**

`Forces.jl` は既存 W2a の凍結 manifest に全体の SHA で固定されている。
元の 1,527 bytes と関数をそのまま保存して末尾に追加しても、
`test_candidate_c_w2a_source_manifest_and_criteria_hashes_resolve` が失敗する。
このテストは未変更の base `e3dcdf61` の独立コピーでは PASS した。
凍結 manifest、既存テスト、登録済み job を書き換えて失敗を隠してはいない。

利用者への確認は、**新規 `Force00.jl` に分離して新規 entrypoint から明示的に
読み込む案**（推奨）か、指定どおりの `Forces.jl` 追加と source-pin テストの失敗を
明示的に許容する案か、という要件の優先順位である。回答待ちのため配置変更は未適用。
適用可能な提案パッチ `wp02_preserve_pins.proposed.diff` を用意し、
`git apply --check` を通した。実装はレビュー用の途中状態であり、merge 対象の完成版ではない。

GPU は一切実行していない。FORCE-00 全体の採否判定も実行せず、`gate.json` は作成していない。
qualification flag と既存 study の判定は変更していない。

## 作ったもの（パス、1 行ずつ）

- `julia/CFDSDFWaterLily/src/Forces.jl`：保存済み μ₀ の telescoping 読み出し、2D/3D control volume、候補 box 検証、3 読み出しを追加。既存関数は byte 不変。
- `scripts/force00_selftest.jl`：CPU で 78 チェック。一様圧力、解析場の各 CV 項、legacy byte 一致、scratch 保存、候補と地面を検証。
- `scripts/force00_uniform_pressure.jl`：流れを解かず U1 80 配置と U2 24 配置を計算し、決定的な JSON を排他的に出力。
- `scripts/force00_uniform_inputs.py`：既存 NPZ loader、登録済み FID shift、既存 Halton generator を再利用する JSON/TOML bridge。
- `scripts/waterlily_force00_job.jl`：登録 job のコピー。元の 13 列を保存し、cur/nds/cv 各 5 列、box の入力・検証・記録を追加。
- `scripts/waterlily_force00_job.diff`：登録 job と新変種の正確な差分。
- `scripts/waterlily_force00_dispatch.jl`：F1 の flow_24 を選ぶ launcher。case inventory と filter の 2 箇所だけを include 時に変更。
- `scripts/force00_job_regression.jl`：実際の両 measurement 関数を同じ v18、flow_16、短い CPU 窓で実行し byte 比較。
- `scripts/force00_gate.py`：参照 SHA、CSV byte、面積・位相・単位・窓・box を検証し、C1〜C5 と採用規則を計算する write-once CLI。
- `tests/test_force00_gate.py`：33 個の合成・出典・異常入力テスト。
- `tests/test_force00_uniform_inputs.py`：登録済み配置と親の読み出し、改変 hash の拒否を検証。
- `docs/evidence/force00_2026_11/`：CPU の配置別 JSON、job 回帰、独立レビュー、実行ログ、決定性、source-pin 衝突の記録と SHA256SUMS。
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_design.md`：設計、読んだ authority、仮定、観測した blocker。
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_preserve_pins.proposed.diff`：既存 pin を保存する配置案。未適用。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

```julia
CFDSDFWaterLily.nds_telescoping(sim)
CFDSDFWaterLily.pressure_force_nds(sim; box=nothing)
CFDSDFWaterLily.viscous_force_nds(sim; box=nothing)
CFDSDFWaterLily.force_on_body_nds(sim; box=nothing)
CFDSDFWaterLily.control_volume_terms(sim, box)
CFDSDFWaterLily.control_volume_force(sim, box)
CFDSDFWaterLily.validate_force_box(sim, box; body=sim.body)
CFDSDFWaterLily.force_readouts(sim, box; body=sim.body, validate_box=true)
```

力は body-force 符号、drag=+Fx、downforce=−Fz。raw `nds_telescoping` は指定どおり
保存済み μ₀ の前進差分であり、SDF から作り直さない。減算前に Float64 へ昇格する。
力の積分では WaterLily の領域端の μ₀ BC jump を除く。候補＋地面の scene では
`body=bodies.candidate` と候補を囲む box を使う。

`box` は inclusive な圧力セル index の `NTuple{D,UnitRange}`。
面の solver 座標は `first(range)-2` と `last(range)-1`。
CV は面上へ u/p を補間し、両側の `WaterLily.S` を平均し、蓄積項に u⁰ と
`Δt[end-1]` を使う。流れの配列を変更せず、legacy が使う f scratch も保存・復元する。

GPU job の必須環境変数は `FORCE00_CV_BOX='lo:hi,lo:hi,lo:hi'`。
dispatcher は `FORCE00_CASE=flow_24|flow_32` も要求する。元の 13 列の後に
`cur_`, `nds_`, `cv_` の fx/fy/fz/drag/downforce 各 5 列を追加する。
box の lower/upper index は summary に保存する。

gate は `force00_runs.json`（schema `force00_runs_v1`、flat な `runs` list）、
各 CSV/summary、`uniform_pressure.json`、repo 相対の SHA256SUMS を読む。
run item は `run`, `phase_id`, `state`, `grid`, `forces_csv`, `summary_json`。
欠け run は INCOMPLETE。不明値・hash 不一致は例外。既存 gate.json は入力を読む前に拒否する。
詳細と未実行の GPU manifest template は evidence の README にある。

## テスト（コマンドと結果。全体 pytest の失敗集合が base と同一か）

- `julia --project=julia/CFDSDFWaterLily -O0 scripts/force00_selftest.jl`：78/78 PASS。独立した fresh Julia 実行でも 78/78 PASS。
- `julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl <new-output>`：2 回が byte 同一、104 配置。SHA-256 `dab15c1c39ad1c0bb223115d1eed357cdf0f1ebaa861935abca3369d94c1bb87`。
- 一様圧力の実行時間：wall 250.48 秒／193.41 秒、CPU user 79.29 秒／88.78 秒。数分で終了した。
- `julia --project=julia/CFDSDFWaterLily scripts/force00_job_regression.jl <new-directory>`：13 samples、14 steps。元の 13 列、追加 cur 5 列、最終 u/u⁰/p/f/μ₀/μ₁/Δt が byte 同一。
- 元の CSV と先頭 13 列投影の SHA-256 はともに `c48e92cbd81c144df121087f82c2d364870390399238655773ec034ead7df78a`。
- `.venv/bin/python -m pytest -q tests/test_force00_gate.py tests/test_force00_uniform_inputs.py`：**35 passed in 23.04s**。内訳は gate 33、入力 2。
- `.venv/bin/python -m compileall src tests`、Python scripts の py_compile、`git diff --check`：PASS。
- **全体 pytest の失敗集合の一致は未達・未確認。** Forces の追加だけで既存 source-pin テストが FAIL、独立した未変更 base では同じテストが PASS。最初の baseline 実行は途中で編集後の source を読んだため比較証拠から除外し、旧 full-suite 試行も中断した。clean base の独立コピーでの全体実行は、要件衝突への回答待ちで中断（exit 2、1,348 passed／24 skipped、1590.10 秒）。局所 PASS や中断時点の件数を全体 PASS として扱っていない。

一様圧力での最大力ベクトル norm（solver units、CPU Float64）：

| fixture | R_cur | R_nds | R_cv |
| --- | ---: | ---: | ---: |
| v18 flow_24（40 配置） | 20.0320 | 1.161e-13 | 0 |
| v18 flow_32（40 配置） | 33.5221 | 1.839e-13 | 0 |
| sphere R=8（8 配置） | 0.237500 | 5.867e-14 | 0 |
| sphere R=16（8 配置） | 0.938703 | 1.558e-13 | 0 |
| sphere R=32（8 配置） | 0.447844 | 9.098e-13 | 0 |

R_nds は全配置で 1e-12 以下。C2 だけの独立な再計算と入力 provenance 検証も PASS。
R_cur は同じ C2 閉包閾値を満たさない。これは p=1 の読み出し残差であり、
解いた流れの親の力との差や過去の利得の変更を示す値ではない。

## 仕様からの逸脱と理由

- **file placement と pin の衝突が未解決。** 指定どおり Forces.jl に追加した現状では受け入れ条件を満たせない。提案パッチは新規ファイルへの分離であり、承認なしに適用していない。
- Julia 自己テストの cold-start「数秒」は未達。checkset の実測は約 69 秒と独立実行 160.9 秒で、JIT を含む。warm 実行秒数は確認していない。数秒と報告していない。
- literal な flow_32 job copy だけでは F1 flow_24 を走らせられないため、別 launcher を追加。copy 本体の solver/window/phase は変えていない。
- C4 は依頼本文と表の 15% を採用し、rev 0 末尾の 10% も診断値として報告する。仕様本文は変更していない。
- f32a のみでは k15/k16 がないため、実際の f32b を参照する。F1 も八つの U01 phase を捏造せず、U01 と U2 の明示した出典を使う。
- UNC-01 に camber_m19.7 の σ_d がないため、C5 は INCOMPLETE。FID σ や他 mode の値を転用せず、採用を NONE とする。
- U1 は FID V1 の登録済み 3 軸 32 shift と、次の四つの mirror pair の z-only 8 shift。U2 は追加 8 vector の全 3 成分を使う。球の空の遠方領域は CPU geometry-only 計算用に crop した。
- field は Float64、元の phi は Float32。U1 の面積は genesis の planform area をセル面積で割った値、U2 は πR²。0.64 m² の係数基準面積とは区別する。
- OpenCode Go MCP は存在せず、CLI は通常経路で log path のアクセスエラー、一時 XDG 経路で `Provider not found: opencode-go`。native worker に分担し、親が差分と結果を確認した。追加有料 API は利用していない。
- 元 worktree の Git metadata は書き込み禁止で index.lock を作れない。公開用の独立した一時 checkout を使い、元 worktree の Git metadata と unrelated files は変更しない。

## 未確認の仮定（実行して初めて分かることなど）

- GPU 配列での kernel compile、性能、F1/F2 の T4 byte 回帰、F1 の phase SD と符号・帯、F3 の差分は未確認。
- **issue #293 の組み込みと control volume の 7〜9% の差が、本プロジェクトの親でどうなるかは GPU 実行まで分からない。**
- box の 4 セル clearance は SDF の離散面サンプルによる検証。非距離 SDF に対する連続幾何の証明ではない。物理的に動く物体の momentum correction も今回の静的な親の適格化対象ではない。
- T4 の byte 参照は RTX 4070 Ti へ自動的には移らない。gate は今回の登録 T4 の identity を要求する。

## Claude／ユーザーへの提案する追記（authority と仕様は未編集）

- FORCE-00 rev 0 の C4 の 15%／10% を統一し、F1 の八つの phase と F2 の f32a/b 出典を明記する。
- C5 の estimator と mode を実在する登録 evidence に結び直す。UNC にない σ を推測で補わない。
- source pin を保存する Force00.jl の opt-in 配置を認める場合、WP4 の include 手順もインターフェースに追加する。
- CPU の個別 capability と、未実施の FORCE-00 全体／GPU adoption を別に記録する。自己テストの cold JIT 時間も実測として追記する。
- phase_plan、STATE、exploratory_index、登録・gate・spec の本文は本作業では改定していない。

## 次に要るもの（GPU 実行、ユーザーの判断）

1. Forces.jl の file placement と既存 source pin の優先順位の回答。推奨は用意した opt-in Force00.jl パッチ。
2. 決定した配置で必要な source-bound CPU capture を更新し、clean base と全体 pytest の失敗集合を比較する。
3. cold selftest の秒単位の起動時間を厳密な条件とする場合、その性能要件は残る。
4. user/Claude による C4/C5 と参照 matrix の整理、登録・freeze、F1〜F3 の GPU 実行。その後で one-shot gate を実行する。
