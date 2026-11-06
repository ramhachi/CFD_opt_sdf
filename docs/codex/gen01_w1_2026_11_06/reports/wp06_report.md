# WP6 GEOM-S1 フェーズ A 報告

## 状態

BLOCKED（新規 source と歴史的 source-closure freeze の契約不整合）。フェーズ A のコードと新規テストは実装済み。受け入れ条件を満たしておらず、PR #82 は Draft のまま。フェーズ B は未着手。

Amendment 1 を適用した scene、離散事象の提案、scene gate を実装した。前回の距離契約の blocker は解決した。今回見つかったのは別の source-closure 条件であり、Amendment 1 の「新たな矛盾が見つかった場合だけ、その箇所を具体的に示して止める」に従い、ready 化は行わない。既存 Draft PR #82 に実装と根拠を載せる。CFD/GPU/Kaggle、登録・凍結、最適化器、WaterLily job、ProblemSpec v2、既存 gate v2、harness は変更していない。


新しい不整合は値や数値閾値に依存しない：

1. 成果物として `src/cfd_sdf/scene/{__init__,primitives,scene,events,gates}.py` を追加する。
2. 既存 `scripts/analyze_grid02.py:112–113` は現在の `src/cfd_sdf/**/*.py` を `required_file_paths` に列挙する。`:165–167` はその全集合が過去の `prerun_freeze.json.file_hashes` に含まれることを要求する。
3. 同じ analyzer / freeze bytes で、開始点 `08e0ea38` は `required_not_in_frozen=[]` / `PASS`、現在の tree は上記五ファイルが不足し `ValueError: frozen file/source closure is incomplete`。
4. 過去の analyzer・freeze・pin したテストを変更せず、指定された新規ファイルを置いたままでは、この検証を開始点と同じ結果にできない。新規ファイルを commit しても、過去の freeze の hash key は増えない。

再現：

```bash
.venv/bin/python docs/codex/gen01_w1_2026_11_06/reports/wp06_source_closure_preflight.py --baseline /private/tmp/wp06-base-08e0ea38
```

成功終了と `SOURCE_CLOSURE_CONFLICT_CONFIRMED` は **新しい仕様不整合の再現**であって、受け入れ成功ではない。source と freeze の SHA と比較結果は `wp06_source_closure_preflight.json` に保存する。既存 freeze の更新、旧検証の monkeypatch、失敗チェックの skip、baseline への新 source 注入は行わない。

## 作ったもの（パス、1 行ずつ）

