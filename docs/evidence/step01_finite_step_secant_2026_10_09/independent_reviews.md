# STEP-01 独立レビュー（実行前）

2 本の read-only レビュー（別 agent、狭いスコープ、T4・push なし）を source commit `d7bd1fda` の前に受け、指摘を反映した。反映後の第 2 ラウンドは行っていない（tests と、runner の fake job による fail-closed の確認で閉じている）。

## 1. 入力・inventory・runner の lineage
結論: **実害のある欠陥なし**。確認できた事実: numpy の摂動は `construct_state` と byte 一致（40 単一 + 4 合成の全 state、47 state の C 順 SHA も一致）、`raw[~active] = parent.phi[~active]` はこの 6 方向では no-op（active 外の非零 node は 0）、runner の `W4_*` env は FD-08 runner の `state_env` と baseline 行で完全一致、job は FD-08 formal と同一（SHA `1d8dbcb6…`、T4 の project/manifest も一致）、sparse checkout は runner と job が読む全パスを含み src tree hash は job の include の上位集合、timeout は余裕あり（A/B ≈ 4450 s / 6900 s、C ≈ 1310 s / 3300 s）、DONE は構造上「全 state 完了」でしか書かれない、baseline CSV の SHA は formal の実 CSV と一致。
| 指摘（Low） | 対応 |
|---|---|
| pin が worktree から計算され commit と食い違いうる | 反映: kernel の render 前に、tracked file が clean で、全 pin が `git show <commit>:<path>` と同じ bytes であることを検査（`verify_pins_against_commit`） |
| `CUDA_DEVICE_ORDER`、runtime smoke、runner SHA・python/numpy の版・platform が FD-08 と違う／記録なし | 反映: note に deviation を明記、`run_identity.json` に runner SHA・python・numpy・platform を記録 |
| per-state の kernel 上の検証が FD-08 より薄い | 変更なし（設計: host analyzer の gate が summary・SHA・時刻・再計算を検査。DONE は「完了」の意味にとどまる） |
| inventory の再導出が repo 外の NPZ に依存、NPZ SHA は監査できない | 変更なし（開示。runner は phi の SHA を検証し、NPZ SHA は job の identity の記録だけ） |
| baseline CSV SHA の定数が 2 箇所 | 反映: `step01_states.FD08_BASELINE_CSV_SHA256` に一本化し、一致のテストを追加 |
| テストが fixture の鏡写し（pin 不一致・方向 pin の改ざん・`W4_*` 全キー・render された baseline SHA） | 反映: pin 不一致と方向 pin 改ざんで kernel が止まるテスト、FD-08 の `state_env` との全キー一致テスト、render された SHA の一致テストを追加 |

## 2. analyzer・定義・文言・テスト
結論: 定義・符号・単位・baseline・補間の中核は設計どおり（`g_sec` の符号、minus 側の一方向 secant、R0 は kernel の baseline、resolved は両側、補間は 10 点＋原点の PCHIP、ĝ/SE のキー、gate 失敗時に series を出さない）。文言（agreement radius・ĝ・SE）に過剰表現はなし。
| 指摘 | 対応 |
|---|---|
| 【重】凍結の検証が analyzer と inventory だけ（`contract`・`force_io`・formal criteria・ĝ を変えても RECORDED になる） | 反映: analyzer、contract、states module、force_io、formal_criteria、inventory（正規 JSON）の SHA と、凍結した 8 本の ĝ・SE を照合。freeze は必須 |
| 【重】空の manifest・空の pins が通る | 反映: manifest が index・identity・nvidia-smi・全 state の 3 ファイルを列挙していることを要求、pins と方向ファイルが空なら失敗 |
| NaN・欠損キーが比較をすり抜ける／例外で落ちる | 反映: `not (x <= tol)` 形、全 state の検査を `except Exception` で INCOMPLETE、ĝ=0・SE=0 は INCOMPLETE、series の計算失敗も INCOMPLETE |
| `defect_exceeds_interpolation_spread` が常に真になりうる（格子点上で spread が 0） | 反映: 不確かさ = 2 成分の |PCHIP−線形| の和、flag は spread と分解能（10σ0）の両方を超えたときだけ（`…_and_resolution`） |
| `sign_stable_through_mm` が `constant_over_resolved_steps` と矛盾（全 step が未分解でも 12.5） | 反映: 反転の手前の、分解された最後の step。無ければ null |
| agreement / drift が resolved を無視、`z_…` のキー名、worst の組の形、note の件数ミス（20 → 21 state）、freeze の件数が直書き、report の来歴 | 反映（note に挙動を明記、キーを `diff_over_nominal_se`、worst を dict、件数を inventory から、report に freeze・analyzer・manifest の SHA と source commit） |
| テスト: 隔離できない・同義反復・combo が常に厳密加法的・1 kernel だけ違う baseline など | 反映: 空 manifest/pins、各凍結入力、ĝ の改ざん、NaN の summary、DONE+ERROR、nvidia-smi 欠落、manifest 改ざん、1 kernel だけ違う baseline、未分解 step、ĝ と逆符号、非線形な合成で defect が spread と分解能を超える、provenance の各テストを追加 |
| freeze builder が commit・clean tree を検査しない | 反映: tracked file が clean で、source commit が HEAD の祖先であることを要求 |
