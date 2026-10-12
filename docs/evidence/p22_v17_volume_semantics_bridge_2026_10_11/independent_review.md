# Independent review and root disposition — 2026-10-12

Reviewer: Claude Sonnet 5.5 (`claude-sonnet-5-5`), high effort, read-only file tools. Primary investigation: GPT-6 Astra High. Native Codex completed documentation, verification and integration after the primary worker reached its usage limit. The reviewer did not execute tests; root executed the reported assertions and test comparisons.

Final disposition: **approved to record/merge as INCONCLUSIVE after B1–B3 wording corrections**. Root applied the requested corrections before freezing classification:

- B1: removed current-success mapping language; stated same-STL SHA identity and Oct11 historical replay separately from the failed current replay.
- B2: replaced ambiguous “classification C” with CONTRACT_NONPORTABLE_ACROSS_LATTICE.
- B3: added `classification_rule_provenance.md`, citing both the unchanged frozen audit plan and the user request §10.D numerical implementation drift condition.
- Historical `source_geometry_replay.json` bytes remain unchanged; report/classification now explicitly identify it as historical and superseded for current reproducibility by Oct12 failed checks.
- Failure log frame text does not match the current script. No failure-time script hash is available. This limitation is disclosed; line text is not used as source identity evidence.
- `source_replay_saved_field_supplement.json` records current dependency versions and saved-field hard count (8272, 0.12925000000000003 m³). Historical environment equivalence and source-mapping cause remain unresolved.
- Proposal now refers to the frozen audit plan and remains contingent on reproducibility resolution and separate user approval.
- `validation.json`, the full pytest logs/XML and failure-set comparison are retained. SHA256SUMS is generated after this review and classification freeze.

No numerical threshold, tolerance, contract or parent changed. The three nonzero mapping differences remain a verification failure despite equal retained hard counts. No CFD/Kaggle/preregistration follows. There is no unresolved blocking finding for recording the failed investigation; the investigation itself remains INCONCLUSIVE.

The following is the reviewer’s final response, preserved verbatim (draft-file line numbers reflect the files read at review time):

# 最終独立レビュー（読み取り専用）

私はファイルの閲覧と検索だけを行い、コード・テスト・スクリプトは実行していません。pytest、NPZ の hash と count、履歴再生の結果は、すべて root の報告をそのまま引用しています。私自身は確認していません。

## 判定

**INCONCLUSIVE 調査記録として record/merge してよい（条件付き承認）。** 下記の B1〜B3 を文言修正してから凍結してください。いずれも分類や数値には影響しません。

- 分類は fail-closed の INCONCLUSIVE です。この判断は妥当です。
- `classification.json` では `source_mapping_replay_current_pass: false`、`trilinear_zero_set_identity_claimed: false`、`volume_limit_changed: false`、`parent_replaced: false`、`shape_update_allowed: false`、`selected_delta: null` となっています。
- CONTRACT_NONPORTABLE_ACROSS_LATTICE は、`conditional_retained_state_interpretation` というキーに限定されています。
- tolerance、契約、parent の変更は見当たりません。
- 連続体や収束を主張する文言も見当たりません（`continuum_convergence_claimed: false`）。

## 凍結前に直すべき点

**B1. 「replay が通った」と読める記述が `audit_report.md` に残っています。**
- 124 行目に「same-source replay」とあります。実際に確立しているのは、STL の SHA 一致による同一性だけです。
- 126 行目に「Verified same-source mapping … support」とあります。mapping の再現は Oct12 に失敗しています。
- 修正案: 「same-source SHA identity と Oct11 の replay（historical）」に書き換える。
- 同じ箇所の「retained-state arithmetic … supports」も、「mapping 再現が未確立である」旨を併記してください。

**B2. `audit_report.md` 117 行目の「classification C」は紛糾の元です。**
- 同じ文書で「C」は LOWDIM-03 parent の状態名でもあります。
- 修正案: CONTRACT_NONPORTABLE_ACROSS_LATTICE と明記する。
- 修正後、カテゴリとして C を確定させたと読める文は残りません。

**B3. 「predeclared numerical implementation drift rule」の出典が `audit_plan.md` にありません。**
- grep では `drift` が 0 件でした。
- plan にあるのは 52〜53 行目の「numerical consistency cannot be established」だけです。
- `audit_report.md`、`classification.json`、`source_replay_recheck_2026_10_12.json` は、この規則を predeclared と呼んでいます。
- 修正案: plan の該当行を引用する。user 指示由来であれば、その旨を記録する。

## 軽微な不整合

- **古い pass 記録に印がありません。**
  - `source_geometry_replay.json` は `source_replayed_now: true` と `phi_bitwise_equal: true` を持っています。日付も historical の印もありません。
  - 保存済みの中身は変えない前提で、`audit_report.md` と `classification.json` から「Oct11 の historical、Oct12 で superseded」と明示的に参照してください。
  - `check_source` は、この JSON を期待値として読み込みます（スクリプト 163 行目）。
