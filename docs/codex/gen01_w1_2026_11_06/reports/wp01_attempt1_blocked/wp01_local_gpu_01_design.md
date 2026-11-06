# WP1 / LOCAL-GPU-01 設計メモ

日付: 2026-11-06。対象 branch: `feat/gen01-w1-01-local-gpu`。
調査対象 HEAD: `e3dcdf6188df6079e197eb28f7fcba1451ec512d`。
状態: **BLOCKED、実装前の契約確認で停止**。

## 目的と停止規則

目的は RTX 4070 Ti / WSL2 を、登録済み runner → Julia job →
`WaterLily.Simulation` の経路で使用するための道具を作ること。
今回許可された実行は CPU の短い検証だけで、GPU gate の実行・凍結・登録ではない。

最初に読んだ [00_README.md](../00_README.md) の最終段落は、
「BLOCKED のときは、推測で埋めずに止める」および
「仕様が矛盾している」の場合は報告して終了することを明記している。
以下の矛盾を確認したため、新規 runtime / gate / checkpoint の実装には進まない。
既存の登録ファイル、runner、job、Project / Manifest、ロードマップ、仕様本文を変更しない。

## 読み取った契約と確認範囲

- `docs/phase_plan.md` が唯一のロードマップ・状態・実行順序の authority、
  `docs/problem_register_2026_09.md` は issue ledger。GEN-01 の計画記録は backend の登録済み資格を与えない。
- [LOCAL-GPU-01](../../../local_gpu_env_gate_2026_11_01.md) は環境・再現性・処理量・再開・安定性の工学 gate。
  C3 / C4 は記述で、T4 との力の一致を合否条件にしない。物理・格子独立性の判定には使わない。
- [LOCAL-OF-01](../../../local_openfoam_env_gate_2026_10_20.md) §§2–7 と実装・lock・テストは、
  locked identity、登録 runner の保全、限定された再試行、欠けた証拠の分類の手本となる。
- harness v1.1 は現在 T4 専用。出力パスの可変性と GPU backend の可変性は別である。
- facts 文書 §5 は WSL2 の後日の検証に必要な背景資料として読んだ。今回は OS / GPU の事実を live 検証していない。

仕様・WP 指示・harness 文書・template・rendered replay runner / metadata / campaign・schema / verifier・
`grid01_gpu.py`・両 Julia Project / Manifest・GRID-02 job・LOCAL-OF の指定実装 / infra / テストは、
親または独立レビュー worker が全文を読んだ。`AGENTS.md`、`STATE.md`、branching strategy、
`docs/README.md`、problem resolution plan、GEN-01 plan、facts 文書も読んだ。
長い handoff / phase_plan / problem register は現行 authority、PROC-01、GEN-01、
freeze / amendment / GPU 関連箇所の確認と全文検索までで、全歴史本文の通読は未完了。
仕様矛盾により停止した調査を、実装前の必読条件をすべて完了したものとは扱わない。

## 実装を阻む契約の衝突

| 項目 | 現在の source / 契約 | 必要な判断 |
| --- | --- | --- |
| RTX と無改変 runner | `scripts/grid01_gpu.py:25` は可視 GPU がすべて `Tesla T4` であることを要求。template `:216` と既存 replay render `:239` が Julia 起動前に呼ぶ | T4 の登録結果を保全した、新しい明示的 backend profile と rendering を認めるか |
| C2 の既存 verifier | `campaign_verify.py:84–88` が同じ selector と `GPU_EXPECTED` を検査。`campaign_schema.py:72,341` は probe と summary の GPU 名を T4 に固定 | RTX の実名 / UUID を検証できる opt-in 契約を認めるか |
| R1 の T4 byte gate | `harness01_replay_campaign.json:79` の `first_state_csv_sha256` が既存 render と verifier で必須。一方 LOCAL-GPU-01 §§1,6 は cross-GPU byte 一致を要求しない | ローカル用 campaign では T4 の CSV を記述比較だけに使うことを明記する |
| Julia project | 指定の `CFDSDFWaterLily` は WaterLily だけを直接依存に持ち、CUDA package が Manifest にない。実際の template `:23` は `CFDSDFWaterLilyT4` を選ぶ | GPU 用には既存 CUDA 6.3.1 入り project を使い、CPU 自己テスト project と区別するか |
| R5 の kill→resume | R3 の `waterlily_lowdim02_flow32_job.jl` に checkpoint 呼出しがない。仕様 §3 は job への追加を求め、WP1 は job 編集を禁止 | 新しい checkpoint 対応 job / campaign を許可するか、統合まで C5 を INCOMPLETE にするか |

