# WP4：TOPO-2D-00 WaterLily 側 — Amendment 3 報告

## 状態

**PARTIAL**。`ba3164c7` からの第3回修正。幾何の sliver／閉辺、cell severity、scene 高さの拘束を修正し、全10 scene・campaign・図を更新した。対象 pytest 219件と CPU 自己テスト59件は成功。指定の全体 pytest は3701 passed／74 skipped／0 failedで完走し、失敗node集合はbaseと同じ空集合。

`CONCORDANT_PARTIAL` の到達性は **仕様の整合確認待ち（BLOCKED）**。登録 Amendment 3 §5 の「片方の Re のみ SIGN_AGREE_12」「両側で resolved な範囲の順位一致」と、従来の先行 UNRESOLVED を同時に保つと、PARTIAL に到達できない。独立 checker と生データの合成反例を保存した。未解決の他方 Re を許す狭い例外にする解釈をユーザーへ照会中で、無回答を承認とは扱っていない。この条件を満たすと偽って全ラベル完了とは報告しない。

本報告は software／CPU capability の証拠。登録、凍結、本測定、物理 downforce、Re 転写、GPU 適格化、FSAE の結果ではない。commit／push／PR #89 本文更新は最新のユーザー指示に従い Claude host が行う。agent は stage／commit／push していない。

## 作ったもの

- `src/cfd_gen/topo2d/geometry.py`：表を通る自然 CubicSpline と単調 PCHIP pairing は維持し、元表 station と別グリッドの単純な和集合を廃止。各元表区間の弧長・曲率 monitor を等分して元表の全点を残しつつ再標本化する。元の最短 0.005648 mm の原因を除去した。
- 同生成器の gate：全周期線分に 0.1–1 mm、隣接長比 ≤3、TE cap 2頂点以外の角度 ≤5°、頂点の重複なしを適用。既存の4Δxの厚さ／間隙、clearance、self-intersection、source／camber／TE／LE cap identity も維持。
- `docs/harness/topo2d00_scenes/*.json`：全10 scene を再生成。JSON は終点を重複しない頂点列で、閉辺は最後→最初。sharp は公開の有限TE原形を意味し `mathematically_sharp=false`。
- `julia/CFDSDFWaterLily/gen01/Topo2D.jl`：多角形 SDF を周期的に評価し、最後→最初の距離と winding を含める。既存 job の編集はない。
- `src/cfd_harness/scene_campaign.py`：scene JSON の高さを export と state identity の唯一の出所とし、宣言した config／height の不一致を pin／run／verify／CLI validate で拒否。異なる phase が同じ SHA を共有しても各宣言を検査する。
- `docs/harness/topo2d00_campaign.json`：全 scene SHA を更新。Re1000 56run、Re3000 61run、confirmation 8run、計125 state。元の主評価96、確認8、secondary16、determinism1、DOMAIN対照4を維持。未凍結の draft。
- `scripts/topo2d00/analyze.py` と `check.py`：cell 集約を INCOMPLETE > MESH_FAILED > NUMERICAL > SETTLED に変更。checker は analyzer を import せず再計算する。cap／独立した未完了記録が numeric failure より先になり、単独の実非有限 failure は NUMERICAL のまま。重複 mesh が failure 診断値を保持しても CI を出さない。
- `scripts/topo2d00/plot_geometry.py`：生成器を別途呼び直す経路から、実際の検証済み scene JSON を描く経路へ変更。閉辺と scene の高さを使う。
- `scripts/topo2d_selftest.jl`：閉辺に最近接する square SDF probe 3件を追加。既存の CPU、移動地面、位相、core、checkpoint、WP1／WP2 integration も実行。
- `tests/topo2d00/`：全10幾何 variant の独立周期検査、5種類のsampling欠陥拒否、cell severity／順序不変性／cap／重複mesh、scene height／同一SHA異宣言／CFD前拒否を追加。
- `reports/topo2d00_geometry.png`：更新後の E1／E2／E3 と元の有限TE原形、厚肉比、gap、4Δx の範囲を表示。PNG を実際に開いて確認した。
- `reports/wp04_validation_amend3/`：新しい実行ログ、raw CSV／summary、source／scene SHA、独立 review、保護対象確認、WP5 readback、schema比較、合成 checker と policy反例。過去の validation は変更していない。

## 幾何の数値と出所

