# WP4 TOPO-2D-00 WaterLily 側 — Amendment 5 報告

## 状態

**DONE（Amendment 5 の実装・専用テスト・CPU検証・全体回帰を完了）**。本測定はNOT_RUN。

基点は `db36e4e50f3e926ff71fe2fff9de804c7aec4511`、branch は
`feat/gen01-w1-04-topo2d-waterlily`。開始時の tracked / untracked 差分は空。
今回の authority は follow-ups worktree の登録 Amendment 1–5 と Opus review
`wp04_review_1_opus.md`。読取元パスとSHAは `wp04_validation_amend5/authority.json`。
この報告は実装と短いCPU/software validationであり、TOPO-2D-00本測定、TR-00適格化、
GPU適格化、物理downforce、Re転写、FSAE、grid independenceの結果ではない。

GPU・Kaggle・RANS実行、登録・凍結・ロードマップ改定はしていない。
最新 Amendment 5 に従い、commit／push／PR #89 更新は Claude host が行う。
この agent は stage／commit／push を行っていない。

## 作ったもの（今回の修正）

- `julia/CFDSDFWaterLily/gen01/Topo2D.jl`：静的sceneのstepを remeasure=false、
  fingerprint／preflight／summaryを更新。Δtの機械精度崩壊をNUMERICALにする。
- `scripts/topo2d_selftest.jl`：E1/E2の再測定経路とのbit一致、branch内WP1の再開、
  E1/E2/E3 tuple unionのisbitstype、実jobのtiny-Δt exit42を追加。
- `src/cfd_harness/scene_campaign.py`：prefix環境scrub、exact stop key、親pre-runの
  別選択・verify、raw再計算による窓admission、未照合geometryのformal拒否。
- `scripts/topo2d00/prerun_window.py`：実force履歴からB／S0／Wを導出し、式・単位・
  raw SHAを持つrecordをexclusive-createする。手入力の統計ではformalに入れない。
- `docs/harness/topo2d00_campaign.json`：既存3kernelを維持、E1/main/phase0の親を
  各Reに追加。127宣言state = primary96 + confirmation8 + secondary16 +
  determinism1 + DOMAIN4 + prerun2。通常formal集合は従来の125、親は別実行。
- `scripts/topo2d00/analyze.py`、`check.py`：per-Re判定、点推定σ、研究ラベルの
  precedence、凍結raw digitisationの再計算、tr00.jsonとSHA256SUMS、written-once。
  checkerはanalyzerもWP5 readerもimportしない。
- `src/cfd_gen/topo2d/geometry.py`：形を変えず、鼻の薄さをmetadataへ追加。
  `docs/harness/topo2d00_scenes/*.json` 全10件を再出力し、全polygon/surface座標が
  変更前と完全同一であることをassertした。sharp3件はJSON bytesも従来どおり。
- `reports/topo2d00_scene_schema.json` とPython／Julia docstring：開いた頂点列、
  暗黙の閉辺、重複拒否を明記。schemaは構造、実gateは距離・sampling・交差を検査。
- `reports/topo2d00_rans_result_schema.json`：observableと既存WP5 raw-reference
  manifest interfaceを明記。WP5とのschema byte一致は指定どおりClaudeが統合する。
- `scripts/topo2d00/plot_geometry.py` と図：E3鼻の注意を追加。
- `tests/topo2d00/`：全ラベル、P=2 DOMAIN、raw参照偽造、全5geometryのverification、
  生成器metadata、pre-run estimator／formal admission／環境scrubを回帰検査。

[実行記録と後日のrunbook](wp04_validation_amend5/README.md)。
旧validation／旧evidenceは保持し、今回の記録は同directoryにのみ追加した。
今回の移動はない。cfd_gen／Julia gen01への移動は既に基点に含まれる。
`src/cfd_sdf/topo2d/` と `julia/topo2d/` は存在しない。

## 幾何、出所、厚肉化と解像度

座標は既存 `data/zz2003/{single_element_table2,main_element_table3,flap_table4}.dat`
の44／44／18行。今回再転記・推測補完はしていない。採用済みindexed OCR転記を保ち、
全行の `# UNVERIFIED` とsourceの `UNVERIFIED_OCR` は維持した。PDFページ画像照合は
未完で、formal入場は意図どおり拒否される。研究freezeやsource検証済みへの昇格はない。

