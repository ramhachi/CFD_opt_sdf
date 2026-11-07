# WP5 TR-00／TOPO-2D-00 RANS 側 — Amendment 1 報告

## 状態

**PARTIAL（修正実装・指定検証完了。密な WP4 幾何を使う E2 再 smoke／再 render は保留）**。
ユーザー指定の `cb4df650` から Amendment 1 の source-review 修正を行った。
Kaggle への push、本番 5000／15000 反復、Cp 図のデジタイズ、freeze、登録判定は行っていない。
commit／push と Draft PR #87 の更新は Amendment 1 §12 に従い Claude が host で行う。
`work/wp05/publication.git` は使用していない。現在の HEAD は `cb4df650` のまま。

旧 WP4 入力5構成は新しい density guard に全て拒否され、手元の入力集合には E3_sharp もない。
このため正式な6構成の BL 計画は作っていない。密な入力を WP4 が渡し、Claude が指示するまで
kernel は再生成しない。実装の分岐を確認する synthetic test render だけを一時ディレクトリで行った。
第1回の E2 mesh／200反復は保存した歴史的 smoke であり、修正後の source の受け入れ証拠にはしない。

## 作ったもの（パス、1 行ずつ）

- `scripts/topo2d00/t2d_multibody_case.py` — 入力の折れ角・線分長 guard、供給済み後縁 cap の検証、全6構成の共通 BL 計画。
- `scripts/topo2d00/t2d_foam_case.py` — 共通 BL 計画を要求する本番 case、共有収束 policy、両 chord による h、継続 dictionary と runtime の一致。
- `scripts/topo2d00/digitize_cp.py` — reader SHA の相違、各面10点以上、読み取りごとの各要素 Cl 正、E2 不確かさの判定用分離。
- `scripts/topo2d00/collect_rans.py` — T2-0c 分類、family 内層数一致、重複 mesh SHA、observable、thickening 記述量、欠け run／mesh failure の区別。
- `scripts/topo2d00/run_rans.py` — checkMesh の採否、非有限／FPE の divergence、BL 計画の SHA 検証と generator への受け渡し。
- `scripts/topo2d00/build_tr00_kernels.py` — clean な tree＋明示 freeze 1＋検証済み6幾何を要求する ready 規則と、開発 render の実行阻止。
- `tests/topo2d00/` — 既知積分、入力 guard、収束反例、層数、mesh SHA、結果とインフラ、freeze／render の回帰テスト190件。
- `reports/topo2d00_rans_result_schema.json`・`topo2d00_rans_measurement_schema.json` — WP4 への共有形式と詳細診断形式を更新。
- `reports/cp_digitised_format.md`・`wp05*_design.md` — CSV 契約、修正前後の判断、入力と検証の範囲を記録。
- `reports/wp05_amendment1_validation/` — 入力 audit、旧 render 失効、synthetic mesh、変更禁止ファイルの照合、テストと hash の記録。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

### 幾何と BL 計画

`load_geometry(source, family='fine30')` は JSON／pickle 不使用 NPZ を読む。
非 cap 頂点の折れ角 >5°、**cap を含む全線分**の長さ >family.ds は、要素名・index・値付きの例外で拒否する。
WP5 は spline 再標本化しない。入力 SHA と供給された頂点を保持する。
数学的 cusp は既存 fan、有限 cap は no-fan。`*_sharp` は原形という arm 名であり、
WP4 の原形にある有限厚 TE を勝手に尖らせない。

generic JSON は `elements[].cap_start_index` で有限 cap の第2端点を指定できる。
省略時は単一の closing edge。指定端点から閉点までは、供給済みの直線上の単調な頂点だけを許す。
WP4 JSON は `suction_mm[::-1] + pressure_mm[1:]` をそのまま prefix として保ち、その後に供給済みの
straight cap subdivision と閉点を置く。adapter が cap の index を導くので WP4 に冗長な index は不要。

