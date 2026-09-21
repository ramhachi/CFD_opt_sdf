# DF0–DF7 実行計画 — 2026-09-21

Status: **historical implementation plan; DF0--DF6 component slices were
implemented on 2026-09-21.** The active next-work plan is PQ0.1/PQ0.2/PQ1.1/PQ2--PQ6 in
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md),
subordinate to [`phase_plan.md`](phase_plan.md).

Scope: concrete slice-by-slice implementation plan for the adopted DF0–DF7
work packages, grounded in the current repository state and external
primary-source research.

This document is retained to explain why the DF0--DF6 modules were built. Its
repository-state table and "next action" section describe the pre-implementation
snapshot and must not be used as current status. DF7 was not completed.

Authority: `phase_plan.md` remains the sole roadmap/status authority. This
document adds execution detail (target files, test slices, research
resolutions, decision points) and introduces no new numeric thresholds;
registered qualification-profile values are only referenced, never duplicated.

---

## 1. 前提の把握（本計画の根拠になった調査結果）

### 1.1 repository 実装の現状（検証済み箇所）

| 領域 | 現状 | 場所 | DF |
| --- | --- | --- | --- |
| 目的関数の hard-code | `objective_gradient = -d(downforce)/d(rho)` が固定配列名として読まれる。ProblemSpec terms には未接続 | `src/cfd_sdf/fixed_grid_optimizer.py:155-159`, `:941-969` | DF1 |
| 受理判定が線形化のまま | `_linearized_prediction` で制約をチェックするが、reject でも artifact は `ok: True` で書かれる。受理制御は advisory | `fixed_grid_optimizer.py:853-876`, `:202-204`, `:275-277` | DF3 |
| identity profile | `rho_filtered = rho_projected = rho`、`alpha = beta_max * rho`、`beta_max` は median 推定 | `fixed_grid_optimizer.py:879-896`, `:1029-1038` | DF1 |
| backend | `projected-gradient`（Dykstra 型投影）と `slsqp-linearized`。`production_gcmma: False` を明記 | `:22-30`, `:574-581`, `:753` | DF3/DF6 |
| restart | `topology_state.json` lineage あり。runner 復元は stub(`copy_optimizer_step_artifacts`)。iteration loop は src に存在しない | `:899-921`, `:1087-1098`; loop 実体は `scripts/stage_t_filtered_ramp.py:350-410` | DF3 |
| ProblemSpec v2 | objectives / constraints / term aggregation / topology policy / legacy migration 完備 | `src/cfd_sdf/problem_spec.py:163-183`, `:975-1091` | DF1 の入力は既に揃っている |
| transform | ConeFilter（物理半径・転置あり）/ tanh projection / RAMP / chain rule は script 内にあり自己検証済み。BlockFilter は divisor 丸めあり | `scripts/stage_t_filtered_ramp.py:107-217`, `:164-211` | DF1 の移行元 |
| artifact lineage | `GradientBinding` と semantic validation はあるが transform/iterate provenance フィールドがない | `src/cfd_sdf/fixed_grid_artifacts.py:51-64`, `:389-452` | DF1 |
| drag sensitivity ゼロ充填 | 面: `drag_sensitivity_mode = "zero-filled-not-provided-by-faceSensNormal"`。cell: `topOSensas1` を読むため cell path は nonzero | `src/cfd_sdf/openfoam_sensitivity.py:18`, `:92`; `fixed_grid_sensitivity.py:141-233` | DF2/DF4 |
| 抽出損失 | density → iso-surface で体積 8–12% 損失の記録あり | `src/cfd_sdf/handoff.py`; `docs/evidence/binarized_ranking_2026_09.json:109-121` | DF4 |
| WP6-2 manifest 矛盾 | purpose `>=0.15 m` vs definition `>=0.10 m`、`extraction_sensitivity: {}`、17-shape verdict `unresolved` を再確認 | `work/fixed_shape_ranking_2026_09/reachable_set_ranking_manifest.json:5,7`; `docs/evidence/reachable_set_cross_fidelity_ranking_2026_09.json` | DF0（P18 既登録: `problem_register_2026_09.md:49,60-94`） |
| 数値閾値の所在 | grid convergence downforce absolute 5e-3、stationarity profile はコード内 versioned profile のみ | `src/cfd_sdf/cfd.py:99-139` | DF2/DF5 はここだけ参照 |
| テスト層 | artifacts/spec は厚い。optimizer は 4 tests（accept-path・restart・spec-driven なし）。`stage_t_filtered_ramp.py` と handoff E2E に pytest なし | `tests/test_fixed_grid_optimizer.py` | 各 DF で補完 |

