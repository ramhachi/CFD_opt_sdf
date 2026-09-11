# P0 canonical state transfer — 2026-09-11

## 判定

このスライスの判定は **capability GO / P0 qualification NO-GO** とする。

Stage Tの検証済みcanonical candidateを、uniform Cartesian OpenFOAM source gridへ
保存的に写す片道変換を実装した。許可する式は次だけである。

```text
rho_source = P @ rho_target
P[s,t] = overlap_volume(source[s], target[t]) / volume(source[s])
```

`rho_target`は`stage_t_candidate_binding.json`が指定する`rho`、`rho_filtered`、
または`rho_projected`である。`rho_source`はOpenFOAM source cellのx-fastest順序で保存する。
sourceからtargetへのstate逆変換、`P.T`によるstate変換、`rho`から`alpha`またはBrinkman係数への
意味変換は、この境界では行わない。

## 実装した境界

`transfer-stage-t-candidate-to-openfoam`は、次を入力として受け取る。

- nativeかつ`execution_ready`なProblemSpec
- 検証済み`stage_t_candidate_binding.json`
- 単一block、axis-aligned、uniform、ungradedな`blockMeshDict`
- `global_label = values[x_fastest_index]`を表す完全なNPY permutation
- 新規の出力directory

candidate bindingの検証により、ProblemSpec snapshot、canonical grid snapshot、STL由来mask
manifest、topology state、density VTI、candidate ID、parent ID、iteration、選択したrho配列を
exact hashで固定する。変換時にはtarget/source両gridのhashを
`ExactCartesianOverlapTransfer.build`へ渡し、両方の全grid domainが完全に被覆される場合だけ
`P @ rho`を実行する。

出力は次の二つである。

```text
openfoam_source_state.npz
  source_rho_xfastest
  source_rho_global_label
  source_global_cell_labels_by_xfastest

provenance.json
  problem/candidate binding identity and hash
  target density file/value hash
  target/source grid origin, spacing, shape, order, hash
  transfer matrix shape and nnz
  active-mask hashes and full-coverage result
  NPZ file hash and exported-array hashes
```

provenanceは`status=capability_only`、`qualified=false`に固定する。ここで証明したのは、
canonical stateを別解像度のuniform Cartesian solver gridへ一貫した規則で渡せることだけである。

## gradient direction suiteのlineage強化

`run-fixed-grid-sensitivity-direction-suite`は、baselineのStage T candidate bindingとProblemSpecを
対で受け取れる。検証済みcompact identityをsuite summary、direction summary、plus/minusの
topology stateへ伝播する。bindingが参照するtopology stateとbaseline topology stateが異なる場合、
run directoryを作る前に拒否する。

`aggregate-fixed-grid-gradient-gate`は各行について、次を追加で検証する。

- suite rowのproblem/candidate bindingが集約時に指定したbindingと完全一致する
- plus/minus topology stateに同じ`baseline_candidate_binding`がある
- plus/minus topology stateファイルをartifact hash一覧へ含める

このため、正しいcandidate IDをsummaryへ付けつつ、別のplus/minus density contractを混ぜる経路は
gateで失敗する。bindingなしのlegacy入力は引き続きdiagnostic-onlyであり、後付けIDでは昇格しない。

## 実行方法

```bash
cfd-sdf transfer-stage-t-candidate-to-openfoam \
  stage_t_candidate_binding.json \
  project.yaml \
  openfoam_case/system/blockMeshDict \
  source_global_cell_labels_by_xfastest.npy \
  work/candidate_0000/openfoam_source_state

cfd-sdf run-fixed-grid-sensitivity-direction-suite \
  BASELINE_CASE \
  --run-dir RUN_DIR \
  --candidate-binding-json stage_t_candidate_binding.json \
  --problem-yaml project.yaml \
  --direction-mode sensitivity \
  --epsilon 1e-4
```

## 検証

集中テストでは次を確認した。

- targetの2分割cellをsourceの1 cellへ体積平均し、期待する`P @ rho`になる
- 非identity permutationでx-fastest stateをOpenFOAM global-label順へ正しくscatterする
- state/gradientの双対性を検証する既存exact-transferテストが通る
- candidate lineage、target/source grid identity、配列hash、NPZ hashを記録する
- target/source domainのpartial overlapを拒否する
- NaN、shape不一致、`rho < 0`、`rho > 1`を拒否する
- 既存出力directoryを上書きしない
- plus/minus topology bindingの不一致をgradient gateが拒否する
- direction summary、validation report、plus/minus primal metadataのbinding改変を拒否する
- plus/minus topology state自身のlineage・density hashを照合し、同一stateの再利用を拒否する

このスライスでは、G2の720000-cell canonical candidateを実OpenFOAM caseへ投入していない。
したがって、32GB RAMやRTX 4070 Ti上の実行時間・peak memory・solver convergenceを示す証拠ではない。

## 次の実装境界

P0を完了させるには、次を同じcandidate lineageのまま接続する。

1. `openfoam_source_state.npz`の`source_rho`をsolver case compilerがOpenFOAM入力fieldへ変換し、
   rho-to-alpha/Brinkman式、field dimensions、boundary conditionをmanifestへ残す。このとき
   x-fastest indexからOpenFOAM global cell labelへの明示的なpermutation artifactを必須とし、
   identity orderingを仮定しない。
2. その入力でfresh baseline/plus/minusを実行し、decomposed `topOSens`をglobal label順へ再構成する。
3. 同じpermutationで`topOSens`をx-fastest順へ並べ、同じsource/target grid hashで
   `target_gradient = P.T @ source_gradient`を実行し、candidate binding、
   solver case、state transfer、gradient transferを一つのiteration identityへ結ぶ。
4. 同一objectiveについて`sensitivity`とseed固定`filtered-random`の2方向、
   epsilon `3e-5, 1e-4, 3e-4, 1e-3`の8行をfresh実行する。
5. primal convergence、clipping、noise floor、sign、ratio `0.8–1.2`、relative error `<= 10%`、
   response units、rho gradient convention、topology-policy valuesを一つのgateで確認する。

この8行が揃うまで、2026-09-10の8192-cell結果はdevelopment evidenceのままであり、
canonical P0 evidenceには使わない。
