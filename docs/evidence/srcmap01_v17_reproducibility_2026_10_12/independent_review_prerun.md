最終レビューをまとめます。ファイルと、読み取り専用で参照した trimesh と rtree のソースの確認は終わっています。

# SRCMAP-01 最終 pre-run レビュー: **PASS**

レビュー対象の freeze SHA は `45ce00295d4d3ca663c34b78f2c331ec3ac6e39f2819e41e5f22d8cf1dd81482` です。
この SHA と各ファイルのハッシュは、私は再計算していません（実行手段がなく、指示にも従いました）。root の検証結果を前提にしています。内容の整合は読んで確認しました。`prerun_freeze.json` の `diagnose_srcmap01.py` の SHA（`dddb2752…`）は、両 inventory の `diagnostic_source_sha256` と一致しています。

## 修正が必要なブロッカー: なし

初回レビューの P0 と P1 は、コード上すべて解消されています。

| 項目 | 確認結果 |
|---|---|
| P0-1/2 | 凍結 python は実在パスの inventory と一致。`logs`/`diagnostics` は marker より前に作成。preflight(inventory のみ、距離計算なし)は marker より前。 |
| P1-1 | `(env, grid, chunk, order, mode)` の group で判定。v17 current 7 本（A×5 + B200000 + Ccanonical）、v16 の 2 本、G の 2 本を pairwise で Float32/Float64 比較。 |
| P1-2 | 全 run で `runtime_before`/`runtime_after`、mesh、点座標の hash を凍結値と照合。除外は entropy 状態 2 キーのみ。 |
| P1-3 | ENV_DEPENDENT は bundle 限定。個別依存の局在と歴史原因は `UNKNOWN` と出力。 |
| P1-4 | 固定 retry ベクトルで結果が変わると REPRODUCIBLE を阻害。 |
| P1-5 | `classification_inputs` を純関数化し、テストを追加。 |
| 21 job + E 1 本 | 21 job は逐次で、marker により再実行不可。失敗時は停止して UNRESOLVED。 |
| strict 比較 | uint ビット比較で allclose なし。符号付きゼロも差として扱う。 |
| 書き込み | 出力はすべて `'x'` モードか事前の存在チェック付き。凍結入力は計測後に再検査。 |

次の点はソースで確認済みです。

- **`ray_recursive_query_count`:** `ray_triangle.py:10` が `from .ray_util import contains_points` で import 時の関数を束縛しているため、初回呼び出しは wrap されません。ray_util 内の再帰呼び出しだけが module global 経由で wrap され、retry のみが数えられます（初回は `ray_contains_points`）。ray_triangle.py の hash は両環境で同一です。
- **RNG の観測:** 4.4.0 は `np.random.random`、5.1.0 は `util.random_generator()` を使い、どちらも patch 対象です。draw と最終状態を保存する neutrality テストもあります。
- **テスト 8 本:** 合成ケースの期待値を手で追い、すべてコードと一致しました。
- **`known` ノード座標:** genesis v17 の origin (-1,-0.8,-0.6) と spacing 0.025 に一致します。

## 残る証拠スコープの限界（結果の解釈時に明記すること）

1. **有限観測:** REPRODUCIBLE は、観測した run かつ現行 bundle に限った結論です。universal な決定性は主張できません。
2. **固定方向ゲートの空振り:** 3 node が retry 経路に入らなければ、3 本の固定ベクトルは同一結果になり、ゲートは空振りで `False` になります。コードは `actual_retry_draws` が空かどうかを見ていません。REPRODUCIBLE を読む際は、`problem_nodes.json` の draw 件数と、各 run の `random_retry_draw_count` を併記してください。未検証の node の retry 感度は残ります。
3. **ENVIRONMENT_DEPENDENT の範囲:** 現行 bundle と minimum bundle の canonical/200000 条件の差に限ります。G は 2 本だけで、entropy 初期化の RNG 下では偶然一致の可能性が残ります。`local_fixed_direction_sensitive` と併読してください。ENV_DEPENDENT の判定自体は、この感度フラグを見ません。
4. **bundle の交絡:** bundle 差には numpy、scipy、trimesh、rtree、libspatialindex（2.1.0 と 1.9.3）、venv パスが含まれます。個別依存や歴史原因は `UNKNOWN` のままです。
5. **Float64 の基準:** 歴史的な pre-cast Float64 は存在しません。登録 Float32 の昇格値との比較は、Float32 の同一性しか意味しません。
6. **D stage:** 診断のみで、分類には入りません。direct と fallback の不一致から歴史経路は推測できません。

## 運用上の注意（ブロッカーではない、freeze 変更不要）

- **preflight の失敗時:** `*_preflight_inventory.json` が `'x'` で残り、再実行が `FileExistsError` になります。marker は未消費なので、残骸を削除してよいかを事前に決めておいてください。
- **起動環境:** baseline の `locale` は `C/C.UTF-8/C/C/C/C`、`pythonhashseed` は `0`、thread 環境変数と `PYTHONPATH` は null で、いずれも構造 identity に含まれます。baseline 取得時と同じ環境で runner を起動してください。違えば preflight で fail-closed になります。
- **runner の起動:** runner 自身も `trimesh` と `rtree` を import します。凍結した current python で起動してください。
- **marker 後の失敗:** summarize で失敗しても、各 job の JSON と NPZ は残ります。ただし marker があるため runner は再実行できません。この場合の再集計手順は、新たなレビューを経て決めてください。
- **`known_problem_nodes_in_query`:** v17 の座標をハードコードしているため、v16 では空になります。これはメタデータのみで、分類には影響しません。

実行して問題ありません。実行は、承認した freeze SHA を `--approved-freeze-sha256` に渡して 1 回だけ行ってください。

Root disposition: all initial blocking findings were addressed before mapping. The two frozen environmental bundles are already authorized by the user; no individual dependency or historical cause will be inferred. A preflight failure is preserved and stops the attempt; no deletion or retry is authorized. Float64 comparisons to promoted registered Float32 describe numerical differences only; run-to-run Float64 bit comparisons independently test repeated outputs.
