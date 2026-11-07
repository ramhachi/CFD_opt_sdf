# WP1：LOCAL-GPU-01 報告

## 状態

**BLOCKED — 実装前の契約確認で停止。**
登録済み runner / 既存 verifier の T4 専用契約と、RTX 4070 Ti を無改変の経路で通す要求が両立しない。
[00_README.md](../00_README.md) の「仕様が矛盾している」場合は推測で埋めず停止する規則に従った。
GPU・Kaggle の実行、gate の凍結・登録・判定は行っていない。

## 作ったもの（パス、1 行ずつ）

- `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_design.md`: source の根拠、停止理由、再開に必要な設計判断。
- `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_validation.json`: CPU probe、source SHA-256、実行コマンド・結果。
- `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_report.md`: この報告。

要求された runtime / gate / bench / checkpoint / 新規テストは未作成。既存ファイルは編集していない。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

提供済みの新規 API / CLI はない。WP4 向けの `save_checkpoint(path, sim, step, rows)` / `load_checkpoint(path)` も未実装。
返り値・復元方法を確定したものとして依存させないこと。
出力パス方式は既存の `CAMPAIGN_WORK_ROOT` を使う案 (a) が可能と確認したが、GPU identity の制約は解決しない。

## テスト（コマンドと結果。全体 pytest の失敗集合が base と同一か）

- `.venv/bin/python` の CPU probe: 既存 `select_worker_gpu` は合成 T4 を受理し、合成 RTX 4070 Ti を `ValueError: every visible worker GPU must be a Tesla T4` と拒否。TOML / AST の確認も成功。
- `.venv/bin/python -m compileall src tests`: exit 0。
- `.venv/bin/python -m pytest -q`: BLOCKED 確定後に中断、exit 2。中断時は **232 passed, 1 skipped, 1 warning / 297.92 s**。base の全体失敗集合は未確定で、実装後との同一性も未検証。
- `git diff --check` と新規記録の末尾空白検査: 成功。
- `tests/test_local_gpu.py`、stub runner、Mac 上の capture_lock、Julia checkpoint 自己テスト: 成果物未作成のため未実行。受け入れ条件は未達。

検証対象 HEAD は `e3dcdf6188df6079e197eb28f7fcba1451ec512d`。これは CPU / source 契約の調査結果で、実機 GPU の測定結果ではない。

## 仕様からの逸脱と理由

実装を始めず、停止記録だけを追加した。主な矛盾は次のとおり。

1. `scripts/grid01_gpu.py:25` が T4 以外を拒否し、既存 runner は Julia 起動前にこれを呼ぶ。`campaign_schema.py:72,341` と `campaign_verify.py:84–88` も T4 を要求するため、RTX の正しい identity では C2 を満たせない。
2. R1 の既存 campaign / runner / verifier は T4 の `first_state_csv_sha256` との byte 一致を要求する。一方 LOCAL-GPU-01 は cross-GPU 差を記述扱いとする。RTX で実際に byte が異なるかは測定していない。
3. 指定の `julia/CFDSDFWaterLily` は CUDA package を含まない。登録 runner は CUDA 6.3.1 を含む別の `julia/CFDSDFWaterLilyT4` を使う。
4. R3 の既存 flow_32 job に checkpoint / resume 呼出しがない。R5 はそれを必要とするが、WP1 は Julia job の編集を禁止する。

JLD2 は両 Manifest に package として存在せず、`WaterLilyJLD2Ext` は optional 宣言のみ。ただし Serialization の fallback は指示で許可されており、停止理由ではない。
長い handoff / roadmap / issue ledger の全歴史本文通読も停止時点では未完了。読了範囲は設計メモに明記した。
OpenCode Go は MCP が未公開、CLI はログファイルへのアクセスで失敗したため、親と独立 worker がローカルの読み取りと CPU 確認を行った。

## 未確認の仮定（実行して初めて分かること、PDF から読めなかった値など）

WSL2 の Julia / CUDA 起動・launch 遅延、NVML telemetry と reset の観測可否、dataset を含む bind mount の要否、
実機の lock 内容、R0 の native Windows 比較、R5 の GPU 再開一致、R6 の長時間安定性は未検証。
`CAMPAIGN_WORK_ROOT` が解決するのは確認した kernel の出力パスであり、全 dataset のパス動作を保証しない。

## Claude／ユーザーへの提案する追記（phase_plan、STATE、exploratory_index、仕様 rev 0 への修正点）

LOCAL-GPU-01 / WP1 の改訂として、既存 T4 の既定動作と凍結済み rendered kernel を保全しつつ、
RTX の実名 / UUID を検査する明示的 backend profile と新規 rendering / C2 検証を許可する範囲を指定する。
GPU 用 project は既存 `CFDSDFWaterLilyT4`、CPU 自己テストは `CFDSDFWaterLily` としてよいか確定する。
ローカル R1 の T4 byte gate を記述比較に置き、R5 用の新規 checkpoint 対応 job / campaign を許可するか、統合まで C5 を INCOMPLETE とするか決める。
roadmap / STATE / exploratory_index / 仕様本文への追記は行っていない。

## 次に要るもの（GPU 実行、Kaggle、ユーザーの判断）

上記の矛盾を解消した仕様と、必要な source 変更・新規 job の許可範囲。
それを受けて必読残部を確認し、TDD で道具・checkpoint・合成 gate テストを実装する。
実機 GPU の gate 実行は、道具の完成・レビュー・環境ロック後にユーザーが行う。

記録の commit・push・PR 作成も未完了。`git add` は共有 Git 管理領域の
`index.lock: Operation not permitted` で失敗した。3 件の記録はこの worktree に未追跡ファイルとして保存済み。

GitHub connector の tree 作成は実行環境の自動承認制御で拒否された。
返された理由は `MCP tool call requires approval, but approval policy is never`。
