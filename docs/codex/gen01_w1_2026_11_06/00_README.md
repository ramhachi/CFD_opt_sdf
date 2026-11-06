# Codex への指示パッケージ：GEN-01 W1 の実装（2026-11-06）

作成：Claude（Fable 5.1）。実装は Codex（`codex exec`）に全面委任する。計画・登録・判定は Claude とユーザーが行う。Codex は **コードとテストと記録**を作り、**凍結・Kaggle への push・課金・登録の判定・ロードマップの改定は行わない**。

このディレクトリの `01`〜`06` が作業パッケージ（WP）で、それぞれ独立した worktree と branch で並列に実行できる。各 WP のプロンプトは単独で完結するように書いてあるが、**どの WP も最初にこの README を読む**こと（規則はここに一度だけ書く）。

## 0. 起動のしかた（ユーザーが実行）

```bash
# 統合 branch を最新にし、WP ごとに worktree を切る（PR #81 統合後は codex/kaggle-batch-migration から。未統合なら plan/gen-system-2026-11-01 から）
cd /Users/sota/projects/FomulaTMU/CFD2026_09
git fetch origin
for wp in 01-local-gpu 02-force00 03-grad00 04-topo2d-waterlily 05-tr00-rans 06-geom-s1; do
  git worktree add "../CFD2026_09-wp-$wp" -b "feat/gen01-w1-$wp" origin/codex/kaggle-batch-migration
done
```

```bash
# 1 つの WP を回す（例：WP1）。トークンは制限しない。最終報告は -o のファイルに落ちる。
# worktree は共有の .git（主リポジトリの .git）に commit するので、その dir を書き込み可にする（--add-dir）。
# ~/.julia も Pkg.instantiate のために書き込み可にする。ネットワークは git push / gh / PDF 取得のために許可する。
W=/Users/sota/projects/FomulaTMU/CFD2026_09-wp-01-local-gpu
codex exec -C "$W" -s workspace-write -c 'approval_policy="never"' -c 'sandbox_workspace_write.network_access=true' \
  --add-dir /Users/sota/.julia --add-dir /Users/sota/projects/FomulaTMU/CFD2026_09/.git \
  -o ../codex_runs/wp01_last.md "$(cat "$W/docs/codex/gen01_w1_2026_11_06/01_local_gpu_01.md")" > ../codex_runs/wp01.log 2>&1
```

PR は `gh pr create` で作る（GitHub の MCP connector は承認が要るので使わない）。

並列に回してよい組：WP1・WP2・WP3・WP5・WP6 は互いに独立。WP4 は WP2（Forces.jl の新しい読み出し）と WP1（checkpoint モジュール）の **インターフェースだけ**に依存するので、WP2／WP1 と同時に始めてよいが、統合は WP2・WP1 の後にする。

## 1. 必ず読む文書（順に、全文）

1. `AGENTS.md` と、そこが指す 5 文書（`docs/opencode_handoff_2026_09.md`、`docs/README.md`、`docs/phase_plan.md`（特に 2026-10-16 の PROC-01 entry と 2026-11-01 の GEN-01 entry と addendum）、`docs/problem_register_2026_09.md`、`docs/problem_resolution_plan_2026_09.md`）。
2. `docs/STATE.md`、`docs/git_branching_strategy.md`。
3. `docs/gen_system_plan_2026_11_01.md`（GEN-01 rev 3.1。主線は WaterLily、SDF はプリミティブ集合の union、勾配なし）。
4. WP ごとの仕様（各 WP のプロンプトに書く）。
5. `docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md`（WaterLily 1.8.0 の source の事実、Zhang & Zerihan の幾何、issue #369／#358／#293、WSL2）。

## 2. 全 WP 共通の規則（破ったら作業を止めて報告する）

**触ってはいけないもの。**
- 登録済み・凍結済みのファイル。目安：`docs/evidence/**` の既存ディレクトリ、`docs/harness/*.prerun_freeze.json*`、`tests/conftest.py` が hash で pin している source（`_PINNED_SOURCE_*`）、`scripts/waterlily_grad_ta1_2026_10_15.jl`、`scripts/quick_tie.jl`、`scripts/waterlily_lowdim02_flow32_job.jl`、`scripts/t20_case.py`、`scripts/t20_foam.py`、`scripts/fid01/*`、`scripts/screen01/*`、`infra/kaggle/kernel_*` の既存ディレクトリ、`julia/CFDSDFWaterLily/Project.toml`・`Manifest.toml`（WaterLily 1.8.0 の pin）。**既存ファイルを編集せず、新しいファイルを足す**のが原則。どうしても既存ファイルを変える必要があれば、理由を報告に書き、テスト（`pytest -q` 全体）が「baseline と同じ失敗集合」であることを示す。
- `docs/phase_plan.md`、`docs/STATE.md`、`docs/exploratory_index.md`、`docs/gen_system_plan_2026_11_01.md`、`docs/*registration*.md`、`docs/*gate*.md`、`docs/*spec*.md` の **本文**（これらは Claude とユーザーが書く。Codex は「提案する追記」を報告に書くだけ）。
- Kaggle（`kaggle kernels push` を含む一切）、クラウド、課金、GPU の長時間実行。**Codex が走らせてよいのは、ローカル CPU の短いテストとドライランだけ**（Julia の CPU モード、小さい格子、数分以内）。GPU が手元にあっても使わない（LOCAL-GPU-01 の gate の前なので）。
- `git push --force`、`git reset --hard`、他 branch の checkout、`git stash` の pop（AGENTS.md）。