Table3×380mm と T2-0 sharpened table×223.4mm を同順に比較した最大絶対差は、
(suction x,z; pressure x,z) の順で **0.05234、0.81702、0.04600、0.85498 mm**。
元の有限TEとXFOIL-sharpened TEは同じ座標列ではない。自然CubicSpline補間、
線分0.1–1mm、隣接比≤3、TE capの2頂点以外の折れ角≤5°は既存規則を維持。
全10 scene の最短線分0.1331799225mm、最長0.9929049002mm、隣接比最大2.8975646881、
非cap角最大3.4453710530°。重複終点なし、最後→最初の辺も検査／SDF評価する。

正overlapは上流TE中点x−下流LE x、正gapは下流suction最低z−上流TE中点z。
最終配置は9／12mm、回転中心(0.567,0.076)c。E2実合成弦は379.428107730mm、
姿勢14.436796729°、正規化は公称c=380mm／14.1°。E3は半弦フラップ2個、
総角度等分、同じgap/overlap規則の構成であり、公開3要素実験の再現ではない。
`*_sharp` は公開有限TE原形で `mathematically_sharp=false`。

| grid／scene | main最大厚肉比 | flap1最大比 | flap2最大比 |
| --- | ---: | ---: | ---: |
| 主格子E1 | 4.594745 | — | — |
| 主格子E2 | 4.594745 | 8.866711 | — |
| 主格子E3 | 4.594745 | 17.733423 | 17.733423 |
| 確認格子E1 | 3.063211 | — | — |
| 確認格子E2 | 3.063211 | 5.911141 | — |

| Δx | mm/cell | c1 cells | flap cells | 半flap cells | 公称gap cells | 4Δx mm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c1/120 | 1.861666667 | 120 | 89.006267 | 44.503133 | 6.445837 | 7.446666667 |
| c1/180 | 1.241111111 | 180 | 133.509400 | 66.754700 | 9.668756 | 4.964444444 |

実Euclidean gapはE2で約8.57mm、E3で約8.40／8.93mm。
公称12mmと区別する。高さ100mmは h/c1=0.447627574／h/c=0.263157895、
80mmは0.358102059／0.210526316。宣言したconfig／heightとscene JSONが違えば拒否。
確認格子は自分の4Δxで再厚肉化するため、格子と幾何の両方が変わる対照であり、
純粋なgrid refinementとは呼ばない。

**E3鼻の注意。** 半flap元最大法線厚さは6.701146189mmで、主格子の
 t_min=7.446666667mm未満。登録Amendment5 §5の概数「弦の最初12.9%が4Δx未満、
6.9%が(2+√2)Δx未満」をsceneの `registered_approximate_chord_fractions` に保持した。
別に、paired camber-normal widthと弦方向射影を明示した最初の線形補間crossingは
12.608231%／6.846234%で、登録の概数とは別項目にした。幅・弦座標の定義を曖昧にして
概数を厳密一致した値とは扱わない。形は変更していない。
鼻はslot内にあり、LE cap／smoothstep rampとともにphase-coreのbulk証明から除外される。
厚さfloorは元の最大厚さstation以後の実polygon法線幅に対するもので、鼻全域の正の
厚さ下限や全phase coreを主張しない。H3と後日の結果解釈にこの注意を残す。

![E1 E2 E3 geometry](topo2d00_geometry.png)

## インターフェースと判定

Python geometry API、13既存CSV列とcur/nds/cv・要素別追加列、force=−(pressure+viscous)、
 drag=+Fx／downforce=−Fz、endpoint-clipped time-weighted mean、drift、共通phaseで
地面も一緒に動かす意味は維持。今回のbranchにForce00.jlは無く、**curのみ**を検証。
nds/cvは予約列NaNで、3readout成功を主張しない。
WP1はbranch内 `gen01/Checkpoint.jl` を使い、provider環境なしで検証した。
WP1本体のdocstringではremeasure=falseは未検証だが、今回のWP4静的sceneのCPUでは
fresh restore後の場・rows・Δt・窓までbit一致した。CUDA restoreは未確認。

