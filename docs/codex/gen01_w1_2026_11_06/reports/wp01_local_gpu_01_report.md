# WP1：LOCAL-GPU-01 報告（Amendment 4）

## 状態

**DONE**。PR #88 の開始 commit `ab801695` に対する2回目の Opus source review と、review worktree の LOCAL-GPU-01 §11.7 Amendment 3 に従い、n1〜n5 を修正した。重点5ファイルは **197 passed / 0 failed / 0 errors**。GPU、Kaggle、実機 lock / gate は実行・生成していない。これは道具の実装完了であり、LOCAL-GPU-01 の環境 gate が PASS したという結果ではない。

commit・push・PR 更新は Amendment 4 指定の host Claude が担当する。Codex は git add / commit / push、別 clone 経由の push を行っていない。

## 作ったもの（host が commit する完全な一覧）

同じ worktree の `ab801695` に対する **変更8ファイル、新規11ファイル、復元0ファイル**。登録済み source / job / Manifest / evidence / 保護テストは今回の対象に含めていない。

- 変更 `scripts/local_gpu_gate.py`：C1/C5 の比較除外、C6 の成熟区間・telemetry・UUID provenance、CSV schema。
- 変更 `src/cfd_harness/backend_profiles.py`：比較時だけ除外する `WSL_INTEROP` の名前を宣言。
- 変更 `tests/test_local_gpu_gate.py`：n1〜n4 の合成回帰と実 collector の受け渡し検査。
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_design.md`：実装前に Amendment 4 の設計を追記。
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_report.md`：本報告と完全な commit 対象一覧。
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_local_gpu_01_validation.json`：今回の結果・SHA・保護範囲・履歴の区別。
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/full-pytest-result.json`：`finished_utc` → `written_utc` のみ。
- 変更 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment3_validation/source-stability.json`：`finished_utc` → `written_utc` のみ。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/tdd-before.txt`：修正前の回帰テスト出力。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/tdd-before.xml`：同 JUnit。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/tdd-before-result.json`：同コマンド・時刻・失敗 node・SHA。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/tdd-after.txt`：修正後の gate 回帰テスト出力。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/tdd-after.xml`：同 JUnit。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/tdd-after-result.json`：同コマンド・時刻・失敗 node・SHA。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/focused-pytest.txt`：重点5ファイルの出力。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/focused-pytest.xml`：同 JUnit。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/focused-pytest-result.json`：同コマンド・時刻・集計・失敗 node・SHA。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/compileall.txt`：compileall の出力。
- 新規 `docs/codex/gen01_w1_2026_11_06/reports/wp01_amendment4_validation/checks.json`：compileall / diff / 12 freeze / metadata 訂正 / source SHA / 独立 source review の記録。

n1：`filtered_environment` は wrapper / runner とも完全な snapshot を保持し、同一 run 内では完全一致を要求する。C1 の paired run、C5 の R3↔R5 と interrupted↔R5 の比較だけで `WSL_INTEROP` を除外する。`gate.json.excluded_identity_environment_variables` に `["WSL_INTEROP"]` を記録し、WSLENV / CUDA 等の非揮発な差は引き続き拒否する。

n2：active group の最初60秒以降に2サンプル以上ある区間だけで VRAM の5%規則を評価する。短い group は `vram_skipped_intervals` に run、開始、最終 sample 時刻、sample 数、成熟 sample 数、理由を残す。短い group 単独では INCOMPLETE にせず、各 repeat に少なくとも1つの評価対象区間を要求する。必須 telemetry の欠測は引き続き INCOMPLETE とする。

n3：必須の minute telemetry は memory.used / utilization.gpu / clocks.sm。power.draw / temperature.gpu は raw CSV と取得記録を残すだけで、欠測・不正値を C6 の判定に使わない。collector が残す field-labelled diagnostic も同じ区分で処理し、混在する必須項目の問題、一般的な取得失敗、reset は隠さない。NVML UUID が取れる sample は CUDA probe と一致させ、取れなければ同じ repeat の検証済み CUDA-probe UUID を使用する。`telemetry_identity` に UUID、probe SHA、NVML sample 数、fallback sample 番号、出典を記録する。repeat 外の sample に同一 run の fallback を捏造しない。device total の telemetry が全て欠ける場合は lock と照合済みの GPU 容量を VRAM 分母に用い、その由来を記録する。容量自体が不明なら評価不能とする。

n4：watchdog CSV は列名の set equality と重複拒否を要求する。列順の変更は許可する。error / driver_reset の欠落、未知列、重複列は FAIL。

n5：前回 full-pytest と source-stability の記録は日時の値を保持し、名前だけ `written_utc` に変更した。元の HEAD の JSON と比較し、それ以外の data が完全一致することを確認した。main validation 内の full-pytest コピーと参照 SHA も更新した。前回の stdout / JUnit / source hash inventory は変更していない。

## インターフェース（WP4 / ユーザー向け）

CLI は既存の `local_gpu.py check-lock / render / run / verify / watch / bench` を保つ。GPU project は `julia/CFDSDFWaterLilyT4`、CPU 自己テストは `julia/CFDSDFWaterLily`。`run` は既存 `CAMPAIGN_WORK_ROOT` を使い、dataset 用の bind helper は必要な場合だけ使う。render 後の runner は実行時に変更しない。

WP4 の checkpoint API は今回変更していない。`src/` は登録 directory pin なので、追加 module は `gen01/` から読む。

```julia
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))
using .CFDSDFWaterLily.Checkpoint
save_checkpoint(path, sim, step, rows; identity=study_geometry_sampling_sha)
payload = load_checkpoint(path)
restore_checkpoint!(fresh_sim, payload; identity=study_geometry_sampling_sha)
# payload.step+1 / copy(payload.rows) から続ける
```

save→path、load→validated NamedTuple、restore→fresh_sim。identity は必須かつ非空で、restore が照合してから field を変更する。`step` は個々の mom_step! の完了回数であり `length(Δt)==step+1`。`sim_step!(sim,t_end)` は複数 advance を行うので呼出回数をこの step にしてはいけない。標準 Flow / MultiLevelPoisson、同一 body/config、default remeasure=true、信頼した自作 Serialization file に限る。

## テスト（コマンド、結果、失敗 node 集合）

修正前の TDD：`.venv/bin/python -m pytest -q tests/test_local_gpu_gate.py -p no:cacheprovider` → **24 failed / 84 passed**。修正後の同じ gate テスト → **108 passed / 0 failed**。いずれも記録用 `--junitxml` を付けた。

重点5ファイル（registered reverify を含む）：

```sh
.venv/bin/python -m pytest -q tests/test_local_gpu.py tests/test_local_gpu_backend.py tests/test_local_gpu_gate.py tests/test_local_gpu_julia.py tests/test_harness_registered_reverify.py -p no:cacheprovider
```

**197 passed / 0 skipped / 0 failed / 0 errors、15.78秒、失敗 node 集合 `[]`**。記録用 `--junitxml` のみ追加した。WSL_INTEROP が別 terminal ごとに変わる C1/C5、非揮発 env の拒否、raw snapshot 保全、短い group と repeat ごとの必要区間、必須欠測、record-only 欠測/不正値、実 collector の受け渡し、同一 repeat の UUID fallback、異 UUID、schema を検査した。既存の stub runner の DONE / local_run.json、default render の byte 一致、include closure、現在の tree の UNC-01 U01 smoke / formal の byte 一致も含む。idle を除外すると PASS / active なら FAIL の両方も引き続き通る。

`.venv/bin/python -m compileall src tests` と `git diff --check` → **PASS**。

`git diff e3dcdf61 -- 'src/cfd_harness/campaign_*.py'` → **出力空**。schema / build / verify / runner template は byte 不変。5 TOOL_FILES の SHA は9 prerun freeze と UNC-01 / FID-01 / SCREEN-01 の freeze1、計12記録と一致。`e3dcdf61` に既に存在するファイルの変更/削除集合も `[]`。Julia src / 両 Project・Manifest / 既存 evidence・campaign・freeze・rendered kernel・登録 job・保護テスト・attempt1 記録への今回の差分はない。

全体 pytest は **Amendment 4 に従い今回は実行していない**。前回の `ab801695` に対応する **3651 passed / 74 skipped / 0 failed / 0 errors**、base `e3dcdf61` の **3482 passed / 74 skipped / 0 failed / 0 errors** と双方の失敗 node `[]` は履歴として残す。これらを今回の tree 全体の再実行結果として扱わない。CPU checkpoint の25 assertions / BITWISE と CPU bench も前回の保存結果であり、Julia source を変更していない今回は再実行していない。

コマンド、時刻、wall、returncode、stdout、JUnit、artifact SHA は `wp01_amendment4_validation/` と main validation に記録した。独立 native worker の read-only source review でも新たな指摘はなかった。

## 仕様からの逸脱と理由

Amendment 4 / 仕様 §11.7 に沿った修正であり、凍結済み tool への変更やテスト例外はない。n3 の「必須 minute telemetry は3項目」に合わせ、VRAM 容量が telemetry で取れない場合は既に同一 lock に bind された容量を使用する。これは容量の推定ではなく、記録された値の再利用である。

attempt 3 の「T4 契約は byte 不変」という主張が誤りだった訂正を維持する。schema/build/verify の復元は前回 `ab801695` で完了済みであり、今回は復元操作を再実行していない。current-tree 再検証と bytes / tool SHA の保護を今回も確認した。

OpenCode Go MCP は未提供、CLI `opencode models opencode-go` も既定 log の FileSystem.open で起動失敗した。global 設定や課金は変更せず、親による限定修正と native worker の非重複・read-only review を使った。追加の有料 API は使用していない。

## 未確認の仮定（WSL2 実機で確認すること）

Julia 起動/JIT/小 kernel launch 遅延、Windows build/driver/WSL kernel/distro/設定反映、HAGS、NVML の実際の memory/utilization/clock/UUID 取得と partial support、Windows Display TDR event4101 の可視性、optional bind mount の要否・権限・解除、専用 depot の instantiate / tree hash、R5 の GPU 別 process 再開、native Windows 比較、R6 の6時間 loop の温度/clock/RAM/VRAM は未確認。今回の fallback は合成データで検証した機能であり、実機での取得成功を意味しない。

KB5127936 保留は提示資料の回帰回避注意で、この更新障害を独自検証した主張ではない。R6 は6時間の cold-process wrapper loop で、GPU-active6時間ではない。reset なしも event monitor の観測範囲に限る。対象物理・T4 force 同値・格子独立・高 Re / FSAE の資格は主張しない。

## Claude／ユーザーへの提案する追記

review worktree の §11.7 Amendment 3 と今回の n1〜n5 対応を PR #88 の owner review に結び、render から gate まで pinned files を変えない手順を維持する。roadmap / STATE / exploratory_index / 仕様本文への編集は今回行っていない。

## 次に要るもの

host Claude が上記19ファイルを同じ worktree から commit・push し、既存 PR #88 を更新する。その後、owner review と事前登録、WSL2 準備・専用 depot の instantiate、実機 lock の capture / review / commit を経て、ユーザーが R0〜R6 と one-shot gate を実行する。後続 GPU 実行は道具の実装 DONE を妨げない。
