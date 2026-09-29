# OpenFOAM 機能除去 中間報告 (interim)

作成日: 2026-09-29 / ブランチ: `chore/remove-openfoam` (base: `origin/codex/kaggle-batch-migration` = `aa2e9d5`)
復元元 tag: `archive/pre-openfoam-removal-2026-09-29` (= `aa2e9d5`)

この文書は事実のみを記す。**最終報告 (`openfoam_removal_result.md`) ではない。作業は途中で停止している。**

## 0. 現在のブランチ状態 (重要)

- **このコミットは壊れた中間状態である。テストは通らない。全 pytest は実行していない。**
- 実際に行ったこと: src / scripts / OpenFOAM 関連ディレクトリの `git rm` (ステップ1) と、テスト 1 ファイルの新規作成、examples 1 件の復元のみ。
- まだ行っていないこと:
  - `src/cfd_sdf/cli.py` の編集 (現在も削除済みモジュールを import しており、`import cfd_sdf.cli` は失敗する)
  - `src/cfd_sdf/research_cli.py` の `doctor` コマンド除去 (`runtime_diagnostics` を遅延 import しているため、他は動くが doctor は動かない)
  - 到達不能テストの削除 (84 ファイル、下記)
  - 部分的に残すテストの編集 (`test_campaign_assertions.py`, `test_fd_preregistration.py`, `test_research_cli.py`)
  - inventory スクリプトの hash 検証を git object 方式へ変更
  - 汎用 sidecar 整合性テストの新規作成
  - AGENTS.md / CI / pyproject / README / bootstrap の更新
  - `docs/issues/openfoam_removal_result.md` の作成
  - `compileall`、pytest、`cfd-sdf --help` の実行

## 1. 実際に削除済みのもの (ステップ1、staged -> このコミットに含む)

`git diff --cached --shortstat`: 219 files changed, 75238 deletions (+ 新規 `tests/test_geometry_pipeline.py` と本メモ)。

| 対象 | 内容 |
|---|---|
| `src/cfd_sdf/*.py` (トップレベル) | 下記「残すもの」以外すべて。約 70 モジュール |
| `scripts/` | Kaggle/WaterLily/SDF-native/inventory/bootstrap 系以外すべて (pq*, stage_*, run_stage_v*, register_stage_*, audit_*, build_*, p0_*, rejudge_*, run_df2_*, *.ps1 の demo / porous 系) |
| `openfoam_extensions/`, `openfoam_utils/` | 11 ファイル (C++ 拡張と Make) |
| `examples/fixed_grid_backend_spike/` | OpenFOAM テンプレート case |
| `docs/evidence/**` | **無変更 (削除・変更なし)** |

削除済みモジュール (src): adjoint, adjoint_calibration, adjoint_topology, analytic_candidate_shapes, cfd, convergence_qualification, cross_fidelity_ranking, density_optimizer, design_state, design_transform, design_transform_declaration, evidence_audit, execution, extraction_qualification, extraction_sweep, fixed_grid_artifacts / backend / canonical_state_injection / connectivity / contract / gradient_gate / optimizer / primal / sensitivity, gradient_check, handoff, independent_verification, nonlinear_acceptance, openfoam (および openfoam_blockmesh_grid / canonical_field_transfer / canonical_state_transfer / case_renderer / cell_order_derivation / evidence / field_reconstruction / mass_imbalance / native_artifacts / oracle / response_renderer / sensitivity), optimization, path_b_bracket, phase2_*, porous_force_validation, preflight_v2, preflight_v4_core, problem_spec_compiler, projected_restoration, projection, robust_fields, runner, runtime_diagnostics, sensitivity, shape_feature_metrics, solver_case_compiler, solver_case_manifest, stage_s_* , stage_t_*, stage_v_*, topology, transfer_diagnostic。

一度削除して復元したもの: `examples/g2_openfoam_compile/project.yaml` (名前は OpenFOAM だが、`test_problem_spec.py` / `test_canonical_geometry_masks.py` / `test_canonical_grid_snapshot.py` が problem-spec fixture として使うため残す)。

