# Stage S Work F — post-A1 architecture memo (0-run)

作成日: 2026-09-25

対象: [`stage_s_work_f_post_d3_plan_2026_09_25.md`](stage_s_work_f_post_d3_plan_2026_09_25.md) §21.5--§21.6 /
[`phase_plan.md`](phase_plan.md) / [`problem_register_2026_09.md`](problem_register_2026_09.md)

状態: D4.4 と A1 の fail を受けた architecture fork。solver を追加で流さず、次に選び得る
二案だけを比較する。ここでは候補を選定しない。選定は新しい登録済み計画で行う。

## 1. 確定した状態

```text
derivative_qualified=false
shape_update_allowed=false
```

- E-SI (`sensitivityType surface`) は 32-primal FD campaign で完全 qualification に届かず、
  単一 option の ablation では説明できなかった（D4.3/D4.4）。
- native FI (`sensitivityType shapeFI`) は A1 で単独実行し、lineage・schema・convergence は
  pass したが、条件を満たさなかった
  ([`evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json`](evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json),
  SHA-256 `de814a57de1a55f8cc1e4cee7039874d80af0f58e24d76692cd76bf914f0ed92`)。
  - pass control の悪化: downforce gradient-aligned `1.0409 -> 1.1333`、
    drag downforce-gradient-aligned `1.0266 -> 1.0861`。
  - failing row の残存: downforce seed2026 `0.9094`（9.1% 外）、drag seed2026 `1.5798`（58% 外）。
  - component の入れ替わり: `dxdbVol` が非ゼロ化し `dxdbSurf` がゼロ化したが、`dSdb` は
    E-SI と同一値のまま。total は双方の差を説明できない。
- v2512 image の shape sensitivity は連続随伴の 4 種のみである
  （`shapeESI` base、`surface`、`surfacePoints`、`shapeFI`）。image 内に discrete adjoint
  の実装は存在しない。名称だけの「discrete adjoint」は候補にならない。

## 2. 許可されている二案

### 案 1 — 別 sensitivity 経路

要件（登録時に具体化する）:

- 同じ discrete primal residual/response に整合する sensitivity 実装であること。
- 利用可能な solver/toolchain が実在すること（現 image には無いため、追加実装か別
  toolchain の evidence が必要）。
- registered V1 baseline を再現できること（Cd `2.5234065`、downforce `1.690821`、
  mesh は不変）。
- full gradient の取得コストを見積もり、登録予算内に収まること。
- 同じ centered-FD contract（epsilon ladder、plateau、sign、near-zero）で資格化できること。

リスク: 実装コストが最大。既存コードパスが無い。効果は未知。

### 案 2 — 低次元 parameterization + centered FD 経路

要件（登録時に具体化する）:

- 設計空間を K 個の smooth mode（K << 648）として事前登録する。既存 B-spline の修正では
  なく、新しい design-space contract とする。
- 1 gradient あたりの primal 数は mode あたり plus/minus の `2K`。観測済み primal 時間
  （約 22 s）では `K=16` で約 32 primals / gradient となり、既存 32-primal campaign と
  同程度の予算で運用できる。
- 形状表現力は 648-var B-spline より低い。registered geometry gate（minimum solid width
  `0.05 m`、clearance、checkMesh profile `concave <= 0.06128`）を満たすことを
  mode 登録時に確認する。
- FD がそのまま gradient になるため、analytic-vs-FD 不一致のクラスが存在しない。
  ただし mode ごとの epsilon ladder、plateau、sign、near-zero、holdout は同じ規律で
  登録する。
- D5/D6/D7 に相当する holdout・requalification・one-step gate を新しい basis で最初から
  登録する。旧 648-var 結果を継承しない。

リスク: 表現力と最適化性能のトレードオフ。mode set ごとに契約と preflight が必要。

## 3. 両案に共通の固定条件

- primal、mesh、drag/downforce objective、Aref/rhoInf/UInf。
- 5%・sign・plateau・near-zero の判定規則。
- geometry/clearance/mesh gate と one-step manifest の discipline。
- shape update は、選定した architecture の下で holdout と requalification が完全 pass し、
  D7 相当の one-step manifest が別途登録されるまで禁止。

## 4. 禁止事項（両案に共通）

- E-SI と FI の混合、option の組合せ探索。
- fitted component scale、response 別補正、方向別補正。
- 既存 4 directions への合わせ込み。
- parameterization-only の変更を第一選択にすること。
- 原因診断と資格化の混同。

## 5. 判断の記録

- A1 は `candidate_formulation_supported=false` で終了した。
- 本メモは二案の比較条件を登録するだけであり、どちらも未選択である。
- 次の solver campaign は、案 1 または案 2 のいずれかを新しい immutable contract として
  登録した後にのみ開始する。現時点で新しい run は 0 である。
