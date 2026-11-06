# WP6 GEOM-S1 フェーズ A 報告（Amendment 2）

## 状態

**DONE（フェーズ A：scene と gate の移設・再検証完了）**。開始点は `9aa93169155501af0ed9392d376dad5ee5f543e9`、branch は `feat/gen01-w1-06-geom-s1`。`cfd_sdf.scene` を `cfd_gen.scene` へ移し、歴史的 source closure への追加を取り除いた。今回の全体 pytest の失敗 node 集合は `[]` で、Claude が host で取得した base の `[]` と同一。フェーズ B は未着手。

この状態は作業ツリー上のソフトウェア受け入れ完了を表す。Amendment 2 §3 に従い、Codex は `git mv`、`git add`、commit、push、index/ref 更新、PR 編集を行っていない。下記のファイルを Claude が host で commit・push し、既存 Draft PR [#82](https://github.com/ramhachi/CFD_opt_sdf/pull/82) の本文更新・ready 化を行う。今回、remote の PR 状態は変更していない。

## 作ったもの（commit すべき完全な一覧）

移動はファイルシステムの `mv` で実施した。通常 index は変更していないため、host が stage するまで Git 上では削除と未追跡追加に見える。

| 区分 | 完全なパスと内容 |
| --- | --- |
| 移動 | `src/cfd_sdf/scene/__init__.py` → `src/cfd_gen/scene/__init__.py`：公開型。内容は byte 一致。 |
| 移動 | `src/cfd_sdf/scene/primitives.py` → `src/cfd_gen/scene/primitives.py`：板・端板・箱・固定 STL。内容は byte 一致。 |
| 移動・変更 | `src/cfd_sdf/scene/scene.py` → `src/cfd_gen/scene/scene.py`：union、lattice、JSON/hash。既存 `SDFDesignState` の import 1 行だけ絶対 import に変更。 |
| 移動 | `src/cfd_sdf/scene/events.py` → `src/cfd_gen/scene/events.py`：seed/knock-out/merge、履歴、分割 warm start。内容は byte 一致。 |
| 移動・変更 | `src/cfd_sdf/scene/gates.py` → `src/cfd_gen/scene/gates.py`：scene gate。既存 helper/state の import 2 行だけ絶対 import に変更。 |
| 新規 | `src/cfd_gen/__init__.py`：GEN-01 top-level package の最小定義。 |
| 新規 | `src/cfd_gen/README.md`：歴史 freeze の列挙対象と、GEN-01 新コードの Python/Julia 配置を 3 行で記載。 |
| 変更 | `tests/scene/test_birth.py`：import 先だけを `cfd_gen.scene` へ変更。 |
| 変更 | `tests/scene/test_events.py`：import 先だけを変更。 |
| 変更 | `tests/scene/test_gates.py`：import 先だけを変更。 |
| 変更 | `tests/scene/test_primitives.py`：import 先だけを変更。 |
| 変更 | `tests/scene/test_scene.py`：import 先だけを変更。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.py`：import と診断対象の source path だけを変更。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.json`：新しい source path/hash で再生成。50 ケースの数値は前回と完全一致。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_design.md`：移設前の Amendment 2 addendum と、現在の指示と履歴の区別。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_report.md`：本報告。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_validation.json`：今回のコマンド、終了値、failure node、artifact/source SHA256、host base の出典、delivery 境界。前回の JSON は履歴として保持。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_amendment2_source_closure.json`：移動前後の SHA256、import 以外の不変性、旧 directory 不在、既存 Python 130 / Julia 13 source の host base との一致、歴史 closure の照合。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment2-compileall.log.gz`：今回の compileall 完走ログ。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment2-closure-pytest.log.gz`：closure 関連 4 node の完走ログ。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment2-closure-pytest.xml.gz`：同 JUnit。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment2-full-pytest.log.gz`：指定した全体 pytest 1 回分の完走ログ。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment2-full-pytest.xml.gz`：同 JUnit。 |

`src/cfd_sdf/scene/` は `__pycache__` を含め存在しない。旧 namespace の shim は置いていない。`pyproject.toml` は既存の `setuptools.packages.find.where = ["src"]` で新 package を列挙できるため変更不要。

前回の `wp06_attempt1_blocked/`、`wp06_source_closure_preflight.py/.json`、`wp06_cpu_only_pytest.py` と旧 gzip は変更していない。旧 source-closure reproducer は attempt 2 の当時の tree に対する履歴であり、今回の受け入れコマンドではない。今回 CPU profile plugin は使っていない。

## インターフェース（他 WP が使うもの）

公開 import は `from cfd_gen.scene import PlateElement, EndplatePlate, BoxBody, MeshBody, MergedElement, Scene`。事象は `cfd_gen.scene.events`、gate は `cfd_gen.scene.gates` から import する。既存 state と gate helper は `cfd_sdf.design` から再利用する。

`PlateElement(id,x,z,chord,thickness,angle=0,camber=0,reflex=0,span=1,y=0)` は長さ m・角度 rad。chord は v18 の中央直線長 L で、無変形 stadium の全長は L+t。2D `(x,z)` と 3D `(x,y,z)` は同じ断面を使い、3D は flat-tip extrusion で合成する。無変形の板は厳密な SDF。変形時は v18 の零等位面を保つ fixed multistart polynomial projection の数値的な距離近似であり、一般形の BoxBody も勾配正規化した implicit field である。厳密 SDF の主張と区別する。

`Scene(components,fixed=(),ground=None)` は `phi`、`labels`、`sample(h,dimension=2|3,phase=(px,py,pz),bounds=None)`、`label_grid`、canonical `to_json/from_json`、`scene_sha256` を提供する。JSON schema_version=1、field_contract=`geom_s1_amendment1_v1` は移設前と同じ。scene hash と sampled state hash は別。2D は既存 `SDFDesignState` の `(nx,1,nz)` に格納し、面積と 3D 体積を区別する。

`seed_candidates`、`knockout_candidates`、`merge_candidates`、`downstream_seed_positions`、`thickness_knockout_ids`、`element_count_designs`、`classify_change` は有限の提案・分類だけを返す。`evaluate_scene_gates(...,policy=SceneGatePolicy(...))` は厚さ、gap、solid/void R3、連結、閉空洞、端板接合、出典付き規則箱、clearance、mask/root を判定し、全拒否理由を返す。未測定も受け入れを阻む。CFD 評価回数・予算消費は 0。

Julia/WP4 には各部品の種類・パラメタと JSON SHA を渡し、`AutoBody` callable 内で同じ断面式・projection・extrusion を直接評価し、`SetBody(min,...)` で合成する。Python の格子標本を GPU の三線形補間に置き換える契約ではない。WP4 の polygon SDF は近似した別表面なので、同じ零等位面・厚化・LE/TE 定義をそろえた parity が別途必要。Julia job 自体は変更していない。

WaterLily 主線に `r_c` はない（Amendment 1）。h は格子と開発時の幾何下限を規定し、節点変位フィルタの半径ではない。フェーズ B では部品ごとの parameter bounds と刻みを宣言する。t_min=g_min=4h は開発時の既定であり、登録値は RES-00 の梯子で決める。

## テスト（今回の結果）

| 対象 | コマンド・出典 | 結果 |
| --- | --- | --- |
| scene / Birth-0 / Birth-1 のソフトウェア準備 | `.venv/bin/python -m pytest -q tests/scene -p no:cacheprovider` | 86 passed、20.71 s（移設 worker の実行結果）。全体 JUnit でも scene 86 件の成功を確認。 |
| 旧 blocker に関連した 4 node | GRID-02 evidence / prereg 3 件、LOWDIM-03 prereg 1 件。完全な node ID は validation JSON / JUnit に保存 | 4 passed、60.58 s、failure node `[]`。 |
| compileall | `.venv/bin/python -m compileall src tests` | 終了 0。 |
| host base | Claude 提供：`e3dcdf61`、Metal module を ignore | 3482 passed / 74 skipped / 0 failed、failure node `[]`。今回 base の再取得なし。 |
| 結果側の全体 pytest | 下記コマンドを 1 回完走 | 3568 passed / 74 skipped / 0 failed / 0 errors、終了 0、1035.366 s。 |
| failure node 集合 | 全体 JUnit と `-rf` の結果 | base `[]` / final `[]`、同一。 |
| source closure | `wp06_amendment2_source_closure.json` | 移動 source 5 件と tests 5 件の許可した import 差分だけ。既存 Python 130 / Julia 13 source の一覧と bytes は host base と一致。GRID-02 登録検証 PASS。 |
| whitespace | `git diff --check` | 終了 0。新規 text の行末も検査。 |

```bash
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider \
  --junitxml=/private/tmp/wp06-amendment2-full-pytest.xml
```

今回の全体 run は他の module を ignore せず、CPU profile plugin、歴史テストの例外、pin/freeze の変更を使わない。base の再実行、stash、追加 worktree は不要として行っていない。full suite には既存 Julia CPU preflight の回帰検査を含むが、新しい scene の CFD campaign・GPU 測定は 0。ログ/JUnit は gzip（mtime=0）で保存し、圧縮・展開 bytes 両方の SHA256 を validation JSON に記録した。

GRID-02 の不足 5 path は移設で消え、新 package は歴史 closure の列挙対象外。LOWDIM-03 の元 freeze には WP6 より前から存在する 4 source の差があるため、「その元 freeze に現在の全 source が含まれる」とは主張しない。今回の記録は既存 reader・列挙対象・該当 bytes が host base と一致し、新たな不足がないことと、変更していない実テストの成功を確認する。

WP4 の E2 polygon SDF はこの開始 tree に未実装のため、指定された v18 fallback を維持。`PlateElement` 2 枚の union と v18 の 2 枚板は `atol=rtol=1e-14` の比較に合格し、要求の 1e-3c 以内を満たす。

距離 band 診断は次で再現する。

```bash
.venv/bin/python docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.py
```

c=1 m、t=.1 m、h=.025 m、各条件 1700 query、seed=610。band は |computed phi|≤2h。v18 零等位面を独立にパラメタ化し、片側 50001 点と cap の密な点群への最近距離と比較する。3D 対照は断面距離の flat-tip extrusion。表の gradient error は 2D/3D の中央値の大きい方。数値表は今回再生成した 50 ケースから得ており、前回と完全一致する。

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

最大距離差/t は 5.04087327017285e-05（許容 0.02）、最大 median |∇φ| 偏差は 2.10714778958732e-12（許容 0.10）。無変形板の |∇φ|=1 は非微分集合を避け、atol=1e-8 で検査。これは有限の標本点・固定 t/c と h/c に対する開発診断であり、全厚さ・全パラメタ空間の距離保証ではない。

前回の検証値は今回と混同せず、`wp06_validation.json` の `previous_attempt_2` に保持する。前回 CPU profile base は 3482 passed / 80 skipped / 0 failed、final は 3564 passed / 80 skipped / 4 failed、commit 後の該当 4 node 再検査は 2 passed / 2 failed だった。今回の全体 run は明示 module ignore に統一しており、旧 80 skip の profile は使っていない。

## 仕様からの逸脱と理由

Amendment 2 が指定した top-level package へ移設した。移設前の parent-relative `..design` はそのままでは `cfd_gen.design` を探すため、3 行だけ既存 `cfd_sdf.design` の絶対 import に変えた。helper の複製、旧 namespace の alias、歴史 closure の例外は追加していない。scene テストの内容・閾値は変更していない。

距離の扱いは Amendment 1 と前回実装を維持した。生の変形 v18 field は振幅上限の併用で 2%t を超えるため、同じ零等位面の projection を使う。一般 superellipsoid は厳密 SDF と呼ばず一次近似と記す。`min_c phi_c` は union の符号を保つが、重なり内部の真の最短距離とは限らない。独立可動要素の重なりと、宣言した merge/端板接合は gate で区別する。

OpenCode Go MCP は利用不可。通常 CLI catalog は外部 log の書込制限で失敗し、書込可能な一時 XDG 経路は `Provider not found: opencode-go`。native Codex worker が限定した移設を行い、親が source bytes・差分・検証を確認した。認証や global config、追加課金は変更していない。

## 未確認の仮定・主張の上限

- actual primal の Birth-1 は未資格。今回の Birth-1 は要素数・消えた ID・成分数の変化を分類するソフトウェア準備である。
- 新 scene の Julia/GPU projection、AD、Float32 parity、速度、AutoBody/BDIM の実際の測定は後続 WP。今回その solver を実行していない。
- 4h は開発既定。登録する厚さ/gap と配置位相に対する応答は RES-00 の梯子で決める。
- R3・連結・空洞・接触は宣言した標本規約での検査で、任意の連続形状や製造の保証ではない。R3 再利用は GEOM03_NO_GO / R3 未採用の歴史を改定しない。MeshBody の合成検証も SRCMAP-02 #53 の target signer を適格化しない。
- 実規則の箱、固定 STL/hash、部品の bounds/刻み、v3 宣言、harness v1.2 はフェーズ B。FSAE/FSG 寸法を推測で埋めず、v2 の CFD domain を規則箱の代わりにしていない。
- 分割 warm start は候補の列であり、体積保存や gate 合格、空力的な改善を保証しない。全 qualification flags と `shape_update_allowed` は変更していない。

## Claude／ユーザーへの提案する追記

権威文書の本文は編集していない。追記案：

> GEOM-S1 フェーズ A の scene・離散事象提案・scene gate は `cfd_gen.scene` に実装し、solver-free software/contract として検証済み。historical freeze の列挙対象である `src/cfd_sdf` / `julia/CFDSDFWaterLily/src` には GEN-01 新コードを置かない。Birth-0 と Birth-1 のソフトウェア準備を区別し、actual primal の Birth-1・BDIM 解像度・GPU parity は後続 gate に残す。4h は開発既定で、登録は RES-00。r_c は使わず部品 parameter の bounds と刻みを v3 で宣言する。

`docs/harness/README.md` への追記案（本文は未編集、v1.2 は未実装）：

> harness v1.2 は新しい `campaign_v12.py` 等の wrapper を優先し、scene JSON の SHA と明示的な Julia job 引数に結び付く scene state、checkpoint ごとの有限 event 候補、地面と共に移す z を含む 3 軸位相を扱う。event は提案記録であり、評価・採否・予算消費は別段階。従来 v1.1 campaign は明示的な version dispatch で保持し、validate/verify の byte 不変を検証する。暗黙に移行しない。

## 次に要るもの

Claude が host で上記一覧だけを stage・commit・push し、PR #82 を更新して ready にする。新規 PR は作らず、auto-merge は有効にしない。フェーズ B はその後の別 PR とし、ProblemSpec v3 は `src/cfd_gen/problem_spec_v3.py` に置く。今回の呼び出しはフェーズ A の移設と再検証までで完了した。