- **失敗ログがスクリプトと対応しません。**
  - `source_replay_failure_2026_10_12.log` の frame は、現在のスクリプトの行番号とも、frame 名と引用テキストとも噛み合いません。
  - 例: `<module>` 174 行目に `output = canonical(replay())` とありますが、現在これは `main()` 内の 197 行目です。
  - 例外の発生行（現在の 157 行目の `raise`）も、ログには出ていません。
  - 実行中にスクリプトが編集されたと推測できますが、これは推測です。
  - 失敗時点のスクリプト SHA は記録がありません。それを追記するか、「ログの frame は現行ファイルと対応しない」と注記してください。
  - 「retained without replacement」という主張は保持できます。ただし、行番号での追跡はできません。
- **診断 replay の影響が未定量です。**
  - 差の 3 点は、retained と replay で大きさが同一（例: bits 844307039 と 2991790687、差は符号ビットのみ）で、符号だけが反転しています。値は約 1.2e-8 m で、表面上の点と区別できません。
  - `signed_distance` の符号は `trimesh.proximity.signed_distance`（`src/cfd_sdf/sdf.py:124`）が決めています。符号決定側に原因がある可能性は考えられますが、未検証です。
  - 保存済み replay 場の hard 体積と center 数が記録されていません。解決済みと主張しない限りで構いませんが、追加すれば影響範囲を狭められます（solver 不要）。
- **trimesh の依存バージョンが記録されていません。**
  - 記録されているのは `source_surface_volume_diagnostic.json` の `trimesh_version` 5.1.0 と、`source_replay_recheck` の Python / numpy / platform のみです。
  - `measure_inventory.json` に trimesh、embree、rtree の記載はありません。
  - Oct11 と Oct12 の環境差は、確認も排除もできません。
- **proposal の冒頭が「frozen 2026-10-11 audit」としています。**
  - 実際は draft です。
  - 「Proposed registration content」の見出しと命令形は、registration 推奨と誤読されやすい表現です。
  - 本文には contingent 注記がありますので、軽微な扱いです。
- **揃っていない成果物があります。** 閲覧した範囲では、`validation.json`（`audit_report.md` 141 行目で参照）、`independent_review.md`、`SHA256SUMS` がまだありません。root が作成予定なので、現時点ではブロッカーではありません。

## R1〜R3 の処遇（初回レビュー）

| 項目 | 処遇 |
|---|---|
| **R1**（8272 = 8×1034 の説明） | **解消。** `source_surface_volume_diagnostic.json` が、STL の符号付き体積 0.1292499984670429 m³ と v17 hard との差 1.53e-9（相対 1.19e-8）を記録しています。watertight かつ winding 一貫で、`constraint_authority: false` です。導出が別物であることも、連続体収束を主張しないことも明記されています。 |
| **R2**（登録時評価関数の同一性） | **解消。** `hard_evaluator_history.json` と `--check-history` が、登録 commit `a260a40c…` と現在の AST（docstring 除く）を比較します。範囲は hard の呼び出し連鎖に限定されており、ファイル全体の同一性は主張していません。 |
| **R3**（登録 JSON の hash と inventory の SHA 検証） | **解消。** スクリプト 76〜81 行目で inventory の source SHA と登録 JSON の SHA を検証します。さらに Q1 は `registration["measured"]` を実際に読んでいます。ad-hoc heredoc の限界は、`audit_report.md` に「standalone ではなくローカルセッション依存」と明記されています。 |

## 残る制約

- 現行環境で、v17 の source-mapping 再現は失敗しており、原因は未解決です。
- Oct11 の replay が bit 一致で成功した記録は、historical として残っています。
- 保存済みの A/B/C の状態に対する hard 体積と Q1 は、byte pinned です。これは root が実行した再計算に基づきます。
- 「v16 の limit が v17 に reference を保ったまま移せる」という説は、条件付きの解釈にとどまります。
- 全 pytest は、baseline が 48 failed / 2166 passed / 23 skipped、final が 48 failed / 2176 passed / 23 skipped です。`pytest_failure_comparison.json` では failure ID が同一で、`new_failures` は空です。これは root の実行結果です。
- 新規テスト 10 件の内訳は、私は確認していません。

## 推奨

B1〜B3 を直したうえで、INCONCLUSIVE の調査記録として record/merge して問題ありません。分類は C（CONTRACT_NONPORTABLE）に格上げしないでください。P22-v2 の proposal は、source-mapping の再現性が別途解決され、ユーザーの明示的な承認を得るまで、登録対象にしない扱いが適切です。
