# WP6：GEOM-S1（プリミティブ集合の SDF scene、要素数の事象、scene gate、ProblemSpec v3、harness v1.2）

最初に `docs/codex/gen01_w1_2026_11_06/00_README.md` を読み、その規則に従うこと。仕様は `docs/gen_system_plan_2026_11_01.md`（GEN-01 rev 3.1）の §2 A・B、§3.1、§3.2、§3.8、§4、§6.1。この WP は他より大きいので、**フェーズ A（scene と gate）を完成させて PR を出してから、フェーズ B（ProblemSpec v3 と harness v1.2）に進む**。フェーズ B は別 PR でよい。

## 目的

WaterLily の固定格子に乗せる **部品プリミティブの SDF の union** と、要素数を自由にする離散事象（種まき、knock-out、合体の提案）の生成、scene の幾何 gate、それらを宣言する ProblemSpec v3、そして harness が「baseline＋direction」以外の state（scene のパラメタベクトル）を扱えるようにする拡張を、CFD なしのソフトウェアとして作る。

## 必ず読む（全文）

- `docs/gen_system_plan_2026_11_01.md` の上記の節
- `scripts/v18_plate.py`（解析 SDF の原型。`plate_phi`、`raw_mode`、`mode_phi`、`harness_direction`）、`src/cfd_sdf/design/sdf_state.py`（`SDFDesignState`、hash、npz）、`src/cfd_sdf/design/geometry_gates_v2.py`、`geometry_gates.py`、`volume_semantics_v2.py`、`docs/sdf_native_geometry_gates_contract_v2_2026_10.md`、`docs/width_rule_decision_2026_10_20.md`（R0 の occupancy alias と R3 の開口欠陥）、`docs/sdf_topology_policy_v1_2026_09.md`
- `src/cfd_sdf/problem_spec.py`（v2。役割、multipoint、`topology_policy`）と `examples/generic_problem_v2/project.yaml`
- `src/cfd_harness/campaign_schema.py`、`campaign_build.py`、`campaign_runner_template.py`、`docs/harness/README.md`
- GitHub issue #32（TOPO-01）の Birth-0／Birth-1 の基準（`gh issue view 32`。取れなければ `docs/phase_plan.md` の該当箇所）
- `docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md` §2（`AutoBody`、`SetBody(min, …)`、`measure!`）と §6（BDIM の下限）、`research/waterlily_native_topology_routes.md` §1（MMC、Westra ら 2026 の gradient-free の先例、幾何 gate で拒否した設計は予算に数えない）

## 成果物（フェーズ A）

1. `src/cfd_sdf/scene/primitives.py`：
   - `PlateElement`（v18 の stadium 板の一般化：位置 (x, z)、弦、厚さ、迎角、キャンバー、reflex、スパンは固定。2D と 3D）、`EndplatePlate`（鉛直の板：位置、高さ、弦、厚さ）、`BoxBody`（超楕円体：中心、半径 3 つ、指数）、`MeshBody`（固定部品：STL から符号付き距離。符号は巻き数法。`trimesh.proximity.signed_distance` は内側が正で本リポジトリの φ<0 = solid と逆なので、使うなら符号を反転し、docstring にそう書く。SRCMAP-02 #53 の未解決点は docstring で参照）。
   - どれも **厳密な SDF を解析的に返す**（点の配列 → 距離）。v18 の `plate_phi` と同じ式を 2D／3D で共有。勾配の大きさが 1 であることをテストで確認。
2. `src/cfd_sdf/scene/scene.py`：`Scene(components, fixed, ground)`。`phi(points) = min_c φ_c`、格子への標本化（`SDFDesignState` への変換。lattice は scene の bbox から決め、h は引数）、部品ラベルの格子（argmin）、Julia 側に渡す JSON（各部品の種類とパラメタ）と、そのハッシュ。
3. `src/cfd_sdf/scene/events.py`：離散事象の **提案生成器**（評価はしない）：
   - `seed_candidates(scene, library, positions)`：ライブラリ（厚さ・キャンバー・弦の離散集合）× 候補位置（既存要素の後縁の下流・下方の格子）→ 候補 scene の列。
   - `knockout_candidates(scene)`：要素を 1 つ外した scene の列。
   - `merge_candidates(scene)`：接近した要素対を重ねた scene の列。
   - 「厚さの下限に 2 チェックポイント留まった要素は knock-out 候補」の規則を、履歴を受けて判定する関数。
   - 要素数の外側ループ（N = 1..N_max、分割で warm start）の **設計の列**を返す関数。