追加したもの: `tests/test_geometry_pipeline.py` (4 tests, 単体で pass 確認済み: 4 passed)。旧 `tests/test_front_wing_pipeline.py` のうち OpenFOAM 非依存の幾何テスト (SDF build / 制約 / VTK 出力 / parametric) を退避したもの。旧ファイルは未削除。

## 2. import グラフの結果

手法: `ast` で `src/cfd_sdf`, `scripts`, `tests` の import を解析し (相対 import・`from cfd_sdf import x`・親パッケージを含む)、生きた経路のルートから到達可能集合を計算した。ツールは scratchpad の `graph.py` (リポジトリ外)。

- ルート: `design/`, `gradients/`, `oracles/`, `runtime/`, `fd_preregistration`, `problem_spec`, `grid`, `geometry_preflight`, `canonical_geometry_masks`, `canonical_grid_snapshot`, `candidate_constraints`。
- `infra/kaggle/**` が import する `cfd_sdf` は `design.sdf_state` と `gradients.directional_fd` のみ。`julia/` は Python の `cfd_sdf` を import しない。
- Kaggle/WaterLily 系 scripts が import する `cfd_sdf` は `design*`, `gradients*` のみ。どの Kaggle script も `fixed_grid_*` を使わない。
- ルートからの到達集合は `candidate_constraints`, `canonical_*`, `config`, `design*`, `fd_preregistration`, `geometry_preflight`, `gradients*`, `grid`, `openfoam_grid_transfer`, `oracles*`, `problem_spec`, `runtime*`。
- **切断が必要だった唯一の到達経路**: `research_cli` -> `runtime_diagnostics` -> `execution` (OpenFOAM/Docker/WSL)。`research doctor` コマンドを除去して切る方針 (未実施)。
- `openfoam_grid_transfer.py` は名前に反して numpy/scipy のみの汎用 Cartesian 重なり転送で、`problem_spec` (遅延 import) と `canonical_grid_snapshot` (トップレベル import) から到達される。OpenFOAM 非依存なので**残す**。

## 3. 残す / 消す判断 (ディレクトリ単位 + 判断が分かれたもの)

残す (src):
- `design/`, `gradients/`, `oracles/`, `runtime/`, `fd_preregistration`, `problem_spec`, `grid`, `geometry_preflight`, `canonical_geometry_masks`, `canonical_grid_snapshot`, `candidate_constraints`, `openfoam_grid_transfer`
- 判断が分かれたもの:
  - `canonical_objective.py`: 生きた経路から到達しないが**残す**。`scripts/register_sdf_native_architecture_2026_09.py --verify` が `canonical_semantics` として本ファイルの sha256 を固定しており、削除または変更すると `test_sdf_native_freeze.py` が落ちる。
  - `campaign_assertions.py`: 残す。Stage V / Stage S の evidence 整合テスト (`test_stage_v16_far_field_contracts`, `test_stage_v_domain_continuation`, `test_stage_s_baseline_v16` 等) が `ca.sha256_file` を sidecar 検証に使う。標準ライブラリのみで OpenFOAM 実行を含まない。
  - `config`, `constraints`, `validation`, `sdf`, `export_vtk`, `parametric`, `sample_geometry`: 残す。trimesh/numpy ベースの幾何サービスで OpenFOAM 非依存。`candidate_constraints -> config`、`sdf -> config, grid` の依存がある。CLI の `init` / `build-sdf` / `check-constraints` / `export-vtk` / `validate-outputs` / `write-parametric-wing` / `clean` が使う。
  - `lbm_reference`, `lbm_metal`, `lbm_benchmark`, `research_cli`: 残す。OpenFOAM 非依存の別研究経路 (D2Q9 LBM)。`research_cli` は `doctor` のみ除去予定。
  - `examples/generic_problem_v2/`, `examples/front_wing/`, `examples/g2_openfoam_compile/project.yaml`: 残す (テスト fixture)。