各Reの必要区間は downforce Δ12／Δ23 のWと全qualified RANS cellsの90%区間。
どれか0を含めばC(Re)=UNRESOLVED、それ以外でΔ12符号または平均順位が違えば
DISCORDANT、他はCONCORDANT。先行INVALID→TR_UNQUALIFIED→NUMERICAL→INCOMPLETE→
RESOLUTION_LIMITEDの後、片方unresolvedならUNRESOLVED、両方discordantならDISCORDANT、
concordantとdiscordantの組ならCONCORDANT_PARTIAL、両方concordantならCONCORDANT。
非単調順位の追加隣接区間（E1↔E3など）のresolutionは記述として保持する。
`INVALID`を除いた8研究ラベル、含めた9ラベル全ての到達性を検証した。

σ_d=max(A=phase対差分SD, B=within-run batch SEを対差分SDへ伝播)は点推定。
SE=σ_d/√P、区間=平均±t(.95,P−1)×SE。上側σ係数とBonferroni分割は削除した。
DOMAINのP=2合成例は差0.5、pooled SE=√0.02、z=3.5355でDOMAIN_SENSITIVEを検出。
cell内のINCOMPLETE>MESH_FAILED>NUMERICAL>SETTLEDと研究ラベルの優先順位は分離し、
研究レベルでは独立したNUMERICALがcapより先。MESH_FAILEDも研究NUMERICALへ写像する。
Fieller区間、TR ratio/sign、drag符号、manipulation、determinism、readoutを独立再計算する。
RETENTIONはrelative incrementのdelta-method分散にFiellerを使う近似で、厳密な入れ子比ではない。

共有RANS schemaは `reports/topo2d00_rans_result_schema.json`。
RANS schema SHA-256: `5bba0a153fc033d2a9a0a6f42bbb37d0efe134bce7b8f96fa57472dafad4d175`。
scene schema SHA-256: `d16f0285bccf0882e3c9f1a8f33b05da7d9fb61b97e72c41f25bd3435793c4e2`。
`observable=pressure_cl` はsharp/Cp比較、`total_cl` はthick/WaterLily比較。
observableをまたぐ差分を拒否する。共通c1=223.4mm、両height正規化、model/familyごとの
8paired realisations、相異なるmesh SHA、失敗状態とnull forceを明示する。

WP5既存のraw reference interfaceを再利用した。

```json
{
  "provenance": {
    "reference_estimate": {
      "kind": "topo2d00_pressure_reference_v1",
      "observable": "pressure_cl",
      "manifest": {"path": "canonical absolute path", "sha256": "SHA-256"}
    }
  }
}
```

manifestは `topo2d00_cp_manifest_v1`。E1はtabulated_cl／cl_curve／cp、E2は2要素Cp。
`reference.source.digitization_records` がmanifestと全raw CSVを列挙し、study freeze.inputsが
全件を束縛する。formal CLIはscalar summaryだけでは動かない。
保存normalized inputの `reference_inputs={manifest,sha256:{absolute_path:digest}}` を
両実装が毎回再ハッシュし、別コードで積分する。Cp面10点以上、単調・全extent、
各要素downforce-positive、向き/BOM/改行/float表記を正規化しても異なる2読取を要求。
ΔClとΣ_element |Cl_A−Cl_B|を再計算してsummaryと照合する。
符号逆のreading差+0.006／−0.004で正しい保守的和0.01を再現し、先に合計して差を取る
0.002とは区別した。実WP5 digitizer（読取専用）との数値一致も記録した。
純粋な合成算術APIのみraw参照を省略でき、formal CLIの例外ではない。

出力 analysis.json／analysis.md／tr00.json／SHA256SUMS は全4pathをexclusive-createで
予約してから書く。どれか存在すれば既存bytesを変えず拒否。checker CLIはtr00と
3成果物のchecksumも検査する。合成出力のCONCORDANTはfixtureだけの結果である。

