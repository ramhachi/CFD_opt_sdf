# JOB-02 独立ソースレビュー（1 回、sonnet、2026-10-19、実行前）

対象: `git diff e24e3314` と新規ファイル（harness の run `name`、gate campaign、`scripts/job02_gate.py`、gate spec、prerun note、テスト）。レビュー側は 4 suite（105 件）を実行して pass。判定: **blocker なし**。
既定の挙動（名前なしの campaign）で run 名と state 名の取り違えはない。gate campaign の job env は、参照 4 run（OPT-01 v1 Stage B の a/b、GRID-02 の s24/s32）の env・Julia 1.12.6・pin と一致する（`inventory.json` の `job_env_common`、各 `run_identity.json` の pins で照合）。

| # | 重要度 | 指摘 | 対応 |
| --- | --- | --- | --- |
| 1 | should-fix | gate が読む CSV と、verify 済みの table の結び付きがない（別ディレクトリを渡すと verify していないバイトで PASS し得る） | gate が kernel ごとに `kernel_manifest_sha256` と output manifest の SHA を照合し、manifest の全ファイルの hash を再検査する。テストも追加 |
| 2 | — | env の照合（指摘なし） | 回帰テスト `test_the_gate_campaign_job_env_equals_the_historical_runs_env` を追加 |
| 3 | nit | hash できない `name`／`state` が `ValueError` ではなく `TypeError` になる | `validate_kernel` で str を要求。テスト追加 |
| 4 | nit | `.` と `..` を run 名として受け付ける | 拒否する。テスト追加（state 名にある同じ穴は既存の挙動なので今回は触らない） |
| 5 | nit | `--out` が既にあると traceback で exit 1（FAIL と区別できない） | 書き込みを try の中に入れ、exit 3 にする |
| 6 | nit | prerun note の `gate_freeze.json` の記述が、gate が検査する範囲より広い | note を修正（spec・gate script・freeze SHA の照合は記録時に手で行う。gate は table の source commit と freeze SHA を結果に写す） |
| 7 | nit | smoke は f24 の native run しか通さない | note に記載（`name`・shift・flow_32 の job を Kaggle で初めて通すのは formal） |
| 8 | nit | 参照 env を固定するテストがない | #2 のテストで対応 |
| 9 | nit | README の空行 | 修正 |