### 1.2 外部一次資料の再確認（2026-09-21 時点）

1. **OpenFOAM adjoint（v2312+ user manual, `sensitivitySurface.C`）**
   - `sensitivityType surface` は adjointSolver ごとに独立した
     `faceSensNormal<solver-suffix>` を書く。drag と downforce を並列 adjointSolver として
     宣言し、各 solver suffix のフィールドを読めば両応答の surface sensitivity が得られる。
     現在の `openfoam_sensitivity.py` のゼロ充填は「solver を 1 本しか走らせていない /
     フィールドを 1 個しか読んでいない」実装選択の産物であり、solver 能力の欠如ではない。
   - `includeSurfaceArea true`、`includeMeshMovement true`（E-SI 定式化）、
     `smoothSensitivities`（Helmholtz smoothing, `meanRadiusMultiplier`）を明示設定する。
     符号規約（法線は fluid→solid、正=法線の逆方向へ動かす）を artifact の mode として
     記録する。
   - `sensitivityType volumetricBSplines` + RBF/Laplacian morpher は DF4 の第1選択肢
     （body-fitted morphing baseline）に直結する。OpenFOAM の shape optimisation
     tutorial（DrivAer 等）が fixture 雛形になる。
2. **MMA / GCMMA**: `mmapy`（PyPI 0.3.1、Svanberg MATLAB 移植、依存は numpy/scipy、GPL-3）
   と使用例リポジトリ `TopOpt-MMA-Python` が存在。DF6 の選択肢は
   (a) `mmapy` を利用し license class = GPL-3 依存を evidence に登録、
   (b) Svanberg 1987（と MMA/GCMMA 講義ノート）を一次文献に自前の minimal MMA を所有
   （数百行規模、bounded trial 提案に限定）。DF3 では既存 SLSQP adapter を検証用に維持し、
   DF6 で決定する。どちらでも trial は bounded 提案のみ、受理は DF3 の controller が行う。
3. **Brinkman / RAMP**: phase_plan 2026-09-12 で既に「`alphaMax` を飽和膝に下げ + RAMP
   `q = 8→30→100` 再ベースライン」が実測で有効とされている。新規調査は DF6 の robust
   three-field（Wang, Lazarov, Sigmund 2011）と高 Re の Darcy–turbulence 相互作用
   （Wu & Zhang 2024, Aerospace 11:525）に限る。robust 三場（eroded/intermediate/
   dilated）だけが solid/void 両側の length scale を保証する既知の定式化である。
4. **Control-volume force 診断**: Nangia et al. 2017 の moving CV は Stage T の Brinkman
   体積力との整合確認用診断として DF2 に含める。CV sweep は力抽出の整合検査であり、
   物理の証明器にはならない。

### 1.3 結論

着手順は architecture plan と同じ DF0 → DF7。各 slice は
「1 slice = 1 reviewable diff = 1 feature branch」で実行する。各 slice 完了時は
AGENTS.md の検証コマンドで締める。

---

## 2. Slice 実行計画

### DF0 — 証拠境界と実験登録の修復【最初の slice、単独 merge】