座標は既存の `data/zz2003/{single_element_table2,main_element_table3,flap_table4}.dat`（44／44／18行）。取得は前回記録の公式 PDF indexed OCR であり、今回は再取得していない。Amendment 2 が採用した転記を維持し、全行の `# UNVERIFIED` と provenance `UNVERIFIED_OCR` を保持した。PDFページ画像との照合は未完。推測の座標は足していない。

Table3 を380mm基準、T2-0 を223.4mm基準で mm に直した同順の最大絶対差は、suction x/z、pressure x/z の順に **0.05234、0.81702、0.04600、0.85498 mm**。T2-0 の XFOIL sharp TE と原表の有限TEは同じ座標列ではない。元表の全点が sharp contour に残る誤差は独立検査で ≤2.45e-13 mm。

overlap は上流TE中点x − 下流LE x、gap は下流 suction の最低z − 上流TE中点z。最終配置に9／12mmを適用し、c=380mmと14.1°は公称の正規化。今回の E2 実座標の合成弦は **379.428107730 mm、14.436796729°**。E3 は半弦フラップ2個、総姿勢角を等分、同じgap／overlap規則で構成した例であり、公開3要素実験の再現ではない。

全10 scene の周期的な独立検査：

| 量 | 実測した幾何値 | 規則 |
| --- | ---: | ---: |
| 最短線分 | 0.133179922501 mm | ≥0.1 mm |
| 最長線分 | 0.992904900205 mm | ≤1 mm |
| 最大隣接長比 | 2.897564688141 | ≤3 |
| 最大非cap角 | 3.445371053014° | ≤5° |
| 重複頂点／重複終点 | 0 | 0 |

厚くした後と原形を宣言した並進分だけ戻して比較した独立誤差は、camber ≤8.53e-14 mm、TE中点 ≤2.85e-14 mm、保持LE cap ≤1.43e-14 mm。厚さfloorは元の最大厚さ位置以後の法線幅であり、厚さが0となるLE鼻端やsmoothstep移行区間へ正の全域下限を主張しない。

| scene／grid | main 最大比 | flap1 最大比 | flap2 最大比 |
| --- | ---: | ---: | ---: |
| E1 main | 4.594745 | — | — |
| E2 main | 4.594745 | 8.866711 | — |
| E3 main | 4.594745 | 17.733423 | 17.733423 |
| E1 confirmation | 3.063211 | — | — |
| E2 confirmation | 3.063211 | 5.911141 | — |

| grid | Δx mm | c1 cells | flap cells | E3半弦 cells | 公称gap cells | 4Δx mm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c1/120 | 1.861666667 | 120 | 89.006267 | 44.503133 | 6.445837 | 7.446666667 |
| c1/180 | 1.241111111 | 180 | 133.509400 | 66.754700 | 9.668756 | 4.964444444 |

E3 confirmation scene は登録どおり作っていない。確認格子はその格子の4Δxで再厚肉化するので、格子と幾何の両方が変わる対照であり、純粋な grid refinement ではない。h100 の h/c1=0.447627574、h/c=0.263157895。h80 は0.358102059／0.210526316。どちらも scene JSON と実 clearance を再検査する。

## インターフェース

Python の `build_scene`／`validate_scene`／`polygon_sdf`／`scene_sdf`／`write_scene`／`save_npz` を維持。SDF helper は閉辺を内部で追加できるが、scene JSON は必ず重複終点なし。Julia は同じ raw JSON の SHA を検査して text wire 経由で読む。新規依存はない。

`scene_record(path, expected_sha, declared=None)` は高さ／configを拘束する共通読込口。`scene_wire` の行schemaは維持し、polygonの閉辺だけ周期的に扱う。h80 というファイル名から高さを復元しない。

既存13 CSV列、cur／nds／cv予約列、要素別列、2D N/m と共通c1係数、endpoint-clipped time-weighted mean、drift、`W4_CANONICAL_ORIGIN_M` の x/0/z、地面を含む共通位相は維持。cur fallback の不足列はNaN、WP2接続時は全readoutが有限。WP1 は `save_checkpoint(...; identity)`／`load_checkpoint`／`restore_checkpoint!(...; identity)` の実APIへadapterし、欠測列maskとfingerprintを拘束する。

