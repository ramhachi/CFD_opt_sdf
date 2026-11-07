# WP2 FORCE-00 報告 — Amendment 3

## 状態

**DONE — Amendment 3 の実装・CPU 受け入れ検証を完了。**

継続開始 HEAD は `afac79ed177f774965be07460b2b66bfc3bcf943`、branch は
`feat/gen01-w1-02-force00`。開始時の作業ツリーは clean だった。
ユーザーの Amendment 3 と、指定 review worktree の仕様 Amendment 1 を適用した。
commit・push・PR #84 の本文／ready 操作は、最新指示どおり Claude が host で行う。
今回 HEAD／GitHub は変更していない。

GPU F1〜F3 と本番 gate は実行していない。本番
`docs/evidence/force00_2026_11/` と `gate.json` は存在しない。
CPU 記録はすべて `wp02_validation/amendment3/` に置き、従来の
`wp02_validation/final/` は Amendment 2 の履歴として保持した。

## 作ったもの（commit 対象）

今回の変更は `afac79ed` からの差分。過去 attempt で済んだ移動・削除を
今回の作業として数え直していない。機械可読の完全な対象一覧は
`wp02_validation/amendment3/commit_inventory.json`、末尾に同じ全件を掲載する。

- 新規 `scripts/force00_boxes.py`、`docs/harness/force00_boxes.json`、`tests/test_force00_boxes.py`：phase 0 の親の実測 μ₀ support から各 grid の box を一度だけ作る。既存出力は拒否。
- 変更 `julia/CFDSDFWaterLily/gen01/Force00.jl`：暗黙 box を廃止し、`validate_force_box` に全法線面の厳密な `μ₀ == 1` を追加。
- 変更 `scripts/force00_selftest.jl`：線形圧力の summation-by-parts の大きさ、box／μ₀ の拒否検査、解いた D16・Re100 円柱の入れ子 box 診断を追加。
- 変更 `scripts/force00_uniform_inputs.py`、`scripts/force00_uniform_pressure.jl`：球半径の単一定義、登録 box、job／dispatcher の SHA、box 支援測定、全配置の境界 preflight。
- 変更 `scripts/waterlily_force00_job.jl`、`scripts/waterlily_force00_dispatch.jl`、`scripts/waterlily_force00_job.diff`、`scripts/force00_job_regression.jl`：登録 box、CPU 専用 env override、source SHA、timing／VRAM 非互換、FORCE-00 表記、回帰検証。
- 変更 `scripts/force00_gate.py`、`tests/test_force00_gate.py`：C5 を採用の阻害条件から除外、C1〜C4 不足時の書込拒否、F3 byte 回帰、box と source の結び付け、C4 境界許容。
- 変更 `wp02_design.md`、本報告、`wp02_validation/README.md`、`wp02_validation/SHA256SUMS`：最新の設計・再現手順・検証結果・完全な commit 一覧。
- 新規 `wp02_validation/amendment3/` の全記録：コマンド、exit code、wall time、raw log／JUnit の lossless gzip、CSV／summary、SHA、比較・レビュー記録。

今回の移動元→移動先、復元、削除は **なし**。`src/` は開始時から baseline と一致し、
そのまま保った。`Forces.jl`、module、Project／Manifest、登録 job、conftest、既存 evidence、
roadmap／STATE／登録／仕様本文は変更していない。

## インターフェース

凍結済み module を読み、caller 側から一度だけ opt in する。

```julia
Base.include(CFDSDFWaterLily,
    joinpath(repo_root, "julia", "CFDSDFWaterLily", "gen01", "Force00.jl"))
CFDSDFWaterLily.nds_telescoping(sim, box)
CFDSDFWaterLily.pressure_force_nds(sim; box)
CFDSDFWaterLily.viscous_force_nds(sim; box)
CFDSDFWaterLily.force_on_body_nds(sim; box)
CFDSDFWaterLily.validate_force_box(sim, box; body=candidate)
CFDSDFWaterLily.control_volume_terms(sim, box)
CFDSDFWaterLily.control_volume_force(sim, box)
CFDSDFWaterLily.force_readouts(sim, box; body=candidate)
```

`box=nothing` の既定経路はない。box は圧力セルの inclusive `UnitRange` tuple、
法線面の index は lower と upper+1、solver 座標は lower−2 と upper−1。
`validate_force_box` は 2 セルの domain inset、候補の全 support、scene-SDF の面上 4 セル、
保存 μ₀ の全法線面が厳密に 1 であることを検査する。静止する body／box は最初に検証し、
以後 `validate_box=false` で読む。`cur/nds/cv` は物体力、drag = +Fx、downforce = −Fz。
`cur = -WaterLily.total_force(sim)`、候補＋地面では従来どおり candidate だけを積分する。
Float64 の差と和、CV の `u⁰`／`Δt[end−1]`、`flow.f` の復元は保持した。

