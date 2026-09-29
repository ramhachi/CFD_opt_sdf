# INFRA-01 (#17) / INFRA-02 (#19) 中間報告 (WIP)

ブランチ: `feat/issue-17-19-infra-preflight` (base: `origin/codex/kaggle-batch-migration` aa2e9d5)。
この文書は中断時点の事実のみを記す。テスト・pytest は一切実行していない。

## 完了したこと (実装のみ、未検証)

1. `scripts/waterlily_sdf_directional_fd_v16_job.jl` に環境変数 `FD_PREFLIGHT_STOP_BEFORE_SIM_STEP=1` の preflight モードを追加 (未設定時の本番挙動は不変のつもり)。
   - CPU のみのホスト (`CUDA.functional()` が false) では、各 run の `load_cpu_grid` (phi 読込、SHA、margin gate、GridSDF 構築) の直後に `FD_PREFLIGHT_CPU_BOUNDARY <run_id>` を出して return。
   - GPU ありの場合は `OwnedV16Run` 構築後、`sim_step!` の前に `FD_PREFLIGHT_PRE_SIM_STEP <run_id>` を出して return。
   - `main()` は `summary === nothing` なら continue、ループ後に `FD_PREFLIGHT_DONE runs=N` を出して return (matrix_summary.json / FD_JOB_DONE は書かない)。CPU ホストでは `vram_total` を 0 にする。
2. `infra/kaggle/kernel_sdf_directional_fd_v16/runner.py` の `run_main` に keyword 引数 `input_root`, `source_url`, `source_ref`, `preflight_julia` を追加 (既定値は従来と同じ)。
   - `preflight_julia` 指定時: `gpu_inventory` / `install_julia` / T4 smoke を skip し、指定 Julia で `Pkg.instantiate` とジョブを実行、ジョブ環境に `FD_PREFLIGHT_STOP_BEFORE_SIM_STEP=1` を設定。
   - ジョブ後、ログの stop マーカーが `criteria["run_order"]` と完全一致し、`FD_SOLVER_STEP_INVOKED` が無く、`FD_PREFLIGHT_DONE runs=33` があることを確認して `preflight_boundary_reached` ステージで return (post-job の verify_runner には到達しない)。
   - これらの変更で runner.py と job.jl の SHA は変わる。round 5 の criteria (kernel_runner / julia_job の登録 SHA) とは一致しなくなる。round 5 は変更しない。次 round では新 SHA で登録が必要。

## 未実施

- **#17 の preflight コマンド本体** (`scripts/preflight_kaggle_sdf_directional_fd_v16.py` を想定) は未作成。
- **#19 の supersession 機構** (`src/cfd_sdf/criteria_supersession.py` を想定) は未作成。
- 新規テスト・回帰テストは未作成。既存の `tests/test_kaggle_sdf_directional_fd_v16.py` も未実行 (runner.py / job.jl を変更したため、runner の SHA を固定している既存テストがあれば影響を受ける可能性があるが未確認)。
- `runner.py` の構文チェックも未実行。`python -m compileall` / Julia parse とも未確認。
- 全体 pytest 未実行。`docs/issues/17_19_result.md` 未作成。

## 実測できたこと

- ローカル Julia 1.12.6 で T4 project (`julia/CFDSDFWaterLilyT4`) の scratch コピーに対し `Pkg.instantiate()` + `using CUDA, WaterLily` が macOS で通った (初回 約 3 分、依存ダウンロード込み)。`CUDA.functional()` は false (WaterLilyCUDAExt の初期化で警告が出るが load は成功)。以降 `~/.julia` にキャッシュ済み。scratch コピーなので worktree の Project/Manifest は変更していない。
- macOS にはローカルの gitignore 済み `work/` fixture が無い。canonical state npz とステージ済み dataset は別 worktree にある (読み取り専用で参照するつもりだった):
  - `/Users/sota/.codex/worktrees/issue-16-fd02/CFD2026_09/work/kaggle_sdf_directional_fd_dataset_round5_remote_v5/` (6.8MB、Kaggle からダウンロードしたステージ済み dataset)
  - `/Users/sota/.codex/worktrees/kaggle-batch-migration/CFD2026_09/work/kaggle_w3_v16_dataset_registered_3c54f386/sdf_design_state.npz`
