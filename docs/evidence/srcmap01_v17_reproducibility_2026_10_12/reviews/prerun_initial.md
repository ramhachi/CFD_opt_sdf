# SRCMAP-01 pre-run レビュー: **NEEDS_FIX**

実行、ハッシュ計算、変更はしていません。Read/Grep/Glob で確認した範囲です。凍結 SHA が現ファイルと一致するかは未検証です。

## P0: 修正するまで実行不可

**P0-1. 凍結 job の `python` が棚卸しの環境と一致せず、worktree の `.venv` は実体がない可能性が高い。**
- `prerun_freeze.json:105` ほか A/B/C/D の 19 job は `/Users/sota/.codex/worktrees/p22-v17-volume-audit/CFD2026_09/.venv/bin/python` を指しています。
- 一方 `runtime_inventory.json:172` の `python_executable` と `historical_runtime_audit.json` は `/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python` です。
- worktree 側の `.venv` には `bin/*` も `*.dist-info/METADATA` も、numpy/scipy/trimesh/rtree の `__init__.py` も Glob で見つかりませんでした。シンボリックリンクや隠しファイルの扱いで見落としている可能性は残ります。`ls` と `python -c "import trimesh"` で確認してください。
- この状態だと `run_srcmap01.py:29` で job 1 が失敗します。`execution_started.json` はそれより前の `run_srcmap01.py:20` で書かれているため、21 job の枠を 1 回使い切って `UNRESOLVED` で終わります。
- 修正:
  - job の python を、実在して inventory と同一の環境に揃える。
  - 各 worker の `inventory()['python_executable']` と主要 module path が、凍結 inventory と一致することを実行時に検査する。
  - `execution_started.json` は、この検査を含む preflight（幾何計算なし）の後に書く。

**P0-2. 出力ディレクトリが作られない。**
- `run_srcmap01.py:29` は `E/'logs'/...` を `open('x')` しますが、`logs` を作る処理がありません。`diagnose_srcmap01.py:225` の `np.savez_compressed` は `diagnostics/` が必要です。`diagnostics/` を作る `write_json` の `mkdir` は、その後の 226 行目です。
- 空ディレクトリは Glob に出ないため、すでに存在するかは確認できていません。
- 存在しなければ、全計算後または job 1 で失敗し、marker も消費されます。
- 修正: marker を書く前に、`logs` と `diagnostics` を `mkdir(parents=True, exist_ok=True)` で作成する。

## P1: 原因主張を無効にしうる（凍結前に修正）

**P1-1. 同一環境の非決定性判定が A の組だけで、同一条件の他 run を無視している。**
- `run_srcmap01.py:51` の `pairwise` と 67 行目の `same` は、A 群だけを比較しています。
- `B_chunk_200000` と `C_canonical` は A_v17 と同一条件（chunk 200000、canonical、production）です。この 2 job が A と bit 違いを示しても、`perturb=False` になるだけで、凍結された優先順位が要求する `ALGORITHM_NONDETERMINISTIC` になりません（`UNRESOLVED` になる）。
- G の 2 run が互いに違う場合（`altstable=False`）も、環境 B 内の同一条件での非決定性が無視されます。`same` と `exact` と `perturb` が真なら `REPRODUCIBLE` が出ます。
- 修正: 「同一条件の identity group」をキー（env, grid, chunk, order, mode）で定義し、各 group 内で Float32/Float64 の bit 一致を判定する。G 内の不一致は非決定性証拠として扱う。

**P1-2. 実行ごとの構造的 identity 検査の仕様（author が追加中の項目）。**

追加するなら、次の点を満たす必要があります。
- **比較対象:**
  - python の sha、各 module の version/path/sha、RECORD sha、libspatialindex の sha、numpy の BLAS config。
  - `production_source_sha256`、`backend_sources`、診断スクリプトと `sdf.py` の実行時 sha。
  - mesh の vertices/faces の sha、点座標 sha、thread 環境変数、`PYTHONHASHSEED`、`PYTHONPATH`。
  - `runtime_before` と `runtime_after` の一致。