**現状 → 目標**: WP6 / WP6-2 / 17-shape の主張範囲が、manifest の宣言・実寸法計測・
machine verdict と一致した状態を作り、P18 closure record を出す
（`problem_register_2026_09.md:60-94` の5条件に対応）。

**ステップ**
1. **計測スクリプト**: `scripts/measure_shape_feature_sizes.py`（新規）。
   登録8形状 + 17形状プールの各定義 STL/mask に対し、EDT + Hildebrand local thickness
   分布、連結成分数/体積、パート間 gap、self-intersection を計算し、
   `work/evidence_audit/wp6_2_feature_sizes.json` に candidate × part ×
   percentiles（min/p5/p50）で出力する。union parts は分解して part 単位の厚み分布を
   必ず持ち、複合形状を単一 thickness 値にまとめない。
2. **再監査 audit command**: `scripts/audit_wp6_2_reports.py`（新規）。
   - manifest `purpose` と `definition.reachable_set` の不一致を明示的な fail item にする。
   - `extraction_sensitivity` が空の block は `not_measured` に置換（ゼロとして扱わない
     ことを fail-closed に強制）。
   - 17-shape pooled verdict `unresolved` と prose 中の肯定的主張を突合し、不一致は exit 1。
   - candidate 別 V1→V2 drift 表（8形状 × downforce/drag）を既存 artifact から再計算し、
     継承 0.0147 帯を超える候補を列挙。共通 band の使用は冗長条件化こめて index 別
     一致を宣言した場合に限る。
3. **preregistration schema**: optimizer-generated shapes 用の最低記録 field
   （candidate hash, transform hash, thresholds used, local feature size p5, connected
   components, extraction threshold rule）を JSON schema 草案として
   `docs/optimizer_shape_preregistration_v1.md` に置く。
4. **P18 closure**: 1–3 の結果を `docs/evidence/wp6_2_evidence_audit_2026_09.json`
   に置き、problem_register の P18 節に closure 条件5項との照合表を追記する。closure
   するか、scope-bounded monitoring で閉じるかは照合結果で決める。
   **歴史的 evidence artifact は書き換えない。**
5. テスト: `tests/test_evidence_audit.py` —(a) 不一致 manifest を fail として再現、
   (b) `not_measured` がゼロ扱いされたら fail、(c) feature-size 計測が既知の
   0.10 m 板を計測通して通る。純 Python fixture、solver 実行なし。

**合格**（architecture plan §DF0 と同一、machine-checkable 化）:
- 8形状 + 17形状の p5 feature size が該当 manifest policy 帯に記録され、
  `>=0.10 m` 未満の part を含む候補は ranking claim 範囲から明示的に除外される。
- audit command の exit code が prose claim と一致する。

**停止条件**: 現行 representation で local feature size を測定できない形状が出た場合、
その形状を diagnostic 観測に固定し capability proof から外し、P18 を
scope-bounded monitoring で閉じる。

**工数**: 1–2 session 相当（solver 実行なし、純幾何・JSON・テスト）。計算費なし。

---

### DF1 — ProblemSpec compiler + DesignTransform の一本化

**目的**: 宣言問題と実行問題の一致。hard-coded downforce 目的の撤去。

**ステップ（3 本の submodule diff に分割）**
1. **`DesignTransform` module 化**
   - 新規 `src/cfd_sdf/design_transform.py`。script から移植し dataclass で所有:
     `ConeFilter`（物理半径、`HT = M K (M·/d)`）、`TanhProjection`（eta, b; b<=0 で
     identity）、`RampInterpolation`（q と continuation schedule）。`BlockFilter` は
     production path から外し、診断専用に本体を残す。
   - `fwd(rho_design) -> IntermediateStack(rho_filtered, rho_projected, beta, alpha)`
     と `bwd(g_beta) -> g_rho_design`（逆順 chain）。
   - `solver_grid_transfer`（`P @ rho`）と `P.T @ sens`（integer / non-integer 両 mode、
     既存実装を包む）も transform hash 一覧に含める。
   - 各 stage の intermediates と hash を artifact に記録する field の追加
     （`fixed_grid_artifacts.py` へ `TransformLineage` を追加。schema version は
     v2 の backwards-compatible な追加であり、置換が必要なら fail-closed に新版を出す）。
   - `scripts/stage_t_filtered_ramp.py` を thin CLI に縮小し loop/engine 本体を src へ。
     同一 filter/projection の二重実装は禁止（one-owner rule）。
   - 単位/マスク/cell-order invariants: 既存の canonical cell-order permutation 試験を
     transform 側でも回す。