`scripts/force00_boxes.py` は CPU の `measure!` により親 phase 0 の Float32 μ₀ support を
求め、親 state／raw SHA とともに `docs/harness/force00_boxes.json` を排他的に生成した。
最大の domain-inset box を取り、地面を含めない下側 z 面だけ solver z=4 に置く。
親 support の法線面への最小距離は flow24 が 15 セル、flow32 が 21 セルで、要求の 5 セル以上。
登録ファイルが存在すれば、測定を開始する前に拒否する。

| grid | lower | upper | phase-0 μ₀ support lower | support upper |
| --- | --- | --- | --- | --- |
| flow_24 | [4,4,6] | [149,71,53] | [58,24,21] | [94,52,37] |
| flow_32 | [4,4,6] | [199,95,71] | [77,32,27] | [124,68,48] |

job はこの登録ファイルを grid ごとに読み、全位相と F3 の親／候補に同一 bounds を使う。
`FORCE00_CV_BOX` の override は `FORCE00_CPU_TEST=1` と実際の CPU Array の両方を要求。
`FORCE00_CASE=flow_24|flow_32` を指定する dispatcher は inventory と単一 predicate だけを変える。
登録 job の元 13 列、cadence 8、[80,120] の endpoint-clipped time-weighted window、位相の式は保持。
summary の `force00_source_sha256` は Force00／job／dispatcher の 3 path→SHA の mapping。
wall time／peak VRAM は追加読出しの費用を含むため、登録 job と比較できないと summary に明記した。
`W4_JOB_DONE` filename は harness 互換のため保持し、内容は実際の grid と FORCE-00 を表す。

`force00_uniform_pressure.jl [new-output.json]` は、既存 loader、SHA-verified FID 32 shifts、
同じ Halton 生成器の追加 z-only 8 shifts を使う。親は 2 grid×40、球は 3 radius×8、計 104 配置。
`p=1,u=u⁰=0` で流れを解かない。球の物理半径は pinned `Simulation.jl` の `SPHERE_RADIUS_M` を
Python 入力 reader から読み、gate の重複数値を除いた。U1／U2 とも明示 box を検証する。

`force00_gate.py --evidence-root <directory>` は列挙された artifact と repository-relative
SHA256SUMS だけを読む。CPU reports の subdir は探索しない。
C1〜C4 の入力不足、欠け file／reference／field は非零終了し、`gate.json` を書かない。
C1 の FAIL と別入力の不足が同時に起きても書込拒否。C5 の exact σ_d 不足だけなら
`criteria.C5.status=INCOMPLETE` を残し、C1〜C4 が通る readout の採用は可能。
両方 PASS は R_cv、片方 PASS はそれ、無ければ NONE。C4 は 15%＋1e-9 の相対境界許容、10% は診断。
C1 は F1／F2 に加え FID k7〜k10 の親／camber_m19.7 の 8 CSV も byte 回帰し、計 20 run を要求。
全 summary の bounds は登録値に一致し、3 source SHA は U1 の記録に一致しなければ拒否する。

## テスト（コマンド、結果、artifact、hash と evidence class）

既存 `.venv -> /Users/sota/projects/FomulaTMU/CFD2026_09/.venv` をそのまま使った。
Julia 1.12.6／WaterLily 1.8.0、CPU Array。依存追加、環境の付け替え、pin の変更はない。
Julia wall time は process start と JIT を含む。全体 pytest と同時実行した検証があるため、
これらの秒数を性能 benchmark として扱わない。cold JIT を「数秒」条件に含めない点は Amendment 1 に従う。

