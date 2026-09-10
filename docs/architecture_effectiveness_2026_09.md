# 採用アーキテクチャ有効性スパイク

実施日: 2026-09-10  
対象 commit: `9c55edd76534ba138026bbc9bc4c49e2e21a0886`  
判定: **アーキテクチャは研究開発方針として維持する。ただし、全体の有効性は未実証であり、production へは昇格させない。**

## 1. 今回答えた問い

採用した構成は、次の因果を狙っている。

```text
ProblemSpec / geometry gates
  -> Stage T: density/Brinkman topology exploration
  -> Stage S: density surface extraction and SDF refinement
  -> Stage V: independent body-fitted verification
```

今回の優先課題は、細部の完成度ではなく、この構成が実際の CFD 応答を改善方向へ動かせるかを調べることだった。そこで、現在 non-mock で閉じている最長の経路について、実 OpenFOAM 感度、密度更新、同じ fidelity の別 primal process による再評価を行った。未接続の段は実装済みとみなさず、断線として記録した。

## 2. 結論

| 問い | 判定 | 根拠 |
| --- | --- | --- |
| Stage T の密度変数は実 CFD 応答を制御できるか | **狭い条件で yes** | 8192セルの固定格子 Brinkman ケースで primal と2随伴が収束し、小摂動の方向微分が有限差分と2.23%および4.35%で一致した |
| 随伴勾配から作った候補は同一 fidelity の再評価でも改善したか | **目的単独、小ステップでは yes** | `J=-C_DF` の予測変化 `-0.018945` に対し、同じ固定格子・物理設定の別 primal process の実変化は `-0.018091`、予測誤差4.51%だった |
| 現在の更新幅をそのまま実用反復に使えるか | **no** | move limit `0.03` では実変化/予測変化が0.2815まで低下した |
| 現在の目的・効率・density surrogate下限を同時に満たす更新ができたか | **no** | 初期点が効率制約と active-cell mean `rho` 下限を満たさず、既存 T5 線形化ゲートが候補を棄却した |
| Stage T の改善を Stage S へ同一候補として渡せるか | **未実装** | T5 の cell-data `rho` から iso-surface/SDF と幾何 binding を作る CLI/artifact bridge がない |
| SDF refinement 後も body-fitted CFD で改善するか | **未実証** | sharp-interface refinement solver が未完成で、Stage T 候補と Stage V の因果も接続されていない |
| 32GB Mac/Windowsで高速になるか | **未実証** | Mac の小規模 Docker 実行だけを確認した。Windows RTX 4070 Ti、CUDA、対象規模、peak memory、time-to-improved-feasible-design は未測定 |

今回得られた肯定材料は、Stage T の局所的な数値制御に限られる。それでも、density/Brinkman をトポロジー生成に残し、SDF を形状精緻化に使い、body-fitted CFD で独立監査する責務分担を捨てる理由は生じていない。次の投資先は新しい高速ソルバではなく、現在切れている Stage T -> Stage S -> Stage V の最小実証経路である。

## 3. 実験条件

| 項目 | 値 |
| --- | --- |
| 実行機 | Apple M4、32 GiB unified memory |
| 実行基盤 | Docker、`opencfd/openfoam-default:2512` |
| solver | `adjointOptimisationFoam` |
| 流れ | 定常・非圧縮・層流、`U=(1,0,0)`、`nu=1e-2 m^2/s` |
| 格子 | 一様固定格子、`32 x 16 x 16 = 8192` cells |
| 設計セル | 2909 active cells |
| Brinkman | linear interpolation、`betaMax=2500` |
| 応答 | porous directional drag `+X`、downforce `-Z` |
| 係数基準 | `Aref=0.64`、`UInf=1` |
| 目的 | `J=-C_DF` |
| 診断用効率制約 | `g=3 C_D-C_DF <= 0` |

このケースは高速な数値診断用 fixture である。自動車外部空力、対象 Reynolds 数、乱流境界層、移動地面、車輪、実寸法の物理モデルではない。

