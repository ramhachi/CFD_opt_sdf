# P0意味論・勾配ゲート 第一スライス

実施日: 2026-09-11  
実装commit: `e6d40ccf429d9753b1c432ffd8caa993683f21e3`
判定: **第一スライスは実装完了。P0全体はNo-Goのまま。**

## 今回閉じた問題

従来の`topology_state.json`と`density.vti`は局所的なfixed-grid contractを持つが、
どのProblemSpec、正準格子、STL由来mask、候補反復に属するかを証明できなかった。
また、単発の有限差分検証は存在したが、P0が要求する同一目的の方向×epsilon行列を
満たしたかを一括判定するartifactがなかった。

今回、既存の意味体系を作り直さず、責務を次のように分けた。

- `native_openfoam_v2_artifact_binding.json`は、OpenFOAM応答の単位変換、rho勾配規約、
  solver source、topology valueを引き続き担当する。
- `stage_t_candidate_binding.json`は、Stage T候補をProblemSpec snapshot、正準格子、
  geometry mask manifest、候補ID、topology/densityのexact hashへ結ぶ。
- `fixed_grid_gradient_gate.json`は、既存の方向検証を同一目的の方向×epsilon行列として
  集約し、coverage、数値閾値、収束、clipping、noise floor、artifact hashを判定する。

candidate bindingはsource stateのリサンプリングを行わない。density VTIが正準格子と
一致しない場合は拒否する。これは、exact-overlap transferの`P.T`でsource gradientを
targetへ移す操作と、source stateからtarget stateを一意に復元する操作が別だからである。

## 実装した境界

`bind-stage-t-candidate`と`validate-stage-t-candidate-binding`は、次をfail closedで確認する。

- native v2かつ`execution_ready`のProblemSpecとsnapshot内容・semantic hash・file hash
- verified canonical grid snapshotとSTL由来geometry mask manifest
- topology stateとdensity VTIのexact hash
- canonical gridとdensity gridのorigin、spacing、shape、cell order
- cell-dataの`rho` variant、有限性、`0 <= rho <= 1`
- `active_design_mask`、`forbidden_mask`、`fixed_solid_mask`、`root_mask`の完全一致
- candidate ID、iteration、parent candidateの整合
- topology state自身にあるproblem/candidate lineageとの完全一致
- identity grid transform

bindingのcontract検証が通っても、surface fidelityとStage S物理は検査していない。
そのためsidecarは`ready_for_stage_s=false`を保持する。

`aggregate-fixed-grid-gradient-gate`はP0既定値として、同一目的について
`sensitivity`とseed固定`filtered-random`の2方向、`3e-5, 1e-4, 3e-4, 1e-3`の4 epsilonを
要求する。各行で符号一致、`0.8 <= FD/adjoint <= 1.2`、相対誤差10%以下、primal収束、
clipping情報、noise floorを検査する。異なる目的関数の行は一つの行列へ合算しない。
各direction-suite行には、検証済みcandidate bindingと同じcandidate ID・binding hashを要求する。
CLIは任意のID/hash宣言を受理せず、ProblemSpecに対してcandidate binding全体を再検証する。

OpenFOAM生成物の配線では、ProblemSpec由来の`execution_ready`をcase manifest、flow compilation、
case bundle、convergence evidence provenance、convergence qualificationまで保持するようにした。
実runで生成されるgzip圧縮済み`0/alpha.gz`もnative source validationの正当な入力として扱う。

## 既存成果物を使った判定

2026-09-10のT3成果物3件を新しい集約器へ入力した結果は`fail`だった。

| 目的 | 方向 | epsilon | FD/adjoint | 相対誤差 | 行判定 |
| --- | --- | ---: | ---: | ---: | --- |
| downforce | sensitivity | `1e-4` | 0.956533 | 4.35% | 数値はpass、証拠不足 |
| efficiency constraint | sensitivity | `1e-4` | 0.977702 | 2.23% | 数値はpass、証拠不足 |
| efficiency constraint | sensitivity | `1e-2` | 0.281463 | 71.85% | fail |

この3件は目的が混在し、`filtered-random`がなく、必須8行の行列を満たさない。
さらにProblemSpec/candidate binding、clipping count、solver noise floorがない。
したがって、小epsilonの2件が良好でもP0 passには数えない。

旧8192セルfixtureも正準G2格子として再解釈しない。実行済みOpenFOAM source gridは
`32 x 16 x 16`、spacingは`(0.09375, 0.1, 0.075) m`、grid hashは
`1d3c60e9...`である。G2 ProblemSpecの正準格子は`150 x 80 x 60`、等方spacing
`0.02 m`、grid hashは`0fb8a373...`である。boundsが同じでも同一格子ではない。

機械可読な要約は
[`evidence/p0_semantic_binding_2026_09.json`](evidence/p0_semantic_binding_2026_09.json)に置く。
全履歴集約reportは`work/p0_semantic_binding/historical_gradient_validation.json`にあり、
Git外のため要約にはそのSHA-256を記録する。

## 第二スライスと次の実装判断

第二スライスでは、正準target rhoから`P @ rho`でOpenFOAM source state artifactを生成する
capabilityと、direction-suiteへ検証済みcandidate bindingを伝播する経路を実装した。
stateとgradientの両方向で、OpenFOAM global cell label順をx-fastest順と同一視しないための
明示permutationを必須にした。詳細は`p0_canonical_transfer_2026_09.md`を参照する。

次は、このsource stateをsolver case compilerへ入力し、実`topOSens`を同じpermutationと`P.T`で
正準gradientへ戻してnative writerへ接続する。sourceの`alpha`、`alphaTilda`、`beta`をtarget
stateへ逆変換してはならない。現行のlegacy suiteはcandidate bindingを持たないため、集約器で
P0 passにはならない。

その接続後に、同じProblemSpec、candidate、目的、baseline sensitivityを固定して、
不足している2方向×4 epsilonのplus/minus primalをfresh processで実行する。clippingを許す
境界方向とinterior directionを混ぜず、noise floorを基準反復から先に測る。全8行とnative
response/unit/rho-chain/topology bindingが通るまで、P1候補のStage S資格化やStage V実行へ進めない。