親pre-runは各ReのE1/main/phase0、horizon520c1/U。`--prerun`で独立に実行・verifyする。
`prerun_window.py SERIES SUMMARY` はB／S0／W／単位／formula／raw SHAを1回だけ書く。
Bの100-wide block開始は0/100/200/300、後続complete100-block平均±sample_SD/√nに
入る最初を採りB=max(80,start)。後続2block以上、未bracketの候補は外挿せずskip。
S0はpost-Bの5/10/20/40/80 complete batchesのlength×分散の片側90%χ²上限の最大。
Wは1.5%条件を満たす最小50倍数、上限400。rawのない手入力やcap超過は拒否する。
単位はN/m（ρ=1,U=1）、c1/U、S0は(N/m)^2·c1/U。これらは測定前に固定したengineering
離散化で、formal σ_dの点推定とは別。詳細と後日のコマンドはrunbookに記録した。
実pre-run未実行なので `docs/harness/topo2d00_window_re*.json` は作っていない。

runnerはTOPO2D_*／W4_*／CUDA_*をscrub後にcampaignの明示envを適用し、所有identityを設定。
Numerical stopは(config,Re,height,role)だけに適用。Δtの非有限／非正／時刻進行不能、
または Δt≤eps(T)×max(1,|solver_time|)をNUMERICALとする（物理閾値ではなく機械精度基準）。

## テスト

- `.venv/bin/python -m compileall src tests`：exit0。
- `.venv/bin/python -m pytest -q tests/topo2d00 -p no:cacheprovider`：**278 passed、62.82秒**。
- `julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/topo2d_selftest.jl <今回出力先>`：
  **86/86 pass、test56.0秒／process57.228812秒**。実行環境はTOPO2D_*／W4_*／CUDA_*を
  親から除去しJULIA_NUM_THREADS=1のみ上書き。外部provider/source注入なし。
  Julia1.12.6／WaterLily1.8.0／Array／Float32／QUICK／1thread、CUDA未読込。
  E1/E2 bit一致、動く地面、共通phase、bulk core、WP1再開、tuple isbitsを確認。
  tinyΔtの実job exit42／NUMERICALは意図したnegative testで、通常runの失敗ではない。
- 独立Python host_readouts：raw CSVからの窓がJuliaと≤1e-12 N/mで一致。
- 汚染env実CPU smoke：**exit0、29.554秒**、actual840×824、6steps、finite forces、
  top_factor=1、remeasure=false。harness verify integrity.pass=true。
- 合成write→checker CLI：discrepancies=[]、written-once再書込拒否。
- 全体 `.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider`：**4160 passed／74 skipped／0 failed、749.61秒（process 750.232秒）、失敗node集合=[]、指定baseと一致、source前後SHA一致**。
- `git diff --check`：exit0。7295 warningsは既存pytest deprecation等で、raw logを保持した。

baseはユーザー提供Claude hostの `e3dcdf61`、3482 passed／74 skipped／0 failed、
失敗node集合=[]。base側は今回再実行していない。結果側だけを指定flagsで完走し、
件数でなくnode集合を比較する。正確argv／環境／時間／source前後SHA／raw logは
`wp04_validation_amend5/`。raw logはSHAを記録したgzipで保持する。

## 仕様からの逸脱、未確認の仮定と§10への回答

4Δx、[0.5,2]、α=.05、予算・既存job・力の符号・窓定義は変更していない。
全保護pathの変更／新規file集合は空（tracked36341件）。参照INTERFACEの指定pathは無く、
実canonical `scripts/screen01/INTERFACE.md` を全文読んだ。README指定の全governing文書と
phase_plan全7782行はworkerと範囲分担して省略せず確認した。
OpenCode MCP未提供、CLIはlog権限失敗、隔離XDGではproviderなし。global設定・課金を
変更せずnative workerへfallbackした（`worker_routing.json`）。

| 登録§10項目 | 今回分かったこと／残るもの |
| --- | --- |
| 座標、Cp参照、DOI | 採用済みOCR転記を保持しT2-0差とsamplingを検証。PDF画像照合、Table15 h/c1=.448の確認、実double Cp2読取・一次DOI確認は未完。formalは拒否。 |
| E3構成 | 半弦2個・角度等分・9/12mm規則を維持。公刊3要素referenceなし。鼻の注意を数値化。 |
| 2D job、厚さ、core | CPU契約は成功。LE/ramp全域、GPU、長窓、iid/batch近似のadequacy、物理は未確認。 |
| blunt-TE multi-body meshing | WP5の範囲。今回mesh/checkMesh/RANS実行なし。shared raw-reference readerのinteropはsoftwareのみ。 |
| Mahon & Zhang、model選択 | 本WPでは原論文に基づくSA/SST適格化はしない。 |

