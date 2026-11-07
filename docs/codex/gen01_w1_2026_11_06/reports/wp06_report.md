# WP6 GEOM-S1 フェーズ A 報告（Amendment 3）

## 状態

**DONE（フェーズ A：Opus source review の修正・再検証）**。開始点は `6536cbf04b86eaf022c0c201a91f548fd4389e94`、branch は `feat/gen01-w1-06-geom-s1`。review の MAJOR 4 件と Amendment 3 の指定項目を修正し、追加の相互レビューで見つかった BoxBody gap の距離根拠と履歴の時点別 floor も修正した。結果側の全体 pytest は **3680 passed / 74 skipped / 0 failed / 0 errors**。失敗 node 集合 **[]** は host 提供 base の `[]` と同一。フェーズ B は未着手。

これは作業ツリー上のソフトウェア受け入れ判定であり、登録・物理 qualification・Birth-1 primal の完了を表さない。Amendment 3 §15 に従い、Codex は staging、commit、push、index/ref 更新、PR 編集を行っていない。HEAD は開始 commit のまま。Claude が host で下記だけを commit・push し、既存 PR [#82](https://github.com/ramhachi/CFD_opt_sdf/pull/82) を更新する。

## 作ったもの（今回 commit すべき完全な一覧）

今回は移動なし。`6536cbf0` からの変更・新規ファイルを列挙する。歴史的な `cfd_sdf.scene` → `cfd_gen.scene` の移設は開始 commit に含まれており、今回の変更ではない。

| 区分 | 完全なパスと内容 |
| --- | --- |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_amendment3_review_checks.json`：review/plan/issue入力、修正とテスト対応、130/13 frozen source hash照合。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.json`：今回source/oracle SHAで再生成した50ケース。数値は前回と同一。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_design.md`：実装前のAmendment 3設計、worker境界、レビューで見つかったfloor/Box補足。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_report.md`：本報告、完全一覧、今回の結果・限界・提案。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment3-compileall.log.gz`：今回の完走ログ/JUnit。圧縮・展開bytesのSHAはvalidationに保存。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment3-full-pytest.log.gz`：今回の完走ログ/JUnit。圧縮・展開bytesのSHAはvalidationに保存。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment3-full-pytest.xml.gz`：今回の完走ログ/JUnit。圧縮・展開bytesのSHAはvalidationに保存。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment3-red-gates.log.gz`：修正前の部分的TDD gate失敗ログ。正式qualificationではない。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment3-scene-pytest.log.gz`：今回の完走ログ/JUnit。圧縮・展開bytesのSHAはvalidationに保存。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment3-scene-pytest.xml.gz`：今回の完走ログ/JUnit。圧縮・展開bytesのSHAはvalidationに保存。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_validation.json`：今回のコマンド/結果/failure node/artifact SHA、開始HEADとhost delivery。 |
| 変更 | `src/cfd_gen/README.md`：固定文脈と設計の範囲、2M/8M cap、MeshBody計算量、merge/Juliaの限界。 |
| 変更 | `src/cfd_gen/scene/events.py`：最近方向merge、footprint保存split、時点別floor履歴、翼限定knock-out、符号付き種まき。 |
| 変更 | `src/cfd_gen/scene/gates.py`：movable限定制約、片側gap guard、共通floor、joint範囲、例外/cap/hash記録。 |
| 変更 | `src/cfd_gen/scene/primitives.py`：共通ID validator、負ゼロ正規化、BoxBody/MeshBodyの実態に合うdocstring。 |
| 変更 | `src/cfd_gen/scene/scene.py`：mesh path非依存hash、merged ID、型付きsample資源上限、負ゼロ。 |
| 変更 | `tests/scene/test_birth.py`：2D/3D Birth-0の有効seedがpolicy gateを通る正の対照。 |
| 変更 | `tests/scene/test_events.py`：非同一merge、span gap、N1..5、履歴floor、種まきpolicyとknock-outの回帰。 |
| 変更 | `tests/scene/test_gates.py`：fixed付き、限界16位相、距離根拠、floor履歴、joint/cap/早期拒否schemaの回帰。 |
| 変更 | `tests/scene/test_primitives.py`：負ゼロ、共有ID、BoxBody continuationの回帰。 |
| 変更 | `tests/scene/test_scene.py`：STL locatorを変えたhash、merged ID、sampling cap/巨大寸法の回帰。 |

旧 `wp06_attempt1_blocked/`、Amendment 2 の closure JSON、旧ログ/JUnit gzip、旧 CPU profile plugin は変更していない。`src/cfd_sdf/scene/` は生成 bytecode を含め存在せず、旧 namespace の shim はない。`src/cfd_sdf`・`julia/CFDSDFWaterLily/src` の既存 source はすべて host base `e3dcdf61` と byte 一致。v2 parser・v2 gate・harness・WaterLily job・計画本文・登録済み evidence は変更していない。

## 修正と対応する確認

| review 項目 | 修正と確認 |
| --- | --- |
| M1 | envelope、ground/domain clearance、forbidden mask、root 所有を `scene.components` に限定。z=0 に接し、翼用の規則箱と domain の外にある固定タイヤを追加しても翼が合格。タイヤに root を要求せず、タイヤ領域の forbidden mask も翼に干渉しない。有限 union の連結性と可動 vs fixed の gap は維持し、近すぎる fixed は拒否する。 |
| M2 | merge は最近点方向へ gap＋宣言した overlap δ だけ第2板を移動。第1板と child ID を保持する。長さ・厚さ・角度が異なり下流・上方にある main＋flap が、2D/3D とも元 scene 2 solid → merge 後 1 solid で gate に合格し、消えた2 ID を正しく分類する。 |
| M3 | 分割子の直線弦を `(L-t-gap)/2` に修正し、親の軸方向 footprint `L+t` を保存。camber/reflex は弦比で縮め、相対振幅を保つ。開発既定 t=4h、gap=4h の N=1..5 がすべて gate に合格。正の子弦を作れない要求は例外で拒否。 |
| m1 | distance/projection 場では標本最小 d が g_min 未満なら確定 fail。guard は g_min より上の片側で受け入れ保留に使う。一般 BoxBody の正規化 implicit 値は真の距離の上界ではないため、重なりの符号証拠または AABB の合格証拠がない限り unmeasured とする。 |
| m3 | `_normal_width` と同じ算定から部品ごとの parameter floor を導出し、gate と履歴判定で共有。形状/ID が変わる履歴には checkpoint ごとの `parameter_floors` を保存でき、flat → cambered の各時点の床や削除済み ID を現在の床で誤判定しない。 |
| m7 | 有効 Birth-0 の policy 合格を2D/3Dで検査。t=4h/gap=4h の16位相を2D/3Dで検査。fixed 付き、N≥3、非同一 merge の正の対照を追加。 |
| M4 | gate が標本化 2,000,000 node 超を `sampling: unmeasured` として理由・要求 shape/count・cap を記録。R3 の独立した 8,000,000 refined-node cap も数値付きで記録。MeshBody の O(P*T)、毎回の STL 全体再 hash と Python triangle loop を README に明記。 |
| m2 | `MergedElement` ID を全 gate report の `distance_contract_exemptions` に列挙。重なり内部の band 距離契約の例外と BDIM 未測定を docstring/README に明記。 |
| m4 | joint 規則の翼側と knock-out を `PlateElement`/`MergedElement` に限定。BoxBody と端板の component は knock-out しない。 |
| m5 | -0.0 を 0.0 に正規化。scene 幾何 hash は STL path を除外し SHA を保持。MergedElement、primitive、履歴、policy の ID に共通 validator を使う。ID は `:` を許すので、拒否理由と pair key の区切りは `|`。 |
| m6/n6 | BoxBody continuation は連続だが ray 単調ではなく、球だけが厳密 SDF であることを明記。`_finite` alias を削除。空/ground-only/fixed-only の早期拒否にも scene/state hash と exemption list を入れる。 |
| n3 | 下流種まきは正の world x と符号付き world z offset。上/下の許可 policy は明示引数 `allowed_quadrants`、既定は両方。 |
| n2 | v18 との field 値の 1e-3c 以内という比較を**無変形板のみ**に限定して記載。変形板では零等位面と数値的距離の検査を別に扱う。 |

完全なテスト名と読んだ review/plan/issue のハッシュは `wp06_amendment3_review_checks.json`、実行コマンド・結果・artifact SHA は `wp06_validation.json` に記録する。

## インターフェース（他 WP が使うもの）

公開型は `cfd_gen.scene` の `PlateElement, EndplatePlate, BoxBody, MeshBody, MergedElement, Scene`。事象は `cfd_gen.scene.events`、gate は `cfd_gen.scene.gates`。既存 `cfd_sdf.design.SDFDesignState` と helper は import して使う。

`PlateElement(id,x,z,chord,thickness,angle=0,camber=0,reflex=0,span=1,y=0)` は長さ m、角度 rad。chord は v18 の直線中央長 L で、無変形板の軸方向全長は L+t。2D `(x,z)` と3D `(x,y,z)` は同じ断面を使い、3Dは flat-tip extrusion で合成する。無変形板は厳密 SDF、変形板は v18 の零等位面への固定 multistart 数値射影。一般 BoxBody は勾配正規化した implicit field であり、厳密距離ではない。

`Scene` の union は負=solid、exact zero=fluid の占有規則。`sample(h,dimension=2|3,phase=(px,py,pz),bounds=None)` は2Dを `(nx,1,nz)` に保存し、面積と3D体積を区別する。既定2,000,000 nodeを超えた直接の sampler 呼出しは `SceneSamplingLimit`（`shape`・`node_count`・`max_nodes` を保持）という専用例外で止まり、`evaluate_scene_gates` がそれだけを捕捉して unmeasured 記録へ変える。欠落・不正な入力の例外は握りつぶさない。

`Scene.to_json()` は STL locator を含む transport JSON。`scene_sha256` は mesh の `path` だけを除いた canonical 幾何 payload の SHA256で、STL の検証済み SHA は含む。mesh がなければ transport JSON の SHA と一致する。mesh があればファイルの保存先に依存せず、host/worker で同じ STL bytes を同じ scene と認識する。sampled state の hash は格子・field・mask・scene source hash を別に束縛する。

`merge_candidates(scene, *, max_gap=None, overlap=None)` の既定 δ は pair の小さい厚さの1/4、既定 max_gap は平均厚さ。断面の閉集合間距離と span 区間間距離に分け、8個の決定的な始点から既存 SciPy SLSQP で最近点を数値的に求める。再構成した3D witness の零面残差も検査する。これは変形板での大域最小距離の証明ではなく**提案用**。接触/重なり済みの pair は新規 merge にしない。scene gate は必須で、内部 min union の band 例外も記録する。

`thickness_parameter_floors(scene, *, h, dimension=3, policy)` は可動 plate/merged child ID ごとの t parameter 下限を返す。3D の span 下限は独立であり、t を増やして修復できない。`thickness_knockout_ids(history, minimum_thickness=None, *, tolerance=...)` の row は `checkpoint, thickness` と任意の `parameter_floors`。時点別 snapshot はその row の thickness ID を過不足なく覆い、各時点の床で2連続 checkpoint を判定する。scalar/map fallback は supplied history 全体で床を固定した互換経路。出力は merged child を含む**parameter ID**であり、top-level component の自動削除指示ではない。履歴の geometry 自体の認証は対応する scene 証拠を caller が保持する必要がある。

`downstream_seed_positions(scene, downstream, vertical_offsets, *, allowed_quadrants=("above","below"))` は、正 z が上、負 z が下。offset の0・非有限値、不正 policy は拒否し、許可していない象限は列から除く。`seed_candidates/knockout_candidates/merge_candidates/element_count_designs/classify_change` は有限提案/分類で、CFDや採否や予算消費を行わない。

Julia/WP4 は AutoBody callable 内で同じ断面と射影を直接評価し、SetBody(min,...) で合成する必要がある。変形断面は **2面×6始点×13 Newton反復**。Python の標本格子を三線形補間して代用する契約ではない。WP4 polygon distance は別の近似表面なので、零面・厚化・LE/TE 定義を合わせた別検査が必要。Julia job は編集していない。Float32/AD と GPU cost は未測定。

WaterLily 主線に r_c はない。h は標本化と開発時の厚さ/間隙下限を規定し、変位フィルタ半径ではない。t_min=g_min=4h は開発時の既定で、登録値は RES-00 の梯子で決める。フェーズ B は bounds/刻みを `src/cfd_gen/problem_spec_v3.py` で宣言する別 PR。

## テスト

| 対象 | 実行コマンド/出典 | 結果 |
| --- | --- | --- |
| scene 全体・Birth-0・Birth-1のソフトウェア準備 | `.venv/bin/python -m pytest -q tests/scene -p no:cacheprovider --junitxml=/private/tmp/wp06-amendment3-scene-pytest.xml` | **198 passed、終了0**（terminal 22.33 s、JUnit suite 8.618 s）。 |
| compileall | `.venv/bin/python -m compileall src tests` | 終了0。 |
| band 診断 | `.venv/bin/python docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.py` | 50ケースすべて成功、数値は Amendment 2 と完全一致。source/oracle SHAを更新。 |
| host base | Claude提供 `e3dcdf61`、Metal module ignore | 3482 passed / 74 skipped / 0 failed、failure node `[]`。再取得しない。 |
| 全体 pytest | 下記を1回完走 | **3680 passed / 74 skipped / 0 failed / 0 errors、終了0、934.923 s**。 |
| failure node 集合 | JUnit と `-rf` log | final `[]` / host base `[]`、同一。 |
| source closure | `wp06_amendment3_review_checks.json` | Python130/Julia13の全 source が host base とbyte一致。旧scene directory不在。新コードは `src/cfd_gen/` のみ。 |
| diff check | `git diff --check` | 終了0。 |

```bash
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider \
  --junitxml=/private/tmp/wp06-amendment3-full-pytest.xml
```

全体ログの warnings は7,295件で、前回Amendment 2 のログも7,295件だった。scene単独ログに警告出力はない。

全体を再実行したのは結果側1回のみ。base の再取得、stash、別worktree、CPU profile plugin、歴史テストの例外、freeze/pin の変更を使っていない。full suite は既存のローカルCPU preflight回帰検査を含むが、新sceneのCFD campaign/GPU測定は0。実行ログ/JUnitはgzip(mtime=0)で保存し、圧縮・展開 bytes 両方のSHA256を記録する。開始 commit の前回報告・validation は Git履歴に残り、今回 validation の `previous_amendment_2` にも前回結果を保持する。

WP4 の E2 polygon はこの開始treeでは未実装のため、指定の v18 fallback を使う。**無変形 PlateElement 2枚**の union と v18板2枚は atol=rtol=1e-14 で一致し、要求の1e-3c以内。変形板は field 値の同一性を要求せず、v18と同じ零面と次の band 距離検査で扱う。

c=1 m、t=.1 m、h=.025 m、各条件1700 query、seed=610。band は |computed phi|≤2h。独立にパラメタ化したv18零面（片側50001点＋caps）への最近点距離と比較し、3Dは flat-tip extrusion を検査。gradient errorは2D/3Dの中央値の大きい方。以下は今回 sourceで再生成した結果。

| camber/c (%) | reflex/c (%) | band 点数 2D / 3D | 最大距離差/t 2D | 最大距離差/t 3D | 最大 median gradient error |
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

最大距離差/tは **5.040873270172855e-05**（許容0.02）、最大 median |∇φ|偏差は **2.107147789587316e-12**（許容0.10）。無変形板は非微分集合を避けて |∇φ|=1 を atol=1e-8 で検査する。有限標本・固定t/c,h/cの開発診断であり、全パラメタ空間の距離保証やBDIM資格ではない。

## 仕様からの逸脱と理由

距離の式は review を受けて確定した2026-11-06 bの計画どおり維持した。生の変形v18 implicit値は組合せ振幅で2%tを超えるので、同じ零面への固定射影を使う。内部mergeの min はその例外として明示し、別の距離保証を捏造しない。

nearest-pair merge は既存SciPyの数値最適化を提案用に利用する。解が収束しないときは例外で止め、中央への移動や無根拠の代替へ黙って戻さない。標本化上限だけは gate unmeasured へ変換し、不正入力の fail-closed を保持する。

OpenCode Go MCPは存在しなかった。通常CLIはsandbox外log書込制限で失敗したが、task-local XDG runtimeと既存authへのローカルread-only symlinkで現行catalogを取得できた。実worker呼出しは接続障害後の再試行で **401 api_key_expired**。worker成果は返っていない。global認証/設定や追加課金を変更せず、native workerにeventsとidentity/samplingを分担し、親がgateと統合検証を行った。相互レビューのBoxBody距離根拠と時点別floorの修正を含め、worker出力だけでは完了にしていない。

## 未確認の仮定・既知の限界

- Birth-1は **software preparation** のみ。実primal応答、採択、統計的改善は未検査。qualification flagとshape_update_allowedは変更しない。
- 自動design samplingは2,000,000 nodeでunmeasured。R3は8,000,000 refined nodeでunmeasured。reviewの1.4 m span、h=5 mmの例 `[281,1137,57]` は **18,211,329 node** でcap超過。小さな3D fixtureの成功をMW-01規模のgate利用可能性とは呼ばない。
- MeshBody windingはO(P*T)。P=1,000,000、T=100,000なら **10^11 point/triangle対**。各phi呼出しでSTL全bytesを再read/hashし、boundary生成もPython triangle loop。高速化・3D資源設計はMW-01前の別WP。SRCMAP-02 #53 target signerは依然未資格。
- merged bandの距離例外はBDIM影響未測定。一般BoxBodyは内部continuationがray単調でなく、距離fieldからの一般gap合格/違反判定も未資格。十分なAABB分離と負符号の重なり証拠を別扱いする。
- Julia/GPU/Float32/ADのprojection精度・速度、WaterLily AutoBody/BDIMの実測、4hの物理的妥当性は後続gate。RES-00の登録値をここで決めていない。
- R3・連結・空洞・接触は標本規約に対する検査で、製造/連続位相の保証ではない。既存GEOM03_NO_GO/R3未採用の歴史を変更しない。
- splitは軸方向footprintを保持するwarm startで、体積保存や任意の変形/配置に対するgate合格、空力改善を保証しない。history floor snapshotはcallerが対応するscene evidenceを保持する必要がある。
- 実規則の箱、STL/hash、部品bounds/刻み、ProblemSpec v3、harness v1.2はフェーズB。FSAE/FSG寸法を推測で埋めない。

## Claude／ユーザーへの提案する追記

権威文書本文は未編集。追記案：

> GEOM-S1フェーズAのsource review修正は `cfd_gen.scene` に実装し、scene/全体回帰を検証した。fixed contextとmovable designの制約範囲、最小方向merge、footprint保存split、時点別parameter floorの履歴を明示する。merged bandの距離例外、2M design/8M R3 node cap、MeshBodyのO(P*T)と再hashはMW-01前の既知の限界。Birth-0とBirth-1のsoftware preparationを区別し、physical/BDIM/GPU資格と登録4hは後続gateに残す。

`docs/harness/README.md`への追記案（本文未編集、v1.2未実装）：

> harness v1.2は新規wrapper `campaign_v12.py`等を優先し、path locatorを除いたscene geometry SHAとSTL SHA、明示的Julia引数、checkpointごとの有限event候補、地面と共に移すzを含む3軸位相を扱う。transport JSONのファイルSHAとscene geometry SHAを混同しない。eventは提案記録で、評価・採否・予算は別段階。v1.1 campaignは明示version dispatchで保持し、validate/verifyのbyte不変を検査する。

## 次に要るもの

Claudeがhostで完全一覧だけをstage/commit/pushし、既存PR #82本文を更新する。新規PR/auto-mergeは作成しない。フェーズBは別PRであり、この呼出しでは始めない。MW-01の前に3D資源設計、MeshBody高速化、Julia projection/Float32/AD検査とmerged bandのBDIM影響を別WPで扱う。
