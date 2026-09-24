# 現状整理と次の実行計画 — 2026-09-25

状態: **pre-campaign historical snapshot**。これは centered-FD campaign 実行前
（`d08dc99` 時点）のキャッチアップと計画であり、campaign の verdict は
[`stage_s_work_f_fd_diagnosis_plan_2026_09_25.md`](stage_s_work_f_fd_diagnosis_plan_2026_09_25.md)
と [`evidence/stage_s_work_f_surface_fd_result_2026_09.json`](evidence/stage_s_work_f_surface_fd_result_2026_09.json)
を優先する。
対象スナップショット: `feat/p0-openfoam-closed-loop` / `830758d0e57e6319dc4ed3c693c3c2156615e072`

この文書は、現時点のリポジトリと登録済み証拠を基にしたスナップショットである。
ロードマップ・状態・実行順序の唯一の正本は引き続き
[`phase_plan.md`](phase_plan.md)、問題台帳の正本は
[`problem_register_2026_09.md`](problem_register_2026_09.md) とする。
将来この文書と正本文書が食い違った場合は、その時点のリポジトリ上の証拠と正本文書を優先する。

## 1. 結論

Work F は V1 の primal baseline より先へ進み、現時点で次の準備まで完了している。

- v16 の `rho_projection` iso-0.5 形状を Stage S baseline として登録し、ハッシュで拘束した。
- V1 body-fitted mesh と primal baseline は、登録済みの mesh、residual、force-stationarity gate を通過した。
- drag/downforce 別の surface-FD manifest と、両応答で共有する 32 ケースの摂動 catalog を登録した。
- 登録済みの全 epsilon・両符号について、solver-free geometry preflight を通過した。
- matched-Re・laminar 条件の `adjointOptimisationFoam` base case で、drag と downforce の adjoint を個別に完走した。
- 両 adjoint から `volumetricBSplines` の設計変数微分ファイルを生成した。

ただし、32 ケースの centered-FD campaign は**まだ開始可能ではない**。現在の証拠は明示的に
`perturbation_allowed=false`、`shape_update_allowed=false` を保持している。
不足しているのは、登録済み方向を OpenFOAM の active B-spline 変数順序へ厳密に写像し、
control point に `+/- epsilon` の変位を与え、`moveMesh` を実行し、各 geometry/mesh を再認定した後、
primal を実行して drag/downforce の中心差分を評価する morpher-based perturbation path である。

さらに、摂動 primal を許可する前に base adjoint の machine-readable qualification を強化する必要がある。
solver ごとの収束、最終 residual と最終 iteration の対応、response identity、derivative file schema、
active-variable ordering、各ハッシュを、return code とファイル存在だけに頼らず検証・記録する。

したがって、直近の推奨作業は 32 primal の実行ではない。まず次の二つだけを一つの review checkpoint とする。

1. base derivative contract を厳密化し、4 本の摂動方向を不変 artifact として確定する。
2. morpher と mesh qualification を実装し、32 個すべての符号付きケースを solver-free で preflight する。

## 2. リポジトリの現在状態

| 項目 | 確認結果 |
| --- | --- |
| branch | `feat/p0-openfoam-closed-loop` |
| upstream | `origin/feat/p0-openfoam-closed-loop` と同期 |
| HEAD | `830758d` — `Run the Work F base adjoints and record the analytic derivatives` |
| この文書を作る前の working tree | clean |
| local `main` との関係 | 125 commits ahead、0 behind |
| 稼働中の CFD/test process | 観測なし（`simpleFoam`、`adjointOptimisationFoam`、`moveMesh`、`snappyHexMesh`、`pytest`） |

長時間存在している interactive な `opencode --auto` process は、このリポジトリを current working directory
としているが、OpenFOAM の child process は観測されなかった。したがって、process の存在だけを根拠に
campaign が実行中とは判断しない。

## 3. V1 primal baseline 以後の変更

`5b47ce9` より後の 4 commits は次のとおり。