`boundary_layer_plan({config: geometry_input})` は E1／E2／E3 の thick と sharp **全6構成**の
最小 ground／inter-element gap から、fine30 と med30 の `T.layers` を一度ずつ計算する。
幾何 SHA、構成別 gap、全体の最小 gap、family の mesh_spec／層数／厚さを記録する。
compact sorted JSON（改行なし）の SHA が `plan_sha256(plan)`。
`write_case(..., boundary_layer_plan=plan_or_path)` は計画の同じ層数を全要素と ground block に使う。
本番で計画なし／6構成未満は出力作成前に拒否する。短い synthetic case の小集合計画は development と明記する。

### 結果・収束・observable

収束 policy は `collect_rans.CONVERGENCE` を foam が再 export する。
immutable T2-0b `force_summary` と T2-0c `classify` を使い、20% tail（最低50行）、20反復 block の
相対 std／drift が各0.005未満なら plateau、raw-tail Cl 相対 std **0.005超のみ** UNSTEADY。
初回5000、plateau 不成立時のみ一度15000まで継続し、最後の segment で判定する。
T2-0d の `steady_stats`／`urans_stats`、1e-3 閾値、`limit_cycle` は使用しない。
選択した observable の収束を使い、他の成分の収束は診断として保持する。

`collect_rans.py` の共有出力は `topo2d00-rans-results-v1`。
各 force の `observable` を必須化し、sharp は `pressure_cl`、thick は `total_cl`。
詳細診断には各要素・合計の total／pressure／viscous Cl・Cd と両収束状態を保持する。
共通規格化は c1=0.2234 m、span=0.002 m、Aref=0.0004468 m²、Cl は下向き正、Cd は流れ方向正。
共有 `coefficient_reference` に h/c1=100/223.4 と h/c=100/380 を出す。
case manifest では nominal h の datum と実輪郭 clearance、それぞれの両規格化を分けて保存する。

同じ family の集計 run は `n_layers` が一致しなければ例外。
各 (config,model,family) の8つの mesh SHA が重複すれば `DEGENERATE_REALISATIONS`。
有限な点平均は残すが `ci90=null`、ratio は INCOMPLETE。
旧 WP4 reader にも affected per-run status を INCOMPLETE と渡し、誤ったゼロ幅区間で適格化させない。
正常 cell の90% t区間の計算は引き続き WP4 analyzer の責任で、collector の点診断とは別。

`cell.thickening_alone` は E1／E2 について、同じ observable の E*−E*_sharp を pressure／total 別に出す。
記述量であり合否規則はない。E3_sharp は BL 計画の一員だが solve matrix にないため、その差は未出力。
shared の5結果構成 map と、`provenance.study_geometry_sha256` の6幾何 map を区別する。

gmsh proxy は情報のみ。checkMesh が mesh の採否を決める。
generator／mesh failure は MESH_FAILED、非有限係数・FPE・fatal は diverged／NUMERICAL、
欠け run・実行枠による loss は INCOMPLETE。timeout が非有限／FPE の結果を上書きしない。

### Cp 入力（ユーザーが用意するもの）

完全な JSON manifest と CSV の例は [cp_digitised_format.md](cp_digitised_format.md)。
UTF-8 CSV の列は厳密に `x/c,Cp`。E2 は2要素×物理的上面／下面×2読み取り＝**8 CSV**、各面10点以上。
`x/c` は global streamwise X を宣言した chord で割った座標で、両面が同じ投影端点を覆う。
local-chord の座標をそのまま積分しない。対応する A／B の upper／lower CSV は SHA が異なる必要がある。
同じ内容を別名で渡すと拒否する。各読み取りで各要素の積分 Cl は downforce 正でなければ拒否する。
独立性はファイル差だけでは証明できないため、人／ツールと方法の出典 metadata も必要。

E2 の digitising sensitivity は要素ごとの |Cl_A−Cl_B| の和。
登録 §4／Amendment 1 §6 の5% test は **E2 のこの値**を使う。
E1 の読み取り感度と E1+E2 の全差分感度は別フィールドに残し、判定用感度へ足さない。
単一要素は Table 15 の1.009（h/c1=0.448）を独立した表値として、または2本の Cl(h/c) 曲線として扱う。
後者の CSV も SHA 相違を要求するが、面ではないので線形補間の最低点数は2。
読み取り差は信頼区間でも総参照不確かさの上限でもない。総参照不確かさは未確定のまま。
参照帯 **[0.5,2]** と **5%** は変更していない。