完全な基準実行 artifact では primal が154反復、drag adjoint が660反復、downforce adjoint が1078反復で収束した。OpenFOAM solver が最終行で報告した `ClockTime` は28秒、`ExecutionTime` は27.52秒だった。Docker起動、case生成、library staging、再構成、VTK変換は含まないため、E3の総時間やコンテナ全体のwall timeではない。この値は小規模 Mac fixture の能力確認に限り、Windowsとの速度比較や実用規模の性能予測には使わない。

## 4. 局所勾配の実測

基準応答は次の通りだった。

| `C_D` | `C_DF` | `J=-C_DF` | `g=3 C_D-C_DF` |
| ---: | ---: | ---: | ---: |
| 3.41235451 | 0.63588104 | -0.63588104 | 9.60118249 |

感度で正規化した全 active-cell 方向に対して、別々に生成した plus/minus ケースを OpenFOAM で再計算した。

| 応答 | epsilon | 有限差分 | 随伴予測 | FD/adjoint | 相対誤差 | 符号 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| efficiency constraint | `1e-4` | 4266.189887 | 4363.487386 | 0.977702 | 2.23% | 一致 |
| downforce | `1e-4` | 339.086186 | 354.494976 | 0.956533 | 4.35% | 一致 |
| efficiency constraint | `1e-2` | 1228.160730 | 4363.487411 | 0.281463 | 71.85% | 一致 |

`epsilon=1e-4` では、局所勾配の符号と大きさが実 solver 応答に整合した。`epsilon=1e-2` の plus 側では、ゼロ密度に近い多数のセルへ材料が加わり、drag が3.412から11.329へ跳ねた。これは密度下限での非対称 clipping と Brinkman 応答の非線形性が強いという解釈に整合するが、両要因の寄与を独立に分解した実験ではない。直接確認したのは、応答の跳躍とFD/adjoint比の低下である。

この結果は、単一 epsilon の偶然だけを採用根拠にしないことも示している。小さい摂動で通った勾配を、その100倍の更新幅に外挿してはならない。

## 5. 一更新と再評価

既存の T5 projected-gradient adapter で、move limit を `1e-4` に制限した目的単独の候補を作り、同じ固定格子上の別 primal で再評価した。この候補は downforce 感度方向の plus ケースと同じ局所診断であり、独立した二つの成功回数には数えない。

| 量 | 基準 | 線形化予測 | 再評価 | 実変化 |
| --- | ---: | ---: | ---: | ---: |
| drag `C_D` | 3.41235451 | - | 3.44273716 | +0.03038265、+0.89% |
| downforce `C_DF` | 0.63588104 | - | 0.65397239 | +0.01809135、+2.85% |
| objective `J=-C_DF` | -0.63588104 | -0.65482628 | -0.65397239 | -0.01809135 |
| efficiency constraint `g` | 9.60118249 | 9.67282518 | 9.67423909 | +0.07305660、+0.76% |

予測した目的変化は `-0.01894524`、再評価した目的変化は `-0.01809135` だった。実変化/予測変化は0.95493、相対予測誤差は4.51%である。したがって、**目的だけを見る局所ステップは意図した方向に効いた**。

ただし、この候補は効率制約を悪化させた。制約を無効にした診断なので、最適化成功や採用可能形状ではない。

同じ診断を move limit `0.03` で行うと、目的変化の予測は `-5.68357`、再評価は `-1.60050` で、実変化/予測変化は0.2815だった。目的の符号は改善側だったが、drag は3.412から6.377、効率制約は9.601から16.896へ悪化した。現行 adapter に非線形再評価、accept/reject、rollback、trust-radius 更新が必要である。

## 6. 制約付き最適化がまだ成立しない理由

既存の efficiency と active-cell mean-`rho` limits を有効にした候補は、`linearized_reject` になった。