| commit | 内容 |
| --- | --- |
| `23e8085` | v16、Stage S baseline、Work F V1 の状態に合わせて正本サマリーを整合させた。 |
| `f38410f` | drag/downforce surface-FD manifest と共有摂動 catalog を登録し、solver-free geometry preflight を通過した。 |
| `f01ec1b` | matched-Re・laminar base adjoint case を render し、構造および OpenFOAM preflight を行った。 |
| `830758d` | base primal と downforce/drag adjoint を実行し、設計変数微分 artifact を記録した。 |

## 4. 確認済みの数値状態と contract

### 4.1 Stage T と Stage S の境界

- v16 は追加 87 updates、累積 97 accepted updates まで進み、attempt 88 で Path B bracket の符号が
  `d_adj < 0`、`d_fd > 0` に分かれたため fail-closed で停止した。
- 登録済み convergence window は満たしておらず、独立 terminal repeat も実行していない。
- v16 candidate は geometry extraction が可能で、iso-0.5 における PQ4.1 v2 を通過しているが、
  converged Stage T terminal ではなく blocked-stop checkpoint である。
- したがって P2 は strict terminal-convergence criterion の下で open のままである。
- P19 は field-semantic mismatch として closed。採用済みの constraint/backend/handoff geometry path は
  `rho_projection` を使い、`beta_solver` は solver audit field として残す。
- P20 は登録済み entry-measurement contract に限って closed。
- P17 は登録済み v16 iso-0.5 candidate の V1 body-fitted solver run に限って closed。

### 4.2 Work F V1 primal baseline

証拠: [`evidence/stage_s_work_f_v1_solver_2026_09.json`](evidence/stage_s_work_f_v1_solver_2026_09.json)

| 量 | 確認値 |
| --- | ---: |
| cells | 39,848 |
| concave-cell fraction | 0.06126（登録上限 0.08 未満） |
| primal iterations | 292 |
| 最終 `Ux/Uy/Uz/p` initial residual | `4.91e-7 / 8.18e-7 / 9.80e-7 / 3.11e-6` |
| mean `Cd` | 2.52344 |
| `Cd` stationarity-window drift | `-1.106e-4` |
| mean downforce coefficient | 1.69084 |
| downforce stationarity-window drift | `-6.305e-5` |
| baseline gate による surface FD 許可 | true |
| shape update 許可 | false |

生の `checkMesh` 出力には concave cells に対する failed-check が 1 行ある。これは raw clean pass ではない。
観測された concave fraction を 0.08 まで許容する登録済み qualification profile に基づく qualified pass である。

### 4.3 登録済み surface-FD contract

証拠:

- [`evidence/stage_s_work_f_surface_fd_catalog_2026_09.json`](evidence/stage_s_work_f_surface_fd_catalog_2026_09.json),
  SHA-256 `e4cdbe437eaa32dc752ad603a5d921aa94a4a47511e4a0403ead58ac49d5b4a8`
- [`evidence/stage_s_work_f_surface_fd_preflight_2026_09.json`](evidence/stage_s_work_f_surface_fd_preflight_2026_09.json),
  SHA-256 `93c6c6b5007f6ff6741a3bedc4fa2d87ce85d48c5bf8be0b2a0297bff9588efc`
- drag manifest SHA-256 `ab924482b5902b2b6f44cbacd8e6f060ef10cb834d396ae2ad9f59948b4fc8f4`
- downforce manifest SHA-256 `64115353a2d5b2bb4159b3f2eb8e90fece275d513e6d67f9401779e532f6530a`

登録済みの摂動行列:

- basis: axis-aligned `8 x 8 x 8` `volumetricBSplines` control volume
- free patch: `design_candidate`
- fixed patches: inlet、outlet、sideMin、sideMax、bottom、top
- 最大登録変位: `1e-3 m`
- epsilon ladder: `1e-4`、`2.5e-4`、`5e-4`、`1e-3 m`
- directions: downforce-gradient-aligned、drag-gradient-aligned、random seed 11、random seed 2026
- centered pairs: 4 directions x 4 epsilons x 2 signs = 32 primal cases
- response verdict: drag と downforce を別々に判定
- qualification: 符号一致、相対誤差 5% 以下、epsilon plateau、登録済み near-zero rule
- 片側でも失敗すれば centered pair 全体を無効とし、one-sided difference へ置換しない。