WP5用共有JSON Schemaは既存の `reports/topo2d00_rans_result_schema.json`。SHA256:
`ce5c4c90f821aa5dcf3d63493096a16cad6f72395c461f434307a7dcd3ceb5a7`。
`schema=topo2d00-rans-results-v1`、共通c1係数、両h正規化、reference、cells(model,family)、8 realisations、config別mesh SHA／status／force、`observable` を持つ。sharp=pressure_cl、thick=total_cl、observable間の差分は拒否する。Fieller、A/Bと上側限界、90%区間、TR ratio/sign、対照、written-onceは既存の独立実装と合成試験で確認した。

現在のWP5 schema SHAは `c47d77013fcf7a8fef52c30ae42475a60b55bafb9711cc3d4fd4bdcfcf9cbcf9` で byte一致していない。JSON差分は `schema_comparison.json` に全列挙。ユーザー Amendment 2 §5 の指定どおり Claude が統合時に揃える。本WPはWP5 sourceを変更していない。

## テスト

- `.venv/bin/python -m compileall src tests`：exit0。
- `.venv/bin/python -m pytest -q tests/topo2d00 -p no:cacheprovider`：**219 passed、85.01秒**。
- `julia --project=julia/CFDSDFWaterLily scripts/topo2d_selftest.jl <新規出力先>`：**59/59 passed、testset95.4秒、process97.64秒**。CPU320×160、Re200、短窓。E1／E2 finite、evolved near-ground u≈U、共通shift、16phase bulk core、fallback／実WP1再開、実WP2 cur/nds/cv と host再計算。CUDA module_loaded=false。
- 合成 `write_analysis` → 独立 `check.py` CLI：discrepancies=[]、再書込はFileExistsError。結果のCONCORDANTは合成fixtureの値であり本測定の判定ではない。
- `git diff --check`：exit0。
- 全体 `.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider`：**3701 passed、74 skipped、0 failed、1001.69秒（process1002.53秒）**。失敗node集合=[]、指定baseの空集合と一致。対象sourceの開始／終了SHAも一致。7295 warningsはpytest deprecation等としてraw logに保持した。

baseはユーザー提供のhost実行 `e3dcdf61`、3482 passed／74 skipped／0 failed、失敗node集合=[]。この作業でbase側を再実行していない。結果側の実失敗node集合を `full_execution.json` に保存し、件数だけでなく集合を比較する。

## 仕様からの逸脱と未完

PARTIALの新定義と先行UNRESOLVEDの整合以外に、今回の閾値変更はない。4Δx、[0.5,2]、α=.05を維持した。登録・roadmap・STATE本文、旧job、source freeze、tests/conftest.py、Project／Manifestは変更していない。`src/cfd_sdf/topo2d/` にbytesは残っていない。保護対象144sourceとその他指定pathの `e3dcdf61` からの差分は空。

PARTIALの数学的問題：両側の完全順位が確定して一致すれば、E1/E2の順序、従ってΔ12の符号も一致する。片方のReだけSIGNが真となるには、他方に未解決の必要区間か、確定した順位の不一致が必要になる。前者はUNRESOLVED、後者はDISCORDANTが先に発火する。`partial_precedence_counterexample.json` は Re1000を未解決、Re3000を符号／順位一致とした生の合成入力で、analyzer／checkerともUNRESOLVED。八つの科学的ラベル全ての到達性を達成したとは扱わない（INVALIDを含めると仕様表のラベルは九つ）。

提案した最小clarificationは「一方で符号・順位が確定一致し、他方は未解決、かつ確定した順位不一致がなければPARTIAL」。このときだけ他方の未解決を先行UNRESOLVEDの必要条件から外す。採否はユーザー／Claudeの登録判断であり、本実装では先取りしない。

WP5実loaderのread-only preflight（作業中のsource更新後もv2で再確認）は **0/20受理**（10scene×2family、全件 `WP4 polygon/surface identity mismatch`）。これは現snapshotの `_wp4_scene` が旧表現の重複閉終点を要求するためで、mesh／RANSの失敗ではない。WP5は新しい重複なしJSONを検査した上で、内部contourにだけ最初の点を追加して既存の明示閉曲線helperへ渡すadapterが必要。raw JSON／SHAは共通のままにする。loader path／SHAと各拒否は `wp5_geometry_readback.json` と `wp5_geometry_readback_v2.json` に保存した（v2の読込中sourceは不変）。RANS側の実装・mesh生成は行っていない。