- 基準点は `g=9.60118 > 0` で、最初から efficiency 制約外だった。
- active-cell mean `rho` は0.01925で、設定下限0.05を満たさなかった。この値はdensity surrogateの平均であり、抽出STLやbody-fitted形状の物理体積率ではない。
- move limit `0.03` 内の候補でも、線形化した `g` は約357.34、active-cell mean `rho` は0.04374だった。
- 真の実行可能性回復とは別に、move limit `1e-4`、efficiency limitを初期値9.60118に置いた非悪化診断も行った。既存 projected-gradient adapter は40回の投影後も、この緩い非悪化条件を満たせなかった。これは `g<=0` への回復試験ではない。
- connectivity nominal/eroded は未評価で、T5では無効だった。このため、今回の「制約付き」判定はefficiencyとactive-cell mean `rho` に限られ、全ての製造・連結制約を試したものではない。
- dense SLSQP backend のproduction適合性を追跡可能なartifactとして測定していない。scalable constrained backendの選定は未評価である。

この失敗はアーキテクチャ全体の反証ではない。現在の canonical seed、制約値、体積意味論、optimizer adapter の組合せが、実用的な feasible-start または feasibility-restoration 問題になっていないことを示す。現状の成功は unconstrained local sensitivity control で止まっている。

## 7. エンドツーエンドの断線

現在の最長 non-mock 経路はここまでである。

```text
fixed-grid rho
  -> Brinkman alpha/beta
  -> OpenFOAM primal
  -> OpenFOAM adjoint density sensitivity
  -> bounded density update
  -> same-fidelity OpenFOAM re-evaluation
```

次の経路は一つにつながっていない。

```text
T5 cell-data rho
  -> iso-surface STL
  -> density-to-SDF fidelity report
  -> geometry-role / ProblemSpec binding
  -> SDF sharp-interface refinement
  -> body-fitted OpenFOAM comparison
```

legacy topology prototype には point-data density から STL を出す経路があり、legacy STL を SDF と body-fitted OpenFOAM に渡す経路もある。一方、T5 が書く cell-data `rho` を同じ候補として Stage S/V へ渡す bridge はない。逆方向の legacy-density -> Stage-T contract だけが存在する。

また、現状の fixed-grid と body-fitted 設定では `Aref`、`UInf`、応答の単位・方向、格子写像が統一されていない。raw coefficient を直接比較して cross-fidelity agreement と報告できない。

## 8. 採否の再検討

アーキテクチャの各責務を一つの巨大ソルバへ統合する必要はない。今回の結果は、分離した設計の利点も示した。Stage T の局所感度だけを独立に合否判定でき、大ステップの非線形性と Stage S/V の欠落を、数値成功から切り離して記録できたからである。

本採用の意味を次のように固定する。

1. density/Brinkman は、新しい material の発生・消滅を含むトポロジー探索候補として維持する。
2. SDF は、抽出された境界の fidelity を確認した後の sharp-interface refinement に使う。
3. body-fitted OpenFOAM は、最適化と独立した監査経路として維持する。
4. LBM/CUDA/Metal は、同じ問題と acceptance gate で time-to-improved-feasible-design が短いと実測された範囲だけ昇格する。
5. 現時点の Stage T は「局所数値能力あり」、Stage S/V を含む全体は「効果未実証」と表示する。

## 9. 次に行う最小実証

小機能を増やす前に、以下を一つの canonical 問題で閉じる。

1. **共通応答を固定する。** Stage T/V で `Aref`、`UInf`、密度、方向、係数式、境界条件を同じ ProblemSpec artifact に束ねる。
2. **T5 -> S bridge を作る。** cell-centered `rho` から iso-surface を抽出し、STL、threshold、grid transform、hash、geometry role を持つ fail-closed artifact を出す。
3. **handoff fidelity を測る。** 体積誤差、surface/Hausdorff error、component/root preservation、hard-mask、最小厚さ・隙間を候補ごとに判定する。
4. **同一候補を独立再評価する。** 初期形状と小ステップ候補を body-fitted OpenFOAM の少なくとも3格子で計算し、圧力・摩擦・合力を比較する。
5. **予測/実改善で候補を採否する。** Stage T と Stage V の符号、改善比、制約余裕を記録し、悪化時は rollback して move limit を縮める。
6. **実行可能性を回復する。** 初期 seed と制約を整合させるか、明示的な feasibility-restoration phase を設け、目的改善と制約回復を混同しない。