消す (src): 上記 1. の一覧。判断が分かれたもの:
  - `analytic_candidate_shapes`, `shape_feature_metrics`, `design_transform`, `robust_fields`, `evidence_audit`, `cross_fidelity_ranking`: numpy ベースで OpenFOAM 非依存だが、WP5/WP6/DF1/DF6 の Stage T/V 専用で生きた経路から到達不能のため削除した。**GEOM-01 が再利用する可能性は否定できない**。必要なら `git checkout archive/pre-openfoam-removal-2026-09-29 -- <path>` で復元できる。
  - `fixed_grid_artifacts`, `fixed_grid_contract`: 契約スキーマ実装だが消費者が OpenFOAM primal/sensitivity のみで、W3/W4/FD/Kaggle は使わないため削除した。`docs/fixed_grid_data_contract_v2.md` は無変更。
  - `design_state` (`DensityDesignState` 相当): Density/Brinkman 専用のため削除。
  - `runtime_diagnostics`: docker/OpenFOAM/WSL 確認が中心のため削除。
  - `handoff`, `problem_spec_compiler`, `independent_verification`, `transfer_diagnostic`: Stage T/S/V 専用のため削除。

scripts:
- 残す: `prepare_kaggle_*`, `register_kaggle_*`, `register_sdf_native_*`, `sdf_native_*`, `verify_kaggle_*`, `waterlily_*.jl`, `w0b_*`, `w1g_*`, `bootstrap.sh` / `bootstrap.ps1` / `bootstrap_wsl.sh`, `inventory_sdf_native_repo(.v2).py`, `colab_mcp_session.py`, `t4_backend_identity.py`, `run_waterlily_w2a_cpu_2026_09.py`
- `bootstrap.sh` は最後に `cfd-sdf research doctor` を案内している。doctor 除去後に文言修正が必要 (未実施)。
- 消す: 上記以外 (Stage T/S/V, pq*, OpenFOAM 実行系、P0 fixture 構築、porous 系 ps1/sh)。

## 4. 証跡 (hash) 拘束テストに関わるファイル

- `docs/evidence/repo_inventory_sdf_native_v1.json` / `_v2.json`: `src/**/*.py`, `scripts/**/*.py`, 関連 `tests/*.py` の sha256 を記録している (v1: 106 src + 109 scripts、v2: 107 src + 111 scripts)。
  - `scripts/inventory_sdf_native_repo_v2.py --verify` と `inventory_sdf_native_repo.py --verify` は **作業ツリーのライブファイル**を hash 照合する。
  - **除去前の `aa2e9d5` でも両方 fail する** (v2 は `src/cfd_sdf/design/__init__.py` が登録後に変更済み、v1 は既に `--verify` が "not reproducible")。どのテストもこれらを実行していない。
  - 登録時コミットの git object に対しては pass することを確認した: v1 は `5750da1` で 0 件不一致、v2 は `a35e687` で 0 件不一致。
  - 方針案: 両スクリプトの `verify()` を `git show <登録コミット>:<path>` の sha256 照合に変更する (v1=`5750da1`, v2=`a35e687`)。証跡の意味は変わらず、削除ファイルにも対応できる。**未実施**。
  - 注意: この方式は git 履歴が必要。CI の `actions/checkout` は既定 depth=1 のため、`fetch-depth: 0` への変更が要る (未実施)。
- `scripts/register_sdf_native_architecture_2026_09.py --verify` (`test_sdf_native_freeze.py` が実行): 固定するのは `design/sdf_state.py`, `oracles/base.py`, `gradients/base.py`, `runtime/fingerprint.py`, `canonical_objective.py`, 自身のスクリプト、handoff bundle docs、evidence JSON。**これらは今回すべて未変更で残しているので、変更しないこと。** ステップ1後に再実行はしていない。
- sidecar `.sha256` を持つ evidence を検証するテスト (Stage V/S 系): `campaign_assertions` が残るため、script/src を import しないものはそのまま動く見込み (未実行)。
- 削除した script/src に依存していたため削除予定の evidence 系テスト: `test_stage_s_v16_contract_audit`, `test_stage_v16_domain_boundary_contract`, `test_stage_s_reduced_basis_fd_v2`, `test_pq3_3b_campaign_v15/v16`, `test_pq3_3b_preflight_v5_lineage`, `test_pq3_3b_record_v6_outcome` など。代替として、`docs/evidence` の全 `*.json` と `.sha256` の一致を確認する汎用テストを 1 本追加する案 (未実施)。

## 5. 到達不能と判定したテスト (未削除、84 ファイル)