4. `src/cfd_sdf/scene/gates.py`：scene gate（rev 3.1 §3.1）：厚さ ≥ t_min（既定 4h）、間隙 ≥ g_min（既定 4h）、R3 型の開口欠陥を solid と void の両方に（`width_rule_decision` の定義を再利用）、連結性、閉じた空洞、要素と端板の接合、規則の包絡（FSAE 2026 T.7 の箱。ProblemSpec から読む）、clearance。拒否理由を列挙して返す。CFD の前に無料で走り、拒否は予算に数えない。
5. #32 の Birth-0／Birth-1：`tests/scene/test_birth.py` で、(0) 意図したプリミティブを正確に 1 つ作る（格子上の solid 成分数、体積、位置）、(1) 種まき・knock-out・合体で要素数の変化が分類どおりになる（成分数の差、どの要素が消えたか）を確認する。
6. テスト：`tests/scene/`（各プリミティブの距離性質、union の符号の一貫性、格子標本化の R0 alias（sub-cell 位相で solid の成分数が変わらない）、gate の各項目の合成反例、events の生成数と重複なし、JSON のハッシュの安定性）。

## 成果物（フェーズ B）

7. `src/cfd_sdf/problem_spec_v3.py`：v2 を **読める**まま（v2 のパーサは変えない）、v3 を新しいモジュールで：プリミティブ集合（種類とライブラリ）、要素の上限数、部品ごとの r_c と mask、規則セット（FSAE 2026／FSG 2026／FSG 2027 の箱を切替）、運転点と姿勢（車高、ピッチ）、目的の重み、固定部品の STL とハッシュ。canonical hash。`examples/topo2d00_problem_v3.yaml` と `examples/front_wing_problem_v3.yaml`。
8. harness v1.2：`src/cfd_harness/` に **最小の拡張**：state の `kind: "scene"`（scene JSON の SHA と、Julia job に渡す引数）、campaign の `events`（チェックポイントの番号と候補の列）、3 軸の位相（JOB-02 の `W4_CANONICAL_ORIGIN_M` に z を足す。既存 campaign は z 無しで従来どおり）。既存 campaign の `validate_campaign`・`verify` が **byte 単位で同じ結果**を返すことをテストで示す（既存のテストが全部通ること）。
9. `docs/harness/README.md` への追記案を報告に書く（本文は編集しない）。

## 受け入れ条件

- フェーズ A：`pytest -q tests/scene` が通り、Birth-0／1 のテストが通り、全体の失敗集合が base と同一。E2（WP4 の幾何）を `PlateElement` × 2 で再現したときの φ が WP4 の多角形 SDF と後縁・前縁の近傍を除いて 1e-3 c 以内で一致する（WP4 が未完なら、v18 の板で同等の比較）。
- フェーズ B：v3 の例が読め、canonical hash が決定的、既存 campaign の検証が不変。
- 設計メモに、2D と 3D の共有の仕方、GPU 側（Julia）での解析 SDF の評価方法（WP4 の多角形 SDF との関係）、r_c と h の関係（rev 3.1 §3.2）を書く。

## やらないこと

- CFD の実行、既存 gate（v2）の変更、`problem_spec.py`（v2）の変更、WaterLily job の編集（WP4）、最適化器の実装（応答曲面・DFO は次の WP）。

## Amendment 1（2026-11-06。1 回目の試み（Draft PR #82、`08e0ea38`）が BLOCKED で止まった点への回答。この節が上の本文より優先する）