2. **`ProblemSpecCompiler`**
   - `ProblemSpec` objectives/constraints/term aggregation から
     重み（response_id × flow_case）、sense、limit、bounds、aggregate `J`/`g` の値と
     勾配を生成する純関数。
   - `FixedGridOptimizer` は compiler 経由の `dJ/drho_design` を使うようにし、
     `:155-159` の固定配列を撤去。
   - compile 不可の response（moment, plugin, pressure-loss など）や未知の sense/relation
     は fail-closed 拒否。
   - volume equality → upper-bound inequality（`g_V = V_occ - V_max <= 0`）とし、
     `V_occ` を projection 後 field に定義固定。
   - efficiency 制約は compiler が所有し、`fixed_grid_sensitivity.py:190` の合成を
     接続する。
3. **`BlockFilter` production 禁止**
   - production transform への BlockFilter 指定は runtime 拒否し manifest に理由を
     書く。ConeFilter のみ production 許可。宣言最小寸法は geometry Gate で正面から
     実測する（DF0 の計測 machinery を再利用）。

**テスト**
- `tests/test_design_transform.py`（新規）: (a) ConeFilter の fwd/transpose adjoint
  identity、(b) projection/RAMP の中央差分 FD（相対誤差 1e-4 未満）、(c) transform hash
  による判定、(d) fail-closed: 未知 response / unit mismatch / sign-unknown / stale
  intermediate / transform hash 不一致 → solver 起動前 reject、(e) `V_occ` が
  projection 後 field に固定されている test。
- `tests/test_problem_spec_compiler.py`（新規）: identity fixture の手計算
  objective/constraints との完全一致、term scaling、declared/actual 不一致の fail-closed。
- `tests/test_fixed_grid_optimizer.py` 拡張: spec-driven objective、reject 時の
  rollback/trace、controller 状態記録。

**合格**: architecture plan §DF1 の合理条項そのまま。
**停止条件**: 同一 density artifact から solver field と extracted geometry の re-load
round-trip hash が一致しない場合、optimizer backend へは進めない。

**工数**: transform 移植移行は既存素材の整理が主、compiler が新規主体。3–5 session 相当。

---

### DF2 — response・力・勾配・格子の資格化

**目的**: optimizer を交絡させない primitive oracle の確立。P6 を close または bound。

**ステップ（preregistration manifest を先に書いてから OpenFOAM 実行）**
1. identity transform で OpenFOAM primitive adjoint の FD suite（§6.3 条件そのまま:
   中央差分相対誤差 5% 以下、sign 一致、4 epsilon × gradient-aligned + 2 random seeds）を
   事前登録して実行。
2. filter/projection を加えて chain rule を FD 検証（DF1 transform の使用範囲で）。
3. transfer: integer-ratio `P`/`P.T`（既存 exact-overlap 実装）の FD 検証、
   non-integer overlap transfer の検証。
   P6 の約 10% bias の診断は 3 段分解（レビュー F3 を反映）:
   (a) primal 側転写誤差、(b) adjoint 側転写誤差、(c) 両者合成、を FD で分離する。
   根拠は consistency（P と P.T の写像整合）と conservativity（積分保存）の区別
   （Farhat et al. 2004 common refinement、de Boer et al. 2008、Najian Asl et al.
   2020 — non-matching 間の nearest-element 逐次写像では adjoint 転置側に
   spurious oscillation が残る実測）。修復経路は (i) integer-ratio contract 制限、
   (ii) common-refinement 型 conservative transfer の実装、の順で検討し、
   (i) で止める判断に文献的根拠を付ける。triage は
   `problem_resolution_plan_2026_09.md` §8。