- **除外するもの:** `numpy_legacy_random_state_sha256`、`trimesh_entropy_random_state`、経過時間は、エントロピー初期化により run ごとに変わるのが正常です。これらを含めると全 run が不一致になります。除外リストは凍結してください。
- **比較単位は環境ごと。** A と G の間で mesh hash や module 構成が違うのは、環境依存の局在候補として報告すべき事実であり、「identity 違反」ではありません。
- **identity 違反の扱い:** `NONDETERMINISTIC` や `ENVIRONMENT_DEPENDENT` を主張せず `UNRESOLVED` にし、再実行しない。その run を除外して選別することもしない。
- **path signature:** try 経路/fallback 経路、例外、random 引数の有無を run ごとに記録し比較する。経路が run 間で違うなら、その事実を分けて記録する。
- 検査コードを足すとスクリプトの hash が変わります。freeze の再生成と独立 pre-review のやり直しが必要です。

**P1-3. `ENVIRONMENT_DEPENDENT` が「局在」の要件を満たさない。**
- `run_srcmap01.py:75` は、A と G の一致状況が異なることだけで成立します。
- G は numpy 1.26.4/2.5.2、scipy 1.11.4/1.18.1、trimesh 4.4.0/5.1.0、rtree 1.2.0/1.4.1 を同時に変えています。
- trimesh 4.4.0 は `np.random.random`、5.1.0 は `util.random_generator` を使う別コードです。個別の dependency には局在できません。
- 修正: `classification.json` に A/G の差分集合と `localization: "not_localized_bundle_of_N_differences"` を出力する。ラベルは「環境束依存」に限定する。差分が 2 件以上のときにこのラベルを許すかどうかは、凍結前にユーザー判断が必要です。個人的には、許さず `UNRESOLVED` に留めることを推奨します。
- 歴史的な Oct11/Oct12 の差も推測しないこと。`historical_cause_resolved=False` の記述は妥当です。

**P1-4. `REPRODUCIBLE` が、非シード乱数の依存を観測しても出る。**
- `trimesh.util._RANDOM_DEFAULT` はエントロピー初期化で、ray の retry 方向に使われます（`ray_util.py:107`）。
- `local_nodes()`（stage E）で固定ベクトルにより 3 node の符号が変わっても、`classify` はそれを一切参照しません。A が 5/5 一致すれば `REPRODUCIBLE` になります。
- 5 run では、低確率の retry 依存を除外できません。
- 修正: 次のいずれか、または両方を凍結前に決める。
  - E の「固定 retry ベクトルで結果が変わる」を `REPRODUCIBLE` の阻害条件にする。
  - `classification.json` に、各 run の retry draw 件数、3 node が ray 経路に入ったか、観測 run 数を出し、「観測した run 内でのみ不変」と限定する。
- 少数 run での再現は証明ではなく、観測です。この限定は必須です。

**P1-5. classification の配線にテストがない。**
- `tests/test_srcmap01_diagnostic.py:50` は `classify()` 単体のみです。
- `summarize()` の `same/exact/perturb/environment` の合成ロジックは未テストです。P1-1 や P1-4 のような欠陥はそこにあります。
- 修正: 判定部を pure function に切り出し、合成 record で次をテストする。
  - G の不一致。
  - B/C の同一条件との不一致。
  - A が全 run で不一致だが安定している場合。
  - 経路が混在する場合。

## P2: 品質、証拠の弱さ

