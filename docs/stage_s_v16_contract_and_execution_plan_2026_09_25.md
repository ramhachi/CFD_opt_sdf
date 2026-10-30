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

## 2026-09-25: v16 factor screen and same-candidate continuation update

The v16-specific factor contract was registered before computation in
`evidence/stage_v_v16_domain_boundary_contract_manifest_v2_2026_09.json`
(SHA-256 `b8eccba3c0bc26fcc5eb392e52287a8e92a44e9b0541e8f589383fe307c54b8a`).
It binds the Stage S v16 STL
(`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`) to the
same Work F V1 baseline and tests exactly two one-factor treatments:
`+0.8 m` far-field domain extension and top `symmetryPlane` to pressure-outlet
replacement. Both treatments completed the registered V1 qualification
profile, while the raw `checkMesh.mesh_ok=false` state remains recorded as an
allowed concave-cell profile result rather than a clean mesh pass.

The corrected factor evidence is
`evidence/stage_v_v16_domain_boundary_contract_v2_2026_09.json` (SHA-256
`e87558be5ee8efb24723603ff4c1bc9ace8a84efeaaec658e34a09db7e0f2ae8`):

| case | cells | Cd | downforce coefficient | delta from Work F V1 |
| --- | ---: | ---: | ---: | ---: |
| Work F V1 baseline | 39,848 | 2.5234447 | 1.6908433 | — |
| domain extension `+0.8 m` | 45,227 | 1.5083067 | 0.6498149 | `-1.0410284` |
| top pressure outlet | 39,848 | 1.5756433 | 0.4379601 | `-1.2528832` |

Both downforce changes exceed the registered absolute bound `0.005`, and both
relative Cd changes exceed `0.02`. The top treatment is not the earlier
preliminary zero-delta result: the copied `postProcessing` directory was
removed before the rerun, the treatment produced a fresh canonical
`coefficient.dat`, and the read source/hash lineage is independently recorded
in `evidence/stage_v_v16_domain_boundary_lineage_audit_2026_09.json` (SHA-256
`c10d19bff2b47e4e7fd8864af969a1c98f378f1f816d5e09766aa99f3fb76071`). The
preliminary reused-history manifest/evidence are preserved under the
`*_preliminary_reused_postprocessing_2026_09.json` names and are diagnostic
only.

The result is a candidate-specific Stage V factor No-Go. It does not qualify
the Work F V1 value as an absolute or grid-independent reference, and it does
not authorize S2 or a shape update. A same-candidate continuation contract was
therefore registered before the next solver run:

- run manifest: `evidence/stage_v_v16_domain_continuation_run_manifest_2026_09.json`
  (SHA-256 `8d28c55e0d2ab6d1ec3c09af4041e4ee035dfdeccafb736a19a621beb1c1337c`);
- immutable parent manifest: `evidence/stage_v_v16_domain_continuation_manifest_2026_09.json`
  (SHA-256 `663ca988c0580d543df8e16a84731a9c4c50f692ff606bef6a77a58b84baaf16`);
- treatment: original v16 V1 domain extended by `+1.6 m`, with the same
  symmetry/freestream/wall boundary semantics and the same v16 STL.

The `+1.6 m` case also qualified its registered solver profile (48,564 cells,
`Cd=1.2749976`, downforce `0.5052721`). Its adjacent transition from the
corrected `+0.8 m` case is `-0.1445428` downforce and `-0.1546828` relative Cd,
both outside the registered bounds. Immutable evidence is
`evidence/stage_v_v16_domain_continuation_2026_09.json` (SHA-256
`e5f02f9091faeab0809dbe80a2e68ed572c2456362ae682fc0ef316e4acf2cb0`).

The revised execution order is now:

1. Keep `reduced_basis_fd_qualified=pending`, `shape_update_allowed=false`,
   and the Stage S absolute reference unestablished. Do not start S2, S4,
   PQ5 ranking, or a production optimization campaign.
2. Register one more same-candidate far-field continuation at `+3.2 m` from
   the original box, retaining the already registered boundary semantics and
   V1 cell scale. Run it only after the immutable contract and staging audit
   pass. This is the last planned domain-only diagnostic in this ladder; it
   tests whether the observed response is approaching a stable far-field
   limit rather than adding an optimizer or changing the objective.
3. If the `+1.6 -> +3.2 m` transition is within the bound, register the settled
   v16 Stage V reference contract at the larger domain and separately decide
   whether local S2 centered-FD evidence may proceed. Even then, S2 remains
   local Work F derivative evidence, not a grid-independent downforce claim.
4. If the `+3.2 m` transition remains outside the bound, stop extending the
   box blindly. Register a physically justified far-field formulation and
   audit the case-construction and pressure/velocity boundary semantics before
   any further solver run. Do not reinterpret the moving response as an
   optimizer signal.