4. **固定 binary shapes の三格子 Stage T 評価**: 8-shape 集合を Stage T grid family
   （事前登録した integer-halving voxel family。レビュー F4 を反映）で再実行し、
   response ことに数値不確かさを得る。Ghasemi & Elham 2022 の実測（feature あたり
   >=7 cells で interface 力誤差 <4%）を Stage T manifest に錨として preregister
   する — ただし target physics の threshold には転用しない。multi-stage
   coarse→projection→refine procedure は cost 削減の先行例（3D で最大 45%）として
   DF3 の格子上げ方針に使う。OpenFOAM 実行 + budget manifest。
5. **同一 anchor geometry の Stage V 三格子**: plain fixed-domain family（V1/V2/V3
   qualified）を anchor candidate で再確認。response ごとに registered bound（downforce
   absolute 5e-3）と比較し、asymptotic range 内なら GCI を報告。
6. **CV momentum balance 診断**: `scripts/cv_momentum_audit.py`（新規）。
   圧力/粘性/対流/非定常/Brinkman body force の必要項を含め、CV 位置スイープを行い
   Stage V domain artifact に書く。CV 診断は response oracle の整合検査であり、
   不確かさ帯の代用にしない。

**力の構成（決定事項）**
- Stage T の設計微分と一貫する Brinkman volume force を主 response とする。
  CV force は harness 分離の diagnostic。CV と volume force の一致は
  force 抽出経路の positive check であり、calibration ではない。

**合格**: FD suite 全 pass、P6 close-or-bound、Stage T/Stage V の response 別不確かさが
候補ごとに記録される。
**停止**: downforce が refinement に対して非単調 → GCI を出さず、domain/BC/steady-
unsteady/discretisation factor study に戻る。

**工数**: 2–4 session 相当（OpenFOAM runs が bottleneck）。

---

### DF3 — 最小 nonlinear constrained Stage T loop

**目的**: 縮約 laminar 問題での最初の実再評価 feasible improvement。

**ステップ**
1. **runner 化**: `src/cfd_sdf/stage_t_loop.py` に iteration runner を作る
   （OpenFOAM primal/adjoint driver を wrapper 経由で呼び、artifact hash で lineage）。
   既存 script の OC engine / filtered-ramp engine と restore option を共有する。
2. **controller（GCMMA 型保守性 loop。レビュー F1 を反映）**:
   `NonlinearAcceptanceController`（新規 pure module）。
   - outer iteration: 勾配は 1 回だけ評価し、MMA/GCMMA 型の convex な conservative
     近似 subproblem を backend が解いて bounded trial を出す。
   - inner iteration: trial の真の目的・全制約を **実 primal 再評価** し、近似が
     conservative（Svanberg の GCMMA 実装と同型: `f̃_i(trial) >= f_i(trial)` の判定、
     ただし objective は sense 変換後に統一符号で判定）でなければ asymptote / penalty
     を保守化して同一 x 上で再解く（inner iteration で勾配は再評価しない）。
   - 受理は conservativity check + 全 hard constraint tolerance 内 + geometry Gate。
     reject → rollback + 対象 i の `rho^(k,ν+1)` 更新（GCMMA 式 (3.9) 相当）+ 同一
     parent hash からの再試行。move limit / step norm / iteration cap は事前登録。
   - SLSQP adapter は診断 reference としてこの構造と並行検証する。
   DF6 の backend 導入はこの受理数理の変更ではなく、近似 subproblem solver の
   差し替えである。