1. **距離の契約（決定）。** 「v18 と同じ式」と「厳密な SDF（|∇φ| = 1）」は、非零のキャンバー／reflex では両立しない（反例は `reports/wp06_sdf_preflight.json`）。採るのは **選択肢 2 に数量の帯を付けたもの**：
   - 可動プリミティブの φ は **解析的な implicit field** で、無変形の stadium 板では厳密な SDF（これは今までどおりテストで |∇φ| = 1 を要求）。キャンバー／reflex 付きでは、零等位面は v18 の式が定める面のまま、距離は一次近似（`|v + f(u)| − t/2`）でよい。
   - 根拠：WaterLily の `AutoBody.measure` は d を |∇φ| で正規化する（調査 F §2：「`measure` takes the gradient of the SDF by AD, normalises `d` by the gradient magnitude」）ので、|∇φ| ≠ 1 の一次誤差は solver 側で補正される。本リポジトリの gate 2（`sdf_distance_property`：band 内の median ||∇φ| − 1| ≤ 0.10）も同じ許容の考え方。
   - テストは次に置き換える：(a) 無変形の板で |∇φ| = 1（1e-8）；(b) 変形付きの板で、band（|φ| ≤ 2h）内の median ||∇φ| − 1| ≤ 0.10（gate 2 と同じ）と、**数値の最近点距離**（零等位面を細かく標本化した点群への最短距離）との差が band 内で ≤ 2 % × t（登録する許容差。設計時の既定）；(c) 本プロジェクトで使う振幅の範囲（キャンバー ≤ 6 % c、reflex ≤ 4 % c）で (b) が成り立つことを表にして報告に載せる。
   - union `min_c φ_c` は重なりの内側で真の最短距離ではない。これは docstring に書くだけでよく、停止理由ではない（重なりは scene gate で禁止するので、BDIM の band には現れない）。
2. **`r_c` は WaterLily の線では使わない。** rev 2 の Vertex Morphing の名残で、rev 3.1 の WaterLily 主線には節点変位のフィルタが無い。ProblemSpec v3 から `r_c` を外し、代わりに **部品ごとのパラメタの範囲（bounds）と刻み**を宣言する。GEN-01 rev 3.1 §2・§3.8 の `r_c` への言及は Claude が直す（Codex は本文を編集しない）。
3. **厚さ・間隙の既定 4h は「開発時の既定」**で、登録値は RES-00 の梯子で決まる。docstring と報告でそう区別する。
4. **#32 の Birth-1** は実際の primal 応答を要求するので、WP6 のテストは「Birth-1 のソフトウェア準備（要素数の変化の分類）」と記す。Birth-0 はそのまま。
5. **道具の注意。** 今回の sandbox では共有の Git dir（`/Users/sota/projects/FomulaTMU/CFD2026_09/.git`）に書き込めるので、この worktree の branch `feat/gen01-w1-06-geom-s1` で直接 commit・push する（1 回目の sparse clone は使わない）。worktree は remote の `08e0ea38` に同期済み。1 回目の記録 `reports/wp06_*` は `git mv` で `reports/wp06_attempt1_blocked/` に移す。PR は既存の Draft PR #82 を `gh pr edit`／`gh pr ready` で更新する（新しい PR は作らない）。
6. 必読文書のうち、`docs/opencode_handoff_2026_09.md`、`docs/problem_register_2026_09.md`、`docs/problem_resolution_plan_2026_09.md` は **目次と該当節（geometry gates、SDF、topology policy、PROC-01）だけ**でよい。全体 pytest は **実装後に 1 回完走**させ、base の失敗集合は `git stash` ではなく、開始 commit を別ディレクトリに `git worktree add --detach` して取る（共有 `.git` は書き込み可）。

これで矛盾は解消しているはずなので、今回は BLOCKED にせずフェーズ A を完了して PR を ready にすること。フェーズ B は別 PR。新たな矛盾が見つかった場合だけ、その箇所を具体的に示して止める。

## Amendment 2（2026-11-06。2 回目の試み（Draft PR #82、`9aa93169`、フェーズ A 実装済み）への回答。この節が本文と Amendment 1 より優先する）

