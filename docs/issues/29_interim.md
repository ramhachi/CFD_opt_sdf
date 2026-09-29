# Issue #29 (GEOM-01) 中間報告

ブランチ: `feat/issue-29-geom-gates` (base: `origin/codex/kaggle-batch-migration`)。
状態: **WIP。実装とテストは書いたが、一度も実行していない。** pytest、コンパイル、v16 artifact 生成のいずれも未実施。

## 完了したこと
- issue #29 / #30 / #31 / #32 の読解、既存コードの調査。
- `src/cfd_sdf/design/geometry_gates.py` を新規作成 (未実行)。
- `tests/test_sdf_native_geometry_gates.py` を新規作成 (未実行)。

## 未完了のこと
- 上記コードの import・実行確認、テストの修正。
- 契約 doc `docs/sdf_native_geometry_gates_contract_v1_2026_09.md` (未作成)。
- v16 用 artifact 生成スクリプトと artifact (JSON + `.sha256`) (未作成)。
  テストは `docs/evidence/sdf_native_geometry_gates_v16_2026_09.json` を参照するが、このファイルは存在しない。現状ではそのテストは落ちる。
- 結果メモ `docs/issues/29_result.md` (未作成)。
- 全体 pytest (未実施)。新規失敗ゼロの確認もできていない。

## gate 一覧 (geometry_gates.py に実装、未実行)
sdf_finite_structure / sdf_distance_property / sdf_boundary_margin / mask_preservation / component_connectivity / topology_change_classification / min_feature_width / inter_component_gap / export_surface_integrity / surface_self_intersection / domain_clearance / volume_semantics。
各 gate は pass / fail / unmeasured を返し、全体は AND。unmeasured は fail と同様に受理を止める。

## 閾値の出所 (コード上の設計。結果を見る前に固定したもの)
- 最小 solid/void 幅、最小 gap、root、max_components: `SDFTopologyPolicy` (ProblemSpec v2) から取得。None なら unmeasured。
- volume 上限: 呼び出し側引数。v16 では `SMOOTHED_VOLUME_LIMIT_M3` (#27 で登録済み)。None なら unmeasured。
- 物理 clearance (`min_clearance_m`) と eikonal 許容 (`eikonal_median_tolerance`): 引数。未登録なら unmeasured。Stage V の 0.25 m は継承していない。
- 構造的定数 (この contract で固定): `BOUNDARY_MARGIN_CELLS=1`、表面体積相対許容 1e-6、超サンプル 4、長さ許容 1e-9 m、自己交差検査の三角形上限 12000。

## 再利用 / 再実装の判断
- 再利用: #31 の `evaluate_sdf_topology_transition` (違反文字列を gate に分配)、#27 の `volume_semantics` (`sharp_volume_m3`、`smoothed_volume_and_gradient`、`_corner_mean`)。
- コピー: `extraction_qualification._triangles_self_intersect` と補助関数群 (P20 で修復済みの検出器)。Stage S/PQ4 モジュールへの依存を避けるため。解析フィクスチャでの再検証テストは書いたが未実行。
- 再実装: 最小 feature 幅 (DF0 の ridge 統計と同じ方式を 4x 超サンプル EDT で再実装、境界は edge padding)。component 間 gap は `component_boundary_gap_m` を再利用せず、26 近傍膨張 + EDT で再実装。
- gap を再実装した理由 (コード読解による推論。未実行): 既存関数は Euclid 最近傍の cell 対を選ぶため、cube 面距離が最小の対を逃して gap を過大評価しうる。反例 A={(0,0,0),(0,1,1),(1,2,2)}, B={(3,0,0)} で既存は 2h、正しくは sqrt(3)h。テストに記載したが、既存関数での実測は未実施。
- export 表面: VTK surface nets (`contour_labels`、smoothing なし) を cell occupancy に適用。PQ4.1 v2 の handoff と同じ抽出器。

## 測定した事実 (v16。読み取り専用で確認したもの)
- 入力: `work/sdf_native_genesis_v16/sdf_design_state.npz`、SHA-256 `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`。genesis evidence 記載の `state.state_file_sha256` と一致。
- state_sha256 (evidence 記載): `44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`。
- shape (61,33,25)、origin (-1.0,-0.8,-0.6)、spacing 0.05、narrow_band_width 0.05、generation 0、topology_policy_id は `sdf_native_topology_policy_v1` (内容ハッシュ束縛なし)。
- phi は強く量子化されている。`phi<0.1` の値集合は {-0.05, 0, 0.05, 0.0707, 0.0866, 0.1}。voxel 由来の truncated SDF で、厳密な距離場ではない可能性が高い (eikonal の実測は未実施)。
- node occupancy (phi<0): 1420 node、26 近傍で 1 component。cell occupancy (中心 trilinear 平均 <0): 1009 cell、1 component。cell の index 範囲は (8,7,7) から (29,24,16)。
- genesis evidence 記載: root / fixed_solid / forbidden の mask cell 数はすべて 0。
- 境界層の phi 最小値は 0.35 以上 (x 面 0.39999998、y 面・z 面 0.35 と 0.35000002)。
- 以下は未測定: 最小 feature 幅、component 間 gap、export 表面の健全性、自己交差、clearance、eikonal 偏差。

## 未検証事項
- geometry_gates.py が import できるか、テストが通るか。
- fixture の cell 中心サンプルが exact zero にならない設計 (FACE_OFFSET=0.2) が意図どおり動くか。
- surface nets が edge 接触 voxel で非多様体 (edge の面数が 4) を出すか。頂点が結合されるか。
- void 幅の ridge 測定が、ドメイン全体の流体に対して偽の小さな値を出さないか。
- 自己交差検出器の Python ループが v16 規模の三角形数で実用時間か。
- v16 で node 数と cell 数の component 数が一致すること以外の整合性。

## 次にやること (推奨順)
1. `geometry_gates.py` を import し、fixture テストを 1 つずつ通す。落ちた fixture は期待値の誤りか実装の誤りかを切り分ける。
2. v16 用スクリプト `scripts/sdf_native_geometry_gates_v1_2026_09.py` (既存の `sdf_native_volume_semantics_v1_2026_09.py` の書式を踏襲) で artifact を生成し、SHA-256 sidecar を付ける。policy は `unresolved_registration()`、parent は state 自身 (identity)、volume 上限は `SMOOTHED_VOLUME_LIMIT_M3`。
3. 契約 doc と `29_result.md` を書く。
4. 関連テストを通したうえで、全体 pytest を 1 回だけ実行し、`baseline_fail.txt` と比較する。