- **RNG 観測のテストがない（要件）。** instrumentation 自体は中立に見えます。`RandomProxy` は state を読むだけで消費せず、`np.random.random` も元関数を呼ぶだけです。ただし、プロキシあり/なしで同じ draw 列と同じ最終 state になることのテストが必要です。
- **`wrapper` は instrumentation の失敗で挙動を変えうる。**
  - `diagnose_srcmap01.py:97-103` の `args[-1]` 参照とハッシュ計算は、`try` の外にあります。
  - ここで例外が起きると、`signed_distance` の `except Exception` に拾われ、黙って fallback に切り替わります。
  - 修正: 準備処理を try で囲み、失敗は記録に残して本体は必ず呼ぶ。
- **ray の retry の追跡が不足。**
  - `ray_util.contains_points` の再帰呼び出しは wrap されていません。3 node が broken 集合に入ったかが分からず、draw が誰に効いたかを帰属できません。
  - 帰属を主張するなら、`ray_util.contains_points` も wrap する必要があります。この関数は keyword 呼び出しがありうるので、`args[-1]` は使えません。
- **`rtree_batch_intersection`（`diagnose_srcmap01.py:142`）の `known_problem_nodes_in_query` は無意味。** 引数が box の mins/maxs だからです。害はありませんが、誤読を招きます。
- **Stage E は凍結した python を使っていない。**
  - `run_srcmap01.py:34` は `sys.executable` を使うため、A の環境と一致しない可能性があります。
  - `diagnose_srcmap01.py:254,255` の nominal な `signed_distance` と `contains` では、retry draw を記録していません。3 node の原因主張にはこの記録が必要です。
- **retained field の不変性は開始前にしか検査していません。**
  - `load_inputs` と `run_srcmap01.py:18` の SHA 検査は、開始前と各 worker の読み込み時だけです。
  - 全 job 終了後、`classification.json` を書く前に、再度 SHA を検査して結果に残してください。
  - 書き込み側は `write_json` の `'x'` モードと `refuse overwrite` があり、概ね問題ありません。ただし `np.savez_compressed` は上書きを拒否しません。事前チェックはありますが、`diagnostics/*_difference.npz`（`run_srcmap01.py:61`）には事前チェックがありません。
- **`perturb` が Float32 のみ。** B/C を A canonical と Float64 でも pairwise 比較しておくと、診断として有用です（任意）。
- `E` の job は 21 件に含まれません。Stage E は別枠の 1 回実行である点を、plan に明記してください。

## 要件ごとの結果

| 項目 | 結果 |
|---|---|
| strict 比較（bit/uint、allclose 不使用、signed-zero 区別） | PASS。`strict()`（`diagnose_srcmap01.py:47`）と `classify` に tolerance はない。 |
| 21 job 固定、retry なし | PASS。A 7 + B 6 + C 3 + D 3 + G 2 = 21、1 回限りの marker、失敗で停止。ただし P0-1 と P0-2 の preflight が必要。 |
| 結果を見た後の条件追加がない | PASS。 |
| 実装との整合（grid/points/chunk/cast） | PASS。genesis の `resample` と同一（`np.arange` 方式、float32 cast、chunk 200000）。 |
| fallback の instrumentation | 概ね PASS。try 成否、例外、`_contains_safe`、`mesh.contains` の失敗を記録する。ただし P2 の wrapper の堅牢性が残る。 |
| 歴史経路の推測 | PASS。`historical_path_proven` は常に False で、現在の direct/fallback の差から推測していない。 |
| production の不変 | PASS（コード上）。`sdf.signed_distance` を無改変で呼ぶ。 |
| 同一環境の非決定性の証拠 | NEEDS_FIX（P1-1、P1-2） |
| 環境依存の局在 | NEEDS_FIX（P1-3） |
| RNG 観測 | 実装は PASS、テストと帰属は P2 |

## 限界
- 何も実行していないため、凍結ファイルの SHA 一致、各 test の合否、`.venv` の実在は検証できていません。
- `.venv` の有無は Glob のみでの判断です。
- 5 run または 7 run の一致は、再現性の証明にはなりません。

修正後は、スクリプトの hash が変わるため freeze を再生成し、独立 pre-review を再度行ってください。