1. **`src/cfd_sdf/` は登録済みの source closure。** `scripts/analyze_grid02.py`（`required_file_paths`）と `scripts/analyze_lowdim03.py` は `src/cfd_sdf/**/*.py` と `julia/CFDSDFWaterLily/src/*` を **現在の tree から列挙**して凍結 `file_hashes` に含まれることを要求するので、`src/cfd_sdf/` にファイルを 1 つ足すだけで GRID-02 の 2 node が落ちる（2 回目の残り 2 件はこれ）。歴史テストの例外は **不要・不許可**。代わりに **パッケージを `src/cfd_sdf/scene/` から新しい top-level package `src/cfd_gen/scene/` へ移す**（`src/cfd_gen/__init__.py`、`src/cfd_gen/scene/{__init__,primitives,scene,events,gates}.py`。import は `cfd_gen.scene …`）。`src/cfd_gen/README.md` に「`src/cfd_sdf` と `julia/CFDSDFWaterLily/src` は歴史 freeze の列挙対象なので、GEN-01 の新コードは `src/cfd_gen/` と `julia/CFDSDFWaterLily/gen01/` に置く」と 2〜3 行書く。`cfd_sdf` の既存モジュール（`SDFDesignState` など）は従来どおり import して使う。テスト `tests/scene/` は import 先だけ直す。`src/cfd_sdf/` には 1 byte も残さない（`git mv` 後に `src/cfd_sdf/scene/` が存在しないこと）。
2. **フェーズ B の置き場所も変わる**：`problem_spec_v3.py` は `src/cfd_gen/problem_spec_v3.py`（v2 の `src/cfd_sdf/problem_spec.py` は読むだけ）。harness v1.2 は **新規ファイル優先**（例 `src/cfd_harness/campaign_v12.py` が v1.1 を wrap）とし、既存 `src/cfd_harness/*.py` を編集する場合は全体 pytest の失敗集合が host の base と同一であること（4 項）で示す。フェーズ B は別 PR のまま。今回の呼び出しはフェーズ A の移設と再検証まで。
3. **commit／push は Claude が host で行う。** 2 回目の `GIT_INDEX_FILE`＋`commit-tree`＋`update-ref` の経路は今後使わない。Codex は `git mv` も `git add` もせず、ファイルシステム上で移動（`mv`）と編集だけを行い、報告の「作ったもの」に commit すべきファイルの完全な一覧（移動元→移動先、変更、新規）を書く。worktree の通常 index は Claude が `9aa93169` に同期済み（`git status` は clean から始まる）。
4. **全体 pytest**：結果側だけを `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` で **完走**させ、失敗 node 集合（期待：空）を報告に書く。base は Claude が host で取得済み（e3dcdf61、3482 passed / 74 skipped / 0 failed、`tests/test_lbm_metal.py` を ignore）。Codex は base を取り直さない。2 回目の CPU profile plugin（`wp06_cpu_only_pytest.py`）は使わず、`--ignore` で揃える。
5. **記録**：`reports/wp06_report.md`・`wp06_validation.json` を更新し（2 回目の表と検証結果は残してよい）、状態を DONE（フェーズ A）にできるか判断する。Draft PR #82 の本文は Claude が更新する。新たな矛盾が見つかった場合だけ、その箇所を具体的に示して止める。

## Amendment 3（2026-11-06。3 回目（フェーズ A DONE、PR #82、`6536cbf0`）への Opus source review の回答。この節が本文と Amendment 1・2 より優先する。フェーズ B はまだ始めない）

review 全文：`/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1/docs/codex/gen01_w1_2026_11_06/reviews/wp06_review_1_opus.md`（読む。再現スクリプトの説明も含む）。計画本文の更新は同じ worktree の `docs/gen_system_plan_2026_11_01.md` §3.1 の「距離の契約の実装形（2026-11-06 b）」（読む）。verdict は INTEGRATE_AFTER_FIXES（MAJOR 4）。次を直す。