この最小経路で同じ候補の改善が Stage V まで残れば、採用アーキテクチャの中心仮説が初めて実証される。残らなければ、density-to-surface transfer、Brinkman fidelity、または対象物理のどこで改善が反転したかを特定して、その段だけを修正する。

判定は次の3ゲートに限定する。

| ゲート | Go 条件 | 今回の状態 |
| --- | --- | --- |
| E1: Stage T 一更新閉ループ | primal/adjoint が数値ゲートを通り、同一fidelity再評価後に目的が改善し、ProblemSpecで要求した全制約が実行可能。予測変化がノイズより十分大きい場合、暫定的に実変化/予測変化を0.5–2.0に収める | **No-Go**。局所目的と予測比は通ったが、efficiency とactive-cell mean `rho` は実行不可能。connectivityは未評価 |
| E2: Stage V 独立3格子比較 | fine-grid 改善が正、3格子で改善符号が不変、hard constraint が全て合格。下記の正規化改善量がbaseline/candidateのfine-medium差の2倍を上回る | **未実行**。同一候補を渡す bridge がない |
| E3: 総コストと32GB適合 | 同一ホスト上で、OpenFOAM Stage Tを参照経路、候補高速backendを比較経路とし、同じE1/E2品質へ初めて到達するまでの総時間とpeak memoryを比較経路が下回る。Mac/WindowsともホストRAMとGPU/Metal allocationを別記する | **未実行**。小 fixture のsolver clockだけがある |

E1を通過した候補だけをE2へ渡し、E2を通過した結果だけを速度比較E3の「改善候補」と数える。solverの単体速度やreturn code 0だけでは高速アーキテクチャのGo判定にしない。

E2では、最小化する同じ無次元目的 `J` と、結果を見る前に固定した正の `J_scale` を使う。baselineを `b`、candidateを `c`、medium/fine格子を `m/f` として、

```text
I_f = (J_b,f - J_c,f) / max(abs(J_b,f), J_scale)
S_b = abs(J_b,f - J_b,m) / max(abs(J_b,f), J_scale)
S_c = abs(J_c,f - J_c,m) / max(abs(J_b,f), J_scale)
```

を記録し、`I_f > 2*max(S_b, S_c)` を暫定Go条件とする。coarse格子は改善符号の頑健性確認に使う。E3の `T_total` はProblemSpecと入力形状の検証開始から、最初のE2合格artifact書込みまでとし、setup、全primal/adjoint、棄却候補、handoff、独立3格子監査、I/Oを含める。

## 10. 証拠と再現境界

機械可読な要約は [`evidence/architecture_effectiveness_2026_09.json`](evidence/architecture_effectiveness_2026_09.json) に保存した。生の case、VTK、solver log は79 MiBあり、`work/architecture_effectiveness_20260910/` に置いた。`work/` はGit管理外であるため、JSONには主要 artifact のSHA-256を記録した。

このスパイクはソースコードを変更していない。実行に使った CLI と OpenFOAM case template は対象 commit の既存実装である。

完全な基準primal/2-adjoint artifactは、case templateの `nIters=4000` を保ったまま `Allrun` をDockerで実行し、`reconstructPar` と `foamToVTK` を実行して作った。主要な局所チェックは、その完全実行から作ったT1 contractと感度場を入力にし、custom objective library をビルド済みの環境で次の既存CLIから再現できる。以下の最初の `--adjoint-iterations 1` は再評価用primalを得るための短縮設定であり、上記154/660/1078反復の完全基準実行を再現するコマンドではない。