**Julia の追加モジュールの置き場所（2026-11-06 追記）。** `julia/CFDSDFWaterLily/src` は `campaign_build.BASE_PINS` の directory pin で、歴史 freeze（DIAG5／GRID01／GRID02／LOWDIM／STEP01）がその hash を bind している。src/ にはファイルを足さず、GEN-01 の新しい Julia module は `julia/CFDSDFWaterLily/gen01/` に置き、job から `Base.include(CFDSDFWaterLily, …)` で読む。

**Python の追加モジュールの置き場所（2026-11-06 追記）。** `src/cfd_sdf/**/*.py` も `scripts/analyze_grid02.py`／`analyze_lowdim03.py` が現在の tree から列挙して凍結 closure に含まれることを要求するので、`src/cfd_sdf/` にファイルを足すと GRID-02 の検証が落ちる。GEN-01 の新しい Python パッケージは `src/cfd_gen/` に置く（`cfd_sdf` は import して使う）。`scripts/`・`tests/` の新規ファイルは問題ない。

**commit／push（2026-11-06 追記）。** Codex の sandbox は `.git` 配下を書けない（`--add-dir` でも不可）。Codex は commit・push・`/tmp` の clone 経由の push をせず、報告に commit すべきファイルの完全な一覧を書く。commit・push・PR 作成は Claude が host で行う。

**書き方。**
- 最小で動くものを書く（YAGNI）。既存の helper・パターン・型を再利用する（`src/cfd_harness/`、`src/cfd_sdf/`、`scripts/local_openfoam.py`、`scripts/harness.py`、`julia/CFDSDFWaterLily/src/`）。新しい依存は、標準ライブラリ・既存依存で書けないときだけ足し、`pyproject.toml` に理由をコメントで書く。
- 非自明なロジックには必ずテストを付ける（`tests/` の慣習に合わせる。合成データで決定的に）。Julia 側は `julia/CFDSDFWaterLily/test/` の慣習に合わせる（無ければ `scripts/*_selftest.jl` を置く）。
- fail-closed：欠けた入力、ハッシュ不一致、未知の値は例外で止める。黙って既定値にしない。
- 数値の契約（窓、位相、符号、単位）は既存の registered semantics に合わせる：力は `-(pressure + viscous)`、drag = +Fx、downforce = −Fz、窓は endpoint-clipped time-weighted mean、位相は JOB-02 の機構。
- macOS の注意：`sed -i ''`、`timeout` コマンドは無い、Python は `.venv/bin/python`、`kaggle` は触らない。

**手順（毎 WP 共通）。**
1. `git status`、`git diff`、`git log --oneline -20` を確認してから編集する（AGENTS.md）。
2. 最初に `docs/codex/gen01_w1_2026_11_06/reports/<wp>_design.md` に **設計メモ**（読んだ文書の要点、インターフェース、ファイル一覧、テスト計画、未確認の仮定）を書いてから実装する。
3. TDD で進める。各ステップで `.venv/bin/python -m pytest -q tests/<新規>` を回し、最後に全体：`.venv/bin/python -m compileall src tests`、`.venv/bin/python -m pytest -q`、`git diff --check`。全体の失敗集合が base と同一であること（base の失敗は最初に記録しておく）。
4. **自己レビュー**（別の視点で、チェックリスト：仕様の各項目に対応するコード・テスト・記録があるか、fail-closed か、既存の pin を壊していないか、ハードコードした数値に出典コメントがあるか、報告に未確認の仮定を列挙したか）。見つけた問題は直す。
5. 意図したファイルだけ `git add` して commit（`Co-Authored-By` は付けない。メッセージは英語、何をなぜ）。branch を push し、PR を **`gh pr create`** で `codex/kaggle-batch-migration` 向けに作る（本文は §3 の形式。GitHub の MCP connector は使わない）。**auto-merge は有効にしない。** worktree の `.git` は主リポジトリの `.git` を指すファイルなので、`index.lock` の書き込みが拒否されたら、それは sandbox の設定（`--add-dir` に主リポジトリの `.git` が無い）であり、作業は未追跡のまま残して報告に書く。
6. **最終報告**を `docs/codex/gen01_w1_2026_11_06/reports/<wp>_report.md` に書いて commit し、同じ内容を標準出力に出して終わる。

## 3. 報告の形式（PR 本文と `<wp>_report.md` に同じものを書く）

```
# <WP 名> 報告
## 状態
DONE / PARTIAL / BLOCKED（理由）
## 作ったもの（パス、1 行ずつ）
## インターフェース（他 WP が使う関数・CLI・ファイル形式）
## テスト（コマンドと結果。全体 pytest の失敗集合が base と同一か）
## 仕様からの逸脱と理由
## 未確認の仮定（実行して初めて分かること、PDF から読めなかった値など）
## Claude／ユーザーへの提案する追記（phase_plan、STATE、exploratory_index、仕様 rev 0 への修正点）
## 次に要るもの（GPU 実行、Kaggle、ユーザーの判断）
```

BLOCKED のときは、推測で埋めずに止める。PDF の値が読めない、外部にアクセスできない、仕様が矛盾している、のいずれもその旨を書いて終わる。
