# WP2 FORCE-00 報告

## 状態

**DONE**

継続開始 HEAD は `21d1e8e7`、branch は `feat/gen01-w1-02-force00`。
最新の Amendment 2 を適用した。実装の配置決定待ちは解消済みで、
`src/` の directory pin と file pin を保持した。
commit・push・PR #84 の本文／ready 操作は Amendment 2 に従い Claude が
host で行う。今回、その Git／GitHub 変更は試していない。新しい PR、
一時 checkout、API blob、課金はない。HEAD は変更していない。

GPU F1〜F3 は未実施。ここでの DONE は CPU 実装の受け入れ条件に限る。
本番 `docs/evidence/force00_2026_11/` と `gate.json` は存在しない。
CPU fixture とソースレビューから、採用や物理 qualification は判断しない。

## 作ったもの（commit 対象の完全な一覧）

HEAD `21d1e8e7` からの変更・復元・新規 source/document は次のとおり。
機械可読の完全な stage 対象一覧は
`wp02_validation/final/commit_inventory.json` にも保存した。

- `julia/CFDSDFWaterLily/gen01/Force00.jl`：新規。元の未追跡 src/Force00.jl から移動。保存 μ₀ の nds、圧力・粘性、2D/3D CV、box 検証、3 読み出し。
- `julia/CFDSDFWaterLily/gen01/README.md`：新規。凍結 src 外の opt-in module の読み込み規則。
- `julia/CFDSDFWaterLily/src/Forces.jl`：復元。HEAD の FORCE-00 追加を除き、e3dcdf61 の bytes に戻した。
- `scripts/force00_gate.py`：変更。gen01 provenance、完全 cadence／endpoint／summary 検証。C1〜C5、write-once、採用規則。
- `scripts/force00_job_regression.jl`：変更。gen01 include／SHA 参照。元 job と新 job の実 measurement 関数で CPU byte 回帰。
- `scripts/force00_selftest.jl`：変更。gen01 opt-in。CPU の解析場・閉包・legacy bytes・solver 状態など 78 checks。
- `scripts/force00_uniform_pressure.jl`：変更。gen01 include／source provenance。決定的 U1/U2 JSON、104 配置、既存出力拒否。
- `scripts/waterlily_force00_job.jl`：変更。gen01 opt-in。登録 job のコピー、元 13 列を保持、3 読み出しの各 5 列と明示 box。
- `scripts/waterlily_force00_job.diff`：再生成。登録 job と新規 copy の正確な git diff --no-index --unified=0。
- `tests/test_force00_gate.py`：変更。44 tests。C1〜C5、採用、INCOMPLETE、書込拒否、cadence、不正入力、reports 非探索。
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_design.md`：更新。Amendment 2 を反映した現在の設計と検証計画。
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_report.md`：更新。本報告。

次の 3 ファイルは適用後に削除した。
`wp02_preserve_pins.proposed.diff` のみ HEAD で追跡済みだったため削除を commit する。
残る 2 件は継続開始時の未追跡ファイルで、削除後の Git diff には現れない。

- `docs/codex/gen01_w1_2026_11_06/reports/wp02_preserve_pins.proposed.diff`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_tree_pin.proposed.diff`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_complete_working_tree.patch`

既存 entrypoint が使う `scripts/force00_uniform_inputs.py`、
`scripts/waterlily_force00_dispatch.jl`、`tests/test_force00_uniform_inputs.py`
は前回 HEAD で commit 済みで、今回の追加 commit には差分がない。
その loader、Halton generator、dispatcher の既存実装を引き続き再利用する。

CPU 記録の移動元→移動先は次の全件。過去の raw JSON/CSV/log と旧 manifest
は bytes を保持して移動し、旧 path・旧失敗・旧環境は historical として
`wp02_validation/README.md` に明記した。追跡済みの旧 path の削除と新 path の追加を
同じ host commit に含める。Amendment 1 の未追跡記録もすべて移動先を追加する。

