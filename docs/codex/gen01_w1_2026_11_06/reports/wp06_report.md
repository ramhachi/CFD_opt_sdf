# WP6 GEOM-S1 報告

## 状態

**BLOCKED：非零キャンバー／reflex における距離関数の仕様の選択待ち。** フェーズ A の scene・gate は未実装、フェーズ B は未着手。

[Draft PR #82](https://github.com/ramhachi/CFD_opt_sdf/pull/82) を `codex/kaggle-batch-migration` 向けに作成した。auto-merge は無効。これは実装完了の PR ではなく、不整合と再開条件のレビュー用である。

WP6 成果物 1 の「v18 の `plate_phi` と同じ式」と「厳密な SDF、|∇φ|=1」は、非零キャンバー／reflex では両立しない。共通 [00_README.md](../00_README.md) 最終行の「BLOCKED のときは、推測で埋めずに止める」「仕様が矛盾している」に従い、数式を黙って変更せず停止した。

v18 の局所座標で `s=2u/L`、`f(u)=C(s²−1/3)+R(s³−0.6s)` とすると、端から離れた滑らかな部分で `φ=|v+f(u)|−t/2`、したがって `|∇φ|=sqrt(1+f'(u)²)` になる。C/R が非零なら一般に 1 ではない。

既存関数の直接評価で、`L=1 m、t=0.1 m、C=0.1 m、R=0、点=(0.25,0,0.1) m` は `|∇φ|=1.0198039027193047`。表面上の対照点も同じ値である。境界点 `(0.242,0,0.05990773333333334) m` では `φ=0` で、元の点からの距離 `0.0408826350235783 m` は返値 `0.04166666666666667 m` より短い。有限差分の誤差や非微分点を理由にできない、最短距離の直接の反例である。

## 作ったもの（パス、1 行ずつ）

- `docs/codex/gen01_w1_2026_11_06/reports/wp06_design.md`：必須資料の読解、条件付き API、2D/3D・Julia 接続、gate・hash・検証計画と不明点。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_sdf_preflight.py`：既存 `plate_phi` の負の距離診断。平板、camber、reflex、両方、表面上の 5 例と近い境界点を自己検査する。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_sdf_preflight.json`：source/probe SHA、各勾配、境界点の witness を保存した `solver_free_development_diagnostic`。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_pytest_interrupted.log`：全体 pytest の中断時点の出力。完走した baseline ではない。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_validation.json`：コマンド、結果、失敗集合の未確定、source 不変と成果物の SHA を記録。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_report.md`：本報告。実装の受け入れ完了を示す文書ではない。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

新しい production API は提供していない。診断は次で再現できる。

```bash
.venv/bin/python docs/codex/gen01_w1_2026_11_06/reports/wp06_sdf_preflight.py
```

終了コード 0 と JSON の `CONTRACT_CONFLICT_CONFIRMED` は、仕様不整合の再現成功を意味する。scene acceptance、Birth-0/1、幾何 gate の適格化を意味しない。

## テスト（コマンドと結果。全体 pytest の失敗集合が base と同一か）

- 上記診断：終了 0。5 例の中央差分と解析勾配が許容差 `1e-8` で一致し、平板 control はノルム 1、4 変形例は 1 から逸脱。境界点 witness も通過した。
- 診断を再実行し保存 JSON と byte 比較：一致。独立 reviewer の再実行も byte 一致、source/probe SHA 一致、レビュー PASS。
- `.venv/bin/python -m compileall src tests`：終了 0。
- `.venv/bin/python -m pytest -q tests/test_v18_plate.py`：`18 passed in 9.66s`、終了 0。これは既存テストの回帰確認であり、非零 camber/reflex の厳密な距離性の証明ではない。
- `.venv/bin/python -m pytest -q`：開始点 `e3dcdf6188df6079e197eb28f7fcba1451ec512d` の無変更コードで起動したが、仕様矛盾による実装停止に合わせ、`901 passed / 24 skipped`、778.01 秒で SIGINT により中断した（終了 2）。完走した失敗 ID 集合は得られていない。ログは `wp06_pytest_interrupted.log`。baseline と最終の失敗集合の同一性は **未判定**。
- `git diff --check`：終了 0。`git diff --exit-code e3dcdf6188df6079e197eb28f7fcba1451ec512d -- src tests scripts pyproject.toml`：終了 0。これらの領域の新規 untracked source/test もない。
- `pytest -q tests/scene`、Birth テスト、E2/v18 との scene 比較：未実施。対象の実装・テストを追加していないため、受け入れ条件は未達である。

今回の変更は新しい reports ファイルだけで、src/tests は不変である。ただし source 不変の確認を全体テスト完走の代用にはしない。受け入れ条件を満たしたとは主張せず、再開時には完走した baseline と最終の比較が必要である。

## 仕様からの逸脱と理由

成果物 1〜8 の実装を行っていない。これは距離定義の選択に依存するためであり、ゼロ変形だけの部分実装をフェーズ A 完了とすることは避けた。フェーズ A 完了 PR に代えて、不整合と再現手順のレビュー用 draft PR とする。B は A 完了後という順序を維持する。

元の worktree では Git 管理領域が sandbox の書き込み範囲外で、`git add` が `index.lock: Operation not permitted`。許可された `/private/tmp` の独立 sparse clone に、開始点と同名 feature branch を保って意図した reports ファイルだけを移して commit/push した。元の worktree の branch/index は更新できないため、そこでは追加ファイルが untracked（中断ログは ignore 対象）のまま残る。この制限を clean と報告しない。

OpenCode Go MCP は存在せず、CLI 1.19.3 の確認は通常経路の log 書き込み制限、隔離 XDG 経路の `Provider not found: opencode-go` で失敗した。Go に委譲できたとは扱わず、native read-only worker に文書の全文確認と独立レビューを分担した。global config、認証、課金は変更していない。

## 未確認の仮定（実行して初めて分かること、PDF から読めなかった値など）

- `r_c` の意味と h の関係は、指定された GEN-01 rev 3.1 §3.2 に定義がない。定義や物理的根拠を推定していない。これは B の設計までに必要な補足である。
- FSAE/FSG の包絡の具体値・座標基準、固定 STL、任意の超楕円体の距離評価と Julia 側の計算費用は、今回の診断では確認していない。
- R3 の scene 実装、sub-cell 位相への頑健性、mesh signer、GPU/BDIM、厚さ・間隙の物理解像は未検証。既存 `GEOM03_NO_GO`、`SRCMAP02_INCONCLUSIVE` を変更する証拠は作っていない。
- `min phi_c` は要求どおりの union の符号を表すが、overlap 内部では一般に真の負の最短距離ではない。これは primitive の厳密性とは分けて文書化すればよく、min union を変更する停止理由ではない。

## Claude／ユーザーへの提案する追記（phase_plan、STATE、exploratory_index、仕様 rev 0 への修正点）

仕様の選択を一つ記録することを提案する。

1. **厳密な距離を優先する場合**：v18 の零等位面を保持した最近点距離を採用し、非零 camber/reflex の数値解法・許容差を認める。「同じ式」との一致を無変形 stadium に限定し、WP4 比較の幾何・距離基準を明示する。
2. **v18 の値の互換性を優先する場合**：非零 camber/reflex を analytic implicit field と記し、厳密 SDF 要求と距離テストを改める。

`r_c` は意味、SI 単位、h との関係、出典を補う。厚さ・gap の開発時既定 `4h` は、登録した BDIM 梯子での適格化値と区別する。正式な [#32 Birth-1](https://github.com/ramhachi/CFD_opt_sdf/issues/32) は actual primal response を要求するため、WP6 の分類テストは「Birth-1 のソフトウェア準備」と記す。各権威文書の本文は編集していない。

`docs/harness/README.md` への将来の追記案（**未実装**）：

> harness v1.2 は scene JSON の SHA と明示的な Julia 引数に結び付いた scene state、checkpoint ごとの有限 event 提案、地面と一緒に移す z 位相を扱う。event は提案の記録であり、評価・採否を行わない。従来の v1.1 campaign は既存の reader/verifier と固定 z を使い、既存 table の bytes と tool hashes を保持する。旧 campaign から新 version への暗黙の移行はしない。

この案は A 完了後の B でテストしてから採用する。README 本文は編集していない。

## 次に要るもの（GPU 実行、Kaggle、ユーザーの判断）

必要なのは距離契約の選択である。推奨は **v18 の零等位面を保持した真の最近点距離を優先し、数値解法と許容差、無変形 stadium の一致基準を明示する**こと。選択後、フェーズ A の実装と全受け入れテスト、PR を完了してから B に進む。今回の不整合を解決するための CFD/GPU/Kaggle 実行は必要ない。
