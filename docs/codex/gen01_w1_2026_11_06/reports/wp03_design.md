# WP3 GRAD-00 設計メモ

## Amendment 2 実装前メモ（2026-11-06）

今回の開始 HEAD は `0b226184`。直下は `383e37e9`、`ae978d5d` で、作業ツリーはクリーンだった。
以下の追記が下の初回記録を上書きする。登録・凍結・ロードマップは変更しない。

- 指定 README、AGENTS と5文書、STATE、branching strategy、GEN-01、GRAD-00 rev 0、facts、TA1 source/plan/result、renderer/builder、terminal verifier、FD-08 reference/generator、現実装とテストを再確認した。長文の authority は3 workerが分担し全文を読んだ。GEN-01 plan の v18 記述より、今回のユーザー指示とGRAD-00仕様の v17 を優先する。
- OpenCode Go MCP は公開ツールに無い。CLI の通常ログ書き込みが sandbox で失敗し、一時 XDG_DATA_HOME でのモデル照会も `Provider not found: opencode-go` だった。グローバル設定・追加課金を変更せず native worker に分担する。
- reference は Claude が定義済みの `docs/evidence/grad00_lambda_2026_11/reference.json` をそのまま用いる。ε は全方向 `0.003971641173621408 m`、spread は Model A の `se_g_n_per_m`（fx=drag、fz=downforce）。実ファイル受理、generator `--check`、source 1 byte 改変拒否、4方向同一で ≤5 mm を新規テストで確認する。既存 evidence と generator は編集しない。
- D′ `vanLeer_safe` は `ForwardDiff.value(d) == ForwardDiff.value(u) ? c : vanLeer(u,c,d)` のみを WaterLily に include する。plain に対する式は D と同じで、Dual の等値退化だけを避ける。job の constructor routing と λ 型検査を保持する。20-step preflight に D の plain 対照を追加し、u/p の SHA による bit equality と D′ Dual の有限性を gate にする。A の TA1 との比較方法、sampling/window/watchdog/error/BLOCKED 閾値は保持する。
- analyzer に D′ と型 identity を追加する。A–D の必須条件は維持し、D′ 未実行は `NOT_RUN` とする。存在するが壊れた D′ 出力は欠落として扱わず拒否する。D′ の実行条件は人が判断し、analyzer は自動判定しない。次段規則への D′ の扱いは仕様 §5 の候補範囲との整合を確認して記録する。
- builder は5腕を扱い、新 helper を source pin に含める。reference 付きの render は既存の生成3ファイルを上書きできるようにし、既存 UNCONFIGURED ディレクトリからの更新も許す。reference 無しで既存出力を壊すことはしない。commit/source/reference を検証し、全腕を render してから書く。テストは tmp_path 内で default `infra/kaggle/` を模倣するだけで、今回実ディレクトリは触らない。
- 実装は Julia helper/job/selftest、Python analyzer/reference tests、builder/tests を分担する。最初に必要なテストを追加し、既存 helper と標準ライブラリを再利用する。root が差分・CPU preflight・統合結果を検証する。
- CPU は同じ20 steps、`G2_BACKEND=cpu G2_DRYRUN_T_END=0.4 TA1_PREFLIGHT_ONLY=1`、Julia 10 threadsで短い preflight のみ。A/B/C/D/D′、1.10 quick、Float64 A/B を確認する。D は初回の非有限を保持して報告し、D′ の成功で D 自体の結果を書き換えない。1.10 の instantiate と manifest 不変性も確認する。
- 結果側全体 pytest は `.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` を時間 cap 無しで完走する。base は再採取しない。失敗 node 集合を保存し、host baseline との同一性判定は Claude に渡す。
- 今回は `infra/kaggle/kernel_grad00_*/`、commit/push、PR本文、GPU/Kaggle に触らない。Claude が reference と D′ を含む実装を commit/push した後、指定コマンドで5 kernelを再生成して別 commit にする。最終報告には今回 commit すべき全パスを列挙する。

以下は初回試行時の設計記録として保持する。

作業開始: 2026-11-06。base: `e3dcdf61`、branch: `feat/gen01-w1-03-grad00`。
この文書は実装の設計記録であり、登録、凍結、ロードマップの変更ではない。

## 読んだ文書と適用範囲

