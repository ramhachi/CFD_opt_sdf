# Independent source and draft audit review — 2026-10-12

Reviewer: Claude Sonnet 5.5 (`claude-sonnet-5-5`), high effort; first-party Claude CLI using existing subscription authentication. Read-only Read/Glob/Grep tools, no command execution, no permission denials. Primary: GPT-6 Astra High. This initial review is provisional; its requested supplements and final disposition are recorded in `independent_review.md`.

# 独立レビュー（読み取り専用・solver-free）

## 1. 暫定結論

**`CONTRACT_NONPORTABLE_ACROSS_LATTICE` は、ここまでの証拠から支持できます。ただし最終確定の前に下記 R1〜R3 を追記または補強する必要があります。**
- `SEMANTIC_MISMATCH_CONFIRMED` は支持されません。#51 は P22 の hard 評価関数を直接呼んでおり、別の測度を使っていません。
- `TRUE_PARENT_INFEASIBLE` も支持されません。baseline（v17 B）自身が `0.12925 > 0.126125` で、parent（C）だけが超過しているわけではないためです。事前宣言した条件（B が limit 内で C のみ超過）を満たしません。
- 現時点で、計算の誤りと確認できた欠陥はありません。未達のものは、証明の不足と文書の未作成です。

## 2. 確認できた事項（ソース照合済み）

- **hard 評価関数の同一性**
  - `scripts/build_lowdim01_inputs.py:25` は `sharp_volume_m3` を `cfd_sdf.design.volume_semantics` から直接 import しています。
  - `scripts/audit_p22_v17_volume_semantics.py:120` の `G.sharp_volume_m3 is V.sharp_volume_m3` が True で、別実装の余地はありません。
  - `geometry_gates.cell_occupancy`（`geometry_gates.py:133`）も同じ `_corner_mean(...) < 0` で、呼び出しの連鎖は M1 と一致します。
- **Float32 の順序付き 8 節点平均と zero-fluid**
  - `_corner_mean`（`volume_semantics.py:224-236`）は float32 配列を左から順に加算し、最後に `np.float32(0.125)` を掛けます。
  - `sampled_solid_centers_count` の判定は厳密な `< 0.0` です。
  - テストの合成ケース（2^25, -1, -2^25）は、加算順序と float32 丸めに依存します。Float64 平均は -0.125 で、これとは区別できます。
  - 別順序なら結果が変わるため、順序の検出力もあります。
  - 厳密ゼロ中心のテストは、`design_mask` の既定が True（`sdf_state.py:274`）のため、勾配ゼロの検証として空振りしません。
- **Q1（原本 v16 の再現）**
  - v16 の NPZ SHA `3d2cd6c1…` と state SHA `44507748…` は、登録済み JSON `sdf_native_volume_semantics_v1_2026_09.json` の `input_lineage` および `state_sha256` と一致します。
  - `phi_sha256` `45b6c8f4…` も一致します。
  - 再計算値は 1009 centers、`0.12612500000000004`（`==` 比較）で、登録 JSON の `volume_m3` と一致します。
  - ゲートは B/C の測定より前に置かれています（`audit_p22_v17_volume_semantics.py:78`）。
- **v16/v17/parent の状態と lattice**
  - 原点は同一、物理境界は一致、`spacing_17 == spacing_16 / 2` です。
  - v17 の共通節点（`[::2,::2,::2]`）は v16 とビット単位で一致します。
  - 中心点集合は互いに素で、サンプル数は 8 倍です（46080 → 368640）。
  - `v16_v17_identical_trilinear_zero_sets_claimed: false` が明記されており、「物理 STL の同一性は零集合や連続体体積の同一性を意味しない」という要求を守っています。
  - 同一 STL の SHA は `5e6d2107…` で、A/B の `source_sha256` と一致するチェックがあります。
  - parent と baseline のマスクは等しく、parent は保存済み direction と `construct_state` で再構成され、NPZ がバイト一致します。
- **hard と smooth の区別、および node occupancy**
  - sharp、smooth、node occupancy（`constraint_authority: false`）は、すべて別フィールドです。
  - smooth の残差は登録済み limit だけを使います。
  - `g_V <= 0` は feasibility の証明にならないことが、B と C の `sharp_reference_feasible: false` と矛盾なく読めます。
  - node occupancy は A 1420 節点 → `0.1775`、B 9764 節点 → `0.15256`、C 5698 節点 → `0.08903` です。
  - B と C の `solid_nodes` は大きく違うのに、hard は同じ 8272 centers です。これは「節点占有数は契約測度ではなく、診断のみ」という主張と整合します。
- **baseline と parent がともに `0.12925` であることの意味**
  - `parent_minus_v17_baseline_hard_m3 = 0.0` で、中心数はどちらも 8272 です。
  - 差の `+0.003125` は C 固有の摂動ではなく、B の時点で既にあります。
  - 一方、smooth は `-1.05e-3` 動いています。hard が sub-voxel の変化に鈍感であることとも整合します。

## 3. 必要な追加証明・修正（重要度順）