| command | result |
| --- | --- |
| `.venv/bin/python scripts/force00_boxes.py` | 登録成功。親 support、最大 box、combined scene の CPU preflight を検査。既存出力拒否もテスト済み |
| `julia --project=julia/CFDSDFWaterLily scripts/force00_selftest.jl` | 116/116 PASS、exit0、58.16 秒（JIT 込み） |
| `julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl <new-output.json>` ×2 | 両方 exit0、104 配置、54.28／46.18 秒。86,828 bytes が同一 |
| `julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/force00_job_regression.jl <new-output-dir>` | PASS、15.30 秒。13 samples、元 13 列／追加 cur／最終 flow 配列が byte 同一 |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_force00_gate.py tests/test_force00_boxes.py tests/test_force00_uniform_inputs.py` ＋ W2a／directory-pin の 2 tests | 100 PASS（gate86＋boxes10＋inputs2＋pins2）、21.18 秒 |
| `.venv/bin/python -m compileall src tests` | exit0 |
| `.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` | **3580 passed / 74 skipped / 0 failed / 0 errors**、exit0、1149.41 秒で完走 |
| `git diff --check`、`git diff e3dcdf61 -- julia/CFDSDFWaterLily/src`、job `.diff` の byte readback | PASS、src diff は空、添付 diff は fresh no-index diff と同一 |

全体 pytest に記録専用の `--junitxml=.../full-pytest.junit.xml` を追加した。
base は user 提供の完走済み host `e3dcdf61`：3482 passed／74 skipped／0 failed、失敗 node 集合 `[]`。
中断した過去実行や一時 CPU 環境は比較に使わない。結果側の失敗 node 集合も `[]`。両者の集合は同一（`true`）。
全体実行開始後、gate test の既存 decoy case に書込拒否の assertion だけを追加したため、
その最終 test body は上記 focused 100 PASS でも検証した。gate／数値／job 実装は開始後に変更していない。

U1／U2 の測定（solver units、p=1）：

| group | R_cur max norm | R_nds max norm | R_nds RMS norm | R_cv max norm |
| --- | ---: | ---: | ---: | ---: |
| U1 flow24 | 20.0320202 | 1.16089254e-13 | 4.71162967e-14 | 0.0 |
| U1 flow32 | 33.5220572 | 1.83924127e-13 | 9.42493204e-14 | 0.0 |
| U2 R8 | 0.237500217 | 5.86745516e-14 | 4.51541930e-14 | 0.0 |
| U2 R16 | 0.938702755 | 1.55837757e-13 | 1.13641584e-13 | 0.0 |
| U2 R32 | 0.447844478 | 9.09830202e-13 | 4.36817365e-13 | 0.0 |

R_nds の全配置最大は `9.098302021585842e-13` ≤ `1e-12`。
本番 validator で uniform provenance、登録 box と全 20 reference の SHA を直接照合し、
C2 の projected-area 閾値は nds／CV とも PASS。CV はこの静的な一様場では構成上零となるので、
この C2 だけから solved flow の妥当性は結論しない。issue #369 の表は JSON に併記し、
異なる off-grid fixture の記述的な比較として扱う。

解いた円柱は D16・Re100、1500 warm-up＋800 sampled steps、cadence8、時間重み付き平均。
R_cv mean drag は 12.8221663／12.8280682／12.8255013、box 間 spread 0.0460181%。
R_cur は 11.3992262、R_nds は 11.3965941。CV はこの fixture で cur より 12.48〜12.53% 大きい。
box1 と box3 の瞬時 lift 差 RMS は 0.2590345 で、平均力の box 非依存性とは区別した。
この診断に新しい合否閾値やプロジェクト親への転用はない。

主要 SHA-256：

- uniform JSON（2 回同じ）：`fc76ee6d3143d9aec9f385756be41b009002790a33fc04086ec780bf84ad369b`
- 元／projected CSV：`c48e92cbd81c144df121087f82c2d364870390399238655773ec034ead7df78a`
- Force00.jl：`4f3649a5710cb2a51fab1febf3feb3aa9aa38981c99a362965ad971a5b83e7f2`
- job：`3d98483dffc846b10f2e9920db9505342ef881fd70e0bcb33f66f7f459ccdb73`
- dispatcher：`e43fe90f6ebb932ab2e6f8649a6092d76dda2dc8d5311779d5bf0b68bc292a1a`
- 不変 Forces.jl：`0e5a6b9dae2a5a3044a9ed08162a42ceb9e5ea5fac41585e7a758184205adc8e`

src の全 13 ファイルの集合と bytes が e3dcdf61 と同一であることを
`source_preservation.json` に記録した。Julia numerical、gate、job と親の registry／uniform を
別 worker が相互に read-only review し、現登録値に対する must-fix は残っていない。
OpenCode MCP はなく、CLI は log 権限失敗、隔離 XDG で `Provider not found: opencode-go`。
Go への委譲済みとはせず、native worker と実 diff／出力で確認した。追加課金 API は使っていない。

## 仕様からの逸脱と理由

- 最新 Amendment 2／3 の `gen01/` と caller Base.include を継続し、frozen src は 1 byte も変えていない。
- `nds_telescoping(sim)` も Amendment 3 の box 必須化に合わせ `nds_telescoping(sim, box)` にした。
- 全体 test は最新指示の Metal file ignore と user 提供 host base を使用し、追加の base worktree は作らない。
- F1 は登録 artifact の U01 smoke k0／formal half＋U2 k1〜k6、F2 は f32a k13/14＋f32b k15/16。
- commit／push／PR 操作は Claude host に引き継ぐ。

## 未確認の仮定

**#293 の「組み込みと control volume は 7〜9% ずれる」が本プロジェクトの親でどうかは、
GPU F1〜F3 実行まで分からない。** 今回の円柱診断の約 12.5% を v18 の値として扱わない。
GPU kernel の compile／実行、T4 での C1 bytes、位相 SD、C4 の帯、F3 対差分、readout 採用は未確認。
F1〜F3 は仕様 Amendment 1 に従い Kaggle T4 の reference identity が必要。

CPU support は実測 Float32 μ₀ 配列だが、CPU GridSDF の map は Float64 で、GPU device_copy は
map 自体も Float32。GPU 幾何演算の bitwise replay とは主張しない。現登録は最小 15／21 セルの余裕を持ち、
本番も全法線面 μ₀＝1 と scene-SDF の preflight を必ず通す。
job の support 上側検査は generator の法線面 upper+1 より 1 セル保守的で、現登録の余裕では影響しない。
非 metric SDF の sampled clearance は連続幾何の証明ではない。

球は pinned W2a 解析半径を使い遠方を crop した geometry-only fixture。
W2a solved-flow domain／upstream の同一配置の再現、物理 qualification、grid convergence、
過去の SCREEN／FID／UNC 結論の変更を意味しない。

## Claude／ユーザーへの提案する追記

roadmap／STATE／exploratory_index／仕様本文は編集していない。
owner 側で指定 review worktree の仕様 Amendment 1 と共通 README の gen01 規則を統合するときに、
C5 非阻害、15%＋境界許容、登録 box、F3 C1、3 source SHA、T4 backend を整合させる。
将来の FORCE-00 campaign freeze では gen01 source、job、dispatcher、box registry、gate を明示 pin する。
正式登録・採用・qualification flag の判断は GPU evidence と owner に属する。

## 次に要るもの

Claude が下の完全一覧の意図したファイルだけを stage し、
既存 branch で commit／push、既存 PR #84 の本文／ready 状態を更新する。
ユーザーが後で F1〜F3 を実行して本番 artifact と SHA256SUMS を揃える。
C1〜C4 が完備した時だけ gate を一度書く。C5 の未登録 exact σ_d は採用を止めない。

## 完全な commit 対象一覧（afac79ed から）

移動／復元／削除はなし。次の **52 ファイル**を host で commit する。

- `docs/codex/gen01_w1_2026_11_06/reports/wp02_design.md`：変更
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_report.md`：変更
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/README.md`：変更
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/SHA256SUMS`：変更
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/README.md`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/SHA256SUMS`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/box-registration.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/closure_check.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/commit_inventory.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/compileall-execution.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/compileall.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cpu_job_regression.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cpu_job_regression/force00.original_columns.csv`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cpu_job_regression/force00/flow_16.forces.csv`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cpu_job_regression/force00/flow_16.summary.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cpu_job_regression/registered/flow_16.forces.csv`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cpu_job_regression/registered/flow_16.summary.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cpu_job_regression/regression.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/cylinder_box_diagnostic.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/final_sanity.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/focused-execution.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/focused.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/full-pytest-execution.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/full-pytest.junit.xml.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/full-pytest.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/full_suite_comparison.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/job_regression_readback.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/log_archive.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/selftest-execution.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/selftest.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/source_preservation.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/source_review.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/uniform-a-execution.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/uniform-a.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/uniform-b-execution.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/uniform-b.log.gz`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/uniform_determinism.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/uniform_pressure-repeat.json`：新規
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment3/uniform_pressure.json`：新規
- `docs/harness/force00_boxes.json`：新規
- `julia/CFDSDFWaterLily/gen01/Force00.jl`：変更
- `scripts/force00_boxes.py`：新規
- `scripts/force00_gate.py`：変更
- `scripts/force00_job_regression.jl`：変更
- `scripts/force00_selftest.jl`：変更
- `scripts/force00_uniform_inputs.py`：変更
- `scripts/force00_uniform_pressure.jl`：変更
- `scripts/waterlily_force00_dispatch.jl`：変更
- `scripts/waterlily_force00_job.diff`：変更
- `scripts/waterlily_force00_job.jl`：変更
- `tests/test_force00_boxes.py`：新規
- `tests/test_force00_gate.py`：変更
