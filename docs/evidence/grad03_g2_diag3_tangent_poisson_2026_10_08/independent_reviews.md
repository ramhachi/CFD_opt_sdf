# 独立レビュー（T4 前、2 役）

どちらも別 agent が read-only で実施。判定は両方 **PASS-WITH-FINDINGS**（数学上・設計上の blocker なし）。指摘は freeze 前に反映し、fixture・CPU dry-run（最終版の job）・テストで再確認した（修正後の再レビューは行っていない）。

## Review A — 数学・AD の正しさ
- 線形化: Dual の残差 `r = z − A x` の tangent `dr = dz − dA x − A dx` は `L`（`D`・`iD`・粗い level を含む）の tangent を自動的に含む。継続は `A e = dr` を値だけの演算子で解く反復改良で、`dx_new = A⁻¹(dz − dA x_n)`（内側の解の誤差を除く）。`x_n = x*` なら収束解の導関数に一致し、差は `A⁻¹ dA (x* − x_n)`（body 帯域、未定量）。打ち切り反復の導関数（`(dM/dθ)·r` の項）と FD-08 の観測量には一致しない。note の記述は正確（唯一の言い過ぎ「主因」を修正: 打ち切り Poisson 反復の微分、と言い換え）。
- ガウジ: `A` は対称で、マスクセルの行・列は 0。核は活性集合の指示関数、値域は活性集合の和が 0 のベクトル。活性集合の平均の除去は値域への直交射影で正しい。射影後の aux の `residual!`（全セルの平均）は `s ≈ 0` で干渉しない。
- `aux_solve!` は `solver!` と V-cycle・smoother・`ω` の更新・`perBC!` が一致（停止判定・固定回数・上限のみ意図的に異なる）。
- primal の bytes: `x` への書き込みは `add_tan`（`FD.value(x)` を保持）だけ。`residual!` は `p.r` のみ。`diag3_mom_project!` は Flow.jl と文単位で一致。値の checksum は十分な gate（SHA はより強いが nit）。
- 指摘と対応: (1) 停止判定が Float32 の再帰残差のため τ=1e-6/1e-7 は上限 64 に達しうる → analyzer が「上限に達した projection の割合」と「達成した残差の中央値」を報告（規則は不変）。(2) `DualStop` の停止判定が tangent の平均を含む → 活性集合の平均を除いた tangent 残差に統一。(3) fixture の残差の検証が `dA x` に鈍感・hook を直接呼んでいない → `dA` を 0 にした系との差（`dA x` が tangent 残差の約 137 倍）を記録し、有限差分の検証が感度を持つことを示す。(4) 検査は hook そのものを primal を緩く解いた系（primal は 1 cycle で停止）で呼ぶ。(5) 補助の演算子が生きた演算子と一致することを smoke と各 arm の終わりで検査（不一致は例外）。(6) 連結成分が 1 つという仮定は smoke で上限到達を記録。

## Review B — 実験の独立性・事前登録の完全性・durability・GPU 経路
- Julia と Python の定数・窓・`MIN_POINTS`・floor・分類・plateau・選択は一致。cuda 上で手動の override は到達不能。bridge・FD-08 の値は出ない。arm ごとに新しい simulation（状態の共有なし）。
- 指摘と対応:
  - **F1（高）Stage B が打ち切られた・失敗したとき、Stage A の verdict が最終結果に見える** → トップレベルの `verdict` は全工程が COMPLETE のときだけ（`stage_a_verdict` は別。Stage B 中の status は `RUNNING_STAGE_B`）。analyzer は status ≠ COMPLETE を integrity failure、Stage B の結果がなければ INCONCLUSIVE。
  - **F2（高〜中）smoke が空洞（`abst`/`absp` は非有限を 0 にする）で、refine が実際に動くことを確認していない** → 非有限は `count` で検査し、固定回数の継続が 2 cycle 走ること、threshold 継続で tangent 残差が減ることを assert。
  - F3（中）補助の演算子の検査 → 上記 (5)。
  - F4（中低）cap に達した arm → analyzer が割合を報告（規則は不変）。
  - F5（低）Python/Julia の差: 平均 cycle 0 を inf にしない、`a0_ok` でないとき `s0` を NaN に、count 族だけの plateau のときの提案文を「ユーザー判断」に。
  - F6（低）Stage B に 20000 step の上限、履歴と進捗を 400 step ごとに保存、`longrun.steps.csv` を 8 step ごとに flush、analyzer が freeze 済みの自分自身の SHA を検査。