solver-free preflight は、保守的な uniform normal offset を使い、全 epsilon・全 sign で watertightness、
winding、self-intersection、minimum width、volume change、clearance を通過した。これは geometry feasibility
だけの証拠である。実際の B-spline directions は、`moveMesh` 後に pair ごとの geometry/mesh qualification が必要になる。

### 4.4 Base adjoint run

証拠: [`evidence/stage_s_work_f_adjoint_run_2026_09.json`](evidence/stage_s_work_f_adjoint_run_2026_09.json),
SHA-256 `5034dc01b508a4e8e6f6628de7fab67776cdbd23f5640d6b59865c811cc8aeb7`

この証拠は、現在の adjoint preflight SHA-256
`0f5f94fb50ac566952d384311bd6da91f91d008c0465b8bbfe05a264239e45b4` に拘束されている。

| solver | 観測された収束 | 次の slice で使う出力 |
| --- | --- | --- |
| primal `op1` | `solution converged in 292 iterations` | qualified baseline response |
| `adjDownforce` | `solution converged in 425 iterations` | 648 行の B-spline derivative file |
| `adjDrag` | `solution converged in 562 iterations` | 648 行の B-spline derivative file |

生成済み derivative files:

- `optimisation/derivatives/volumetricBSplinesadjDownforceadjDownforceESI425`
- `optimisation/derivatives/volumetricBSplinesadjDragadjDragESI562`

各ファイルは 648 個の active design-variable rows を含む。B-spline control-point catalog は
512 points（`8 x 8 x 8`）と各 3 coordinate components を持つが、boundary confinement により
全 1,536 components の一部が active space から除かれている。次の実装では各 derivative `varID` を
正確な active control-point component に写像しなければならない。row position を暗黙の写像として使わない。

最終 case output に存在する `faceSensNormal` は `faceSensNormaladjDragESI` だけである。一方、
response-specific な design-variable derivative file は両応答について存在する。このため、現在の roadmap が
analytic comparison を active B-spline variable space の inner product に限定した判断は妥当である。
将来の runner は、drag の `faceSensNormal` 表現と downforce の control-point derivative を混在させてはならない。

## 5. 現時点で言えること／言えないこと

### 言えること

- v16 candidate は iso-0.5 で登録済み Stage S entry gate を通過している。
- 登録済み Stage S baseline surface は、V1 body-fitted mesh と primal solver gate を通過している。
- matched-Re・laminar 条件の二つの base adjoint が実行を完了し、response-specific な B-spline derivative file を出力した。
- 登録済み epsilon は、保守的な solver-free offset diagnostic の範囲で geometry feasible である。
- perturbation runner の実装へ進むための contract 準備は整っている。

### まだ言えないこと

- いずれかの response について analytic derivative と centered-FD が一致すること。
- qualified drag/downforce surface derivative が得られたこと。
- Stage S shape update を実行してよいこと。
- Stage T optimizer が収束 terminal に到達したこと。
- Stage T から Stage S への改善が numerical/extraction uncertainty を超えたこと。
- Stage V downforce の grid convergence または GCI が成立したこと。
- target-Re、turbulent、finite-wing、moving-ground、full-vehicle、physical validation に関する主張。
- optimizer-generated shapes に対する一般的な cross-fidelity ranking が成立したこと。

## 6. FD campaign 前の重要な監査所見

### 6.1 現在の run evidence は必要条件を満たすが、base gate としては未完成

adjoint log には明示的な convergence marker と小さい final residual がある。一方、現在の evidence writer は
`adjoint_converged=true` を、主に正常な process return と期待される derivative/sensitivity filename の存在から
設定している。solver ごとの residual table、final-iteration binding、response/objective identity hash、
derivative schema validation はまだ記録していない。

derivative 値から摂動を作る前に、次を parse・拘束する append-only qualification artifact を生成する。

