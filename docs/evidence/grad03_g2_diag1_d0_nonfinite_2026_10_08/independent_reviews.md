# 独立レビュー（T4 前、2 役）

どちらも別 agent が read-only で実施。判定は両方 **PASS-WITH-FINDINGS**（blocker なし）。指摘は全て T4 前に反映し、CPU dry-run とテストで再確認した（修正後の再レビューは行っていない）。

## Review A — 観測の非干渉
- stage コピー 4 関数は `Flow.jl` 156-167 / 190-196 / 205-210 / 223-232 と文の順序・引数・`@fastmath` の位置が一致。差は `probe(...)` と、省略した `@log`（`@logmsg`、logger なしでは no-op）・`udf!(…, nothing, …)`（no-op）のみ。
- probe は flow/Poisson の配列・`Δt` に書かない（`stats`/`host_elem`/`capture` は reduction または host コピー）。唯一の書き込み `maybe_inject!` は `DIAG1_BACKEND=cpu` でしか有効にならず、cuda では `DIAG1_*` が 1 つでもあると起動時に error。
- `instrumented_step!` は `sim_step!(sim)`（remeasure あり）と等価。毎 step の力のサンプル（`flow.f` を scratch に使う）は、`conv_diff!` が `f` を全面上書きするため後続の状態に影響しない。
- `build` / `load_raw` / `sample_row` / `vp` / 定数は G2 と byte 一致。`FD.Tag(run_one_tag, Float32)` は G2 の tag と数値上等価（run 内の tag は 1 種類）。
- 指摘（反映）: (1) GPU 側の probe 未検証 → 起動時 preflight と host コピーへの fallback を追加。(2) ground 力の非有限で first_bad が立ちうる → stage 名で区別でき、Case E として扱う（仕様どおり）。(3) checksum は弱いが SHA が補完（維持）。(4) G2 再現判定は厳格（仕様どおり、保守側）。(5) `@fastmath function diag_mom_step!` の存在をテストに追加。

## Review B — 診断の網羅性
- 12 項目（durable な partial、first bad の identity、primal/tangent 分離、stage 局在、Poisson、力の分解、成長曲線、空間局在、幾何監査、snapshot、verdict、禁止事項）は dry1/dry2/dry3 の実ファイルで確認。
- 指摘と対応:
  - M1 NaN/Inf が JSON で `null` → `first_nonfinite_{primal,tangent}_repr` を追加し、analyzer の identity に載せた。
  - M2 case 規則の不整合（C が A を隠す、primal 先行の case がない）→ 優先順を E > D > F > A > C > B に変更（F = primal 先行を新設）。「tangent のみ」は最初の非有限**要素**で判定。note・freeze・テストを更新。
  - M3 reference 側の例外で B が走らない → reference を try/catch し、B は必ず実行（verdict は INCOMPLETE）。
  - M4 CUDA 経路の未検証（`host_elem` の view、closure が型を捕捉）→ `host_elem` は線形 index、`ToReal{R}` の isbits callable、first-bad の探索は host コピー、preflight と fallback。
  - M5 kill 後に解析不能 → `diag_index.json`（RUNNING）を開始時に、`first_bad.json` を検出の瞬間に、`snapshot_index.json` を snapshot ごと、`stage_order.json` を step 1 の後に書く。analyzer は index 欠落でも ledger から部分解析する。
  - L1 例外時の ring を出す、L2 `prev` の key を force probe と分離、L3 粗い level の field は localize しない、L4 analyzer の例外を stub 報告にする。
  - nit: `peak_vram_bytes` → `used_vram_bytes_at_end`、ring と scheduled snapshot の重複書き出しを省略。
- Float64 は診断の累積（device 上の reduction）にのみ使う。Float64 の Dual simulation は存在しない（テストで固定）。