```bash
mkdir -p work/architecture_effectiveness_20260910
cp -R examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base \
  work/architecture_effectiveness_20260910/stage_t_base

docker run --rm --entrypoint bash \
  --mount "type=bind,source=$PWD,target=/work" \
  -w /work/work/architecture_effectiveness_20260910/stage_t_base \
  opencfd/openfoam-default:2512 \
  -lc 'source /usr/lib/openfoam/openfoam2512/etc/bashrc || exit; \
       export FOAM_USER_LIBBIN=/work/openfoam_extensions/porousDirectionalForce/lib; \
       export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:${LD_LIBRARY_PATH:-}; \
       bash ./Allrun'
```

この完全実行では、`openfoam_extensions/porousDirectionalForce/lib/libcfdSdfPorousObjectives.so` が先に存在する必要がある。実行後、同じimageとmountで `reconstructPar -latestTime -no-libs` と `foamToVTK` を行い、次のT1 contractを作った。

```bash
.venv/bin/cfd-sdf build-fixed-grid-contract \
  work/architecture_effectiveness_20260910/stage_t_base \
  --output-dir work/architecture_effectiveness_20260910/t1_contract \
  --efficiency-min 3 \
  --docker-image opencfd/openfoam-default:2512 \
  --solver-version 2512
```

T1以降の局所チェックは次の通りである。

```bash
.venv/bin/cfd-sdf run-fixed-grid-primal \
  work/architecture_effectiveness_20260910/t1_contract/topology_state.json \
  --case-dir work/architecture_effectiveness_20260910/t2_baseline \
  --template-case-dir examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base \
  --backend docker --execute --timeout-seconds 300 --overwrite \
  --adjoint-iterations 1

.venv/bin/cfd-sdf run-fixed-grid-sensitivity-direction-suite \
  work/architecture_effectiveness_20260910/t2_baseline \
  --run-dir work/architecture_effectiveness_20260910/t3_efficiency_direction_eps1e4 \
  --sensitivity-vti work/architecture_effectiveness_20260910/t1_contract/fixed_grid_sensitivity.vti \
  --objective efficiency_constraint --direction-mode sensitivity \
  --epsilon 0.0001 --relative-error-tolerance 0.25 \
  --backend docker --execute --timeout-seconds 300 --overwrite \
  --template-case-dir examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base \
  --adjoint-iterations 1

.venv/bin/cfd-sdf run-fixed-grid-constrained-step \
  work/architecture_effectiveness_20260910/t1_contract/topology_state.json \
  --sensitivity-vti work/architecture_effectiveness_20260910/t1_contract/fixed_grid_sensitivity.vti \
  --sensitivity-summary-json work/architecture_effectiveness_20260910/t1_contract/fixed_grid_sensitivity_summary.json \
  --primal-summary-json work/architecture_effectiveness_20260910/t1_contract/fixed_grid_primal_summary.json \
  --output-dir work/architecture_effectiveness_20260910/t5_update_local \
  --move-limit 0.0001 --volume-fraction-min 0.0 --volume-fraction-max 0.55 \
  --no-enforce-efficiency --no-enforce-connectivity --enforce-volume \
  --optimizer-backend projected-gradient

.venv/bin/cfd-sdf run-fixed-grid-primal \
  work/architecture_effectiveness_20260910/t5_update_local/topology_state.json \
  --case-dir work/architecture_effectiveness_20260910/t5_update_local_reval \
  --template-case-dir examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base \
  --backend docker --execute --timeout-seconds 600 --overwrite \
  --adjoint-iterations 1
```

T1以降のCLI列は、実感度場が既に存在する地点から始まる。ゼロからの再現では、その直前に示した完全なprimal/adjoint実行に加え、`reconstructPar` と感度fieldのVTK変換が必要である。完全実行のsolver log、case設定、custom objective libraryのSHA-256も機械可読evidenceに記録した。