```sh
.venv/bin/python scripts/topo2d00/digitize_cp.py path/to/user_manifest.json --out path/to/tr00_reference.json
.venv/bin/python scripts/topo2d00/collect_rans.py path/to/extracted-output \
  --plan path/to/frozen/run_plan.json --geometry-plan path/to/main/run_plan.json \
  --reference path/to/tr00_reference.json --out rans_results.json
```

### render と freeze 1（今回は実物を再生成しない）

`--study-geometry CONFIG=PATH` を繰り返して全6構成を宣言し、`--freeze PATH` に owner の freeze 1 を渡す。
新しい freeze input interface は次の通り。WP4 の post-run analysis freeze は代用しない。

```json
{
  "schema": "topo2d00-rans-freeze1-v1",
  "stage": "freeze1",
  "source_commit": "<正確な40桁のHEAD>",
  "input_sha256": {"<全bundle member>": "<SHA256>"},
  "geometry_sha256": {"E1": "<SHA>", "E1_sharp": "<SHA>", "E2": "<SHA>", "E2_sharp": "<SHA>", "E3": "<SHA>", "E3_sharp": "<SHA>"}
}
```

全 bundle member には登録文書、renderer、runtime source、6幾何、BL 計画を含む。
whole tree が clean、HEAD と全 hash が一致、全幾何の source metadata が明示的に VERIFIED、
main はさらに適格 cell が明示済みの場合だけ ready。それ以外は render_kind=development、ready=false、push_plan=[]。
VERIFIED は今後 WP4 側で根拠とともに設定する新しい interface で、現行の UNVERIFIED_OCR は通らない。
この token だけで学術的な検証をしたとは扱わない。今回は freeze を作っていない。

## テスト（コマンドと結果。base との失敗集合）

- `.venv/bin/python -m pytest -q tests/topo2d00 -p no:cacheprovider --basetemp /private/tmp/wp05-amendment1-final-unit2 --junitxml=/private/tmp/wp05-amendment1-focused-final.xml` — **190 passed / 55.42 s / exit 0**。gmsh がある環境。ない場合は mesh-executing tests が従来流儀で skip。pin は増やしていない。
- `.venv/bin/python -m compileall src tests` — **exit 0**。
- `.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` — **3672 passed / 74 skipped / 0 failed / 7295 warnings / 2059.24 s（34分19秒）/ exit 0**。failure node 集合 **[]**、error node 集合 **[]**。
- `git diff --check` — **exit 0**（最後に再確認）。
- JSON Schema Draft 2020-12：両 schema と通常／duplicate-SHA／total-only-valid の合成出力を既存の一時 validator で検証。依存追加なし。
- 17個の変更禁止 source／pin／authority ファイルを base `e3dcdf61` と byte 照合し、すべて同一。diff も WP5 範囲に限定。

base の比較対象はユーザーが提示した **Claude host の e3dcdf61: 3482 passed / 74 skipped / 0 failed**。
この amendment で base／Metal を再実行していない。result 側の上記除外コマンドも失敗 node 集合 **[]** で、指定の base と一致した。warnings の同一性は比較していない。

TDD で A1／A3 の欠落7件、A2／A3 の既存分類差9件、非有限1行の3件、独立レビューでの timeout/FPE と
selected-observable の7件を先に失敗させた。周期2、周期7、0.2%白色雑音の review 反例は settled を確認。
Cp はコピー CSV／点数不足／符号誤り／相殺する要素差、render は dirty／freeze 欠落／OCR／第6構成欠落を検査した。
最終の合成 mesh は archive の member/hash を read back して照合した。これらは実験参照や物理 qualification の証拠ではない。

### ローカル OpenFOAM smoke の範囲

**修正後の E2_sharp／E2 の OpenFOAM mesh-only／200反復は未実行**。
手元の旧幾何は main 最大15.45°、flap 最大55.53°、長い線分11.5〜14.7 mm を含み、fine30 ds=2 mm の guard を通らない。
`geometry_preflight.json` は5入力の SHA、要素別の指標、拒否理由を保存する。
WP5 で再標本化せず、WP4 の密な幾何を待つという Amendment 1 §1 と再 render 禁止に従った。