## §10の未解決点への回答／未確認の仮定

| 項目 | 現状 |
| --- | --- |
| 表座標・reference | OCR転記は保持、数値差とsmooth再標本化を検証。PDFページ画像、Table15のh/c1=.448、double Cpの独立2読取、DOI一次資料確認は未完。 |
| E3構成 | 半弦2個、総角度等分、9／12mmの決定的構成。公開3要素referenceなし。 |
| WaterLily job／厚さ／core | CPU59検査と16phase bulk coreは成功。LE／cap／rampを含む全域core、GPU、長窓、physicsは未確認。 |
| blunt-TE gmsh | 新JSONにWP5 adapter更新が必要。mesh／checkMesh／RANSはWP5側。受理をmesh成功と呼ばない。 |
| Mahon & Zhangモデル選択 | このWPで原論文によるSA／SSTの適格化はしていない。 |

iid phase／batch近似、σ上側限界、Fiellerのdelta法による入れ子比近似、source metadataのplatform間float一致は登録前reviewの範囲。数字の一致やCPU試験を物理／GPUの資格にしない。

## Claude／ユーザーへの提案する追記

1. 登録 Amendment 3 §5 で PARTIAL と先行 UNRESOLVED／resolved範囲の意味を明文化する。承認された規則からanalyzer／checker／全ラベル合成試験を同時に確定する。
2. WP5 adapterを重複なしJSONへ対応させ、同じ10sceneのSHAを読み込んで20件のreadbackをやり直す。meshの結果は別に評価する。
3. WP4／WP5 schema bytes、scene SHA、WP1／WP2 sourceを統合し、画像reference／review／freezeが揃ってから別途許可された本測定へ進む。

## 次に要るもの

PARTIAL規則の回答、WP5側のadapter／schema統合、PDF画像とTR reference、plan／source review。Claude hostで末尾の一覧のみをcommit／pushし、PR #89を更新する。GPU／Kaggle実行、登録判定、ロードマップ更新はこのWPではしていない。

## Hostでcommitすべき完全なファイル一覧

Amendment3内の移動はなし（Python／Juliaの移動は基点ba3164c7に含まれる）。raw .logはarchiveとraw SHAを保存し、commit対象一覧から除く。実際の全パスは以下と `wp04_validation_amend3/wp04_pending_files.json` に記録。

### 変更（25ファイル）

- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_geometry.png`
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
- `julia/CFDSDFWaterLily/gen01/Topo2D.jl`
- `scripts/topo2d00/analyze.py`
- `scripts/topo2d00/check.py`
- `scripts/topo2d00/plot_geometry.py`
- `scripts/topo2d_selftest.jl`
- `src/cfd_gen/topo2d/geometry.py`
- `src/cfd_harness/scene_campaign.py`
- `tests/topo2d00/test_analyze.py`
- `tests/topo2d00/test_campaign.py`
- `tests/topo2d00/test_check.py`
- `tests/topo2d00/test_geometry.py`

### 新規（49ファイル）

- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/README.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/SHA256SUMS`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/amendment_authority.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/checker_cli.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/compileall.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest.stderr.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest.stdout.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E1/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E1/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E1/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E1/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E2/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E2/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E2/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/E2/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/job_entrypoint/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/job_entrypoint/entrypoint.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/job_entrypoint/entrypoint.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/job_entrypoint/entrypoint.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/job_entrypoint/job_preflight.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/job_entrypoint/job_preflight.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/selftest.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/selftest.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/wp2_integration/W4_JOB_DONE`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/wp2_integration/host_readouts.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/wp2_integration/topo2d.forces.csv`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/wp2_integration/topo2d.summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/cpu_selftest/wp2_integration/topo2d.summary.toml`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/diff_check.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/full_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/full_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/geometry_summary.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/independent_geometry_review.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/log_archives.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/partial_precedence_counterexample.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/protected_source_closure.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/provider_origins.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/schema_comparison.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/synthetic_analysis/README.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/synthetic_analysis/analysis.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/synthetic_analysis/analysis.md`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/targeted_execution.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/topo2d_pytest.log.gz`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/validation.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/worker_routing.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/wp04_pending_files.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/wp5_geometry_readback.json`
- `docs/codex/gen01_w1_2026_11_06/reports/wp04_validation_amend3/wp5_geometry_readback_v2.json`