**R1（重要・説明不足）: `8272 = 8 × 1034` の一致が説明されていません。**
- `measure_inventory.json` は、`historical_number_collision` を「数値は同じだが導出は別」と結論づけています。しかし、v17 の 8272 centers は handoff の revoxelized 1034 cells のちょうど 8 倍（`8272 × 0.025³ = 1034 × 0.05³`）です。
- 登録 JSON によると、この 1034 cells は表面 mesh 体積と約 1e-8 の相対差です。つまり STL の体積は `0.12925` にほぼ一致します。
- 「偶然の一致」と書くだけでは不十分です。次のような説明がありえます。STL が 0.05 の voxel staircase なら、v17 の 0.025 の trilinear 中心は staircase をほぼ再現し、v16 の 0.05 中心は粗い補間で 1009 に減る。
- ただし、これは推測です。次のいずれかを追加する必要があります。
  - `reference_surface.stl` の符号付き体積を、solver-free で独立に再計算する。
  - 「v17 の hard は mesh 体積と一致するが、導出は別」と言える根拠を示す。
- この結果は分類を強める方向に働く可能性があります。v16 の limit は粗い lattice のバイアスを含み、v17 の方が STL に忠実だ、という読みです。ただし、これは「連続体体積が同一」という主張ではありません。このため、文言の扱いには注意が必要です。
- いまのままだと、「別測度ではない」という主張が数値の偶然に依存して見えます。

**R2（Q1 の厳密性）: 評価関数コードの同一性は、値の一致でしか示されていません。**
- 登録時（2026-09 中旬）の `volume_semantics.py` と、現在のファイル（`measure_inventory.json` で SHA `021c2da0…`）が同一かは、証拠にありません。
- 現在の `_corner_mean` で、登録時の 1009 / `0.126125…` と NPZ SHA が再現することは、強い間接証拠です。
- ただし「original evaluator identity」を厳密に言うなら、登録時コミットの `_corner_mean` と `sampled_solid_centers_count` の同一性（例: 当該コミットでの diff 無し）を一行で記録する必要があります。
- 同一性を確認できなければ、規則どおり INCONCLUSIVE です。

**R3（スクリプト・証拠の欠落）**
- `audit_p22_v17_volume_semantics.py` は、登録 JSON `sdf_native_volume_semantics_v1_2026_09.json` の SHA `0142ace4…` を検証しません。
  - `0.12612500000000004` と 1009 は、スクリプトとテストにハードコードされています。
  - 登録 JSON の `volume_m3` と `sampled_solid_centers` を読み込んで照合すると、Q1 の根拠が閉じます。
- `measure_inventory.json` に記録された評価関数ソースの SHA は、`--check` で再検証されません。
  - 現在のファイルのハッシュを実行時に比較しないため、記録は静的な主張にとどまります。
- 「#51 ブロッカーを生成したコードは ad-hoc の heredoc で、保存ファイルがない」という点は、`excerpt` と JSONL 行番号でしか辿れません。
  - 抜粋 `blocker_generator_excerpt.txt` は import と呼び出しのみで、`SDFDesignState`、`root`、`inv`、`S`、`B` の定義を含みません。
  - したがって、このファイルだけでは単独で再現できません。
  - 欠落は「#51 が P22 の `sharp_volume_m3` を直接呼んだ」という本質的な結論を損なうものではありません。ただし、再検証可能という主張は弱くなります。
  - 元のセッション記録に依存している点は、明示してください。

**R4（軽微・テスト）**
- `test_reconstruction_and_frozen_comparison_replay` は、ローカルの `docs/evidence/lowdim03_dual_grid_primal_2026_10_10/` の保存 direction に依存します。
  - 欠けていれば失敗するので、fail-closed ではあります。
  - ただし、タイトルの「portable」とは相反します。テストが依存する非 inputs ファイルを明記してください。
- 4 個の `exact_zero_centers_fluid` はすべて 0 です。実状態での zero-fluid は未発動で、合成ケースのみの検証です。分類には影響しません。
- Float32 と Float64 平均で符号が変わる中心の数は、A/B/C 実状態で報告されていません。追加しても害はありません（計算の誤りではなく、追加情報）。

## 4. 保留中の文書と、誤った計算の区別

- **文書の未作成（欠陥ではない）**
  - 分類の本文
  - P22-v2 の移行提案（pre-optimization の元幾何に基づくこと。選択済み parent は使わない）
  - `SHA256SUMS` と最終の `independent_review.md`
  - `audit_plan.md` は、分類は独立レビューまで draft と定めています。
- **誤った計算**
  - 今回確認できた範囲では、ありません。
  - hard/smooth 値、中心数、差分の符号と算術（`0.12925 − 0.126125 = 0.003125`、1034 × 8 = 8272）は、すべて整合しています。
  - JSON の算出値は、スクリプトの `--check` 再現と一致するはずですが、私は実行していません。この点は root で再確認してください。

## 5. 守られている制約

- 閾値と契約の変更はありません（`threshold_changed: false`、`shape_update_allowed: false`）。
- CFD の実行は 0 回です（`cfd_runs: 0`）。D 状態の再生も行われていません（理由が明記されています）。

## 6. root への推奨

1. R1 を解消する（STL の体積を独立に再計算し、8×1034 の一致を説明する）。
2. R2 の登録時の評価関数の同一性と、R3 の登録 JSON ハッシュ検証を追加する。
3. 上記が満たされない項目は、規則どおり INCONCLUSIVE とする。

R1〜R3 が満たされ、移行提案が元幾何ベースで作成されるなら、`CONTRACT_NONPORTABLE_ACROSS_LATTICE` の確定に進めると判断します。

なお、このレビューは約 19 回のツール呼び出しで行い、コード・テスト・スクリプトは実行していません。