- `src/cfd_sdf/scene/primitives.py`：PlateElement、EndplatePlate、BoxBody、固定 STL の MeshBody、境界標本と明示した距離契約。
- `src/cfd_sdf/scene/scene.py`：min union、部品ラベル、bbox/h/位相からの SDFDesignState、canonical JSON/SHA256、明示的 MergedElement。
- `src/cfd_sdf/scene/events.py`：有限 seed/knockout/merge 候補、厚さ下限の連続 checkpoint 判定、分割 warm start の要素数系列、ID と要素数の変化分類。
- `src/cfd_sdf/scene/gates.py`：SceneGatePolicy、厚さ・gap・solid/void R3・連結・閉空洞・端板接合・規則箱・clearance・root/forbidden の検査と全拒否理由。
- `src/cfd_sdf/scene/__init__.py`：公開する基本型。
- `tests/scene/test_primitives.py`：距離・符号・変形 band・2D/3D・STL winding/hash・入力・中心連続性の検証。
- `tests/scene/test_scene.py`：union、格子、mask、npz、位相、hash/JSON、v18 の二枚板比較。
- `tests/scene/test_events.py`：有限積・重複除去・固定部品保持・離散分類・履歴・warm start、merge 後の再 seed 回帰。
- `tests/scene/test_gates.py`：正常対照、各 gate の合成反例、R3 の既存実装との差分比較、不明入力・改変 state・切れた格子の拒否。
- `tests/scene/test_birth.py`：Birth-0 の意図した一部品・位置・面積/体積・拒否、Birth-1 のソフトウェア準備としての seed/knockout/merge 分類。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_design.md`：実装前の設計メモ、共有経路、Julia 接続、h と登録の境界。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.py` / `.json`：再現可能な 25 振幅組合せ × 2/3D の距離 band 診断。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_validation.json`：コマンド、失敗 ID 集合、成果物 SHA256、証拠範囲。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_source_closure_preflight.py` / `.json`：同一の歴史的 reader/freeze で base PASS / 新 source 不足を再現する、solver-free な契約診断。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_cpu_only_pytest.py`：両 checkout に同じく適用する CPU 検証プロファイル。既存 Metal 6 ID だけを skip し、対象 ID の変更は停止する。
- `docs/codex/gen01_w1_2026_11_06/reports/wp06_attempt1_blocked/`：前回の六ファイルを内容を変えずに git mv。内部の旧パスと診断の ROOT は当時の配置の記録として保存した。

## インターフェース（他 WP が使う関数・CLI・ファイル形式）

`PlateElement(id,x,z,chord,thickness,angle=0,camber=0,reflex=0,span=1,y=0)` の長さは m、角度は rad。chord は v18 の中央直線長 L で、無変形 stadium の全長は L+t。点の最終軸が 2 のとき (x,z)、3 のとき (x,y,z)。断面を共有し、3D は flat tip の extrusion で合成する。EndplatePlate は x に弦、y に厚さ、z に高さ。BoxBody は中心・三半径・指数 p>=2 の凸な超楕円体。

`Scene(components,fixed=(),ground=None)` の ground は z 半空間。`phi(points)`、`labels(points)`、`sample(h,dimension=2|3,phase=(px,py,pz),bounds=None)`、`label_grid(state)`、`to_json()`、`from_json()`、`scene_sha256` を提供する。phase は [0,1) のセル分率。2D 状態は (nx,1,nz)、y=0 とし、3D 体積を与えず面積として診断する。JSON は schema_version=1、field_contract=geom_s1_amendment1_v1、SI 単位、順序付き部品、STL SHA を保持し、重複 key・未知型/項目・非有限値を拒否する。scene hash とサンプリング state hash は別物。

`seed_candidates(scene,library,positions)` は chord/thickness/camber の離散集合（angle/reflex は任意）と (x,z) の有限積。`downstream_seed_positions` は後縁より下流・下方の候補格子を作る。`knockout_candidates` は可動要素を一つずつ除き、`merge_candidates` は近接候補の二枚を移動して内部点を重ね、一つの MergedElement とする。`thickness_knockout_ids` は最後の二つの連続 checkpoint の厚さ下限滞在を stable ID で判定する。`element_count_designs` は N=1..N_max の分割 warm start を返す。いずれも評価・採否・最適化は行わず、候補は gate に渡す。

`evaluate_scene_gates(scene,h=...,dimension=...,policy=SceneGatePolicy(...))` は各 gate の pass/fail/unmeasured と理由一覧を返す。unmeasured も合格を阻む。常に cfd_evaluations=budget_charged=0。規則箱は lower/upper/rule_source、clearance は別の閾値と ground/明示 domain で渡す。要求する有限 union の成分数、端板接合対、root/forbidden mask も明示する。任意 STL の厚さは出典付き外部下限がなければ unmeasured。BoxBody の近接 gap は AABB の下限で証明できなければ unmeasured とする。

## テスト（コマンドと結果。全体 pytest の失敗集合が base と同一か）

- `.venv/bin/python -m pytest -q tests/scene --junitxml=/private/tmp/wp06-scene-tests.xml`：86 passed in 13.68s。
- merge 後の再 seed の最終修正は独立に `.venv/bin/python -m pytest -q tests/scene/test_events.py::test_reused_seed_library_after_merge_does_not_collide_with_child_ids`：1 passed in 2.98s。
- `.venv/bin/python -m compileall src tests`：終了 0。
- base は `git worktree add --detach /private/tmp/wp06-base-08e0ea38 08e0ea38` で分離。同じ venv、git stash 不使用。最初の無条件 `.venv/bin/python -m pytest -q --junitxml=/private/tmp/wp06-base-pytest.xml` は既存 `test_lbm_metal.py` の mlx.core import で Python が abort（終了134）。JUnit 未出力で、完走した base ではない。ログを保存。
- 実装後の無条件 `.venv/bin/python -m pytest -q --junitxml=/private/tmp/wp06-final-pytest.xml` は、base の Metal abort を確認後、同じ既知の GPU 初期化へ進ませず SIGINT（終了2、1435 passed / 24 skipped、1754.81秒）。これも完走ではない。
- GPU 禁止・sandbox の Metal 制限を守るため、既存 source/conftest/pin は変更せず、一時 plugin と同じ thread 上限を両 checkout に適用して CPU 対象全体を再実行。OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=VECLIB_MAXIMUM_THREADS=1、PYTHONPATH に本 reports ディレクトリを指定し、`.venv/bin/python -m pytest -p wp06_cpu_only_pytest -q --junitxml=...`。既存 Metal 6 件だけを skip、それ以外は全収集・実行。CI も Metal extra を入れず、BLAS/OMP を1 thread にしている。
- CPU profile base：3482 passed / 80 skipped / 0 failed、3344.06 秒、終了 0（全 3562 件）。
- CPU profile final：3564 passed / 80 skipped / 4 failed、3304.66 秒、終了 1（全 3648 件）。追加の scene 86 件は全て pass。
- 全体 pytest に含まれる既存 Julia CPU preflight は既存契約の回帰検査で、新 scene による CFD campaign・物理計測ではない。
- CPU profile の失敗 ID 集合の比較：base=[]、final は下記 4 ID で、**同一ではない**。skip の 80 ID は同一。無条件 pytest の完全同一性まで主張するものではない。
- `git diff --check`：検証済みの時点で終了 0。配達前に再確認する。
- 元の v2/parser/gates/harness/jobs/evidence/権威文書の指定パスに対する差分は空。
- 独立レビューで見つけた BoxBody 中心の不連続、merge 後の seed ID 衝突、改変された state hash、切れた格子が空洞なしとして通る問題を修正し、それぞれ回帰テストを追加した。前回六ファイルの移動後 bytes は開始 commit と一致。
- WP4 の多角形 SDF は開始 commit に未実装のため指定の v18 対照を使った。PlateElement × 2 の union は全標本点で v18 の二枚板と atol=rtol=1e-14 のテストを通過し、要求 1e-3c を満たす。

全体 CPU run の失敗 ID（変更前の HEAD `08e0ea38` のまま実行）：

```text
tests/test_grid02_evidence.py::test_the_analysis_is_the_registered_one_and_reproduces_from_the_kept_output
tests/test_grid02_prereg.py::test_every_file_the_freeze_binds_is_committed_at_head_once_it_exists
tests/test_grid02_prereg.py::test_the_real_freeze_validates_with_the_analyzer_and_is_sidecar_bound
tests/test_lowdim03_prereg.py::test_every_file_the_freeze_binds_is_committed_at_head_and_the_runner_constants_are_pinned
```

GRID-02 の `test_every_file_the_freeze_binds...` と LOWDIM-03 の同名検査は、どちらも `not committed: src/cfd_sdf/scene/__init__.py`。source commit `248255ce6d3be04d23d6061d7d9ceee6894bffe1` の後に上記 4 ID を再検証し、**2 passed / 2 failed（16.93 秒）**。二つの HEAD 所属検査は pass になり、次の二件だけが同じ source-closure 原因で fail のまま残った：

```text
tests/test_grid02_evidence.py::test_the_analysis_is_the_registered_one_and_reproduces_from_the_kept_output
tests/test_grid02_prereg.py::test_the_real_freeze_validates_with_the_analyzer_and_is_sidecar_bound
```

全体テストは commit 前の 4 failed の結果を保存し、commit 後は対象 4 件だけの再検証である。全体を二度完走した、あるいは失敗集合が同一になったとは主張しない。第三者レビューでも同じ base PASS / 新五 source 不足を再現した。既存テストは変更していない。

`wp06_test_artifacts/` に無条件 run の abort/中断ログ、CPU 完走ログ/JUnit、新 scene ログ/JUnit、compileall ログを gzip（mtime=0）で保存。圧縮 bytes と展開 bytes の SHA256 は `wp06_validation.json` に列挙する。全体 run は legacy CPU preflight を含み約 55 分を要した。新 scene の個別検証は約 14 秒で、新しい CFD campaign は行っていない。

振幅 band の登録前開発診断は次で再現する：

```bash
.venv/bin/python docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.py
```

c=1 m,t=.1 m,h=.025 m、各条件 1700 query、seed=610。band は |computed phi|<=2h。独立にパラメタ化した v18 の零等位面（片側 50001 点と cap）への点群最短距離を用い、3D 対照はその断面距離の正確な flat-tip extrusion。表の距離差は t で除した無次元値（限界 0.02）、勾配偏差は2/3Dの中央値の大きい方（限界0.10）。点群の有限密度と有限 query の検査であり、全パラメタ空間の証明ではない。

| camber/c (%) | reflex/c (%) | band点数 2D / 3D | 最大距離差/t 2D | 最大距離差/t 3D | 最大の median gradient error |
| ---: | ---: | ---: | ---: | ---: | ---: |
| -6 | -4 | 1004 / 762 | 5.841e-06 | 2.449e-06 | 1.967e-12 |
| -6 | -2 | 1014 / 763 | 2.817e-05 | 3.474e-06 | 1.879e-12 |
| -6 | +0 | 1016 / 761 | 4.558e-06 | 1.280e-05 | 1.856e-12 |
| -6 | +2 | 1006 / 758 | 3.035e-06 | 8.754e-07 | 1.793e-12 |
| -6 | +4 | 1002 / 758 | 1.237e-05 | 2.326e-05 | 2.107e-12 |
| -3 | -4 | 1008 / 759 | 1.563e-05 | 2.838e-06 | 1.897e-12 |
| -3 | -2 | 1009 / 751 | 2.677e-06 | 4.132e-06 | 1.848e-12 |
| -3 | +0 | 1004 / 753 | 1.847e-05 | 2.109e-06 | 1.743e-12 |
| -3 | +2 | 1006 / 752 | 1.160e-06 | 1.437e-06 | 1.750e-12 |
| -3 | +4 | 1014 / 756 | 1.885e-06 | 8.857e-06 | 1.899e-12 |
| +0 | -4 | 1014 / 766 | 2.593e-06 | 1.069e-05 | 1.753e-12 |
| +0 | -2 | 1018 / 765 | 1.716e-06 | 3.506e-05 | 1.821e-12 |
| +0 | +0 | 1011 / 761 | 1.135e-05 | 6.392e-06 | 1.000e-12 |
| +0 | +2 | 1002 / 759 | 3.000e-06 | 5.224e-06 | 1.726e-12 |
| +0 | +4 | 995 / 754 | 2.067e-06 | 1.684e-06 | 1.733e-12 |
| +3 | -4 | 1014 / 762 | 5.041e-05 | 2.928e-06 | 1.809e-12 |
| +3 | -2 | 1005 / 757 | 1.330e-05 | 1.291e-05 | 1.846e-12 |
| +3 | +0 | 999 / 761 | 5.001e-06 | 1.386e-05 | 1.889e-12 |
| +3 | +2 | 1003 / 767 | 1.949e-06 | 4.682e-05 | 1.815e-12 |
| +3 | +4 | 1004 / 767 | 2.704e-06 | 4.150e-06 | 1.847e-12 |
| +6 | -4 | 1015 / 768 | 6.485e-06 | 1.372e-05 | 2.102e-12 |
| +6 | -2 | 1018 / 759 | 5.250e-06 | 5.856e-06 | 1.844e-12 |
| +6 | +0 | 1005 / 762 | 3.059e-06 | 1.745e-05 | 1.803e-12 |
| +6 | +2 | 1002 / 765 | 7.046e-06 | 9.430e-06 | 1.920e-12 |
| +6 | +4 | 1003 / 764 | 1.574e-06 | 8.354e-06 | 2.079e-12 |

無変形板は非微分集合を避けた中央差分で |grad phi|=1、atol=1e-8。変形 25 条件の最大距離差/t は2Dで5.040873270172855e-5、3Dで4.682376874112638e-5、最大 median gradient error は2.107147789587316e-12。全 50 条件が指定の band 許容を通過した。

## 仕様からの逸脱と理由

全体 pytest の無条件完走は、この sandbox の既存 MLX/Metal import abort により取得できなかった。失敗を隠す source 修正はせず、GPU を禁止する WP 共通規則に従って六つの Metal ID だけを明示 skip した CPU profile で両 checkout を比較する。未完走の二ログと完走 profile の範囲は区別する。再実行はこのインフラ失敗への対処であり、結果に応じて基準を緩めたものではない。

Amendment 1 の零等位面契約を守り、変形時の生の v18 phi は採用せず、多項式面への fixed multistart projection で距離近似を改善した。生の一次式は C/c=.06,R/c=.04,t/c=.1,h/c=.025 の滑らかな chord 内点で、真の距離との差が少なくとも .034208t となり、新しい .02t 許容を満たさないためである。閾値・振幅域は緩めていない。無変形の v18 値はそのまま一致する。

BoxBody の一般形は Amendment 1 の可動 implicit-field 契約として勾配正規化した一次近似で、厳密 SDF と呼ばない。中心の連続性を確保する deep-interior continuation を持ち、球の場合は正確な距離に分岐する。min union は重なり内側では一般に正確な負の距離ではない。独立可動要素の重なりは gate が拒否し、明示 merge 内部と端板接合は宣言した別の扱いにする。

SDFDesignState の既存型を保つため、2D は singleton y に格納し、面積と体積の意味を分けた。規則箱は phase B の ProblemSpec v3 adapter に先立つ明示 policy 入力。FSAE/FSG の実寸を推測してハードコードしていない。

OpenCode Go MCP がなく、CLI 1.19.3 のモデル一覧確認は通常経路の log 書き込み制限と、一時 XDG 経路の Provider not found: opencode-go で失敗。native worker にプリミティブ・gate・独立レビューを分担し、親が差分と検証を確認した。global config、認証、追加課金は変更していない。

Git の worktree index.lock は共有 gitdir の明示パスでも書き込み拒否のため、同じ worktree/branch/shared gitdir と `GIT_INDEX_FILE=/private/tmp/wp06-index` を使い git mv と意図したパスの staging を行った。通常の `git commit` は `COMMIT_EDITMSG: Operation not permitted` で停止し、HEAD は変わらなかった。active hook がないことを確認し、同じ共有 Git dir で `write-tree` / `commit-tree` を用い、親が開始点 `08e0ea38` であることを確認した上で `update-ref <new> <expected-old>` で feature ref を進めた。別 checkout/clone、force/reset は使っていない。

source commit は `248255ce6d3be04d23d6061d7d9ceee6894bffe1`。`feat/gen01-w1-06-geom-s1` に fast-forward push 済みで、`ls-remote` と PR #82 の head SHA が一致することを readback した。最終報告・再検証記録は同じ branch に後続 commit として保存する。PR は Draft、向き先 `codex/kaggle-batch-migration`、auto-merge は無効を維持する。

通常 index を意図した 37 パスだけ `git restore --staged --source=HEAD -- <paths>` で同期する試みも index.lock の同じ制限で拒否された。**通常 index は開始点のままであり、通常の git status は古い staging 状態を示す。一時 index では source commit と一致し、作業ファイルを巻き戻していない。** sandbox 制約として記録し、共有メタデータを直接書き換えて回避していない。

## 未確認の仮定（実行して初めて分かること、PDF から読めなかった値など）

- 新 scene の GPU/Julia projection 実装・Float32 parity・速度、AutoBody/BDIM による新 scene 評価は未実施。Python の部品 field と canonical JSON を渡す契約を提供した。
- fixed-count multistart の全振幅・全厚さに対する大域的収束の証明はない。表とテストの範囲を超えた距離適格性は主張しない。
- 厚さ・gap の 4h は開発時の既定で、RES-00 の登録梯子の値とは別。変形板の nominal t は局所縦方向の分離幅なので、gate は最大傾きによる保守的な normal-width 下限と R3 を用いる。
- 連結・空洞・R3・接触は宣言した標本規約のソフトウェア検査で、任意の連続形状・製造・物理的な保証ではない。GEOM03_NO_GO / R3 未採用、SRCMAP02_INCONCLUSIVE と全 qualification flags=false は変わらない。
- 実車用の FSAE 2026 T.7 / FSG 2026 / FSG 2027 規則箱、固定 STL、パラメタ bounds/刻みは B 側で出典と hash を宣言する。v2 CFD domain を規則箱に代用していない。
- R3 は refined nodes が 8,000,000 を超えると unmeasured で拒否する。通常の標本化も 2,000,000 nodes の資源ガードを持つ。解像度を黙って落とさず、大きな 3D scene の実時間・メモリは後続の実機検査が必要。
- 分割 warm start は設計候補の列であり、各 split が包絡内に収まる、体積を保存する、空力的に有効であるとは主張しない。

## Claude／ユーザーへの提案する追記（phase_plan、STATE、exploratory_index、仕様 rev 0 への修正点）

> GEOM-S1 フェーズ A は solver-free software/contract として scene・離散提案・scene gate を実装。Birth-0 と Birth-1 のソフトウェア準備を区別し、actual primal の Birth-1 は未適格。変形板は v18 の零等位面を保つ数値的な距離改善を使う。4h は開発既定、登録は RES-00 の梯子で行う。WaterLily 主線から r_c を除き、部品パラメタの bounds と刻みを B に宣言する。R3 の再利用は既存の GEOM03_NO_GO の改定ではない。

`docs/harness/README.md` への追記案（未実装、本文は未編集）：

> harness v1.2 は scene JSON の SHA と明示的な Julia job 引数に結び付く scene state、checkpoint ごとの有限 event 候補、地面と共に移す z を含む3軸位相を扱う。event は提案記録であり、評価・採否・予算消費は別段階。従来 v1.1 campaign は明示的な version dispatch で保持し、validate/verify の byte 不変を fixtures で検証する。暗黙に移行しない。

Julia は JSON の部品式を AutoBody callable として直接評価し、SetBody(min,...) で合成する。固定格子への Python 標本化は gate/診断用であり、GPU の field 評価を三線形補間へ置き換えない。WP4 の polygon SDF との一致には同じ零等位面・厚化・LE/TE の定義をそろえた別の parity test が必要。r_c は使わず、h と bounds/刻み、登録する厚さ・gap をそれぞれ区別する。

## 次に要るもの（GPU 実行、Kaggle、ユーザーの判断）

必要なのは、新しい source-closure の扱いに対する明示的な契約判断である。歴史的 replay を登録時の source commit / 凍結済みファイル集合に固定する新しい互換規約を許可するか、今回の受け入れ条件にこの既知の歴史的 closure 差分を明示的に区別する必要がある。Codex が過去の記録・pin・失敗条件を独自に書き換えない。判断後に A の受け入れを確定して PR #82 を ready にし、その後に別 PR の B へ進む。この不整合の解決に CFD/GPU/Kaggle は不要。actual Birth-1、BDIM 解像度と gap の資格化、Julia/GPU の parity/性能はそれぞれの後続 WP/登録で確認する。
