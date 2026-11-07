# WP4：TOPO-2D-00 WaterLily 側 Amendment 1・2 対応報告

## 状態

DONE（本WPの実装・幾何・CPU・software検証まで。実測campaignの判定や登録の成立は含まない）。基点 `88fea06e`、branch
`feat/gen01-w1-04-topo2d-waterlily`、実行日 2026-11-06〜07。

実装、幾何、CPU capability、synthetic 統計の証拠を作成した。GPU／CUDA 初期化、Kaggle、
RANS solver、mesh 生成、課金、凍結、登録、ロードマップ変更は行っていない。
commit／push と PR #89 の更新はユーザーの Amendment 2 §7 に従い Claude host に引き継ぐ。
/tmp に repo clone は作っていない。

## 作ったもの（パス、1行ずつ）

- `src/cfd_gen/topo2d/geometry.py`：元の source closure 外へ移動し、自然 cubic spline、弧長 cap、smoothstep 法線厚肉化、連続 polygon 幅・1 mm・5°・gap／clearance／自己交差の gate を実装。
- `src/cfd_gen/{__init__.py,README.md}`：共通initはWP6とbyte一致、READMEは同じ配置規則の先頭3行を保持（WP6固有の後続追記は取り込まない）。
- `julia/CFDSDFWaterLily/gen01/Topo2D.jl`：旧 `julia/topo2d` から移動した解析 polygon SDF／2D job helper。CPU は Vector、未実行 CUDA 経路は Tuple を保持。
- `julia/CFDSDFWaterLily/gen01/README.md`：WP1 と byte 一致する registered source closure の配置規則。
- `scripts/waterlily_topo2d_job.jl`：`Base.include(CFDSDFWaterLily, …)`、total_cl と2つの高さ正規化、最新 WP1 restore identity に対応。
- `src/cfd_harness/scene_campaign.py`：独立 scene state 入口と source pins を新配置へ更新し、observable と高さを実 raw 出力から再検証。
- `docs/harness/topo2d00_campaign.json`：Re1000／Re3000／confirmation の3 kernel、125 state、共通16位相と対照。
- `docs/harness/topo2d00_scenes/*.json`：主／確認格子・h80・有限TE原形の計10 scene を再生成。W／R はこの JSON と SHA を共有する。
- `scripts/topo2d00/{analyze.py,check.py}`：observable、mesh 独立性、digitization content SHA、厚肉化のみの同一 observable 対照を独立再計算。
- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json`：登録 Amendment の observable、両 h 正規化、8 realization、失敗・記述用 metadata の共有 schema。
- `scripts/topo2d00/plot_geometry.py` と `reports/topo2d00_geometry.png`：新 spline scene の E1〜E3 図。前縁 cap と原形を表示し、最終 PNG を目視確認。
- `tests/topo2d00/*.py`：密度、転記点の補間、弧長による厚肉化の頂点番号非依存性、observable 拒否、checker、8 mesh、独立 digitization 等を追加。
- `scripts/topo2d_selftest.jl`：全56検査・全位相probeを保持し、stage timing と CPU の格納型を検査。
- `reports/wp04_design.md`：実装前の Amendment 設計と実測に基づく確定事項。
- `reports/wp04_validation_amend2/`：commands、ログ、source／artifact SHA、CPU raw、独立 WP5 adapter readback、synthetic written-once と checker、過去の失敗・中断を区別した記録。

上の `reports/` は全て `docs/codex/gen01_w1_2026_11_06/reports/`。
移動元→移動先・変更・新規の完全な commit 対象一覧は末尾と `wp04_validation_amend2/wp04_pending_files.json` に記録した。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

### 幾何と campaign

`from cfd_gen.topo2d.geometry import build_scene, write_scene, save_npz, validate_scene, polygon_sdf, scene_sdf`。
`build_scene(configuration, height_mm=…, dx_mm=…, t_min_cells=4, g_min_cells=4)` は mm 単位。
configuration は E1／E2／E3 と各 `_sharp`。
`scene_sdf` は厳密な点–線分距離と winding による各要素の union。Julia も同じ頂点を直接評価する。
三線形格子を経由しない。

`topo2d-scene-v1` は `elements[{name,polygon_mm,suction_mm,pressure_mm,thickening,sampling,…}]`、
`normalizations{c1_mm,c_mm,h_over_c1,h_over_c}`、source path／SHA、変換、gate を持つ。
source table は自然境界 `CubicSpline(弦長累積, contour)`（T2-0の規則）で補間し、元表の全座標を通る。
`airfoil_points` 自体は固定の単一翼とzero-TEを使うので import せず、既存 SciPy を再利用した。
PCHIP は両面の対応 station を決めるだけで、自然 spline の形は変更しない。
元 spline の区間弧長は速度積分、最終 polygon の辺は実長で ≤1 mm。2つの TE cap corner 以外は ≤5°。

前縁から各面の弧長2%公称弦を保存し、camber 弧長の smoothstep で元の最大厚さ位置へ移る。
その後方の連続 polygon 法線幅に4Δxを要求する。元厚さとfloorの hard max に生じる折れを避けるため、
scaled L8 envelope を使い、独立 normal-ray gate に必要なら offset を増やす。
前縁鼻端と移行部を含む全域の正の一様厚さや、曲線半径の実験的資格化は主張しない。
TE 中点、camber、主翼の配置共通性を再検証する。

overlap = 上流 TE 中点の x − 下流 LE の x（正なら下流 LE が上流へ重なる）。
gap = 下流 suction 最低 z − 上流有限 TE 中点 z。生成後に9／12 mmを課す。
同じ h／grid の主翼はE1〜E3で同一。E3 は flap を半弦2個にし、総 chord angle を等分して順に配置する。
`*_sharp` は有限TEの原形 arm、`mathematically_sharp=false`。
実 E2 弦／姿勢は379.428071 mm／14.436775°で、公称正規化 c=380 mm／14.1°を維持する。
E3 の実全弦は374.677472 mm、構成例であり公開3要素試験の再現ではない。

legacy campaign schema／runner は変更していない。追加 CLI は
`.venv/bin/python -m cfd_harness.scene_campaign`（`PYTHONPATH=src` または既存 editable 環境）。
主96＋確認8＋h80記述16＋determinism1＋DOMAIN4＝125 state。
Re1000は56、Re3000は61、確認格子Re3000は8 runs。DOMAINは同じ拡大領域のE1／E2対。
正式な窓はE1 parent pre-runの式と外部freezeが必要で、draft campaignからは測定を開始しない。

### Job・WP1・WP2

2D `Simulation((n,m),(U,0),L; ν, body=SetBody(min,…),exitBC=true,λ=quick)`。
移動BDIM半空間の地面を含め、`W4_CANONICAL_ORIGIN_M=x,0,z` の shift をscene全体に適用する。
力はwingのみ、`F_body=-(pressure+viscous)`、drag=+Fx、downforce=−Fz。
Re／time／係数の共通基準はc1=223.4 mm。2D物理力はN/mで、scaleはρU²Δx。
窓は端点を線形補間したtime-weighted trapezoid、driftは前後半平均との差／全平均絶対値。

CSVの最初の13列は既存 `FORCE_COLUMNS` を保持し、
`{cur,nds,cv}_{fx,fy,fz,drag,downforce}_solver`、
`element_{main,flap1,flap2}_{fx,fy,fz,drag,downforce}_solver` をこの順で追加する。
E1／E2／E3は33／38／43列。未利用nds／cvはCSVでNaN、JSONでnullとして欠測を明示する。
JSON summary／preflight／failureとavailable readoutに `observable=total_cl`、両高さ正規化を持つ。

WP1の実APIは `Checkpoint.save_checkpoint(path,sim,step,rows;identity)`、
`load_checkpoint(path)`、`restore_checkpoint!(fresh_sim,data;identity)`。
fingerprintと検証済みcolumn maskからexpected identityを構成してrestoreへ渡す。
WP2の実APIは `validate_force_box(sim,box;body=wing)`、
`force_readouts(sim,box;body=wing,validate_box=false)`。gen01/を優先し、source SHAを別pinする。
両moduleが無い現在のcheckoutでもCPU fallbackが動く。実 sibling module はbyte確認したread-only
snapshotから追加統合試験を行った。providerはrepoにコピーしていない。

### Analyzer・WP5 JSON

CLIは `scripts/topo2d00/analyze.py --table … --rans … --freeze … --out …`、
独立checkerは `scripts/topo2d00/check.py PATH/analysis.json`。
formal loaderはraw harness verifierを再実行し、source／scene／runtime／freezeのidentityを照合する。
CPU smokeを正式データへ昇格させない。両outputが存在しないことを先に確認しexclusive-createする。
checkerはanalyzerやその評価helperをimportしない。

共有RANS形式は `topo2d00-rans-results-v1`。`coefficient_reference`に
`chord_mm=223.4,height_mm=100,h_over_c1,h_over_c`、`reference.observable=pressure_cl`。
`cells[{model,family,realisations[8]}]` の各realisationは `id,mesh_sha256,status,forces,diagnostics`。
各forceは `{downforce,drag,observable}`。E1/E2/E3は `total_cl`、E1_sharp/E2_sharpは `pressure_cl`。
異なるobservableを差分にしない。8 mesh SHAに重複があれば点推定のみを残し区間を出さず、
`DEGENERATE_REALISATIONS`を記録する。referenceの独立digitizationはcontent SHAも異なる必要がある。

Amendment 1 §9の厚肉化対照は、WP5のraw diagnosticsにある
`pressure_coefficients.total.{Cl,Cd}`／`coefficients.total.{Cl,Cd}` から各observableを別々に再計算。
raw config／model／family／mesh identity、COMPLETED、usable、そのobservable自身の収束を検査する。
8対と独立meshが揃えば記述用90%区間、それ以外は点推定／UNAVAILABLE。study labelには使わない。
任意のcollector `cell_summary`／`thickening_alone` はschema上受理するが、算術には信用しない。
WP5とのschema byte統合はユーザー指定どおりClaudeが行う。

σdはA（paired phase SD）とB（within-run batch means SEをSDへ換算）の最大。
α=.05の上側限界はA／BへBonferroni配分し、90% t区間を計算する。RANSは8対のt区間、
合格(model,family)の最悪cellを採用する。TR-00の[.5,2]とdigitization 5%規則は維持。
Fiellerは有界／非有界／分離／全実数／空集合とzero-baseline未定義を明示する。
relative incrementの分散はdelta法であり、厳密なnested ratio被覆という主張ではない。

## テスト（コマンドと結果）

最終版で次を完走した。

```sh
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider
git diff --check
```

**3640 passed／74 skipped／0 failed／7295 warnings**、pytest 1260.81秒（外部1261.854秒）。
失敗node集合は **`[]`**。ユーザー指定のClaude host base `e3dcdf61`（3482 passed／74 skipped／0 failed）
の失敗集合 `[]` と一致し、増加158件は本WPの最終対象試験に対応する。baseを/tmp cloneで再測定はしていない。
警告はログに保持した。テスト開始時／終了時のプログラム・入力SHAは一致し、その後も不変を照合した。
`python_execution.json`／`validation.json` がcommands・実行時間・結果・SHAを結ぶ。

さらに、protected source／authorityの170ファイルをbase Git blobへ照合して全てbyte一致。
`src/cfd_sdf`の130 Python filesとJulia `src`の13 filesは追加・欠落なし。
旧`src/cfd_sdf/topo2d/`自体も不在で、historical closureを変更する回避策は不要だった。

個別の確認：

- `.venv/bin/python -m pytest -q tests/topo2d00 -p no:cacheprovider`：最終版 **158 passed／61.08秒**（外部61.315秒）。auxiliary追加前148件の記録とは区別する。
- `julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/topo2d_selftest.jl …`：実WP1／WP2含む56／56、113.192秒。全体Julia testset111.2秒、CUDA module未読込。
- E1／E2は320×160、Re200、窓[.003,.015]。地面近傍u=1、共通位相、有限force、fallback場／窓bit一致、WP1再開窓一致、WP2 cur／nds／cv有限。
- 16位相のface-core probes：E1=9312、E2=16448、E3=23200、すべて通過。保存したbulk probeの範囲の能力証拠で、cap全域の資格化ではない。
- CPU Vector化前後のE1／E2／job entrypoint／WP2のforce CSVはSHAも数値も完全一致（`cpu_vertex_equivalence.json`）。
- 初回closure失敗の2nodeを直接再検証：2 passed／16.25秒。frozen source／historical testの例外は追加していない。
- 実WP5 loaderに10 scene×fine30／med30：20／20。gmsh未読込、mesh／CFDなし。
- synthetic analysisの独立checker CLI：pass=true／discrepancies=[]。2回目の書込を拒否し、既存JSON／MarkdownのSHA不変。
- `.venv/bin/python -m compileall src tests`：最終版exit0。
- `git diff --check`：最終報告保存後を含めexit0。

CPU初回のWP1 keyword欠落による失敗は `attempt1_*`、修正後Tuple版の56pass／1805.965秒は
`attempt2_*` に保存し、最終Vector版と区別した。全体試験の中断は `interrupted_before_aux_*` であり、
完走結果として扱わない。全raw／log／sourceのSHA一覧はvalidation directoryの `SHA256SUMS`／`log_archives.json`／`program_sources.json` に保存した。ログは `.log.gz` を保持し、元ログのSHAも結ぶ。

## 仕様からの逸脱と理由

既存`src/cfd_sdf`／Julia src／Project／Manifest／旧job／既存evidenceはbase e3dcdf61とbyte不変。
新規sourceを登録済みclosureの外へ移し、歴史テストの例外は作っていない。
既存harness sourceの変更は、初回WP4で追加したscene専用moduleへの追従と重複gate呼出しの排除だけ。
同一generation/pin集合内で同じsceneの検証を再利用し、実CFD前／raw verifierのgateは保持する。

座標は初回の公式indexed OCR転記（44／44／18行）を使い、全行UNVERIFIEDを維持した。
今回も公式PDF本体は403で画像照合できなかった。Amendment 2の採用済み境界に従い、
座標を推測で追加・修正していない。T20との差を消すためのTE sharpeningも行っていない。

| Table 3 対 T20 の列 | suction x | suction z | pressure x | pressure z |
| --- | ---: | ---: | ---: | ---: |
| 同じmm単位での最大絶対差 | .05234 | .81702 | .04600 | .85498 |

Table2対T20はx一致、z差最大 .80424／.82658 mm。TE厚はTable2=1.63082 mm、Table3=1.672 mm、
T20=0。登録Amendmentの丸めた「.05／.82 mm」だけをコピーせず、両面4列の実測差を残した。

| 格子 | Δx mm | 4Δx mm | c1 cells | flap cells | half-flap cells | 12mm gap cells |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| main | 1.861667 | 7.446667 | 120 | 89.0063 | 44.5031 | 6.44584 |
| confirmation | 1.241111 | 4.964444 | 180 | 133.5094 | 66.7547 | 9.66876 |

原表の実弦長223.846853／165.478218／82.739109 mmでは、main格子120.2400／88.8871／44.4436cells、
確認格子180.3600／133.3307／66.6654cells。正規化の公称c1／cは変更しない。

| 系列／格子 | main 最大厚さ比 | flap1 | flap2 | 最小隣接gap mm |
| --- | ---: | ---: | ---: | ---: |
| E1 main | 4.594754 | — | — | — |
| E2 main | 4.594754 | 8.866735 | — | 8.574110 |
| E3 main | 4.594754 | 17.733469 | 17.733469 | 8.395086／8.936260 |
| E2 confirmation | 3.063217 | 5.911157 | — | 9.806835 |

最大segment=.992904900 mm、最大非cap折れ角=3.022433061°。確認格子は自身の4Δxで厚さを
作り直すためgridとgeometryの複合対照であり、純粋な格子収束とは呼ばない。
h100はh/c1=.447628／h/c=.263158、h80は.358102／.210526。

![E1〜E3の更新済み幾何。実線が厚肉化、破線が有限TE原形、太線が保存前縁cap。](topo2d00_geometry.png)

登録§5のラベル優先順は変更しない。global-ANDのresolved rankingではDISCORDANTが先に一致するため、
CONCORDANT_PARTIALは整合入力から到達不能。到達する8ラベルと遮蔽反例を検査し、偽のflagsで
全9ラベルのcoverageを作っていない。drag差・区間・符号一致は報告するが、表にない追加のdrag
合否条件は作っていない。登録担当のclarificationが必要な点として残す。

## 未確認の仮定と登録§10への回答

| §10 の項目 | 確認できたこと／未確認の範囲 |
| --- | --- |
| 座標・TR reference | 表転記と補間、T20との差、独立WP5幾何読み込みを確認。画像照合、Table15のh/c1=.448、double Cpの独立2digitization、DOI一次資料確認は未完。 |
| E3 | 半弦2個、総姿勢角の等分、同じ9／12mm規則で決定的に構成。公開3要素測定の再現ではない。 |
| 2D job・厚さ・core | 小格子CPUでfinite force、移動地面、共通位相、56検査、16位相bulk coreを確認。GPU、長窓、全域μ0の資格化は未完。 |
| blunt TEのgmsh | 実WP5loaderに全10sceneを修復なしに渡せた。mesh生成／checkMesh／RANSはWP5で別途検査が必要。 |
| Mahon & Zhang (2006) | 本WPでは原論文によるmodel-choice適格化を行っていない。SA／SSTのTR資格を主張しない。 |

現在のhost以外では、derived float metadataの完全一致がSciPy／platform差を拒否する可能性がある。
source／sceneのSHAと離散identityは厳密に保持しているが、将来のLinux／GPU実行前には同一JSONの
bridge再検証が必要。iidの位相／batch近似、σd上側限界、Fieller近似の被覆も登録前reviewの範囲。

## Claude／ユーザーへの提案する追記

phase_plan／STATE／登録本文は変更していない。実装結果の採否とは別に、§5の
CONCORDANT_PARTIAL遮蔽、dragのlabel上の位置付け、上側σdとFieller近似を登録担当が明文化すること。
座標画像確認とTR referenceが揃うまで正式freeze／測定へ進めない。WP5とのschema byte統合と
同一scene SHAの採用を確認すること。過去のfrozen closureを変更する提案は今回不要になった。

## 次に要るもの

Claude hostで末尾の意図したファイルのみをcommit／pushし、PR #89本文を更新する。
WP1／WP2後の統合、WP5 schemaとscene SHAの照合、PDF画像とTR reference、mesh-only検査、
source／plan reviewと登録freezeを済ませてから、別途許可された本測定へ進む。
本報告の成功はCPU実装・software契約までであり、TOPO-2Dの実ラベル、物理downforce、
FSAE／高Re適格化、GPU／Kaggle挙動を意味しない。

## Hostでcommitすべき完全なファイル一覧

移動3組、変更27ファイル、新規95ファイル。raw `.log`／cacheは除外し、`.log.gz`とraw SHAを含む。
意図した範囲は `wp04_validation_amend2/wp04_pending_files.json` と同じ。agentはstage／commit／pushしていない。

### 移動（元の削除と先の追加を一組として扱う）

- `src/cfd_sdf/topo2d/__init__.py` → `src/cfd_gen/topo2d/__init__.py`
- `src/cfd_sdf/topo2d/geometry.py` → `src/cfd_gen/topo2d/geometry.py`
- `julia/topo2d/Topo2D.jl` → `julia/CFDSDFWaterLily/gen01/Topo2D.jl`

### 変更

- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_geometry.png`
- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_design.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_report.md`
- `docs/harness/topo2d00_campaign.json`
- `docs/harness/topo2d00_scenes/E1.json`
- `docs/harness/topo2d00_scenes/E1_fine.json`
- `docs/harness/topo2d00_scenes/E1_h80.json`
- `docs/harness/topo2d00_scenes/E1_sharp.json`
- `docs/harness/topo2d00_scenes/E2.json`
- `docs/harness/topo2d00_scenes/E2_fine.json`
- `docs/harness/topo2d00_scenes/E2_h80.json`
- `docs/harness/topo2d00_scenes/E2_sharp.json`
- `docs/harness/topo2d00_scenes/E3.json`
- `docs/harness/topo2d00_scenes/E3_sharp.json`
- `scripts/topo2d00/analyze.py`
- `scripts/topo2d00/check.py`
- `scripts/topo2d00/plot_geometry.py`
- `scripts/topo2d_selftest.jl`
- `scripts/waterlily_topo2d_job.jl`
- `src/cfd_harness/scene_campaign.py`
- `tests/topo2d00/synthetic.py`
- `tests/topo2d00/test_analyze.py`
- `tests/topo2d00/test_campaign.py`
- `tests/topo2d00/test_check.py`
- `tests/topo2d00/test_geometry.py`
- `tests/topo2d00/test_source.py`

### 新規

- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/README.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/SHA256SUMS`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/amendment_authority.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest.stderr.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest.stdout.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E1/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E1/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E1/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E1/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E2/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E2/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E2/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/E2/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/job_entrypoint/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/job_entrypoint/entrypoint.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/job_entrypoint/entrypoint.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/job_entrypoint/entrypoint.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/job_entrypoint/job_preflight.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest/job_entrypoint/job_preflight.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt1_cpu_selftest_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest.stderr.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest.stdout.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E1/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E1/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E1/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E1/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E2/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E2/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E2/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/E2/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/job_entrypoint/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/job_entrypoint/entrypoint.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/job_entrypoint/entrypoint.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/job_entrypoint/entrypoint.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/job_entrypoint/job_preflight.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/job_entrypoint/job_preflight.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/selftest.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/selftest.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/wp2_integration/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/wp2_integration/host_readouts.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/wp2_integration/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/wp2_integration/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest/wp2_integration/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/attempt2_cpu_selftest_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/before_aux_topo2d_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/checker_cli.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/compileall.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest.stderr.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest.stdout.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E1/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E1/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E1/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E1/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E2/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E2/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E2/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/E2/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/job_entrypoint/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/job_entrypoint/entrypoint.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/job_entrypoint/entrypoint.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/job_entrypoint/entrypoint.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/job_entrypoint/job_preflight.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/job_entrypoint/job_preflight.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/selftest.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/selftest.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/wp2_integration/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/wp2_integration/host_readouts.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/wp2_integration/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/wp2_integration/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest/wp2_integration/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_selftest_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_vector_review.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/cpu_vertex_equivalence.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/frozen_closure_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/full_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/geometry_review.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/geometry_summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/interrupted_before_aux_full_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/interrupted_before_aux_python_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/log_archives.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/program_sources.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/protected_source_closure.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/provider_origins.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/python_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/synthetic_analysis.json.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/synthetic_analysis.md.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/topo2d_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/topo2d_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/validation.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/worker_routing.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/wp04_pending_files.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend2/wp5_geometry_readback.json`
- `julia/CFDSDFWaterLily/gen01/README.md`
- `src/cfd_gen/README.md`
- `src/cfd_gen/__init__.py`