1. **M1。** envelope・clearance・forbidden mask・root の gate は **可動部品（`scene.components`）だけ**に適用する。fixed（タイヤ、ボディ、地面）は対象外。可動 vs fixed の対 gap 検査はそのまま。fixed のタイヤ stand-in（z=0 に接する）を含む scene で翼が通るテストを足す。
2. **M2。** `merge_candidates` は b を a の中央へ丸ごと移動しない。**最近点方向への最小移動**（gap ＋ 宣言した重なり δ）で接合する（または bridging 規則）。同一でない main＋flap の merge が scene gate を通るテストを足す（現在のテストは同一パラメタの 2 枚で退化している）。
3. **M3。** `element_count_designs` の分割は親の footprint を保つ（子の弦 = (L − t − gap)/2）。4h 既定で N=1..5 が全部 gate を通るテストを足す。
4. **m1。** gap の guard は片側（標本化した d は真の gap の上界なので、d < g_min なら確定 fail）。
5. **m3。** 厚さの床は要素ごと（`_normal_width` から導く）に取り、knock-out 判定と gate で同じ床を使う。
6. **m7。** 正の対照（Birth-0 の有効な seed が `evaluate_scene_gates` を通る）、限界位相（t=4h、gap=4h、16 位相）、fixed 付き、N≥3、非同一 merge のテストを足す。
7. **M4（記録と最小の修正）。** `Scene.sample` の 2,000,000 node 超は例外ではなく gate の `unmeasured` 記録（理由付き）にする。R3 の 8M node cap（3D の MW-01 規模では常に unmeasured）、`MeshBody.phi` の O(点 × 三角形) と毎回の STL 再 hash は **既知の限界**として `src/cfd_gen/README.md` と報告に数値付きで書く（修正は MW-01 の前の別 WP）。
8. **m2。** `MergedElement` は band 内の距離契約の例外であることを gate の記録（`distance_contract_exemptions: [ids]`）に明示する（計画本文にも書いた）。
9. **m4。** joint 規則と endplate の knock-out は `PlateElement`／`MergedElement` に限る（BoxBody は対象外）。
10. **m5。** hash の正規化：`-0.0` を `0.0` に正規化、STL の path 文字列は hash に含めない（STL SHA だけ）、`MergedElement` の id も ID regex に通す、拒否理由の区切りを `:` 以外（例 `|`）にして ID と曖昧にならないようにする。
11. **m6／n6。** BoxBody の内部 continuation の docstring を実態（連続だが ray 単調ではない、球は厳密）に直す。`_finite` の alias を消し、ID validator を 1 つにし、空 scene の早期 return にも `scene_sha256`／`state_sha256` を入れる。
12. **n3。** `downstream_seed_positions` は符号付き offset（後縁の下流かつ上／下の両方）を取り、policy が許す象限を宣言する（既定：両方）。
13. **n2。** 報告の「v18 と 1e-3c 以内」は無変形板だけの話と明記する。
14. **全体 pytest**：結果側だけを `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` で完走させ、失敗 node 集合（期待：空）を報告に書く。
15. **commit／push は Claude が host で行う。** worktree は `6536cbf0`。報告に commit すべきファイルの完全な一覧を書く。

## Amendment 4（2026-11-07。4 回目（PR #82、`6dcd7c62`）への 2 回目の Opus review の回答。round-1 は 13 closed・1 partial。この節が本文と Amendment 1〜3 より優先する。小さな修正だけ。フェーズ B はまだ始めない）

review 全文：`/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1/docs/codex/gen01_w1_2026_11_06/reviews/wp06_review_2_opus.md`。

1. **N1。** 厚さ gate と端板接合 gate も **可動部品だけ**に適用する（M1 と同じ範囲。`scene.bodies` ではなく `scene.components`）。fixed の STL／端板は gate の対象外で、context の解像度は別の記録項目に残す。fixed STL タイヤ＋fixed 端板＋翼の scene が通るテストを足す。
2. **N2。** merge 提案は **16 位相すべて**で gate を通ることを要求する（提案の採否が位相に依存しないように）。既定の重なり δ は **t_min/2 以上**（review の反例では δ = t/2 で 16/16）。斜めの接合（約 0.35 rad の main＋flap）での 16 位相テストを足す。
3. **N3。** 分割の既定 gap を「g_min ＋ gate の guard ＋ キャンバーの余裕」にし、角度付き（0、−10°、−20°）かつキャンバー付きの N=1..5 が 2D／3D で gate を通るテストを足す。報告の「N=1..5 がすべて合格」は条件（角度・キャンバー）を明記した文に直す。
4. **N4。** `thickness_knockout_ids` の scalar fallback は平板（camber = reflex = 0）に限定するか削除する。`_nearest_boundary_pair` が収束しない対は **その対だけ skip して理由を記録**し、scene 全体の merge 提案を止めない。所要時間（1〜2 s／対、強いキャンバーで 24〜26 s）は README の既知の限界に書く。
5. `tests/scene` と関連の重点テストを回す。全体 pytest は **不要**（変更は scene package とテストだけ。`src/cfd_sdf`・`julia/`・`scripts/` を触らないことだけ報告する）。
6. **commit／push は Claude が host で行う。** worktree は `6dcd7c62`。報告に commit すべきファイルの一覧を書く。