- primal、`adjDownforce`、`adjDrag` の solver name
- 宣言済み response direction、reference area/density/velocity、objective sign
- 各 adjoint component の convergence marker、最終 initial/final residual
- 各 derivative filename が参照する final iteration
- control-point catalog と derivative file の SHA-256
- `varID` の一意性、component mapping、有限値、期待 active-variable count
- 使用した OpenFOAM image と source-tree hash

どれか一つでも失敗した場合は `perturbation_allowed=false` を維持する。

### 6.2 Direction vector はまだ不変 artifact になっていない

manifest が登録しているのは direction の役割であり、post-result vector そのものではない。次の slice で、
同一の 648-variable space 上に次の 4 本を決定論的に materialize する。

1. normalized downforce derivative vector
2. normalized drag derivative vector
3. seed 11 の random vector
4. seed 2026 の random vector

各 vector について、`varID` ordering、normalization、norm、sign convention、SHA-256 を記録する。
random vector は active variables 上だけで生成し、confined/fixed control points を尊重する。
analytic directional derivative を作る前に、response 固有の objective sign を明示的に適用する。

### 6.3 登録済み manifest は変更しない

既存 manifest と epsilon ladder は adjoint 結果を見た後に編集しない。base adjoint 前には確定できなかった
active-variable map、vector hash、case path、morpher command などは、既存 manifest hash を参照する
append-only execution sidecar に置く。

### 6.4 小さな文書不整合が二点残っている

- `phase_plan.md` には旧 adjoint-preflight SHA-256 `12fb...` が残っているが、現在の preflight artifact と
  adjoint-run evidence が参照する実ハッシュは `0f5f...` である。
- P19 の詳細 heading は `closed 2026-09-23` だが、上部 summary table の行はまだ `open` である。

これらは live evidence を無効にはしないが、historical evidence を書き換えず、次の documentation checkpoint で訂正する。

## 7. 次の実行計画

### Slice A — base derivative contract の厳密化とハッシュ拘束

二つの B-spline derivative file と control-point catalog に対する小さな parser/qualifier を実装する。

必須出力:

- `stage_s_work_f_adjoint_qualification_2026_09.json`
- `varID -> (control point, component)` の意味を明示した active-variable map
- objective sign 適用済みの response-specific derivative vectors
- 登録済み 4 本の normalized direction vectors と各 hash
- 全 base gate が通った場合に限る `perturbation_allowed=true`

必須テスト:

- duplicate、missing、non-finite `varID` の拒否
- derivative/control-point dimension mismatch の拒否
- drag/downforce file を入れ替えた場合の拒否
- random-vector hash の決定性
- fixed/control-point confinement の保持
- downforce objective sign の正しい処理
- immutable evidence の上書き拒否

停止条件: OpenFOAM の `varID` mapping を authoritative な generated artifact から確定できない場合、
row order から推測しない。mapping を決めるための限定的な diagnostic を先に登録する。

### Slice B — morpher-only perturbation runner の実装

登録済みの各 `(direction, epsilon, sign)` について次を実行する。

1. qualified V1 base case を immutable case directory へ複製する。
2. active control point に、infinity norm が正確に epsilon となる変位を与える。
3. OpenFOAM の登録済み B-spline mesh-motion path（`moveMesh` または検証済み同等経路）を実行する。
4. fixed outer patches と confined control points が動いていないことを確認する。
5. moved surface/mesh を export して hash を取る。
6. geometry、clearance、`checkMesh` qualification を実行する。
7. `simpleFoam` は実行せず、pair-side preflight artifact を記録する。

32 個すべての morpher/mesh sides が通過するまで primal campaign を開始しない。一つでも失敗したら停止し、
結果を見た後に epsilon ladder を縮めない。

主要 check:

- prescribed variable-space displacement の厳密な sign symmetry
- plus/minus case 間で `varID` permutation がないこと
- moved surface が watertight、manifold、non-self-intersecting であること
- volume、minimum width、component/root、0.25 m clearance gate
- 登録済み concave-cell profile とその他すべての mesh-quality gate
- case metadata、response identity、OpenFOAM image の hash

### Slice C — 共有 centered-FD primal catalog の実行

Slice A と Slice B の全ケースが通過した後に限り、次を行う。

