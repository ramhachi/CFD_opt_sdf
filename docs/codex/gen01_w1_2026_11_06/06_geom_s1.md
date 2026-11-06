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
