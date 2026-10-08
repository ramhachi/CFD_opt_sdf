# G2-DIAG4 独立レビュー（T4 実行前）

2 本の read-only レビュー（別 agent、狭いスコープ）を、source commit `a6ecbc61` の前に受け、指摘を反映した。T4 実行前の記録。

## 1. lineage / 介入の同一性（job・runner）
結論: B0 は元の semantics（G2 の `sim_step!`）と同一、B32 は DIAG2 forced-32 と同一（`@fastmath` の構成・`solver!(b; tol=0, itmx=32)`・`measure!` の順序・dt の扱い）。fork は真の clone（残りの状態は次 step の頭で再構築される）、3 simulation は独立（各 arm が自前の phi・body・hook）。fail-open 経路なし。致命的・高重大度の指摘なし。
| 指摘 | 対応 |
|---|---|
| M1 clone 検証が xor/sum のみ | 反映: u・p・Δt を bit 単位（`reinterpret(UInt8)`）でも比較 |
| M2 B0 が 980 以降に早期終了しても job は RECORDED | 設計どおり（analyzer の control が処理。note に記載）。変更なし |
| M3 B0 の first_nonfinite が tangent→primal で上書きされる | 反映: 先の event を保持（CSV には両方残る） |
| M4 fresh の inc 列は別基準 | 変更なし（分類に使わない。fresh の inc を B0/fork と直接比較しない） |
| M5 flow 配列 extent の assertion なし | 反映: cuda で `size(u) == (152,74,56,3)` を検査 |
| M6 DONE が manifest 生成より前 | 変更なし（他の runner と同形。analyzer が verdict を検査する） |
GPU 固有で DIAG4 が新規に使う経路（2 配列 `map`、`map(TanOf())`、`view` への `sum`、`copy(b0.ref)`、CuArray の `mightalias`）は CPU dry-run では確認できないが、isbits の callable で、失敗しても例外で停止する（fail-closed）。
CPU dry-run（gates_pass / gate_failure / exception）は、反映後の job で実行し直した。

## 2. 解析・分類（analyzer・テスト・freeze builder・note）
結論: 窓・stride・隣接・閾値・R² の実装は仕様どおり。B32fresh が主 verdict・閾値・control に影響する経路は、欠落時の INCOMPLETE 以外になし。
| 指摘 | 対応 |
|---|---|
| 1 DELAYED/DIFFERENT/UNLOCALIZED でも interpretation が NO_ONSET 用 | 反映: verdict ごとの固定文言 `INTERPRETATION`。「primal をわずかに」の断定を削除。テスト追加 |
| 2 持続成長が箱 OR 全体の系列 | 変更せず開示（note）。箱外の成長を NO_ONSET にしないため |
| 3 DIFFERENT_MODE の評価点が承認文言より緩い・遅い | 変更せず開示（note）。位置不明は箱外として数える（反映） |
| 4 fresh の欠落が主 verdict を INCOMPLETE にする／INCOMPLETE_ARM が unstable 扱い／READING が強い | 反映: INCOMPLETE_ARM は not_assessed、READING を弱める。欠落での INCOMPLETE は fail-closed として開示 |
| 5 欠番・重複・NaN の CSV が NO_ONSET に写る | 反映: `data_defects` → `INCOMPLETE_ARM`。テスト追加 |
| 6 未登録の値（0.5・BOX）、analyzer SHA 未登録で fail-open、clone/独立性が未検査、ヘッダのテストなし | 反映: `MODE_OUTSIDE_FRACTION` を登録、BOX を analyzer から導出、analyzer SHA が無ければ失敗、index の clone/独立性が true でなければ失敗、Julia ヘッダ照合テスト |
| 7 書き込みの原子性 | 反映: `open("x")` |