This continuation result changes the plan because the same candidate has now
failed two independent outer-condition checks and one adjacent domain
continuation. It does not change the reduced-basis objective, epsilon ladder,
or mode manifest; those remain frozen until an absolute-reference contract is
resolved.

## 2026-09-25: domain ladder stopped and mixed far-field contract result

The final planned domain-only continuation was registered before computation in
`evidence/stage_v_v16_domain_continuation_3p2_run_manifest_2026_09.json`
(SHA-256 `827d93314a8594a9205aa06ad98aa9c50343a6bb361f8e21d2c4d75f36e4aa22`).
At the same v16 V1 boundary semantics, the `+3.2 m` case qualified at 82,907
cells with `Cd=1.0260446` and downforce `0.4279677`.  The adjacent transition
from `+1.6 m` was downforce `-0.0773044` and relative Cd `-0.1952577`, still
outside the registered bounds.  Immutable evidence is
`evidence/stage_v_v16_domain_continuation_3p2_2026_09.json` (SHA-256
`a3c706c4d5c67580ec7f350dbf7f3a7a831a7bdd967caa5bdfb86905ce40bc44`).

This closes the planned domain-only ladder.  A larger box would be a new
unbounded numerical search without a physical stopping rule.  The next
contract therefore fixed the `+3.2 m` domain and changed only the five outer
faces to the OpenFOAM mixed free-stream formulation: mesh `patch`, `U`
`freestreamVelocity` with `(1,0,0)`, and `p` `freestreamPressure` with
free-stream pressure zero and `U U`; the ground and design candidate walls
were unchanged.  The contract and run manifest were registered before the
solver, and the first field-rewrite staging failure was preserved as a
diagnostic without starting OpenFOAM.

The corrected mixed-boundary evidence is
`evidence/stage_v_v16_far_field_contract_v2_2026_09.json` (SHA-256
`1d58f8651f23e57a78c1d5bf58db47914025e1db2681bcf41f2f6a4d12962dc6`).  On the
same 82,907-cell mesh, the mixed case qualified with `Cd=0.9197727` and
downforce `0.3500024`.  Relative to the `+3.2 m` symmetry/patch baseline, the
change is downforce `-0.0779653` and relative Cd `-0.1035744`, again outside
the bounds.  The read-only audit
`evidence/stage_v_v16_far_field_contract_audit_2026_09.json` (SHA-256
`2b8991ee6a09912fcafeb69121909e35142eb50a45ccc831e77ca10722de68ec`) confirms
the candidate, non-boundary mesh files, patch face ranges, fresh canonical
force histories, solver completion, and the exact registered U/p boundary
types.  OpenFOAM's documented mixed conditions switch between free-stream and
zero-gradient behavior according to the boundary flux; they were therefore
treated as a physically defined diagnostic, not as an arbitrary top pressure
outlet.

The physical far-field contract is also a No-Go at this domain and operating
point.  No further OpenFOAM solver run is authorized by this plan until the
case-construction and boundary audit explains whether the response is caused
by (a) the chosen mixed-condition implementation, (b) the reduced laminar
domain/ground arrangement, or (c) an unresolved force-normalization or wake
interaction issue.  The next work is solver-free: audit boundary-flux and
force-patch semantics, compare the generated dictionaries with the declared
ProblemSpec, and write a new contract only if that audit identifies a single
physically justified correction.  Do not start S2, S4, PQ5 ranking, or shape
updates during that audit.

## Solver-free case-construction audit result

The read-only audit is
`evidence/stage_v_v16_case_construction_audit_2026_09.json` (SHA-256
`9785bfa2e6dd9b8df3b171f765c7543c4f69a4e3e0012d0e55f2bdac3fa3ed27`). It
checked the generated `boundary`, `U`, `p`, `transportProperties`,
`turbulenceProperties`, `snappyHexMeshDict`, `controlDict`, force history, and
latest `phi` boundary values for the +3.2 m symmetry baseline and mixed case.
The boundary fluxes close to about `-4.44e-8` and `2.38e-7`; force-patch
semantics, the laminar operating point, and the ground/domain arrangement
match their registered contracts.

The audit remains **No-Go for new execution** because both case metadata files
carry the stale `...domain_1p6_v2` identity under a registered `+3.2 m`
contract. This is a provenance guard failure; it does not turn the prior
response comparison into a physical qualification. The continuation runner now
rejects the mismatch before OpenFOAM is launched. The next action is to repair
the contract identity in a new immutable registration, then reassess whether
any single physical boundary correction is justified. Do not rerun the solver
or start S2 during that repair.