| 移動元 | 移動先 |
| --- | --- |
| `docs/evidence/force00_2026_11/README.md` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/README.attempt1.md` |
| `docs/evidence/force00_2026_11/SHA256SUMS` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/SHA256SUMS.attempt1` |
| `docs/evidence/force00_2026_11/amendment1/README.md` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/README.md` |
| `docs/evidence/force00_2026_11/amendment1/SHA256SUMS` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/SHA256SUMS` |
| `docs/evidence/force00_2026_11/amendment1/cpu_job_regression/force00/flow_16.forces.csv` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/cpu_job_regression/force00/flow_16.forces.csv` |
| `docs/evidence/force00_2026_11/amendment1/cpu_job_regression/force00/flow_16.summary.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/cpu_job_regression/force00/flow_16.summary.json` |
| `docs/evidence/force00_2026_11/amendment1/cpu_job_regression/force00.original_columns.csv` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/cpu_job_regression/force00.original_columns.csv` |
| `docs/evidence/force00_2026_11/amendment1/cpu_job_regression/registered/flow_16.forces.csv` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/cpu_job_regression/registered/flow_16.forces.csv` |
| `docs/evidence/force00_2026_11/amendment1/cpu_job_regression/registered/flow_16.summary.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/cpu_job_regression/registered/flow_16.summary.json` |
| `docs/evidence/force00_2026_11/amendment1/cpu_job_regression/regression.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/cpu_job_regression/regression.json` |
| `docs/evidence/force00_2026_11/amendment1/uniform_pressure.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/uniform_pressure.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/aborted-full-base-mlx.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/aborted-full-base-mlx.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/aborted-full-feature-mlx.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/aborted-full-feature-mlx.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/closure_check.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/closure_check.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/compileall-cpu.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/compileall-cpu.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/compileall.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/compileall.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/cpu_environment.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/cpu_environment.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/cpu_log_archive.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/cpu_log_archive.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/cpu_validation.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/cpu_validation.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/diagnostic-tree-pin.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/diagnostic-tree-pin.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/final_review.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/final_review.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/focused.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/focused.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/full-base.junit.xml.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/full-base.junit.xml.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/full-base.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/full-base.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/full-feature.junit.xml.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/full-feature.junit.xml.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/full-feature.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/full-feature.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/full_base.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/full_base.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/full_suite_comparison.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/full_suite_comparison.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/job-regression.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/job-regression.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/pin.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/pin.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/publication_boundary.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/publication_boundary.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/review.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/review.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/selftest.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/selftest.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/source_pin_preservation.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/source_pin_preservation.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/tree_pin_conflict.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/tree_pin_conflict.json` |
| `docs/evidence/force00_2026_11/amendment1/validation/uniform-run1.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/uniform-run1.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/uniform-run2.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/uniform-run2.log.gz` |
| `docs/evidence/force00_2026_11/amendment1/validation/uniform_determinism.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/amendment1/validation/uniform_determinism.json` |
| `docs/evidence/force00_2026_11/cpu_job_regression/force00/flow_16.forces.csv` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/cpu_job_regression/force00/flow_16.forces.csv` |
| `docs/evidence/force00_2026_11/cpu_job_regression/force00/flow_16.summary.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/cpu_job_regression/force00/flow_16.summary.json` |
| `docs/evidence/force00_2026_11/cpu_job_regression/force00.original_columns.csv` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/cpu_job_regression/force00.original_columns.csv` |
| `docs/evidence/force00_2026_11/cpu_job_regression/registered/flow_16.forces.csv` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/cpu_job_regression/registered/flow_16.forces.csv` |
| `docs/evidence/force00_2026_11/cpu_job_regression/registered/flow_16.summary.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/cpu_job_regression/registered/flow_16.summary.json` |
| `docs/evidence/force00_2026_11/cpu_job_regression/regression.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/cpu_job_regression/regression.json` |
| `docs/evidence/force00_2026_11/force00_runs.example.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/force00_runs.example.json` |
| `docs/evidence/force00_2026_11/uniform_pressure.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/uniform_pressure.json` |
| `docs/evidence/force00_2026_11/validation/compileall.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/compileall.log.gz` |
| `docs/evidence/force00_2026_11/validation/focused-tests.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/focused-tests.log.gz` |
| `docs/evidence/force00_2026_11/validation/gate-tests.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/gate-tests.log.gz` |
| `docs/evidence/force00_2026_11/validation/interrupted-full-early.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/interrupted-full-early.log.gz` |
| `docs/evidence/force00_2026_11/validation/interrupted-full-review.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/interrupted-full-review.log.gz` |
| `docs/evidence/force00_2026_11/validation/interrupted-inplace-baseline.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/interrupted-inplace-baseline.log.gz` |
| `docs/evidence/force00_2026_11/validation/interrupted-isolated-base.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/interrupted-isolated-base.log.gz` |
| `docs/evidence/force00_2026_11/validation/log_archive.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/log_archive.json` |
| `docs/evidence/force00_2026_11/validation/review.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/review.json` |
| `docs/evidence/force00_2026_11/validation/selftest.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/selftest.log.gz` |
| `docs/evidence/force00_2026_11/validation/source-pin-base.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/source-pin-base.log.gz` |
| `docs/evidence/force00_2026_11/validation/source-pin-current.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/source-pin-current.log.gz` |
| `docs/evidence/force00_2026_11/validation/source_pin_conflict.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/source_pin_conflict.json` |
| `docs/evidence/force00_2026_11/validation/uniform-run1.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/uniform-run1.log.gz` |
| `docs/evidence/force00_2026_11/validation/uniform-run2.log.gz` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/uniform-run2.log.gz` |
| `docs/evidence/force00_2026_11/validation/uniform_determinism.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/uniform_determinism.json` |
| `docs/evidence/force00_2026_11/validation/validation.json` | `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/validation/validation.json` |

移動以外の新規 CPU 記録・索引は次の全件。raw log／JUnit の gzip は内容を変えず、
raw と gzip 両方の SHA を `final/log_archive.json` に保存する。

- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/README.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/SHA256SUMS`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/canonical_input_absence.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/closure_check.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/commit_inventory.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/compileall-execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/compileall.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/cpu_job_regression/force00.original_columns.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/cpu_job_regression/force00/flow_16.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/cpu_job_regression/force00/flow_16.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/cpu_job_regression/registered/flow_16.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/cpu_job_regression/registered/flow_16.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/cpu_job_regression/regression.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/final_sanity.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/focused_checks.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/full-pytest-execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/full-pytest.junit.xml.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/full-pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/full_suite_comparison.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/job-regression-execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/job-regression.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/log_archive.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/relocation_verification.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/selftest-execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/selftest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/source_preservation.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/source_review.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/uniform-a.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/uniform-b.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/uniform_determinism.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/uniform_pressure-repeat.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/final/uniform_pressure.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp02_validation/relocation.json`

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

既存 module は変更せず、caller が一度だけ明示的に読み込む。

```julia
Base.include(CFDSDFWaterLily,
    joinpath(repo_root, "julia", "CFDSDFWaterLily", "gen01", "Force00.jl"))
