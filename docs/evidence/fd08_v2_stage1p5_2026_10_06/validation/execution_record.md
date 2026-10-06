# Commands / artifacts / evidence class

Worktree `/Users/sota/.codex/worktrees/issue46-fd08v2-stage1p5-contract/CFD2026_09`、feature `exp/issue46-fd08v2-stage1p5-contract`、baseline integration `5e67022374335aebe5eb7aba5c4c41f90f708628`。使用Pythonは既存 `/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python`、Python3.12.13/NumPy2.5.2。OpenCodeはユーザーのpauseに従い未使用。ponytail原則に従い、既存NumPy/SciPy/runtimeを用い、任意精度はstdlib Decimalとした。

証拠区分はsolver-free numeric/contract design unregistered。条件付きC5検証、prompt/spec-only independent reviews、canonical幾何診断を区別する。qualificationは全6false。

実行順:

1. 出力なしの状態でnumeric規則を設計、独立numerical reviewerへuser request/specだけ渡す。reviewの誤差式訂正を反映しAST/static確認。
2. `python scripts/validate_fd08_v2_numeric_contract.py --freeze` →exit0、freeze SHA cd00beccc6a115baf34c6ed97e98fd206f1a11850c5ed23217dacf2e1eda4226。具体seed46、旧seedoverlap0、source/params/rules/runtimeを記録。
3. `python scripts/validate_fd08_v2_numeric_contract.py > validation/numeric_execution.log` →exit0。46未使用+20historical。stop_a/b/c=false。結果を見た凍結内容変更0。
4. `python -m pytest -q tests/test_fd08_v2_numeric_contract.py tests/test_fd08_v2_gate.py --junitxml=docs/evidence/fd08_v2_stage1p5_2026_10_06/validation/focused.xml` →39passed、exit0。rawをgzip保存。
5. 停止監査完了後だけB3–7設計開始。scientific reviewerにはuser requestのみ。analytic directions presetは計算前固定、canonicalNPZ/保護生成器だけでdiagnostics。`PYTHONPATH=src python scripts/design_fd08_v2_stage1p5_directions.py` →exit0。
6. `python scripts/design_fd08_v2_stage1p5_tables.py > docs/evidence/fd08_v2_stage1p5_2026_10_06/budget_and_ladder.json` →exit0。input-onlyconditioning/固定state費用、R5 raw不使用。
7. ignored canonical fixtureをbyte-identical既存NPZへのsymlinkで結合（新datasetではない）。`python -m compileall -q src tests` →exit0。新5scriptの `python -m py_compile ...` →exit0。
8. `python -m pytest -q --junitxml=docs/evidence/fd08_v2_stage1p5_2026_10_06/validation/full.xml` →exit1、37failed/1484passed/9skipped、1530tests、256.21s。pinnedfailure集合と比較 →new0/resolved0。JUnit/log原本gzipとraw SHAをvalidation_summaryへ記録。
9. `git diff --check`、freeze/oldSHA256SUMS/新SHA256SUMS/source hashes/リンク/flags/既存変更0/再生成設計JSONを最終監査する。Git統合の結果はIssue46のcheckpointへ記録する。

高精度のrawdecimalreference80/120とbinary64resultsはarithmetic_results.json.gz、quantityごとの誤差集計・全subset条件数・C5validity・precisiondelta stringsはarithmetic_comparison.json。raw vs12sig archivedoutput serializationは区別する。full-suite基準failurelistSHAは71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a。

既存コード/criteria/Stage1/R5証跡を変更しない。R5 force/result/analysis/dataset directionraw未読、solver/Kaggle操作/R6/formal登録未実施。

最終static reviewで、解析direction CLIに既存出力を拒否するIO guardを追加した。preset/定義hash/計算式/結果を変更せず、再現は新しい--output-dirで行う。numeric freeze対象ソースは変更0。既存出力への呼出しがexit2で拒否され、保存済みJSON/noteがbyte不変であることを確認した。
