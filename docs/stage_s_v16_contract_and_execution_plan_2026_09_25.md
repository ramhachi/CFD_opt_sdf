# v16 Stage S 契約監査と次の実行計画

Date: 2026-09-25
Status: adopted subordinate plan; `docs/phase_plan.md` remains authoritative

## 目的

次の重い OpenFOAM 実行を、v16 Stage S 候補の系譜・問題定義・境界条件・
メッシュ条件へ結び付けた状態で開始できるようにする。PQ2 で得た数値は、
候補 STL と格子が異なるため、v16 の絶対ダウンフォース参照へ流用しない。

この計画の最初の実行単位はソルバーを起動しない契約監査である。監査が通っても、
それは契約 evidence であり、Stage S の FD 資格、形状更新、grid-independent な
ダウンフォースを意味しない。

## 現在の事実と分離すべき二つの経路

| 経路 | 登録対象 | 現在の状態 |
| --- | --- | --- |
| Stage S local derivative | v16 STL、Work F V1、K=16 reduced-basis centered FD | S0/S1 済み、S2 は PQ2 の影響と契約整理のため停止 |
| Stage V absolute reference | 同一候補の domain / boundary / grid ladder | PQ2 は別候補 `613637…`、v16候補は `5e6d…`; v16の絶対参照は未測定 |

v16候補の登録済み STL SHA-256 は
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11` である。
PQ2 continuation の候補 SHA-256 は
`613637cf0fac8bce8a124a479eb3f18417c06995bdbfbe1c99b792fe1db3686e` であり、
同一候補ではない。したがって、PQ2 の downforce 値や domain drift は、v16の
Stage S baselineを棄却・資格化する根拠にはならない。

PQ2 の測定は引き続き次の事実を示す診断 evidence として保持する。

- PQ2候補では固定 domain / boundary の因子感度が大きかった。
- +0.8 m から +1.6 m への continuation も登録 bound を超えた。
- その結果は、grid-independent な downforce reference ではない。

## 実装済みの最初の slice: solver-free 契約監査

`scripts/stage_s_v16_contract_audit_2026_09.py` を実装し、次の immutable artifact を
登録する。

`docs/evidence/stage_s_v16_contract_audit_manifest_2026_09.json`

監査は次を fail-closed に検査する。

1. v16 baseline v2、v16 surface STL、Work F V1 case、reduced-basis manifest の
   candidate identity と hash。
2. original / reduced ProblemSpec の raw hash と、case metadata の canonical
   ProblemSpec hash。
3. design candidate / allowed design domain の staged STL、`blockMeshDict`、
   `snappyHexMeshDict`、`constant/polyMesh/boundary`、`0/U`、`0/p`。
4. inlet、outlet、sideMin、sideMax、top、bottom、design_candidate の patch type と
   U/p の realized boundary type。
5. v16 Work F の domain bounds、0.05 m voxel、cell shape、background block mesh の
   cell 数、および `stage_v_qualification_v1` の raw `checkMesh` 状態。
6. PQ2 continuation と fixed-domain grid study を diagnostic-only として参照し、
   v16候補への transfer を禁止する明示的な判定。

監査結果の `solver_started`、`mesh_generation_started`、
`optimization_campaign_started` はすべて `false` でなければならない。Work F が
profile-qualified でも raw `checkMesh.mesh_ok=false` なら、その事実を残し、clean mesh
pass と表現しない。

## 次の実行順

### A. v16-specific Stage V contract を登録する

監査 manifest を基準に、同じ v16 STLを使う factor-resolved contract を新規登録する。
既存 PQ2 manifest を書き換えず、domain、boundary、voxel/grid level、force response、
stationarity、mesh profile、one-factor budget、stop rule を一つの immutable manifest に
固定する。

境界条件は少なくとも次を明記する。

- inlet: patch、`U fixedValue`、`p zeroGradient`
- outlet: patch、`U zeroGradient`、`p fixedValue`
- sideMin / sideMax / top: `symmetryPlane`
- bottom: ground wall、`U noSlip`、`p zeroGradient`
- design_candidate: wall、`U noSlip`、`p zeroGradient`

現行 ProblemSpec は inlet/outlet の役割しか宣言していないため、六面体外周と
candidate patch の意味を暗黙の compiler default のままにしない。明示的な versioned
boundary contract が通るまで、v16の Stage V absolute reference は未資格とする。

### B. local reduced-basis path は範囲を限定して判定する

v16-specific contract が通った後に、S0 manifest の K=16、epsilon ladder、mode selection、
FD gate を変更せず、まず最小の S2 calibration を実行するかを判断する。これは同じ
Work F case 内の local derivative evidence として扱い、Stage V の絶対 downforce、
grid independence、production optimizer を主張しない。

S2 が pass しても、S3 gradient、S4 holdout、S5 one-step の順序を守る。S4 の完全 pass と
別 manifest がない限り、shape update は開始しない。S2 の結果を見て mode、epsilon、
boundary、objective、constraint を後付けで変更しない。

### C. absolute reference path は v16候補だけで最小 ladder を回す

v16-specific contract を通した後に限り、同一 STL、同一 flow、同一 boundary semantics
の domain/grid family を事前登録する。結果を見て level や far-field treatment を追加
するのではなく、登録した最小 family と停止条件だけを実行する。少なくとも次を分けて
記録する。

- caseごとの mesh/profile qualification
- raw `checkMesh` の状態
- residual と force stationarity
- candidate-specific downforce / Cd の差分
- grid-independent reference の成立可否

この経路が未成立の間、v16の downforce 値を Stage V の絶対参照として Stage S FDや
PQ5 rankingへ渡さない。

## 明示的な停止条件

- 任何の pinned hash mismatch、candidate mismatch、case staging mismatch。
- 六 patch boundary / field contract の欠落または結果依存の変更。
- PQ2 の別候補結果を v16 の absolute reference に転用する要求。
- S2前の full optimization、multi-step shape update、PQ5 ranking。
- profile-qualified を raw clean mesh pass、contract evidence を target-physics evidence
  とする報告。

## 現時点の判定

v16の Stage S baseline は candidate lineage と Work F case の契約監査を進められる。
ただし、`reduced_basis_fd_qualified=pending`、`shape_update_allowed=false`、
`grid-independent downforce reference=unestablished` は維持する。次に実行してよいのは、
この計画に従う v16-specific contract の登録・監査と、その後に承認された最小の検証 family
だけである。長時間の full optimization campaign はまだ開始しない。
