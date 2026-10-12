# SRCMAP-01 POST-RUN 独立レビュー: **PASS**

分類 `SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC` は凍結済み優先順位と証拠に整合しており、過剰主張は見つかりませんでした。以下は文書上の修正項目で、分類・結論の変更は要りません。実行、新規ジオメトリ、マッピング、編集は一切していません。

## 検証結果

| 観点 | 結果 |
|---|---|
| 分類優先順位 | 凍結ファイルの `classification_precedence`（`prerun_freeze.json:3-9`）と `diagnose_srcmap01.py:307-313` の `classify()` が一致。同条件群が不一致のため `repeat_same=False` で第2規則に到達し、`environment_match` は評価されない。`run_srcmap01.py:48` の ENV 述語は未発火で、`environment_bundle_dependence_demonstrated=false`。 |
| run 選択なし | 凍結 21 ジョブ全件と E 局所解析が各 1 回。`execution_started.json` の存在チェックと `log.open('x')` で再実行を拒否する実装。ファイル更新時刻は approval → preflight → execution marker → 各 log の順。Pairwise は 23 件（現行 v17 の 7 観測が 21 ペア、v16 が 1、minimum が 1）で、選別なし。 |
| 原因主張 | 現行同条件 v17 の 10/21 ペアで符号が変わる（Float32/Float64 とも 4 ノード、最大 2.67e-8 m）。全 production run に `random_retry_draw` が 1 回あり、毎回異なる実 draw と PCG64 状態が記録されている。A1 の方向は draw−0.5 の単位化と手計算で一致。3 本の固定ベクトルで 3 ノードの符号が決定的に反転する（contains=False なら正、True なら負）。符号反転は 3 ノードで直接実証され、残りは同じ機構と整合する状況証拠、という報告書の範囲どおりで過不足なし。 |
| 機構の裏付け | 導入済み trimesh 5.1.0 の `proximity.py:259-292` が報告書の記述どおり。投影が三角形外ならレイ判定に回る。 |
| 履歴 UNKNOWN | `historical_runtime_audit.json` の `remaining_unknowns` と `classification.json` の `historical_cause_resolved=false` が一致。報告書 146-159 行は歴史的原因の解決を主張していない。 |
| chunk/order | 各条件は 1 観測で、エントロピーの影響を分離できていない。報告書 100-102 行は決定論的因果を主張していない。 |
| 個別依存の因果 | minimum の 2 run は互いに一致するが、現行は不安定。`dependency_localization=UNKNOWN`。固定が有効だとの主張もない。 |
| D_unsigned と署名付き参照 | D1〜D3 の unsigned Float32 は絶対値の参照と 0 ビット差。署名付き参照と比べた 10262 ビット（符号差 9764 + 符号付きゼロ 498）は報告書 88-90 行で意味差と明記済み。 |
| unsigned Float64 | 現行 v17 の全 19 ジョブで A1 と 0 ビット差。minimum 2 run は 8 ノードで差があり、最大 2.22e-16 m。独立チェッカーが 8 ビット差を再確認。 |
| 独立チェッカー | 21 ジョブ、315 件のハッシュ検査（21 + 21×14）、23 ペアを検証。主 helper を import せず、新規ジオメトリ問い合わせもしない。 |
| 検証ログ | ベースラインは 48 failed / 2176 passed / 23 skipped、最終は 48 / 2184 / 23。失敗 ID は 48 件で同一、新規 0、増加分 8 は追加テスト 8 件。`all_pass=false` を正直に記載。 |
| ゲート | 元の bridge は INCONCLUSIVE のまま。#51 はブロック、CFD 0、Kaggle 0、`selected_delta=null`。 |

## 修正項目（すべて非ブロッキング）

**P2**
1. `diagnostic_report.md:178`、`diagnostic_report.md:165-166`: 参照先の `validation.json`、`SHA256SUMS`、`independent_review_postrun.md` が現時点で存在しません。完了コミット前に生成するか、未生成なら記述を直してください。
2. `diagnostic_report.md:72`、`diagnostic_report.md:98` 付近: 有限回の限界が人間向け文書にありません。`classification.json:153` の `finite_run_limit` にしかない状態です。「v16 の 2 run 一致、B200000、C canonical、D1 の 0 差は観測した run の範囲に限る。決定論の証明ではない」を 1 文追加してください。
3. `phase_plan.md:7330-7331` と `problem_register_2026_09.md:1989`: 「both v16 controls were exact」に「2 run のみ」を添えてください。

**P3**
4. `diagnostic_report.md:113-114`: 「sends some near-edge points to ray containment」は不正確です。chunk 1 では 200000 点中 168435 点（約 84%）がレイ判定に回っています。「最近傍三角形の平面投影が三角形外の点」と書き、再試行の対象は 19 点だけだと補ってください。
5. `diagnostic_report.md:79-83`: 追加の根拠として、A1 の 19 点の再試行クエリが A 群の全差分ノードと B385385 の 10 差分ノード（座標から手で照合）を含むことを引用できます。`(55,20,26)` は 19 点の 18 番目で、固定ベクトルの介入は受けていません。新規測定は不要です。
6. `diagnostic_report.md:74`: D2 の 3930 は D1 と別アルゴリズム（全点を contains で符号付け、tol.merge 境界の扱いが異なる）による差で、同一条件群に入らず分類にも入らない、と 1 文足してください。`classification.json` の `D_fallback` が `fallback_invoked:false` となる理由（production の外側 fallback ではなく明示的な合成）も同時に書くと誤読を防げます。
7. `phase_plan.md:7325`、`problem_register_2026_09.md:1985`: 見出しに「現行環境」を付け、「歴史的原因は UNRESOLVED」を明記すると、歴史的原因が診断済みと読まれずに済みます。

## 残る限界

- Oct11/Oct12 の実環境・実行経路・外側 fallback・内側 Rtree 経路は UNKNOWN で、歴史的原因は未解決です。
- 現行の符号不安定は再現できましたが、歴史的 run が同じ経路だった証拠はありません。
- 因果の直接実証は 3 ノード × 3 ベクトルです。他ノードは整合する状況証拠です。
- chunk/order は 1 観測ずつで、エントロピーと交絡しています。
- minimum は 2 run だけで、依存パッケージ個別への帰属はできません。
- Float64 の参照は保存された Float32 の昇格値で、歴史的な cast 前の値はありません。
- 全テストスイートは 48 件失敗のままです（既存、増減なし）。
- 物理的に正しい内外ラベルの確認はしていません。

## Root disposition

Verdict accepted. All requested prose clarifications were applied: finite observations; current versus historical scope; general ray-route inputs and 19-point retry subset; explicit D2 semantics; completion artifacts generated before commit. No mapping, diagnostic-source, freeze or measured-output changes followed review.

Two numerical statements in the reviewer narrative require correction against saved data: there are 17 current-environment v17 jobs plus 2 minimum-environment v17 jobs, not 19 current jobs; production retry draw counts range from 1 to 3 by condition, rather than always 1. The canonical A runs each have one draw. These reviewer prose mistakes do not affect the checked classification or primary artifacts.

The frozen minimum inventory force-mesh prose label names the current loader method; load_semantics_analysis.json preserves exact source excerpts/hashes for the actual version-specific method. Actual loaded bytes remain verified. The old bridge manifest includes two living documents whose old hashes are verified at the parent; their new SRCMAP-only appendices have new hashes. protected_authority_check.json records this scope explicitly.