3. **restart**: optimizer state、continuation parameter、design/transform/response hash の
   full checkpoint/resume（`copy_optimizer_step_artifacts` stub の本実装に相当）。
4. **feasibility**: feasible seed を使う。seed なしで始める場合の restoration phase は
   事前登録してから使用する。2026-09-12 の OC evidence（0.7759 → 0.8213 monotonic 改良）
   が受理動作の型を提供する。
5. trace 記録: KKT residual、constraint violation、step norm、move radius、
   solver status、hash を iteration trace JSON に出す。
6. 最初の実行は architecture plan §3.1 の縮約問題
   （min J=-C_DF、g_D、g_V、g_topo、0<=rho<=1）を、primal 再評価あり 12 iteration の
   規模で走らせる。

**テスト**: controller state machine を seeded pure test で検証。OpenFOAM を使う
実 campaign は evidence run として manifest + artifact hash で分離し、mock test では
物理収束を主張しない。

**合格**: baseline より改善した feasible candidate が同 seed/config で再現でき、
各 accepted iterate の実測 constraint trace が揃う。
**停止**: 連続 reject の場合は backend 強化ではなく gradient / transform /
constraint scaling / feasibility を切り分ける。

**工数**: 3–6 session 相当 + OpenFOAM campaign。DF2 の三格子 qualification が entry
Gate。

---

### DF4 — Stage T → S 実形状移行

**目的**: topology candidate を同一性を保った sharp-interface candidate に変換し、
Stage S で drag constraint 付き refinement を行う。

**ステップ**
1. **threshold sweep runner**: `scripts/extract_threshold_sweep.py`（新規）。
   既存 `handoff.build_density_to_sdf_handoff` と `thickness_metrics` を利用し、
   事前登録した threshold range で体積、surface distance、components、
   self-intersection、feature survival、clearance を測定。threshold は最良観測での
   事後選択ではなく、事前登録 range と選択規則に従う。抽出時の体積 8–12% 損失を
   candidate-specific の extraction sensitivity として記録する。
2. **Stage S baseline（web 調査結果の反映）**
   - 第一選択: OpenFOAM `sensitivityType volumetricBSplines` + RBF/Laplacian morpher による
     body-fitted mesh morphing。tutorial 雛形から再現し、surface sensitivity を FD で
     資格化してから Python 側で line search + displacement bound を所有する。
   - surface sensitivity の取得経路: drag と downforce を並列 adjointSolver として宣言し、
     各 solver suffix の `faceSensNormal<downforce>` / `faceSensNormal<drag>` を両方読む。
     `openfoam_sensitivity.py:18,92` の drag ゼロ充填を撤去し、zero-fill mode が
     production path に残ることを fail-closed で禁ずる。符号/規約（法線方向、includeSurfaceArea,
     includeObjectiveContribution）は FD で検証してから採用する。
3. **surface optimizer**: bounded displacement、quality-aware line search、remesh policy、
   checkpoints、hash。
4. SDF/Hamilton–Jacobi 追加は「B-spline baseline で幾何自由度不足が実測された場合のみ」
   （architecture plan §9 の要求順序を維持）。CutFEM/ghost-node 比較はそれ以降。

**合格**: `ready_for_stage_s=true` の実 candidate が extraction Gate を通り、Stage S
first step の objective/constraint 変化が FD と一致し、lineage/hash が切れない。
**停止**: remesh で shape/force が extraction uncertainty を超えて変化した場合、
update を受理せず mesh/extraction layer を修正する。

**工数**: 4–6 session 相当。OpenFOAM tutorial の setup（DrivAer / wing）が最大の未知領域。

---

### DF5 — optimized candidate の独立 Stage V 検証

**目的**: baseline / Stage T candidate / Stage S candidate を独立 body-fitted
discretisation で比較し、改善量が combined uncertainty を超えるか判定する。