W1 `00_README.md`、root `AGENTS.md` と指定の 5 文書、`STATE.md`、branching strategy、GEN-01 rev 3.1、GRAD-00 rev 0、facts for W1、TA1 のスクリプト・plan・result・QuickTie、TA1 rendered runner・metadata・builder、G2 terminal verifier、既存 Julia Project/Manifest と共有 src を確認した。
大きい `phase_plan.md` は担当を 1–2500、2501–5000、5001–7782 行に分けて全文を読んだ。
`phase_plan.md` だけが順序・状態の権威。#23 は主線外、すべての qualification flags は false のまま。今回の CPU 実行は software/code-path evidence であり、登録窓の測定結果ではない。

OpenCode Go MCP は公開ツールにない。CLI 1.19.3 のモデル照会は通常領域のログ書き込みに失敗し、一時 XDG 領域での再試行も `Provider not found: opencode-go`。グローバル設定や追加課金は変更せず、Codex の worker に Julia、analyzer、renderer を分担する。ponytail の順に既存 helper と標準ライブラリを再利用する。

## 未定義の入力を推測しない

指定された FD-08 amend3 の `formal_criteria.json` と `formal_analysis.json` に plateau または spread の定義はない。
記録された共通の formal interior ε は 0.6294627058970836、1.5811388300841898、3.971641173621408 mm で、六点 Model A の内挿検証用である。方向別に選ばれた plateau ε ではない。Model A の SE を spread に置換しない。
ユーザーに方向別 ε と spread の定義・参照先を照会した。回答まで、job は ε を必須の引数として受け取り、analyzer は provenance 付きの明示 reference JSON を必須にする。CPU code-path test の ε は合成 fixture と明記する。本測定用 reference がない renderer は未設定状態で生成し、実行時に fail closed とする。勝手な ε の選択や科学的ラベルの生成はしない。

## 実装とインターフェース

- `scripts/quick_nobound.jl`: `Base.include(WaterLily, ...)` で読み込む単一式。Float32、Float64、Dual で同じ median 式を使う。
- `scripts/waterlily_grad00_lambda_2026_11.jl`: TA1 のコピー。既存 build、sample、window mean、watchdog、BLOCKED 1e30、8× wall abort と error propagation を保持する。`GRAD00_ARM` を constructor の λ に渡し型検査する。
- CLI は TA1 の 11 引数に D0/D1/D2/P1 の ε [m] を 4 個追加する。各腕に共通の alpha=0 plain 1 本と各方向の Dual/plus/minus、計 13 run。仕様の「各方向で plain」は同じ plain の参照と解釈する（§4 の明示した 1+4×3 に従う）。
- `GRAD00_T=Float64` は CPU の精度腕のみ。仕様 F の A/B、D0/D1 を扱う。production は既存の flow_24、[80,120]、8-step sampling、Dual width 1 のまま。既存の CPU-only dryrun hooks を維持する。
- `g2_run_index.json` を保存し、`grad00_index.json` に schema_version=1、arm、real_type、lambda_type、runtime、window、sampling、directions、input_sha256、epsilon_m、preflight、runs、by_direction、status、flags を書く。run record は summary/history/watchdog の相対パスと SHA、窓平均、wall、VRAM、BLOCKED onset を保持する。
- 各 direction は plain/dual/plus/minus の run label を参照する。13-run inventory を隠さない。既存 terminal verifier は 5-run・T4・Float32・元 quick baseline 専用であり、名前を保存しても全腕に直接適用できない。新 analyzer は既存の `grad_g2_window` を使い、各 run の hash、window mean、同じ λ の Dual/plain の整合性を検証する。凍結 verifier を編集しない。
- analyzer の reference JSON は方向別 epsilon_m と fx/fz の spread [N/m]、出典 path/SHA、定義を保持する。比較は同じ λ の中心差分が主で、歴史的 FD-08 Model A は別に記述する。符号・0.1・3×は仕様のまま。次段の規則は B–D だけが対象で、A/E/F は対象外。既存 `analysis.json` は exclusive create で拒否する。
- builder は TA1 builder の `sha` / `verify_source` と凍結 runner template を再利用し、新規 4 kernel ディレクトリだけを作る。source commit/tree、全 imported/read bytes を pin する。未設定 reference の runner は測定前に停止する。GPU runtime から CPU dryrun/Float64 の環境を除去する。timeout は TA1 同様 10800 s、ローカル生成のみ。
- 新規 `julia/CFDSDFWaterLily110/Project.toml` と `Manifest.toml` で WaterLily 1.10.0 を厳密に pin。既存 src を include し、旧 project/Manifest は変えない。
- F の実出力を analyzer に渡すため、`scripts/run_grad00_cpu.py` を追加する。job 単体が作らない runner identity、DONE、output manifest を、既存 builder の source/reference pin 検証を再利用して作る。A/B の CPU Float32/64 と 1.10 quick Float32 だけを扱い、GPU/Kaggle/instantiate は呼ばない。source commit・reference・output・timeout を明示し、CPU project の pins に置き換えて同じ 15 引数の job を起動する。検証は fake subprocess のテストに限定し、今回 full-window CPU 測定は行わない。
- CPU wrapper は仕様 F の 10 Julia threads を強制し、identity に記録する。Float32 の比較対照にも同じ設定を使う。