T4 の合成 inventory を受理し、RTX 4070 Ti の合成 inventory を
`ValueError: every visible worker GPU must be a Tesla T4` と拒否することを CPU で再現した。
RTX が T4 の力 CSV と実際に異なるかは測っていない。R1 の問題は数値差の予断ではなく、要求される合否契約の違いである。
`nvidia-smi` の偽装、import の差替え、monkeypatch、identity の書換えは解決としない。
runner は hash を確認した pinned commit の source を取得するため、単なるローカル helper の追加では契約を変えられない。

## 解決可能な設計事項と、未提供のインターフェース

出力先の方法は **(a) 既存の `CAMPAIGN_WORK_ROOT`** を選ぶ。
template `:28` と replay render `:51` がこれを読むため、この dataset 無し kernel の
出力パスには `/kaggle` の bind mount は不要。dataset 付き kernel の入力パスは個別に確認する必要がある。
パスが解決しても上記 GPU identity の矛盾は残る。

`WaterLilyJLD2Ext` は optional extension の宣言で、どちらの Manifest にも
`[[deps.JLD2]]` はない。実装再開後は、指示どおり標準ライブラリ `Serialization` を使える。
これは停止理由ではない。

WP4 向けに要求された API は `save_checkpoint(path, sim, step, rows)` と
`load_checkpoint(path)`。**今回は実装・export しておらず、WP4 が使用できる提供済み API はない。**
再開時は `u` / `p` / `u⁰` / `Δt` 履歴 / 時刻 / step / 力のサンプル行を保存し、
`load_checkpoint` の返り値と、新しい sim への復元方法、格子・dtype・環境 identity の不一致拒否を定義する。
このメモは返り値を凍結するものではない。CPU の途中保存・再開試験で、圧力 solver 等の追加状態が必要かも確認する。
module の CPU 試験の成功を、既存 R3 job の R5 対応とは扱わない。

lock の capture timestamp と環境 identity は分け、後日の `check-lock` が取得日時だけの違いで
必ず失敗しない形式を明記する必要がある。canonical lock の SHA は保存された JSON 全体に対して計算する。
これは再開後の通常の設計事項である。

## ファイルと検証計画

今回追加するのは、この設計メモ、`wp01_local_gpu_01_report.md`、
`wp01_local_gpu_01_validation.json` のみ。後者に CPU probe の結果、調べた source の SHA-256、
検証コマンドと終了状態を記録する。`infra/local_gpu/`、runtime / gate / bench、
checkpoint module / 自己テスト、`tests/test_local_gpu.py` は未作成。

再開には先に上記契約判断が必要。再開後の検証計画は、stub runner、lock 差分拒否、
全 C1–C6 の合成入力と境界条件、不足 run の INCOMPLETE、出力の存在拒否、
小さい CPU 格子の checkpoint 一致、base と実装後の全体 pytest の失敗集合比較とする。
今回は GPU を使わない CPU 契約 probe と `compileall src tests` を行い、
開始済みの全体 pytest は BLOCKED 確定後に中断した。実装の受け入れ条件を通したとは主張しない。

## WSL2 でしか確認できない点

- Julia / CUDA の起動・JIT / kernel launch の遅延、WSL2 と native Windows の R0 比較。
- NVML の query field、VRAM / clock / power telemetry、reset の観測可否。
- dataset 入力を含む絶対パスや bind mount の必要性・権限・後片付け。
- lock を取る実機の Windows build / driver / WSL / kernel / distro / 設定と CUDA.functional()。
- 長時間の温度・clock・VRAM・メモリ圧力と、実際の GPU 再開の再現性。

これらは未測定。既存 facts 文書の KB5127936 保留注意を含む実機準備手順も、
矛盾解消後の成果物として残っている。gate verdict、登録、qualification flag は作成・変更しない。