- venv Python は 3.12.13 / numpy 2.5.2 で、round 5 criteria の `direction_generation_runtime` と一致 (dataset 再ステージ可能)。
- round 1→5 の criteria 差分 (機械比較): 4→5 で変わったのは `criteria_round, criteria_sha256, inputs(criteria_draft, criteria_registrar, harness_tests, kernel_runner のみ), registered_at_utc, registered_source_commit, source_commit, source_input_sha256, source_tree_commit, supersedes` のみ。1→2 のみ `kernel_id, kernel_title` も変化 (slug 衝突修正)。`supersedes` の形は round ごとに固有 (registrar の `load_round{N}_*_binding` に round 別ハードコード)。
- 既存コードで既にカバー済みの failure class (新規実装不要の根拠):
  - scope leak: `test_runner_has_no_unbound_global_references_in_function_scopes` (symtable)
  - queue path 衝突: `test_run_queue_input_is_outside_the_julia_output_snapshot_path` (Python 側 `write_run_queue` のみ。Julia の `cp` までは走らない)
  - W4 result の tempdir 寿命: `test_loaded_w4_result_survives_source_temporary_directory_cleanup`
  - slug 衝突: 個別の round 2 binding と `test_round5_kernel_identity_...` (静的 JSON チェック)
  - 統合として一本で実行するコマンドは無かった (これが #17 の未充足部分)。

## 設計メモ (未実装、次の担当者向け)

### #17 preflight コマンド
- 本番 `runner.run_main(input_root=..., source_url=<local repo>, source_ref=<criteria.source_commit>, preflight_julia=<julia>)` を `runner.OUT` を tempdir に差し替えて呼ぶ。dataset は `--dataset-dir` (既存ステージ済み) か、`--state` から `prepare_kaggle_sdf_directional_fd_v16_dataset_2026_09.stage()` で tempdir に再ステージ。
- 静的チェックを併用: (a) kernel-metadata の slug 規則 (id != input dataset id、title の slug == id の末尾、dataset_sources == [dataset id])、(b) runner の未束縛グローバル検出 (symtable)、(c) runner が summary から読むキー / `recompute_metrics` のキーが Julia job の summary フィールドに含まれること (round 5 の `close_summary` 全 33 件 fail 型の schema 不整合検出)、(d) worktree の runner SHA が criteria の `kernel_runner` SHA と一致すること。
- Julia 実行の回帰テスト (queue が OUT 内にある場合に `cp` の ArgumentError になること) は、ダミー queue でも Julia job が `cp` まで到達することを利用できる見込み (phi SHA 検査は cp の後)。Julia 未導入 / T4 project 未 instantiate なら skip とする想定。
- 履歴 round (例: round 5) の criteria は登録済み job.jl に preflight フックが無いので、そのままではこの境界に到達できない。到達確認には、フックを含むコミットを source とする新 round の criteria が必要 (下記 preview で代用する想定)。

### #19 supersession
- 想定 API: `build_successor(predecessor_criteria(file+sidecar), terminal_diagnostic, round_number, read_source(path)->bytes, source_commit, motivations)`。
  - 同一でなければならない: `VARIABLE = {criteria_round, criteria_sha256, inputs, registered_at_utc, registered_source_commit, source_commit, source_input_sha256, source_tree_commit, supersedes}` 以外の全 top-level フィールド (thresholds / 測定行列 / slug / prerequisites / inventory を包括的に検出)。ただし predecessor の `kernel_id == input_dataset_id` (round 1 型の slug 衝突) の場合のみ kernel_id / kernel_title の変更を許可し、新 ID の妥当性を検査。
  - `inputs`: predecessor と同名・同 path のみ。sha が変わってよい名前は許可リスト (runner, julia_job, host_verifier, registrar, dataset_preparer, tests, draft, metadata, smoke, directional_fd_contract)。物理・prerequisite 系 (w3/w4 criteria/result、Julia project/manifest、V16 profile/grid/device の Julia src) の変更は拒否。変更された入力ごとに motivation (診断所見) の記述を必須にする。
  - predecessor 検証: ファイル SHA と sidecar、canonical `criteria_sha256`、diagnostic の `criteria_sha256` == predecessor ファイル SHA、`terminal_status` が `<kernel_id>/<version> has status "KernelWorkerStatus.(ERROR|COMPLETE)"`、`host_verification_passed is False`、全 `*_qualified` と `shape_update_allowed` が false、出力先 (round N+1) が未存在。
  - `supersedes` は round 5 と重なるキー名 (`criteria_path`, `criteria_file_sha256`, `criteria_canonical_sha256`, `kernel_id`, `kernel_version`, `dataset_version`, `solver_started`, `solver_step_invoked`, `solver_step_returned`, `measurement_thresholds_changed`, `host_verifier_error`, `failure_stage`) を診断から導出。
- round 4→5 の回帰: 入力 SHA を `git show a07bba2:<path>` (round 5 の source_commit、HEAD の祖先であることを確認済み) から再計算して生成し、round 5 の `supersedes` / `criteria_sha256` / `registered_at_utc` 以外が完全一致することを確認する想定。
- CLI は `--preview` (clean/pushed 検査を省略し scratch に書く) を持たせ、round 6 の登録はせずに preflight の到達確認に使う想定。

## 推奨される次の手順

1. runner.py / job.jl の変更を `python -m compileall` と `julia` の構文 parse で確認し、既存 FD テスト (`tests/test_kaggle_sdf_directional_fd_v16.py`, `tests/test_sdf_directional_fd_contract.py`) を実行して影響を確認する。
2. `criteria_supersession.py` と生成 CLI を実装し、round 4→5 回帰テストを追加。
3. preflight スクリプトを実装し、supersession の preview で作った仮 round 6 criteria に対してローカル Julia (CPU) で `FD_PREFLIGHT_CPU_BOUNDARY` x33 + `FD_PREFLIGHT_DONE` まで通ることを実測する。
4. 最後に全体 pytest を一度実行し、ベースライン失敗 37 件から新規失敗がないことを確認する。結果メモ `docs/issues/17_19_result.md` を作成。

## 検証状況

上記の実装 (job.jl / runner.py の差分) は、実行・構文確認・テストのいずれも未実施。動作は未確認として扱うこと。
