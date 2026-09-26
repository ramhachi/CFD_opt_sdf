# 現在地と次の計画 — 2026-09-26

対象ブランチは `feat/sdf-native-rearchitecture`（権威 branch。旧
`feat/p0-openfoam-closed-loop` は fork 前の base）。ここでの主張は、immutable
manifest と controlled-run outcome に保存した実測値に限定する。ロードマップの
正本は [`phase_plan.md`](phase_plan.md)、問題台帳の正本は
[`problem_register_2026_09.md`](problem_register_2026_09.md) である。

## 完了したこと

v2 moving-ground/freestream physical profile の qualification を実装し、solver
起動前に次を固定閾値で測るようにした。

- 最終時刻の OpenFOAM `phi`、`U`、`p` boundary field から、全 boundary face の
  normalized mass imbalance、ground/candidate normal flux、upstream velocity、outer
  backflow、outer kinematic-pressure disturbance を fail-closed に評価する。
- 既存 `stage_v_qualification_v1` の checkMesh、residualControl、force-stationarity
  条件を再利用し、final initial residual の閾値も登録する。
- candidate/spec/profile hash、Docker image ID、clearance profile、gate の式と閾値を
  immutable manifest に固定する。
- manifest を検証してから case を materialize し、OpenFOAM を登録数だけ実行し、raw
  qualification と境界計測を outcome に保存する。
- physical profile が pass した後、同じ profile/candidate で domain bounds だけを変えた
  二点を比較する immutable convergence result を追加した。

## 実測された経路

最初の V1 box は、solver、mesh、force stationarity、mass、moving ground、candidate
flux、clearance、upstream velocity、backflow を通過した。しかし outer pressure gate
だけが fail し、inlet `0.29055416 U_inf^2`、top `0.051920264 U_inf^2` だった。これは
solver failure ではなく、候補の影響が外周に残った physical-profile No-Go である。

同じ profile と candidate のまま inlet を `-1.5 m` から `-2.5 m` へ移した最初の拡大も、
inlet pressure `0.077604551 U_inf^2` で fail した。閾値は緩めず、この outcome は診断証拠として
保持している。

次の拡大 domain は全 physical-profile gate を pass した。結果は
[`stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json`](evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json)
（SHA-256 `8871255838b9666683581a3cb50d949764f6a4b27fb3dab24d6f6f52b4a75e66`）である。
`42,619` cells、mean `Cd=1.1693991`、mean downforce `0.7565515`、normalized mass
imbalance `1.91e-8`、inlet pressure maximum `0.020346387`、top pressure maximum
`0.026347419` を測った。raw `checkMesh` の allowed concave-cell marker は記録に残している。

