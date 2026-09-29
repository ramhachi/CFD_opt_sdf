# Issue #28 (SDF-02) 中間報告

Status: 中断時点の記録。証跡 JSON、pytest テスト、最終結果メモ (`28_result.md`) は未作成。以下の数値は探索的な実行 (スクラッチ) で得たもので、契約上の証跡ではない。

## 完了したこと

- ブランチ `feat/issue-28-sdf-reinit` を `origin/codex/kaggle-batch-migration` (aa2e9d5) から作成。
- 事前登録コミット 70284b1: `docs/sdf_native_reinitialization_contract_v1_2026_09.md` と `src/cfd_sdf/design/sdf_reinitialization.py` の契約定数 (許容値、method 文字列) を、数値証跡が存在する前に commit・push 済み。
- `sdf_reinitialization.py` に演算子本体を実装 (WIP、未 commit だった分を今回 commit)。
  - `reinitialize_sdf(state, profile, fail_closed)` / `reinitialization_report(before, after, profile)` / `edge_crossings`。
  - 既存の `SDFDesignState.create`、`sharp_volume_m3`、`smoothed_volume_and_gradient`、`classify_topology_events` を再利用。新規抽象なし。

## 手法と選定理由

- 手法: 界面隣接ノードを辺のゼロ交差 (副セル) で初期化し、符号側ごとに決定論的な Jacobi 型 Godunov Eikonal 緩和を行う。
- 理由: 依存追加なしで numpy のみ。ベクトル化されバイト決定論的で、固定点 (値が変化しない) が厳密な停止判定になる。fast sweeping は Python ループが必要、PDE 法は界面が動き固定点判定がないため見送り。
- 手法の修正 (事前登録コミット後、証跡実行前): 初版は 1 次 Godunov。球フィクスチャの探索実行で solid 側 Eikonal p50 が 0.063-0.075 となり登録許容値 0.05 を超えた。平面フィクスチャの誤差は 0.2h 以下 (実装バグではないと確認)、正確な種値を与えた球でも solid 側で平均 -0.087h の過小評価が出たため、1 次 upwind の固有誤差と判断した。そこで Sethian 型の 2 次後退差分 (第 2 upwind ノードが値以下のとき使用) に変更した。**許容値は一切変更していない。** この変更で契約ペイロードのハッシュが変わった (下記)。

## 契約許容値 (固定済み、変更なし)

Band = |phi|<=3h、格子境界ノード除外、中心差分。

- fixture Eikonal `||grad phi|-1|`: p50 0.05 / p95 0.25 / max 0.50 (fluid・solid 両側)
- canonical Eikonal: fluid 側のみ p50 0.10 / p95 0.50 (max なし)
- ゼロ等値面変位: 辺交差分率 t の最大変化 0.25、unmatched 交差 0
- sharp/smoothed 体積の相対ドリフト: 0.05
- マスク完全一致、符号変化 0、node/cell-center のトポロジーイベントなし、成分数一致
- 冪等性: band 上 max|R(R(x))-R(x)| <= 0.10h

## 測定した事実

canonical v16 の入力 (読み取り専用):

- `/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v16/sdf_design_state.npz`
- ファイル SHA-256 `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`
- state_sha256 `44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`
- phi_sha256 `45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785`
- shape 61x33x25、h=0.05、origin (-1.0,-0.8,-0.6)、design_mask 12495 点、fixed/forbidden/root マスクは空。

入力 phi の構造 (直接読み取り、演算子は未適用):

- phi<0 は 1420 点で、値は 1007 点が約 -1e-16 から -0.0 (浮動小数点ノイズ級の負値)、413 点が -0.05 ちょうど。phi==0 は 109 点、phi>0 は 48796 点。
- 固体内部のほぼ全域が phi≈0 で、真の SDF (固体内部で負の距離) になっていない。#36 の `|grad phi|≈2.9e-7` の平坦領域と整合する構造。ただし力レベルの因果は未検証。
- 固体は 26 近傍で 1 成分 (1420 点)。
- band (|phi|<0.1) 3682 点の中心差分 |grad| は p5 0.50、中央値 0.87、p95 1.02。固体内部の phi≈0 領域 (1344 点が |phi|<1e-7) は band 外の扱いのものを含み、この集計では平坦領域を分離していない。