既存 CPU Manifest の ForwardDiff は 1.4.6、登録 T4 は 1.4.5 だった。新しい 1.10 project は T4 と同じ ForwardDiff 1.4.5 に固定する。CPU と CUDA の差、または CPU と 1.10 の依存版の差を精度・median だけの効果として解釈しない。

## WaterLily 1.10 の差の扱い

job は `Simulation`、`sim_step!`、body measurement、force API を使う。`uλ`/`u0` と `mom_project!` を直接呼ばないため、ローカル adapter は想定しない。
ただし 1.10 の side E は median だけの比較にはならない。`mom_project!(w::Int)` の dt=Δt/w（corrector は 2）、境界処理と body-velocity の発散を含む source、Poisson の既定 tol=2e-3 と L∞/normalized L1 の条件が旧版と異なる。ground に velocity があるため不活性とも仮定しない。E の結果は版全体の記述的な差とする。
インストール済み両版の `Metrics.jl` でも、旧版の `promote_type(Float64, field_type)` による力の reduction が 1.10 の `sumdims(df)` に変わることを確認した。job が実際に呼ぶ force readout にもこの差が含まれる。

## テスト計画

変更前の `.venv/bin/python -m pytest -q --junitxml=/tmp/grad00-baseline-pytest.xml` を実行して失敗集合を保存する。
先に合成 test を置き、analyzer の全ラベル、境界、SHA 改変、必須キー、overwrite 拒否、A/E/F の規則除外を検証する。renderer は pin、commit、dryrun leakage、未設定 reference の停止、timeout、成功/BLOCKED/ERROR をローカル fake 実行で確認する。
Julia selftest は式の値、一致・不一致点、Float32/64 と幅1 Dual の finite partials、cds/vanLeer の存在を確認する。実データで 20-step CPU preflight を四腕と Float64 A/B、1.10 quick に行い、quick は凍結 TA1 の quick control の u/p の bit hash と比較する。短い CPU window で 13-run index と analyzer への接続も確認する。
実際の 20-step 計算が各腕で数分かかるため、13-run の orchestration は別の synthetic selftest で確認する。実際の job を module に読み込み、preflight と run_one のみを solver を呼ばない stub に置き換え、main/save_run!/write_indices と窓平均 helper、実 raw の perturbed/cast/hash 処理は実装を実行する。出力には SYNTHETIC_TEST_FIXTURE、solver_steps=0 を明示する。実 preflight と同一の証拠には扱わない。
最後に compileall、全体 pytest の baseline との失敗集合比較、diff --check、凍結対象の diff/hash を確認する。実装を commit してから kernel をその commit に pin して render、記録と一緒に commit/push、integration branch 向け PR を作る。Kaggle、GPU、freeze、登録、auto-merge は行わない。

## 時間の見積もり

TA1 の実測 plain は 138.857970953 s（loop 106.6 s）。9 plain と bounded Dual 4 本を plain の 2–3 倍と仮定すると 39–49 分に setup/JIT を加える。A–D 各 1 T4 時間を予算とし、4 腕は約 4 GPU 時間、E を加えて約 5 時間（仕様 cap 10 GPU 時間）。TA1 の早期 BLOCKED Dual は full-window の速度測定ではない。各 λ と 1.10 の実時間は未測定。精度 F は GPU を使わず、今回は数分以内の CPU 検証に限定する。