CFDSDFWaterLily.nds_telescoping(sim)
CFDSDFWaterLily.pressure_force_nds(sim; box=nothing)
CFDSDFWaterLily.viscous_force_nds(sim; box=nothing)
CFDSDFWaterLily.force_on_body_nds(sim; box=nothing)
CFDSDFWaterLily.validate_force_box(sim, box; body=candidate)
CFDSDFWaterLily.control_volume_terms(sim, box)
CFDSDFWaterLily.control_volume_force(sim, box)
CFDSDFWaterLily.force_readouts(sim, box; body=candidate)
```

最後の関数は `(cur=…, nds=…, cv=…)` の物体力。既存規約どおり
`cur = -WaterLily.total_force(sim)`、drag = +Fx、downforce = -Fz。
候補＋地面の場では `body=candidate` を渡す。`box` は圧力セルの inclusive な
`UnitRange` の tuple。物理面は `first(range)-2` と `last(range)-1`、
領域から 2 セル・scene から sampled SDF で 4 セル以上離し、候補の全 support を囲む。
μ₀ 自体を変えず Float64 にしてから差を取り、CV も Float64 の和を使う。
`flow.f` は例外時も復元する。GPU 配列は `@loop` と backend reduction に対応する書き方だが、
GPU compile／実行の確認は今回行っていない。

`waterlily_force00_job.jl <phi.raw> <output_dir>` は
`FORCE00_CV_BOX='lo:hi,lo:hi,lo:hi'` を必須とし、元 13 CSV 列の後ろに
cur／nds／cv の `(fx,fy,fz,drag,downforce)_solver` を追加する。
元の cadence8、[80,120] endpoint-clipped time-weighted window、phase の式は保持する。
F1 flow24 の選択は追加 dispatcher の `FORCE00_CASE=flow_24|flow_32` で行い、
case inventory と単一 predicate 以外は変更しない。

`force00_uniform_pressure.jl [new-output.json]` は既存 v18 loader／raw phi と
GridSDF/Candidate-C を使い、FID 登録 32 個＋次の 4 mirror pairs の z-only 8 個を読む。
親は 2 格子で 80 配置、W2a 解析球は R=8/16/32 の各 8 配置。
流れを解かず `p=1, u=u⁰=0`。JSON の cur／nds は圧力反作用積分、CV は物体力で、
どちらも正解は零。既存出力を拒否し、timestamp を出力しない。

`force00_gate.py --evidence-root <directory>` は直下の
`uniform_pressure.json`、`force00_runs.json`（schema `force00_runs_v1`）、
repository-relative `SHA256SUMS` とそこに列挙された run CSV／summary のみ読む。
reports を再帰探索しない。`gate.json` は排他的に一度だけ書く。
欠け run／欠け exact UNC sigma は INCOMPLETE。C4 は 15% を採用帯、10% を診断値とし、
完備した合格 readout は CV 優先、次に nds、なければ NONE。

## テスト（コマンド、結果、artifact、hash と evidence class）

環境は既存 `.venv -> /Users/sota/projects/FomulaTMU/CFD2026_09/.venv` のまま。
付け替え・一時 CPU 環境・依存追加・Julia Project/Manifest の変更はない。
Julia 1.12.6 / WaterLily 1.8.0、CPU Array、Julia 1 thread。
以下の CPU 結果は `wp02_validation/final/` に保存した。

| コマンド | 結果 |
| --- | --- |
| `julia --project=julia/CFDSDFWaterLily -O0 scripts/force00_selftest.jl` | 78/78 PASS、exit0、JIT 込み 29.47 秒 |
| `julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl <new-output.json>` を 2 回 | 104 配置、exit0、143.87 秒／118.65 秒。JSON は byte 同一 |
| `julia --project=julia/CFDSDFWaterLily scripts/force00_job_regression.jl <new-output-dir>` | PASS、exit0、80.65 秒。元 13 列、追加 cur、最終 flow 配列が byte 同一 |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_force00_gate.py tests/test_force00_uniform_inputs.py` | 46 PASS（gate44＋inputs2）、10.59 秒 |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_candidate_c_w2a_plan.py::test_candidate_c_w2a_source_manifest_and_criteria_hashes_resolve tests/test_grad_g2_diag5_prereg.py::test_driver_pins_agree_with_the_freeze` | 2 PASS、0.10 秒 |
| `.venv/bin/python -m compileall src tests` | exit0 |
| `.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` | **3528 passed / 74 skipped / 0 failed / 0 errors**、exit 0、1983.90 秒で完走。 |
| `git diff --check` | PASS（最終 receipt も確認） |

全体 pytest には結果記録だけの `--junitxml=…/full-pytest.junit.xml` を追加した。
Amendment 2 指定どおり Metal test file だけを ignore し、conftest や既存 test は変えていない。
base はユーザーが提供した host `e3dcdf61: 3482 passed / 74 skipped / 0 failed`。
今回 base worktree は作らず、旧 attempt の中断記録・一時環境の run は比較に使わない。
base の失敗 node 集合は `[]`（ユーザー提供 host 結果）、result の失敗 node 集合は `[]`。一致は `true`。

閉包の実測（solver units、p=1）。C2 の projected-area 閾値も nds／CV とも PASS。

| group | R_cur max norm | R_nds max norm | R_nds RMS norm | R_cv max norm |
| --- | ---: | ---: | ---: | ---: |
| U1_flow_24 | 20.0320202 | 1.16089254e-13 | 4.71162967e-14 | 0.0 |
| U1_flow_32 | 33.5220572 | 1.83924127e-13 | 9.42493204e-14 | 0.0 |
| U2_R8 | 0.237500217 | 5.86745516e-14 | 4.5154193e-14 | 0.0 |
| U2_R16 | 0.938702755 | 1.55837757e-13 | 1.13641584e-13 | 0.0 |
| U2_R32 | 0.447844478 | 9.09830202e-13 | 4.36817365e-13 | 0.0 |

全 104 配置の R_nds 最大は `9.0983020215858424e-13` ≤ `1e-12`。
一様場の CV はすべて厳密な零。自己テストは別途 off-grid 2D 円／3D 球、
Float32／Float64 moments、μ₀ band 内外、線形圧力の向き、線形速度の各 CV 項、
非零の二次速度粘性、legacy bytes、後続 solver の同一性も確認する。
issue #369 の円 8.5e-3／2.7e-3／2.9e-2、球 R16=0.29 は JSON に併記した。
配置が異なるため、この upstream 表の exact replay としては扱わない。

主要 hash:

- uniform JSON（72,963 bytes、2 回同じ SHA-256）：`058acdc88dce3602f995a7826b81603d186bf23c9dbc1b11ad778a4f4a65ca49`
- 元 job CSV と新 job の元 13 列の SHA-256：`c48e92cbd81c144df121087f82c2d364870390399238655773ec034ead7df78a`（両方同じ）
- gen01/Force00.jl：`84c58a6f029d2dd9705d95020151cec564c7141414cdcb2b3d06283fdf275927`
- 復元した Forces.jl：`0e5a6b9dae2a5a3044a9ed08162a42ceb9e5ea5fac41585e7a758184205adc8e`

`source_preservation.json` では **src 全 13 ファイルの集合と bytes が e3dcdf61 と同一**、
`git diff e3dcdf61 -- julia/CFDSDFWaterLily/src` が空と記録した。
Forces／module／Project／Manifest／登録 job／conftest の SHA も base と一致。
`waterlily_force00_job.diff` は実際の no-index diff と byte 同一。
元 job を編集していない。raw log と JUnit の所在・内容 hash は log_archive／SHA256SUMS、
移動一覧は relocation、完全な commit target は commit_inventory に記録してある。

独立レビューは native の numerical／gate／authority-pins の 3 役で行い、
修正必須の問題なし。親側は実ファイル・diff・hash・CPU 実行結果で照合した。
OpenCode Go MCP はなく、CLI は log 権限失敗後、隔離 XDG でも
`Provider not found: opencode-go`。Go 委譲済みとは扱っていない。
model routing と review の記録は `source_review.json`。

## 仕様からの逸脱と理由

- `Forces.jl` への追加、`src/Force00.jl`、module include は frozen file/directory pin を変えるため行わず、最新 Amendment 2 の `gen01/` と caller Base.include を適用した。
- CPU 記録は Amendment 2 指定の reports 配下。本番 evidence root は作らない。旧 manifest 内の path は historical として保持した。
- Julia の cold-process runtime は JIT 込みで報告した。Amendment 1/2 が cold JIT を数秒条件から除外している。
- 全体 pytest は host 提供 base と比較し、結果側で Metal file を ignore。既存 `.venv` の変更はない。
- F1 の 8 phase は U01 smoke k0・formal half と U2 k1..k6。F2 の k13/14 は f32a、k15/16 は f32b。登録 artifact の実在／hash に従う。
- exact `camber_m19.7` UNC sigma は登録 evidence にないため、C5 は INCOMPLETE。C4 は 15% 採用・10% 診断。ともにユーザー amendment の指定どおり。
- commit／push／PR 操作は host Claude に引き継ぐ。必要な作業ツリー変更と検証記録を残す。

## 未確認の仮定

GPU 配列向けの kernel compile／実行、T4 での F1/F2 C1 regression、
full-window mean、位相 SD、C4 の符号と帯、F3 対差分は未確認。
**#293 の「組み込みと control volume は 7〜9% ずれる」が本プロジェクトの親で
どうかは GPU F1〜F3 実行まで分からない。** CPU の短時間回帰から推定しない。

W2a 球は解析 branch の半径・SDF を使い、空の遠方領域を crop した geometry-only fixture。
W2a の solved-flow domain や upstream の同一配置を再現する証拠ではない。
box の SDF sampled clearance は非 metric SDF の連続幾何証明ではない。
exact UNC camber sigma の不足は C5 の既知の入力欠落であり、推測で埋めていない。

## Claude／ユーザーへの提案する追記

roadmap／STATE／exploratory_index／登録／gate／spec 本文は編集していない。
仕様 rev 0 の owner 側整理候補は、gen01 placement、C4 15%＋10% diagnostic、
F1/F2 の実 reference matrix、C5 sigma provenance の明記。
読み出し採用・qualification flag・凍結 study の再判定は GPU evidence と owner 判定を待つ。
将来の campaign freeze は `gen01/Force00.jl` を include closure に明示 pin する必要がある。
現 checkout の W1 README には gen01 追記が見当たらず、今回の直接の根拠は Amendment 2。
必要なら owner 側で共通 README を同期する。

## 次に要るもの

Claude が上の完全一覧を stage して既存 branch に commit／push し、既存 Draft PR #84 の
本文と ready 状態を今回の受け入れ結果に合わせて更新する。新しい PR は不要。
ユーザーが後で F1〜F3 を GPU で実行し、本番 evidence と SHA256SUMS を用意する。
C5 の exact sigma provenance が解決した後、one-shot gate を判定する。
この CPU タスクでは gate.json、GPU run、正式登録、採用は作成・実行していない。