- 同一 machine 上で 32 primal cases を逐次実行する。
- PQ2 や別の重い OpenFOAM campaign を同時実行しない。
- 各 side で residual convergence と force stationarity を必須とする。
- 同じ case を両 response manifest で共有できるよう、各 run から `Cd` と downforce の両方を読む。
- 両 side が通った場合だけ `(R(+epsilon) - R(-epsilon)) / (2 epsilon)` を計算する。
- 各 response value を moved-mesh hash と case-metadata hash に拘束する。
- failed rows を削除せず保持する。

既存 baseline primal の OpenFOAM clock time は約 25 秒である。32 primal の solver 部分だけなら下限は約 13 分だが、
case copy、mesh motion、`checkMesh`、qualification、I/O が実 wall time を支配し得る。この値は目安であり、
所要時間の約束には使わない。完了後に実測 campaign time を記録する。

### Slice D — drag と downforce を別々に判定

各 response の各 direction/epsilon について次を判定する。

- base adjoint gate が通っている。
- 両 perturbation side が geometry、mesh、residual、stationarity gate を通っている。
- analytic と centered-FD の符号が一致する。
- analytic derivative が分解可能な場合、相対誤差が 5% 以下である。
- epsilon ratios が登録済み plateau を形成する。
- response 自身の gradient-aligned direction が noise floor より大きい。
- non-aligned near-zero direction には事前登録済み absolute-error rule を使う。

| 結果 | 対応 |
| --- | --- |
| drag pass かつ downforce pass | `both_pass=true` を記録し、別の one-step manifest を準備する。同じ evidence slice では shape を更新しない。 |
| どちらかが fail | `shape_update_allowed=false` を維持し、sign、area weighting、normal convention、variable mapping、morpher を一因子ずつ診断する。 |
| どちらかが noise 未満／unresolved | `shape_update_allowed=false` を維持し、pass と読み替えない。 |
| いずれかの pair-side gate が fail | campaign を停止し、one-sided difference への置換や応答を見た後の epsilon 調整をしない。 |

### Slice E — 別 checkpoint の後に限り、Stage S shape step を最大一回

両 surface derivative が通過した場合に限り、次を行う。

1. 完全な FD evidence を review checkpoint として commit・push する。
2. displacement bound と acceptance rule を持つ小さい一歩専用 manifest を別途登録する。
3. body-fitted shape update を最大一回だけ実行する。
4. geometry、volume、width/gap、root/connectivity、clearance、mesh、residual、stationarity、response gate を再実行する。
5. 実現した response change が登録済み directional prediction と整合しない、または combined uncertainty より小さい場合は update を棄却する。

一回の成功だけを根拠に Hamilton-Jacobi evolution、reinitialization、multi-step Stage S optimizer へ進まない。

## 8. 並行・後続作業

- PQ2 の登録済み Stage V domain/boundary factor は独立課題だが、Work F と同じ solver resource を競合させない。
- P6 は Stage T Path B の制限として残り、Work F surface-FD が成功しても close しない。
- P16 は Stage V downforce drift が非単調で登録上限を超えているため open のままである。
- PQ5 は独立した three-grid baseline/T/S comparison であり、candidate 固有の numerical/extraction uncertainty を
  改善量が超えるかを判定する段階である。
- PQ6 の target physics、turbulence、finite-wing、moving-ground/multipoint、full-vehicle は PQ5 より後に置く。

## 9. 推奨する直近 checkpoint

次の reviewable implementation は Slice A と Slice B だけに限定する。

> base B-spline derivative vector を厳密に認定して hash で拘束し、登録済みの 4 本の active-variable
> direction を materialize する。そのうえで所定の control-point morpher を実装し、perturbation primal は
> 実行せず、32 個すべての morpher/mesh preflight を通す。

これは、現在の adjoint output を監査可能な FD input へ変換しつつ、高コストな response campaign を
fail-closed に保つ最小 slice である。この checkpoint を検証して push した後なら、登録済み epsilon ladder、
directions、tolerances を変更せずに、32 本の共有 primal run を開始できる。
