# WP5 TR-00／TOPO-2D-00 RANS 側 報告

## 状態

PARTIAL — 実装・検証・feature branch の push は完了。PR 作成は承認制限で未完了。新しい多体生成器、Cp 積分器、WP4 互換集計器、CPU kernel のローカル生成と、E2_sharp／E2 の mesh-only・各 200 反復 smoke を実装・検証した。TR-00 の実測参照増分や適格性判定はまだ出していない。Kaggle への push・本番実行は行っていない。

通常の一括 pytest は、基準版から既存 Metal backend の import で abort する。この環境制約を明示し、Metal を除いた全体 suite と Metal 6 node の個別実行を合わせ、base の全 3562 node と変更後の全 3681 node を照合した。既存 node の結果はすべて同一、追加119件はすべて pass。一括コマンド自体の成功とは扱っていない。

PR は未作成。作成先: [比較・PR 作成画面](https://github.com/ramhachi/CFD_opt_sdf/compare/codex%2Fkaggle-batch-migration...feat%2Fgen01-w1-05-tr00-rans?expand=1)（base: `codex/kaggle-batch-migration`、head: `feat/gen01-w1-05-tr00-rans`）。auto-merge の設定はしていない。

実装 commit: `f7ab4b0fcb81b8072f105b3be22f3843d21035c1`。検証記録 commit: `2446960e6de89b9a9e24dfbfad5c1fc11da01d04`。

元の worktree の Git 管理領域は sandbox の書込範囲外だったため、許可された `work/wp05/publication.git` に独立した Git 管理領域を作り、同じ feature branch を commit／push した。元の worktree の HEAD・index は base `e3dcdf61` のまま。既存ファイルは変更せず、新規ファイルだけを対象にした。

## 作ったもの（パス、1 行ずつ）

- `scripts/topo2d00/t2d_multibody_case.py` — 閉曲線 1〜3 体の gmsh 生成、要素別 patch、BL、sharp fan／blunt no-fan、入力・メッシュ SHA と品質 proxy。
- `scripts/topo2d00/t2d_foam_case.py` — SA-WF／SST-WF、fine30／med30、5000→必要時 15000 の一度だけの継続、要素別・合計の係数と圧力／粘性力。
- `scripts/topo2d00/digitize_cp.py` — ユーザー CSV の台形積分、独立 2 読み取りの差、Table 15／Cl(h) 入力、共通 c1 への換算。
- `scripts/topo2d00/collect_rans.py` — hash 検証、欠け run、収束分類、共通規格化、WP4 analyzer への変換。
- `scripts/topo2d00/build_tr00_kernels.py`・`run_rans.py` — source／幾何を束ねた CPU kernel の生成、時間上限、実行記録の保存。
- `tests/topo2d00/` — 合成 Cp、閉曲線、schema・収束・欠け run、kernel 分割・継続・上書き拒否の 119 テスト。
- `docs/codex/gen01_w1_2026_11_06/reports/cp_digitised_format.md` — CSV と JSON manifest の完全な入力例、座標・測定量・不確かさの限界。
- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json` — 実際の WP4 と byte 同一の共有形式。
- `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_measurement_schema.json` — 要素別係数・収束・raw artifact の詳細形式。
- `docs/codex/gen01_w1_2026_11_06/reports/wp05*_design.md` — 実装前の設計、格子族・後縁・参照・集計の判断。
- `docs/codex/gen01_w1_2026_11_06/reports/wp05_validation/` — raw smoke、生成済み kernel・幾何入力のアーカイブ、SHA、schema 接続とテストの記録。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

`write_case(out, geometry, model, family, realisation, iters=5000)` は、WP4 の `topo2d-scene-v1` JSON／NPZ、または metre 単位の閉曲線 JSON／NPZ を読む。WP4 の polygon を曲線で近似し直さず、その線分を保持する。patch は `airfoil`／`airfoil_2`／`airfoil_3` と既存 T2-0 の外部境界。fine30 は ds=2 mm、med30 は ds=4 mm、両方 y1=0.6 mm、g=1.2。密な入力頂点によって実際の壁面間隔が名目 ds より細かくなる場合を記録する。

参照の比の帯 **[0.5, 2]** と **5%** の規則は変更していない。

全構成と要素を c1=0.2234 m、span=0.002 m、Aref=0.0004468 m² で規格化し、Cl は下向き正、Cd は流れ方向正。`forceCoeffs` の前後分割を圧力／粘性と取り違えず、`forces` の次元付き出力から成分を保持する。TR-00 の sharp 系は Cp と比較する圧力係数、厚い E1〜E3 は WaterLily と比較する総係数を WP4 へ渡す。

Cp の CSV は UTF-8、正確に `x/c,Cp` の 2 列。各要素の物理的上面／下面を、2 人または 2 ツールで独立に読むため、E2 は計 8 CSV。`x/c` は指定 chord で割った global streamwise X、両面は全輪郭の同じ投影端点を覆う。傾いた local chord 座標をそのまま積分する入力は拒否する。入力 JSON は出典 URL、図／パネル、高さ、座標の根拠、読み取り者・ツールと各 CSV を宣言する。元 manifest と実 CSV を絶対パス・SHA・方法で束ね、study freeze が入力を照合できる形にする。単一要素は Table 15 の Cl=1.009（h/c1=0.448）を別由来の表値として入力するか、独立した Cl(h/c) 曲線 2 本を使う。

```sh
.venv/bin/python scripts/topo2d00/digitize_cp.py path/to/cp_manifest.json \
  --out path/to/tr00_reference.json
.venv/bin/python scripts/topo2d00/collect_rans.py path/to/tr-output path/to/main-output \
  --plan work/wp05/kernels_tr00/run_plan.json \
  --plan path/to/qualified-main/run_plan.json \
  --reference path/to/tr00_reference.json --out rans_results.json
```

TR-only の集計では `--plan kernels_tr00/run_plan.json --geometry-plan kernels_main/run_plan.json` を使うと、未実行の main plan から幾何 identity だけを渡せる。本番の run は期待集合に加えない。共有出力には全 5 構成の一致した幾何 SHA を要求する。

`rans_results.json` は `topo2d00-rans-results-v1` の cells／8 realisations。元の要素別 Cl・Cd、圧力／粘性、メッシュ SHA、収束状態は diagnostics／provenance に残す。欠け run は null／INCOMPLETE として残し、通常 CLI は非ゼロ終了。Cp 未入力時は `--measurements-only` で詳細診断だけを出せる。settled／limit_cycle／diverged に加え、判定不能を not_settled／unavailable と区別する。SIMPLE の周期は反復上の数値的周期であり、物理的な周期や URANS 適格性とは扱わない。

## テスト（コマンドと結果。全体 pytest の失敗集合が base と同一か）

- `.venv/bin/python -m pytest -q tests/topo2d00` — **119 passed、106.41 s**。gmsh がない環境では該当するメッシュテストを skip。既存 conftest や pin は変更していない。
- `.venv/bin/python -m compileall src tests` — exit 0。
- 通常の `.venv/bin/python -m pytest -q` — 基準版が既存 `tests/test_lbm_metal.py` の MLX import で native abort（exit 134）。「No Metal device available」という sandbox 環境障害であり、全体 pass とは報告しない。
- `.venv/bin/python -m pytest -q --ignore=tests/test_lbm_metal.py --junitxml=…` — 独立した base checkout: **3482 passed / 74 skipped（exit 0）**、変更後: **3601 passed / 74 skipped（exit 0）**。Metal 以外の失敗集合 **一致（双方0件）**。Metal 6 test は各々を新しい pytest process で実行し、base／変更後とも同じ 6 node が同じ device 不足で失敗した。分割検証の失敗集合も同一。既存テスト・依存環境は変更していない。詳細とログ hash は `wp05_validation/test_validation.json` と `metal_environment_diagnostic.json`。
- 取得した integration tip `b06452a18b47a81788d4b425b0b2f390affd7d2f` との `git merge-tree --write-tree HEAD FETCH_HEAD` は conflict なし（working tree／branch の merge はしていない）。
- `git diff --check` と独立 Git index の `git diff --cached --check` — exit 0。凍結ソース・既存 infra・登録・roadmap の変更なし。
- 2 つの JSON Schema と合成出力を Draft 2020-12 validator で確認し、WP4 analyzer の観測 snapshot（SHA `704423d491d4b9cf0521b2cf8b0ae7d7417e2249cff661a425ffe7d268a3e8b2`）の `validate_input` も通過。合成データの判定ラベルは接続確認のみで、物理検証には数えない。

ローカルでは下記の wrapper を用い、各 1 realisation で **mesh generation → gmshToFoam → checkMesh → 同じ mesh の SA-WF 200 反復**を実行した。

```sh
.venv/bin/python scripts/local_openfoam.py run \
  work/wp05/local_smoke_kernel/smoke_01 --out work/wp05/local_smoke_run \
  --cpus 4 --memory 8g
```

| 指標 | E2_sharp | E2（厚い版） |
| --- | ---: | ---: |
| cells | 37,754 | 37,848 |
| checkMesh | Mesh OK、failed checks なし | Mesh OK、failed checks なし |
| 最大 non-orthogonality（°） | 54.276422 | 54.664386 |
| 最大 skewness（checkMesh） | 2.3987006 | 1.7989068 |
| 最小 determinant（checkMesh） | 0.034175708 | 0.050301549 |
| 最小 face weight（checkMesh） | 0.14761962 | 0.15404030 |
| 最小 volume ratio（checkMesh） | 0.13512438 | 0.14207175 |
| proxy internal／boundary skew | 0.658047／0.417515 | 0.613896／0.252040 |
| 最小 gmsh SICN（triangle proxy） | 0.310723 | 0.381999 |
| 品質 proxy failures／unused nodes | 0／0 | 0／0 |
| SA-WF | 200 反復、全 force 有限 | 200 反復、全 force 有限 |

両方とも 4 BL 層、厚さ 3.2208 mm、airfoil 第一層中央値 0.6 mm。メッシュ SHA は E2_sharp `68af8c4906a0f27bb9dfd2c4202cb4d5f288029491a144500cbeff8c7ba49013`、E2 `adade07782c033a4617b0ed7558ab6f0c4d1103bfb7a787b0c1891e4f014fe68`。smoke 全体の wrapper wall time は 235.43 s、return code 0、実行後 package inventory は lock と一致した。要素の和・圧力／粘性の和・次元付き force と係数の換算も照合し、最大絶対差は 3×10⁻⁸ 未満だった。収束・格子独立性・Kaggle 再現性の結果ではない。

`local_smoke_artifacts.tar.gz` の SHA-256 は `c44942f8d70253770bc7aa5ccc5e8cadf6661aa937f4b6bb8de03f440a7490db`。`rendered_kernels_and_inputs.tar.gz` は `abaa9f076e193d8b3e25ebc86f24efa5be5fec4f3e4e9b55c429a1f1bb39fb90`。展開後の全 member の hash を照合済み。後者にローカル生成した kernel、WP4 幾何 JSON／NPZ、生成元の snapshot と入力 SHA を含む。

## 仕様からの逸脱と理由

- 通常の全体 pytest は基準版から Metal import で abort するため、残りの suite と Metal 6 test の個別プロセスに分けて回帰を比較した。未使用の Metal backend を修正・削除する変更は本 WP に含めていない。
- 第 2 格子族は既存の **med30** を選び、新しい調整値や pin を追加しなかった。
- WP4 の実入力では `_sharp` は「厚み追加前の原形」の名称で、数学的 cusp ではなく有限厚の後縁 cap がある。この入力を尖らせず、E2_sharp・E2 とも **blunt no-fan** とした。両方の実 checkMesh と proxy は上表のとおり。数学的 sharp の fan は別の合成閉曲線テストで確認した。この結果から全ての鈍い後縁の妥当性は一般化しない。
- 実際の WP4 schema に合わせ、詳細測定形式を別ファイルに残し、共有形式への adapter を追加した。共有 schema は WP4 と byte 同一。
- 登録の 13〜21 分という時間幅は、T2-0 summary では **xfine30** に対応し、fine30 は 6〜11 分だった。依頼の 13〜21 分を計画用の幅として使い、測定実績の誤った帰属は避けた。
- OpenCode Go は callable MCP がなく、CLI のモデル確認も sandbox のログ書込制限で失敗したため、分担した native worker で実装・独立レビューを行った。追加の従量課金 API や global 設定変更は行っていない。

## 未確認の仮定（実行して初めて分かること、PDF から読めなかった値など）

WP4 の source/table SHA を保存した開発 snapshot を smoke と kernel 入力に使った。正式 run 案は WP4 JSON を使用する。NPZ の mesh 入力にも対応するが、raw NPZ SHA を formal WP4 が要求する JSON-file SHA に置き換えず、対応付けは別途合意・検証が要る。元の座標表には未検証 OCR の表示があり、原論文との幾何照合や BDIM core の適格性は、この mesh の成功では解決しない。nominal h=100 mm の datum と実輪郭の最小すき間を別々に保存した。密な polygon と名目 ds の関係を含め、格子族は登録上の独立な realisation として本番で再確認が要る。

SA／SST は trip を置かない fully turbulent wall-function 計算であり、自由遷移位置を予測する遷移モデルではない。実験の自由遷移や 2D／3D・有限幅の差は残る。

Cp CSV はユーザー入力待ちであり、実験 E2 の Cl・ΔCl・不確かさ・TR-00 判定は未生成。2 読み取りの絶対差はデジタイズ感度で、信頼区間や総実験誤差の上限ではない。総参照不確かさは null のまま保持する。Table 15 の高さの丸め・trip 条件、2D CFD の既報の偏りも解消しない。

Kaggle での installer・5000／15000 反復・SST 実行・多体の所要時間は未実行。gmsh の非再現性により、今回のローカル mesh SHA を Kaggle の実測値に代用しない。

## Claude／ユーザーへの提案する追記（phase_plan、STATE、exploratory_index、仕様 rev 0 への修正点）

本報告と保存 artifact を **WP5 tooling／LOCAL_SMOKE** として参照し、本番計測・TR-00 の verdict と分けて記録する。仕様本文は変更していない。共有 schema、sharp 系＝圧力／厚い版＝総力の比較成分、共通 c1、名目高さと幾何 datum、`_sharp` の有限 cap を、統合時に明文化することを提案する。

既存 Metal backend の実機検証と、一括 pytest の native abort を扱う test-runner 方針は別途整理が必要。今回の分割検証は、その backend を通過済みにはしていない。

時間見積りの fine30／xfine30 の帰属と、全セッションを通じた 160 CPU h の予算台帳の管理者を明確にすることを提案する。kernel は 11 h の session cap と case cap を持つが、**複数 kernel を通じた 160 CPU h は自動集計・強制しない**。独立 case cap の合計は最大 400 solver h に達し得るため、ユーザーの共通台帳で登録上限を守る必要がある。

## 次に要るもの（GPU 実行、Kaggle、ユーザーの判断）

ユーザーが一次資料の座標・高さ・圧力の測定量を確認した独立 2 読み取り CSV と manifest を用意し、参照値を作る。その後、凍結・資格条件を確認してユーザーが Kaggle CPU で TR-00 を回す。厚い版本番は、TR-00 の結果から明示した `--qualified-cell model/family` で再生成するまで blocked。GPU 実行は WP5 の範囲に含めない。

| 段階 | run 数 | kernel 数（最大 12 run／kernel） | 5 session 枠での波数 |
| --- | ---: | ---: | ---: |
| TR-00: E1_sharp／E2_sharp × 2 model × 2 family × 8 | 64 | 6 | 2 |
| 厚い E1〜E3: 全 4 cell が適格だった場合の最大 | 96 | 8 | 2 |
| 合計最大 | 160 | 14 | 4（TR 判定を挟む） |

13〜21 分／5000 反復を仮定すると、初回 solve の合計は 34.7〜56 worker h。4 worker／session の分割では、段階を分けた 10 case wave が理想的には **130〜210 分（2.17〜3.50 h、0.09〜0.15 連続日）＋ setup・TR 判断時間**。全 run が 3 倍まで継続すれば 6.5〜10.5 h に相当するが、いずれも多体計測前の計画値。保守的な 4 kernel wave × 11 h は 44 h（1.83 連続日）の枠であり、完了保証や日次 quota の主張ではない。160 CPU h 台帳と実際の所要時間に従って中断・残件を明示する。

**PR 作成は自動承認の制限で拒否された。** GitHub コネクタは `MCP tool call requires approval, but approval policy is never` を返した。この実行環境では必要な承認を要求できない。PR 本文として使える本報告と、上記の作成リンクを残した。