## Claude／ユーザーへの提案する追記・次に要るもの

hostで下記ファイルをcommit/pushしPR #89本文をこの最終実装に揃える。
登録本文を本agentが修正する必要はない。実referenceと画像確認、schema bytesとscene SHAの
WP5統合、review／freeze／backend gateの後にのみ親pre-runと本測定へ進む。
ユーザー機材で行うGPU smokeの条件はrunbook末尾に記録した。直接job、T4 project、
backend=cuda/smoke=1、実GPU UUID、clean env、scratch、E1→E3 formal grid数百step、
compile／tuple parameter／measure!対mom_step! ms/step／CPUとのfinite force比較を記録する。
これはcapability-onlyであり、GPU gateやTOPO-2D-00 evidenceへ昇格させない。

## Hostでcommitすべき完全な一覧

今回の移動はなし。raw `.log` はlossless gzipをcommitし、元path／SHAは `log_archives.json`。
機械可読一覧は `wp04_validation_amend5/wp04_pending_files.json`。

### 変更（24ファイル）

- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_geometry.png`
- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_design.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_report.md`
- `docs/harness/topo2d00_campaign.json`
- `docs/harness/topo2d00_scenes/E1.json`
- `docs/harness/topo2d00_scenes/E1_fine.json`
- `docs/harness/topo2d00_scenes/E1_h80.json`
- `docs/harness/topo2d00_scenes/E2.json`
- `docs/harness/topo2d00_scenes/E2_fine.json`
- `docs/harness/topo2d00_scenes/E2_h80.json`
- `docs/harness/topo2d00_scenes/E3.json`
- `julia/CFDSDFWaterLily/gen01/Topo2D.jl`
- `scripts/topo2d00/analyze.py`
- `scripts/topo2d00/check.py`
- `scripts/topo2d00/plot_geometry.py`
- `scripts/topo2d_selftest.jl`
- `src/cfd_gen/topo2d/geometry.py`
- `src/cfd_harness/scene_campaign.py`
- `tests/topo2d00/synthetic.py`
- `tests/topo2d00/test_analyze.py`
- `tests/topo2d00/test_campaign.py`
- `tests/topo2d00/test_check.py`
- `tests/topo2d00/test_geometry.py`

### 新規（74ファイル）

- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_scene_schema.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/README.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/SHA256SUMS`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/authority.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/campaign_validation.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/checker_cli.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/compileall.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_host_verification.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E1/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E1/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E1/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E1/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E2/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E2/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E2/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/E2/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/dt_collapse/ERROR.txt`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/dt_collapse/job_preflight.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/dt_collapse/job_preflight.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/dt_collapse/numerical_failure.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/dt_collapse/numerical_failure.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/job_entrypoint/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/job_entrypoint/entrypoint.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/job_entrypoint/entrypoint.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/job_entrypoint/entrypoint.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/job_entrypoint/job_preflight.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/job_entrypoint/job_preflight.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/selftest.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_selftest/selftest.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_stderr.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/cpu_stdout.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/full_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/full_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/geometry_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/geometry_regeneration.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/geometry_summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/log_archives.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_force_table.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_job.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/harness_index.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/output_manifest.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/run_identity.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/states/E1_h100_re1000_main_k01/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/states/E1_h100_re1000_main_k01/job_preflight.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/states/E1_h100_re1000_main_k01/job_preflight.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/states/E1_h100_re1000_main_k01/re1000.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/states/E1_h100_re1000_main_k01/re1000.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/polluted_env_smoke/states/E1_h100_re1000_main_k01/re1000.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/protected_source_closure.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_analysis/SHA256SUMS`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_analysis/analysis.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_analysis/analysis.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_analysis/tr00.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/README.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e0_A_lower.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e0_A_upper.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e0_B_lower.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e0_B_upper.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e1_A_lower.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e1_A_upper.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e1_B_lower.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_e1_B_upper.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/synthetic_reference/digitization_manifest.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/targeted.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/targeted_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/validation.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/worker_routing.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend5/wp04_pending_files.json`
- `scripts/topo2d00/prerun_window.py`
- `tests/topo2d00/test_prerun_window.py`