削除した src/script を参照する (名前検索による判定)。代表: `test_openfoam_*`, `test_fixed_grid_*`, `test_stage_s_*`, `test_stage_t_*`, `test_stage_v_*`, `test_phase2_*`, `test_pq3_*`, `test_solver_case_*`, `test_front_wing_pipeline` (幾何 4 tests を `test_geometry_pipeline.py` へ退避済み)。

部分編集で残す予定:
- `test_campaign_assertions.py`: 125 行目以降の runner テスト (`pq3_3b_campaign_2026_09.py` を読む) を削除し、純粋な assertion テストを残す。
- `test_fd_preregistration.py`: `transfer_diagnostic` を使う先頭 4 tests とその import を削除し、FD 登録テストを残す。
- `test_research_cli.py`: doctor テストを削除。
- `test_problem_spec_cli.py`, `test_canonical_geometry_masks.py`, `test_canonical_grid_snapshot.py`, `test_problem_spec.py`: 残す (前 2 つは CLI 編集後に要確認)。

## 6. `cli.py` の方針 (未実施)

2898 行、約 62 コマンド。残す予定: `init`, `validate-problem-spec`, `build-sdf`, `check-constraints`, `export-vtk`, `validate-outputs`, `write-parametric-wing`, `clean`, `preregister-fd-campaign`, `research` サブアプリ (doctor 除く)。それ以外 (OpenFOAM / fixed-grid / adjoint / density / stage-t / stage-v 系) と OpenFOAM 用ヘルパー関数は除去する。抽出は行番号範囲で行う予定 (`init` 135-153, `validate-problem-spec` 154-211, `build-sdf` 444-453, `check-constraints` 709-722, `export-vtk` 724-740, `validate-outputs` 742-753, `write-parametric-wing` 1778-1787, `clean` 2185-2192, `preregister-fd-campaign` 2353-2450, ヘルパー `_load_or_build` 2830-, `_default_project_yaml` 2839-)。

## 7. 未解決リスク

1. 他エージェントとの衝突: `design/` と `gradients/` は無変更。ただし他 worktree は `design/sdf_reinitialization.py` などを追加中で、`problem_spec`, `canonical_*`, `geometry_preflight` を import している。これらは残しているが、削除したモジュール (`shape_feature_metrics`, `design_transform`, `analytic_candidate_shapes`, `fixed_grid_*`) を GEOM-01 等が使う場合は復元が必要。
2. 中間コミットは import が壊れているため CI は落ちる。統合前に本作業の完了が必要。
3. inventory の live verify は元から fail している (上記)。git object 方式へ変える場合、CI の `fetch-depth: 0` が前提。
4. `README.md` (ルート) は OpenFOAM 手順が大半を占め、全面書き換えが必要 (未実施)。`AGENTS.md` の OpenFOAM/Stage V 手順の更新も未実施。
5. ベースライン失敗 37 件との比較は未実施。除去後のテスト数の増減も未計測。
6. claim 可否: 本作業は削除のみで、物理・性能に関する新しい claim を含まない。Stage V の独立検証能力は `archive/pre-openfoam-removal-2026-09-29` からの復元が前提。

## 8. 推奨する次の手順

1. 到達不能テスト 84 ファイルから上記 4 件を除いて `git rm`。部分編集 3 件を実施。
2. `cli.py` を残すコマンドのみに再構成し、`research_cli.py` から doctor を除去。
3. `python -m compileall src tests`、`cfd-sdf --help` を確認。
4. `register_sdf_native_architecture_2026_09.py --verify` と `test_sdf_native_freeze.py` を再実行。
5. inventory 2 スクリプトの verify を git object 方式にし、テストを追加。汎用 evidence sidecar テストを追加。
6. 全 pytest を実行し、ベースライン失敗 37 件との差分を確認 (合格条件: 新規失敗ゼロ、除去テストの消滅以外でテスト数が減らない)。
7. `AGENTS.md`, `.github/workflows/ci.yml` (`codex/kaggle-batch-migration` を追加、`fetch-depth: 0`)、`pyproject.toml`, `README.md`, `bootstrap.*`, `.gitignore` を更新。
8. `docs/issues/openfoam_removal_result.md` を作成。