その case から downstream bound だけを `2.5 m` から `3.5 m` へ広げた二つ目の qualified
domain は、`43,204` cells、mean `Cd=1.1703630`、mean downforce `0.7573549` だった。
pair result
[`stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json)
（SHA-256 `13374c722b4993f941ca6487a305fe2f371551d2eed152f744ef016f5b18b5bf`）は、登録済みの
`|Δdownforce| <= 0.005` と `|ΔCd|/|Cd_parent| <= 0.02` をともに pass した。実測値は
`|Δdownforce|=0.0008034`、relative-Cd `0.0008242` である。両 domain は candidate SHA
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`、physical-profile SHA
`a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca` を共有する。

## 現在の判定

この v16 candidate に対する reduced-laminar moving-ground/freestream profile の
physical-profile gate と二-domain convergence gate は pass した。これで、外周場が近すぎる
問題は登録した profile の範囲で解消した。一方、これは absolute、grid-independent、high-Re
FSAE、または full-vehicle downforce の資格ではない。旧 stationary-ground の値との比較も
参照資格には使っていない。

## 次の計画

1. 今回の profile と二-domain convergence result を Stage V の候補 reference profile として
   freeze し、hash と適用範囲を記録する。
2. 既存 S0/S1 の K=16 reduced-basis centered-FD 経路を、この profile、candidate、domain
   bounds、force normalization に再登録する。まず solver-free construction、epsilon、mesh、
   clearance、lineage の preflight を通す。
3. 登録した FD run で primal/perturbation の gate と S4 holdout（random mode 方向と projected
   gradient 方向）を確認する。`reduced_basis_fd_qualified` はその全 pass まで `pending` のままにする。
4. S4 holdout と geometry/mesh/solver/clearance が全て pass した後にだけ、shape update を一歩
   登録する。PQ5 の三格子検証と production optimizer はさらに下流である。

したがって、今は「最適化 campaign を開始してよい」段階ではなく、「物理 profile と domain
convergence を閉じ、次の K=16 FD qualification を登録できる」段階である。

## 追記 — Stage S reduced-basis FD v2 契約登録と S0R/S1R 完了（2026-09-26）

「次の計画」の 1 と 2 は完了した。v2 の working domain
`[-2.5,-1.2,-0.9] -> [2.5,1.2,0.9] m`（v3 は domain-convergence witness として
のみ保持）を固定し、旧 S0/S1 の K=16 mode basis を byte 単位で再利用して、
candidate `5e6d…`、physical-profile `a846…`、Docker image ID
`sha256:33fb575a…`、force normalization、control-point catalog、epsilon ladder
`1e-4/2.5e-4/5e-4/1e-3 m` を一つの immutable contract に束ねた。

- manifest:
  [`stage_s_reduced_basis_fd_v2_manifest_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json)
  SHA-256 `b96df520e6a359c206b9ded3c4cb1872220344ba9a46c7a7492d0e1ba47860dd`
- Stage S ProblemSpec SHA-256
  `9503400412509be755b7599d1e504b36519a1e33c5599347caf6f0c62e9318ed`
- objective 監査: Stage V reference（`minimize_drag`）との差は `problem_id` と
  `objectives` に限定。Stage S は `maximize_downforce`、canonical `J = -CDF`、
  drag report-only、constraint なし
- S0R/S1R:
  [`stage_s_reduced_basis_fd_v2_preflight_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json)
  SHA-256 `3f6cb15eae5b7770640466c89f9c296a383dd152f9f1dc0fedbc95d69acdaf50`。
  base case 42,619 cells、16/16 mode の ±1e-3 m が morpher、boundary CP
  immobility（exactly 0.0）、realized direction（cosine >= 0.9999999999、
  movement difference <= 4.7e-9 m、even component <= 5.0e-9 m）、watertight、
  self-intersection none、minimum width >= 0.0466 m、volume change <= 0.31%、
  clearance、`checkMesh` profile をすべて pass。flow solver は未起動

`flow_campaign_allowed=true`、`reduced_basis_fd_qualified=pending`、
`shape_update_allowed=false` は維持する。次は「次の計画」3 の S2 epsilon
calibration で、登録済み 3 mode × 4 epsilon × 2 sign（最大 24 primals）を実行し、
各 perturbed shape に v2 physical-profile gate を毎回適用する。結果を見た後の
epsilon・閾値変更はしない。

## 追記 — SDF-native architecture fork（2026-09-26）

K=16 B-spline reduced-basis Stage S v2 経路は `superseded_reference` として
freeze した（[`stage_s_reduced_basis_fd_v2_supersession_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_supersession_2026_09.json)、SHA-256
`1eee51fdd03bc0402650d45b2d8174f969cbe2216c329c76b7275880f2c4a35d`）。
**S2 は開始しない。** 既存の P21 / Stage V / domain-convergence / S0R/S1R の
evidence は一切変更していない。

新しい canonical design state は SDF field `phi`（`phi < 0` solid）とし、
`docs/CFD_opt_sdf_SDF_native_handoff/` を subordinate plan として採用する。
PR-01 は solver-free で、`design/sdf_state.py`、`oracles/base.py`、
`gradients/base.py`、`runtime/fingerprint.py`、canonical semantics
（`f=-CDF`、`g_R=R_min*CD-CDF<=0`、`g_V=V/V_max-1<=0`）、repo inventory
（SHA-256 `00694da5b33b95893ca256bbd8cd5996686ee266c0e0291b8152ff6c562fa559`）、
architecture registration
（SHA-256 `743e90cb58dc46e93392ec3283a6d7f549f7ad8597b93c0d109220ecea637cbe`）
を追加する。WaterLily は candidate primal に限定し、PR #285 の CPU reverse
PoC と GPU reverse Go/No-Go を分離して進める。次の gate 順は SDF genesis →
WaterLily primal → SDF centered FD → CPU reverse → GPU reverse 判定 →
one SDF update → topology birth → OpenFOAM PQ5。全 flagship flag は false の
ままである。

## 追記 — 復元と Web 込み plan audit（2026-09-26）

**復元。** 消失した内容は無かった。handoff bundle `00–05`、README、SHA256SUMS の
SHA-256 は `5750da1` 時点の登録値全部と一致した。実壊れは「リンク集（06）作成時の
README/SHA256SUMS のその場編集」のみで、`git restore` により登録状態へ復元し、06 は
同ファイル自身の §D 推奨位置かつ凍結帯外の
[`references/upstream_code_map.md`](references/upstream_code_map.md) へ移した。
凍結帯の再編集は append-only 規則上しない。検証:
`register_sdf_native_architecture_2026_09.py --verify` = pass
（registration SHA-256 `743e90cb58dc46e93392ec3283a6d7f549f7ad8597b93c0d109220ecea637cbe`、
登録値と一致）。Time Machine ローカルスナップショットは存在せず、要求された検索対象外。

**Web監査（詳細と証拠は
[`references/upstream_code_map.md`](references/upstream_code_map.md) §H/§I）。**
GitHub REST API・raw・arXiv の当日ライブフェッチによる監査の要点:

1. PR #285 は open・未merge、head `feed49f…` は登録値と一致。ただし最終更新 2026-09-20
   で master（`aac3c43`）が先行、`mergeable_state=dirty`。PR-07 は pinned head を別
   Manifest で再現し、master への取込み時のみ rebase と core `src/` 衝突を織り込む。
2. **新契約**: reverse/adjoint cost は pressure-shift-invariant でなければならない
   （`sum(p)` の逆勾配は厳密ゼロ＝Neumann nullspace；ForwardDiff の非ゼロは数値人為）。
   PR-04 以降の cost は力積など。既登録の `f=-CDF` 設計はこの契約と整合する。
3. upstream PR #327 で **Metal バックエンド**（Float32のみ、積算は `sumtype`）が merge済み。
   PR-03 のオプションに MacBook Air Metal Float32 spike を追加できる（non-blocking）。
4. upstream 公式 ext を優先: JLD2（checkpoint）、Meshing（表面抽出→STL handoff）、
   Read/WriteVTK（restart）。自前実装より contract+検証つき採用。
5. Enzyme 監視対象: issue #3195（gc-transition abort）、PR #3148（GPU linalg rules）。
   PR-08 spike の事前登録予算は不変。
6. DAFoam v5.0.0（GPL、OpenFOAM v2506+AD、2026-05-05）と TCLB（GPL-3、activity 2026-03）を
   再検証。OpenLB/waLBerla/lbmpy は今回未検証。
7. LICENSE.md 実物は MIT/Expat（GitHub の NOASSERTION は自動検出の見かけ）。
8. 局所前提: この機械に Julia 未導入。Julia 導入＋Manifest pin は PR-02 の事前条件。

Flag 変化なし: `shape_update_allowed=false`、`sdf_gradient_qualified=false`、
`waterlily_reverse_cpu_qualified=false`、`waterlily_reverse_cuda_qualified=false`、
`topology_birth_qualified=false`。solver 未起動。凍結帯・既存 evidence は無変更。

## 追記 — Colab T4 primary 化（2026-09-26）

実行設計を Colab 使用許可の下で固定した。詳細は
[`colab_t4_batch_worker_plan_2026_09_26.md`](colab_t4_batch_worker_plan_2026_09_26.md)。
要点:

- **役割固定**: Primary = Colab T4（CUDA primal/FD/campaign 全ジョブ）、
  Secondary = Colab CPU（env 検証・smoke）、Witness/開発 = RTX 4070 Ti
  （**同一 manifest の再実行による independent CUDA witness** へ降格）、
  Control plane = MacBook Air（manifest/テスト/review）。
- notebook は研究ロジックを一切持たない薄い bootstrap
  （Drive mount → clone/fetch → exact commit checkout → Julia instantiate →
  runtime probe → `run_worker(job_manifest)` → artifact flush）。
  実体は repo 側の `scripts/run_waterlily_job.py` と `julia/CFDSDFWaterLily/`。
- FD qualification は `direction_NN_plus/minus` を 1 ジョブ 1 manifest entry
  に展開し、Colab 側は「次の未完了 job を 1 個取って実行」。controller は
  `run job / show status / fetch result / resume campaign` の 4 動詞のみ。
- Drive に `campaign/{manifest.json, jobs/, results/}` を残し、セッション死後も
  新しい T4 runtime が続行できる。標語「ログ吐ききってから死ね」を硬要件として明記
  （全退出経路で partial log + fail-closed `result.json` を先に flush）。
- frozen `00_HANDOFF_MASTER.md` §16/§17 の「GPU type 不特定 Colab / 4070 Ti primary」
  の記述は、この plan doc により追加的に修正（凍結帯自体は編集しない）。
  「runtime 変化は別 backend identity」の fingerprint 規律は維持。
- gate 順・PR 構成・全 flagship flag（false）・qualification の証拠区分は不変。
  この変更だけで solver 起動・gradient qualification・shape update は許可されない。

## 追記 — SDF genesis スライス完了（2026-09-26）

ゲート順の最初「SDF genesis from the v16 candidate lineage」を solver-free で
完了した。`src/cfd_sdf/design/genesis.py` が登録済み handoff（manifest
`hash_match` 全検証）から point-grid SDF `phi` と値域 mask を取って不変の
`SDFDesignState` を生成する。mask 投影は policy `v16_handoff_mask_projection_v1`
（design = 8-cell 全 active の interior のみ、fixed/forbidden/root =
any-adjacent）。状態は
`work/sdf_native_genesis_v16/sdf_design_state.npz`、state SHA-256
`44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`、
evidence
[`sdf_native_genesis_v16_2026_09.json`](evidence/sdf_native_genesis_v16_2026_09.json)
（SHA-256 `3c8e241681c80962a7fd62f1926e382d473ec8e9f3e6b9140bea9600d41cf670`）。
mask 契約チェック 9/9 pass、material volume diagnostic `0.129250 m^3` は
handoff の cell-threshold volume と一致。solver 未起動、flag 変更なし、
既存 evidence 無変更。凍結機構の v1 inventory は live-glob 検証のため
append-only 追加で verify が失敗する潜在欠陥が顕在化したため、v1
（byte-frozen 維持）に代わる fixed-set 検証の
`repo_inventory_sdf_native_v2.json`（SHA-256
`8e31d9e30feca97d112a7803d611f926e1e0d8a3f993367f24e043c75a3c5d27`）を発行した。
次のゲートは WaterLily primal（Colab T4 primary）。

## 追記 — plan correction v2.1（2026-09-26、ユーザー承認）

genesis 実測（`V_sharp = 0.12925000000000003 m^3` vs Stage T `V_rho = 0.0719735015 / Vmax = 0.0763256681`）を受けて、
WaterLily primal の前に三契約を正式化した（詳細は [`phase_plan.md`](phase_plan.md) の v2.1 section）:

1. **design grid と flow grid の分離（恒久契約）**: canonical SDF grid
   （61x33x25, h=0.05 m, x[-1,2] y[-0.8,0.8] z[-0.6,0.6]）は局部設計空間であり、
   qualified OpenFOAM v2 flow domain（x[-2.5,2.5] y[-1.2,1.2] z[-0.9,0.9]）とは別格子。
   WaterLily へは world-space adapter（`sdf_at_world(xyz_m)` trilinear）で埋め込み、
   flow grid 解像度は独立変数（同一 phi に対する coarse/medium/fine）。
2. **SDF sharp volume 契約（今登録、違う意味論への切替）**: SDF-native の
   constraint volume は `V_phi = |{trilinear center 評価 < 0}| h^3`
   （∫H_ε(-φ) の center sampling での h→0 極限）。最初の制約は
   `V_phi <= V_phi_0 = 0.12612500000000004 m^3`（genesis 状態から再測定、
   1009 centers）。三つの sampling を分離記録: 契約測度 0.126125（1009）、
   mesh-derived / revoxelized discrete volume 0.12925000000000003（1034 cells、
   物理クロスチェック、比 1.0248）、node 占有 0.17750000000000005（1420、
   非契約 diagnostic）。旧 Stage T `Vmax = 0.0763256681` を SDF Stage S
   評価に持ち込まない。物理的に小さい体積を狙う場合は volume-calibrated
   offset rebuild を伴う別の系統登録。
   実装 `src/cfd_sdf/design/volume_semantics.py`（optimizer 側 enforcement
   は one-step gate 前）、登録 evidence
   [`sdf_native_volume_semantics_v1_2026_09.json`](evidence/sdf_native_volume_semantics_v1_2026_09.json)
   （SHA-256 `0142ace4de9419dd73cc27e90135ed1fe1f847b074ca2faa37fdb0962505bbce`）。
3. **SDFTopologyPolicy v1 = Birth-0 前の必須 gate**（登録は後回し可、
   Birth-0 作業前に必ず登録する）: 今の v16 は root/fixed/forbidden 空、
   root_connectivity not_applicable で root hard gate は何も制約していない。

W 系ゲート列: W0 Julia env registration → W1 GridSDFBody adapter 資格 →
W2 解析球 primal（CPU → T4）→ W2b 同一形状 3 解像度 → W3 v16 primal +
physical-profile adapter → W4 grid/domain response qualification →
SDF centered FD → CPU reverse PoC → GPU reverse Go/No-Go → one constrained
SDF step → SDFTopologyPolicy v1 → topology birth → bounded loop →
OpenFOAM PQ5。inventory v3 は WaterLily primal gate 通過時に mint。
全 flagship flag false のまま。