第1回保存 artifact の歴史的事実：E2_sharp／E2 は各1 mesh、各200 SA-WF反復、checkMesh は Mesh OK、force 有限。
両者の有限 TE は no-fan だった。cells 37,754／37,848、max nonorth 54.276422°／54.664386°、
max skew 2.3987006／1.7989068、min determinant 0.034175708／0.050301549、min face weight
0.14761962／0.15404030、min volume ratio 0.13512438／0.14207175、4 BL層、3.2208 mm。
これで **粗い旧入力を mesh 化できた**ことは示すが、密な corrected input の no-fan 妥当性、現在の pipeline、
Kaggle 再現性、収束や物理精度を検証したことにはならない。

新しい Python/gmsh の2体 synthetic sharp／blunt unit mesh は品質 proxy failure 0、SHA と全 patch を確認。
小さい第3の鼻を持つ synthetic med30 case は topology と有限 proxy reporting を確認するだけで、proxy に失敗項目がある。
そのケースを checkMesh 通過や3要素 qualification として扱わない。実 proxy は synthetic_mesh_summary.json と archive に全て残す。

旧 working render の plan36件、wrapper29件を development／ready=false にした。
source bundle の payload は再生成していない。歴史的 archive の bytes と SHA は保存し、内部の古い ready flag を
`render_invalidation.json` で失効させた。raw 実行記録の extracted copy は変更していない。
追跡対象の既存 infra kernel は編集していない。

## 仕様からの相違点と理由（A1／A3／A2 を明示）

- **A1:** 第1回は粗い WP4 polygon をそのまま受理した。今回、非 cap5°／全線分dsの guard と straight supplied-cap 契約に修正した。WP4 の旧 source は密な input をまだ出さないので、新しい E2 smoke と render は保留。
- **A3:** 第1回は構成ごとに gap で BL 層数が減り、med30 で E1=7／E2_sharp=5／E2 thick=4 となり得た。今回、全6構成の最小 gap で計画した family 定数に統一。正式入力不足を仮の層数で埋めていない。
- **A2:** 第1回 collector は manifest が0.005を宣言しながら T2-0d の1e-3を使い、雑音を limit_cycle とした。今回、manifest／runner／collector／schema を T2-0c の同じ定数と分類へ揃えた。
- `gmsh quality proxy` は情報だけとし、checkMesh の採否と分けた。旧3体 fixture の clean-proxy assertion を、topology と有限指標の検査に限定したことも上記に明示した。
- 根拠 artifact のなかった merge-tree の主張は削除した。今回は merge／merge-tree を実行していない。
- OpenCode Go は callable MCP がなく、通常CLIはログ権限エラー、一時データ先の catalogue query は Provider not found: opencode-go。global設定と有料APIを変えず、native inherited worker の分担＋親レビューで実装した。

## 未確認の仮定と claim ceiling

密な WP4 の E1〜E3 thick／sharp、出典画像照合、正式 BL 計画と freeze 1 は未受領。
Cp CSV はユーザー入力待ちなので、実験 E2 Cl、ΔCl、不確かさ、TR-00 verdict は未生成。
Table 15 の丸め高さ／trip と総参照不確かさは解消していない。
SA／SST wall functions の trip なしは、自由遷移を予測する遷移モデルではない。
既報の2D CFD +5〜17%、3D double-element −7% は文献上の scatter/context であり、criterion や digitization sensitivity に足さない。
LOCAL-OF-01 の gmsh platform 差により、local mesh/force は Kaggle の本番値の代用にならない。
格子独立性、3D／FSAE、正式な Stage T／V ranking、high-Re evaluator GO は主張しない。

## Claude／ユーザーへの提案する追記と WP4 への差分

