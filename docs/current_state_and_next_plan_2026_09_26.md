# 現在地と次の計画 — 2026-09-26

対象ブランチは `feat/p0-openfoam-closed-loop`。ここでの主張は、immutable
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
