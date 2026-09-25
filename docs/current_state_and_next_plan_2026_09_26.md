# 現在地と次の計画 — 2026-09-26

対象ブランチは `feat/p0-openfoam-closed-loop`。この文書の主張は、同じ
commit で保存した immutable manifest と controlled-run outcome に限定する。
ロードマップの正本は [`phase_plan.md`](phase_plan.md)、問題台帳の正本は
[`problem_register_2026_09.md`](problem_register_2026_09.md) である。

## 今回終わったこと

v2 physical profile を solver 起動前に数値 qualification するため、次を実装した。

- 最終時刻の OpenFOAM `phi`、`U`、`p` boundary field を読み、全 boundary face の mass imbalance、
  moving-ground/candidate normal flux、upstream velocity、outer backflow、outer pressure disturbance を
  固定閾値で評価する fail-closed module。
- 既存 `stage_v_qualification_v1` の checkMesh、residualControl、force-stationarity 条件を再利用し、
  final initial residual の閾値も明示した。
- v2 candidate/spec/profile hash、Docker image ID、clearance profile、全 gate の式と閾値を
  immutable manifest に登録する script。
- 登録 manifest を検証してから case を materialize し、OpenFOAM を1本だけ実行し、結果を outcome
  artifact に保存する runner。

登録 manifest は
[`evidence/stage_v_v16_physical_profile_qualification_manifest_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_qualification_manifest_v1_2026_09.json)
（SHA-256 `c556b75f9b37ec674b6c8b04f12e8df43e0025857e03a72f98c7cb918c41353f`）、
実行結果は
[`evidence/stage_v_v16_physical_profile_qualification_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_qualification_v1_2026_09.json)
（SHA-256 `de500ec9ce7166ef71dee721fbd6d45f548896f381a11880b411e6489c7fb002`）である。

## 実測結果

Docker image `opencfd/openfoam-default:2512` の image ID は
`sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319`。
元の V1 box、v16 candidate SHA `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`、
physical-profile SHA `a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca` を使った。

| gate | 実測 | 判定 |
| --- | --- | --- |
| mesh | 39,848 cells、concave fraction `0.06126`（上限 `0.08`） | pass（raw `checkMesh` の allowed failed line は保持） |
| solver | residualControl、546 iterations、`p=5.19e-6`、`Ux=5.36e-7`、`Uy=9.86e-7`、`Uz=8.92e-7` | pass |
| force stationarity | `Cd=1.440331`、downforce `0.886829`、drift/std は profile 内 | pass |
| mass | normalized imbalance `4.84e-9` | pass |
| moving ground/candidate | ground velocity error `0`、両 wall max normal flux `0` | pass |
| upstream velocity | inlet face mean `(1,0,0)`、relative L2 `0` | pass |
| outer backflow | side `0.03559/0.03568`、top `0.00832`、outlet `0` | pass |
| outer pressure | inlet max `0.29055 U_inf^2`、top max `0.05192 U_inf^2`、上限 `0.05` | **fail** |

したがって現在地は **solver は動くが v2 physical profile は未資格** である。外周圧力の失敗は
solver の未収束や mass leak ではなく、元の V1 box では candidate の影響が outer boundary から
十分に離れていないことを示す。旧 stationary-ground run と比較して downforce を判断していない。

## 次の計画

1. 今回の manifest と outcome を immutable evidence として commit/push し、閾値を後から変更しない。
2. 同じ candidate、Re、laminar model、moving-ground/freestream BC、force normalization、physical-profile
   hash を保持し、domain bounds だけを upstream/top/side 方向へ拡大した新しい contract を登録する。
3. 新 contract でも solver 前に hash、clearance、BC、mesh/solver/force、mass、wall flux、upstream、outer
   backflow/pressure の全 gate を固定し、controlled run を必要最小限に限定する。
4. physical-profile gate が pass してから、同じ profile/physics を持つ二つ以上の domain で
   `|Δdownforce| <= 0.005`、`|ΔCd|/|Cd| <= 0.02` を比較する。これは domain convergence の判定であり、
   旧 stationary-ground case との比較ではない。
5. その後に初めて Stage S の reduced-basis FD を再評価する。Stage S、shape update、PQ5、production
   optimization は、physical profile と domain convergence が閉じるまで開始しない。

今回の No-Go は、moving-ground/freestream architecture 全体の否定ではない。solver、mass、壁面条件、
force stationarity が実測で通ったため、残る課題は外周の物理的な距離とその同一 profile 下の収束である。