1. WP4 geometry producer と validate_scene をともに更新し、密な smooth paired surfaces（≤1 mm、5° guardも満たす）と、供給済み straight TE cap subdivision を同一 SHA で W／R に渡す。**LE cap の3 source pairs は TE cap の角度免除ではない。**
2. 全6幾何を BL 計画／実行前 freeze に束縛し、結果構成は従来の5つへ射影する。E3_sharp の run は追加しない。
3. WP4 に両 shared schema の更新を反映する。force.observable／reference.observable、MESH_FAILED、cell_summary（DEGENERATE_REALISATIONSとratio INCOMPLETE）、両 h、thickening_alone、任意の study_geometry_sha256 を読む。observable をまたぐ差を拒否し、重複meshの区間を作らない。
4. VERIFIED の肯定側契約は、Claude／ユーザーが source page image の照合後に根拠付きで設定する。現在のOCRから ready を作らない。freeze、phase_plan、STATE、登録本文、PR #87 の更新は owner 側で行う。
5. 第1回 artifact は歴史的 development としてのみ残し、新 source の smoke／正式計測と区別する。

## 次に要るものと run 数・推定時間

密な6幾何 → Claude の再 render 指示 → local mesh-only＋SA-WF200反復を各1 realisation → source review／正式 freeze →
ユーザーの Kaggle CPU TR-00 → WP4の適格 cell 判定 → 厚い版本番、の順。Cp 入力は並行してユーザーが用意する。
この amendment 中に実物の kernel 再生成／Kaggle push／本番 solve は行わない。

| 段階 | run数 | 12 run以下/kernel | 5同時sessionでの波数 |
| --- | ---: | ---: | ---: |
| TR-00 E1_sharp／E2_sharp ×2 model ×2 family ×8 | 64 | 6 | 2 |
| main E1〜E3 ×最大4適格cell ×8 | 最大96 | 最大8 | 2 |
| 最大合計 | 160 | 14 | 4（TR判断を挟む） |

13〜21分／5000反復の envelope なら、初回 solve は34.7〜56 worker h。
stageを分けた12-run分割は10 case waveで、理想値130〜210分＝2.17〜3.50h（0.09〜0.15連続日）＋setup／判断時間。
全 run が15000まで延びる3倍仮定では6.5〜10.5h（0.27〜0.44日）。
保守的な4 kernel wave×11hの枠は44h＝1.83連続日で、完了保証・日次quotaの意味ではない。
T2-0 summary §3では **fine30は6〜11分、13〜21分はxfine30**。登録§7の幅を計画envelopeとして使い、
多体の実測所要時間とは呼ばない。160 CPU hは全session共通台帳でownerが管理する。
個別2.5h capの合計は最大400 worker hに達し、global_budget_enforced=falseなので、独立capは160hの強制ではない。

## Claude が commit すべき完全なファイル一覧

以下の **34ファイル**。同じ一覧を `wp05_amendment1_validation/commit_files.txt` に保存した。

```text
docs/codex/gen01_w1_2026_11_06/reports/cp_digitised_format.md
docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_measurement_schema.json
docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_design.md
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/README.md
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/SHA256SUMS
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/authority_read_receipt.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/commit_files.txt
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/frozen_inputs_unchanged.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/geometry_preflight.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/render_invalidation.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/run_forecast.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/schema_validation.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/source_inventory.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/synthetic_mesh_summary.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/synthetic_unit_meshes.tar.gz
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/test_logs.tar.gz
docs/codex/gen01_w1_2026_11_06/reports/wp05_amendment1_validation/validation.json
docs/codex/gen01_w1_2026_11_06/reports/wp05_collect_design.md
docs/codex/gen01_w1_2026_11_06/reports/wp05_cp_design.md
docs/codex/gen01_w1_2026_11_06/reports/wp05_design.md
docs/codex/gen01_w1_2026_11_06/reports/wp05_mesh_design.md
docs/codex/gen01_w1_2026_11_06/reports/wp05_report.md
docs/codex/gen01_w1_2026_11_06/reports/wp05_validation/README.md
scripts/topo2d00/build_tr00_kernels.py
scripts/topo2d00/collect_rans.py
scripts/topo2d00/digitize_cp.py
scripts/topo2d00/run_rans.py
scripts/topo2d00/t2d_foam_case.py
scripts/topo2d00/t2d_multibody_case.py
tests/topo2d00/test_build_tr00_kernels.py
tests/topo2d00/test_collect_rans.py
tests/topo2d00/test_digitize_cp.py
tests/topo2d00/test_multibody_case.py
```
ignoredな旧working renderのメタデータ変更は失効receiptで記録し、巨大なworkディレクトリ自体は commit 対象にしない。