**ステップ**
1. 全 candidate を固定 declared domain + clearance preflight（WP1, 0.25 m margin）の下で
   3 格（V1/V2/V3 qualified profile）で実行。V0 は mesh profile 拒否を measurement として
   記録し続ける。
2. mesh quality + residual + force stationarity Gate を fail-closed。gate fail 候補が
   required pair の片方にあるなら ranking conclusion を出さない。
3. pressure/viscous/total 力、moment、flow diagnostics の分解。extraction / meshing
   sensitivity を数値格子不確かさと別 field に記録。
4. required pair は `baseline→T` と `T→S`。改善が candidate-specific combined
   uncertainty（数値 + 抽出）を超えるか判定。
5. Stage V 最細格子結果を optimization iteration の tuning signal に使わない規則を
   trace で機械的に区別（Stage V artifact への import 経路を accept loop に接続しない）。
6. 縮約 case の downforce 現状は V2→V3 drift が registered bound 5e-3 を満たさないので、
   DF2 の三格子結果が非単調でなく asymptotic range に入っていることを確認するまで、
   本 slice の ranking 主張は出さない。

**工数**: 1–3 session 相当 + heavy OpenFOAM campaign（manifest budget 内）。

---

### DF6 — robust length scale と scalable backend

**前提**: DF5 合格まで着手禁止（architecture plan §DF6）。本計画の現在位置では未着手。

**決定事項（レビュー F2 を反映）**
- **robust three-field の使用条件を正確に書く**: eroded/intermediate/dilated の
  length scale 制御は三場が同一 topology を共有する場合に限る保証であり、一貫性は
  a posteriori 確認である。solid/void 両側の同時制御には **dilated design 側への
  volume constraint 適用が必要**（Trillet, Duysinx & Fernández 2021, arXiv:2101.08605）。
  filter/projection パラメータと length scale の対応は Qian & Sigmund 2013 /
  Trillet et al. 2021 の解析式で事前計算し、試行錯誤を preregistration に混ぜない。
  robust 三場は outer iteration あたり primal+adjoint を 3 回走らせるため、budget
  manifest に 3 倍 primal cost を前提化する。filter boundary treatment は domain
  edge 近傍で length scale を崩す既知問題（Clausen & Andreassen 2017）として
  geometry Gate で実測する。
- **fallback path**: robust 三場が topology 不一致を残した場合、Zhou et al. 2015
  （geometric constraints、追加 PDE 解なし・微分可能）とその解析的
  hyperparameter 版（Arrieta, Romano & Johnson 2025, arXiv:2507.16108; SSP 併用）を
  fallback 候補として登録。nominal volume と worst-case performance/constraint の
  使用範囲は ProblemSpec で明示。projection sharpness・RAMP q・move limit の
  continuation を同時に急変させない schedule を manifest 化。
- **backend 選定**: `mmapy`（GPL-3、dependency は numpy/scipy）利用 vs Svanberg 論文
  （1987 と GCMMA FORTRAN manual）からの自前実装。選定基準は reproducibility と
  license 登録の容易さ。DF3 の GCMMA 型受理数理は維持されたまま、近似 subproblem
  solver のみを差し替える。backend 間は同一 KKT/feasibility 定義で比較する。
- **derivatives**: production connectivity derivative（現在は T3 reserved zero field）と、
  robust erosion/dilation state の勾配の FD 検証。

**合格**: mesh refinement で feature-size violation が再出現せず、三 field 間の
geometry/response 差が登録範囲内、backend 差を同じ KKT 定義で比較できる。

---

### DF7 — target-physics ladder

architecture plan の B0–B6, P1 ladder をそのまま使う。追加で確定した点:

- **B3（乱流 bridge）で最も重い検証**は、porous Darcy 項が `kOmegaSST` の wall
  distance / `nut` に干渉する方法論の model-form 比較。Wu & Zhang 2024 を基準に、
  `alpha` field が壁面近傍量に与える影響を flat plate / NACA で分離する。