解析フィクスチャ (41^3、h=0.05、探索実行、2 次版演算子):

- 球 (格子中心・非整列) は全 gate 通過。ゼロ等値面変位 max 0.044-0.077 (辺長=1)、sharp 体積ドリフト -0.0% から -1.0%、冪等性 0.042-0.094h、解析解との band 誤差 max 0.16-0.39h。
- 球の Eikonal (2 次版): fluid p50 0.008-0.010、solid p50 0.032-0.037、p95 0.062-0.091、max 0.09-0.34 (いずれも許容値内)。
- 入力を正のスカラー場 (1+0.6 sin3x cos2y+0.3z) でスケールした「強い歪み」入力では、smoothed 体積ドリフトが -4.9% から -9.9% になり、球の一部と box で 0.05 を超えた。smoothed 体積は phi の大きさに依存するため、入力の大きさ歪みに由来する。演算子は fail-closed で reject する挙動になる。
- box フィクスチャは面が格子点上にあり phi が厳密に 0 になるため、strict `phi<0` 規則で固体が 1 セル分縮み、ゼロ等値面変位 0.5、冪等性 0.5h で失敗した。これはフィクスチャ設計の問題 (面をずらす必要あり)。
- 2 球フィクスチャは間隙 0.26 m (5.2h) で fluid 側の medial axis が band (3h) に入り fluid max 1.0 で失敗。間隙を広げる必要あり (フィクスチャ設計の問題)。

契約ハッシュ:

- 事前登録コミット時の `REINIT_CONTRACT_SHA256` は `590820800283dba25b188c2f25b76b589bf0b94f541fdc4625cbc8a60a538db0` (契約 doc に記載中)。
- 2 次版への修正後は `ba1c02f9d1e8696e4ad32c9c55fa3ce961356a06d67f1165b6cff2e905d5b25e`。**契約 doc のハッシュは未更新で、現在コードと不一致。**

## 未実施・未検証

- canonical v16 への演算子適用と Eikonal 品質・体積ドリフト・トポロジーの測定 (未実行)。gate の合否は不明。
- 証跡 JSON と `.sha256` sidecar、`tests/test_sdf_native_reinitialization.py`、`docs/issues/28_result.md`。
- フィクスチャの修正 (box の面オフセット、2 球の間隙拡大)。
- 契約 doc の更新 (2 次版の手法記述、新ハッシュ、手法修正の経緯の追記)。
- 全体 pytest (既知のベースライン失敗 37 件との比較) は未実行。
- 退化辺 (|pa|+|pb|<1e-7 m を t=0.5 とする規則) の canonical v16 での件数は未測定。
- 入力 phi のノイズ級負値 (約 -1e-16) に対する符号規則の影響は未評価。

## 推奨する次の手順

1. 契約 doc を 2 次版に合わせて更新し、新ハッシュと手法修正の経緯 (許容値不変) を記録して commit。
2. フィクスチャを修正 (box を格子点からずらす、2 球の間隙を 8h 以上に)。強い歪み入力は「smoothed 体積 gate で fail-closed になる」ことを確認するテストとして使う。
3. canonical v16 に `profile="canonical"`, `fail_closed=False` で適用し、入力 SHA-256 と共に証跡 JSON + sidecar を新規保存。gate 結果は許容値を変えずにそのまま報告。
4. テストと `28_result.md` を作成し、全体 pytest を 1 回実行して新規失敗ゼロを確認。
5. #36 への含意: 入力 phi の固体内部が phi≈0 で平坦であることは演算子適用前の入力の事実。演算子出力の平坦領域解消は canonical 実行後に測定して初めて言える。#37 への含意は canonical の結果次第。