- **B5/B6 の multipoint**: case ごとに primitive response と勾配を先に記録し、
  Python 側で aggregate objective/constraint を合成する。この経路は DF1 の compiler で
  テスト済みにするため、DF7 では contract の消費だけになる。
- **非定常 follow-up**: force stationarity を妨げる場合の time-resolved primal +
  sensitivity strategy は別 research 課題として登録する（WP3 transient check により
  縮約 case の steady は有効と確認済み）。steady solution を無理に収束扱いにしない。

---

## 3. マイルストーン・予算・リスク

### 3.1 マイルストーン

architecture plan §13 の M0–M7 表をそのまま使う。各 slice は feature branch
（`feat/df0-evidence-audit` 等の命名は `git_branching_strategy.md` に従う）で
implement → validate → commit/push で締める。

### 3.2 計算予算

- macOS/Linux CPU: DF0–DF3、FD suite、contract tests を優先。Windows 32 GB / RTX 4070 Ti
  は DF2 以降、CPU parity を示した後 sweep / worker として使用。
- Stage V の campaign は DF2 の資格化・DF5 の decision point・physics level 昇格時に
  限定（architecture plan §10 を順守）。

### 3.3 主要リスク（本計画で詳細化した追加）

| id | リスク | 緩和策（詳細化） |
| --- | --- | --- |
| R1 | DF1 の transform 移行中に script 側 OC engine / SLSQP adapter の有効経路が切断される | DF1 は transform 共有までに留め、loop を切断しない。OC engine は script 側を維持し、DF3 runner 化時に one-owner 化する |
| R2 | `faceSensNormal` drag solver suffix の符号・scale（includeSurfaceArea / includeObjectiveContribution）が不明確 | 採用前に FD verification test で sign/scale を qualify してから production path に接続する |
| R3 | extraction による体積 8–12% 損失が Stage S / Stage V の形状・force を崩す | 抽出損失を実 run の必須計測にし、extraction Gate 不合格 candidate は受理しない（DF0 で計測規則を確立） |
| R4 | backend 置換で KKT / feasibility 定義が変わる | backend 間を同じ KKT residual definition で比較する contract を DF3 で定義し、DF6 で消費する |
| R5 | DF2 の三格子で downforce が再度 bound 不達 | architecture plan §DF2 の停止条項に従い計算のさらに対象拡大せず domain / BC / steady-unsteady / discretisation factor study に戻る（phase_plan 2026-09-20 と一致） |

---

## 4. 検証コマンド（各 slice 完了時）

```bash
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest -q
git diff --check
```

OpenFOAM を使う slice では command / return code / mesh solver Gate / artifact paths /
hash / evidence class / 結論を evidence JSON の別 fields に記録する。

---

## 5. 実装後の移行先

DF0--DF6とPQ0/PQ1のcomponent/campaign slicesは実装済みである。次のreviewable sliceは
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
の **PQ0.1 nonlinear production-path integration**。旧DF0/PQ0を再実行せず、
projected-volume、primal artifact reuse、parent-adjoint/trial-primal semantics、
Path B centered FD bracketを一本のproduction pathへ統合する。

---

## 6. 参照

- [`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
  §7 作業パッケージ（DF0–DF7 定義）、§6 Gate 原則、§13 マイルストーン
- OpenFOAM adjointOptimisationFoam manual（v2312 / v2512, openfoam.com）—
  surface / surfacePoints / volumetricBSplines sensitivity、faceSensNormal solver suffix、
  E-SI 定式化
- `mmapy`（PyPI）、GCMMA-MMA-Python（Svanberg MATLAB 移植）— GPL-3、DF6 選定候補
- Svanberg 1987（MMA）、Wang / Lazarov / Sigmund 2011（robust 3-field）、
  Ghasemi & Elham 2022（multi-stage Cartesian TO）、Wu & Zhang 2024
  （Darcy-based turbulence model-form）、Nangia et al. 2017（moving CV）
