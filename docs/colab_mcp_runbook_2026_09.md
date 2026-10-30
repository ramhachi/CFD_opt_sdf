# Colab MCP 操作手順（Codex / CFD2026_09）

更新: 2026-09-27。これは操作手順であり、実験の実行順・判定基準は
[`phase_plan.md`](phase_plan.md) と各 `docs/evidence/*_criteria_*.json` が決める。
Colab の接続確認だけで GPU 実行や研究上のゲート通過を主張しない。

## 1. 接続構成を先に理解する

- このユーザー環境では `~/.codex/config.toml` の `mcp_servers.colab-mcp` が
  `~/.codex/mcp/colab_codex_adapter.py` を起動する。アダプターは
  [googlecolab/colab-mcp](https://github.com/googlecolab/colab-mcp) を中継する。
- 上流サーバーは Colab ブラウザー接続後にツール一覧を更新する。Codex には
  固定の `colab_connect_session`、`colab_list_tools`、`colab_call_tool` を出し、
  実際のノートブック操作名と引数は `colab_list_tools` から取得する。
- `colab_connect_session` の `true` は **Colab の画面との接続成功** だけを示す。
  ノートブックの Python ランタイム、T4、Julia、リポジトリは別に確認する。
- 接続処理は未接続時に一時的な `scratchpad` ノートブックを開く。
  一つの作業では一つの MCP クライアント接続を保ち、ツール呼び出しごとに
  `uvx` やアダプターを再起動しない。既存セルを読む前に上書きしない。

2026-09-27 の実測では、上流ツールに `get_cells`、`add_code_cell`、
`update_cell`、`run_code_cell` などがあった。ツール一覧は固定とみなさない。
同日の新規 `scratchpad` は Julia 1.12.6 の **CPU** ランタイムで、
`nvidia-smi` は存在しなかった。これはオペレーター環境の観測であり、
W1g の GPU 測定ではない。

## 2. Codex から一つのノートブックへ接続する

1. この会話の使用可能ツールに上記の固定3ツールがあるか確認する。
   `config.toml` に登録されていても、設定前から開いていた会話には
   ツールが反映されないことがある。その場合は Codex アプリを再起動して
   新しい会話で再確認する。`opencode_go` や OpenCode CLI を代用しない
   （ユーザー指定の休止期間は 2026-10-20 まで）。
2. セッションが未接続のときだけ `colab_connect_session({})` を一度呼ぶ。
   戻り値が `true` でなければ先へ進まない。
3. `colab_list_tools({})` を呼び、現在の上流ツール名と `inputSchema` を読む。
   接続前に覚えた名前・引数で呼ばない。
4. `colab_call_tool` から `get_cells` を呼び、対象ノートブックのセルを確認する。
   既存の内容がある場合は新しいセルを追加し、無関係なセルを変更しない。
5. コードを実行するときは、`update_cell` または `add_code_cell` の成功後に
   対象 `cellId` を `run_code_cell` に渡す。戻り値の `outputs` とエラーを読む。

上流ツールを呼ぶ形の例（`cellId` は `get_cells` の値を使う）:

```json
{"name":"get_cells","arguments":{"includeOutputs":false}}
{"name":"update_cell","arguments":{"cellId":"<実際のID>","content":"<Pythonコード>"}}
{"name":"run_code_cell","arguments":{"cellId":"<実際のID>"}}
```

この会話で固定3ツールが見えない場合の端末経路は、**一つの長寿命な**
`fastmcp.Client(StdioTransport(...))` を使って同じ3ツールを呼ぶ場合に限る。
`Client` の `async with` をツール呼び出しごとに抜けると、上流接続も閉じる。
短命なクライアントを反復起動して `scratchpad` を増やさない。
Codex で固定3ツールが見える会話では端末経路を使わない。

端末経路を使う場合は、リポジトリ直下から次のヘルパーを**一度だけ**起動し、
同じプロセスの標準入力へ JSON を1行ずつ渡す。`connect` は未接続時に一度だけ
Colab ブラウザーを開く。`tools` の返す `inputSchema` を読んでから `call` を作る。
引数名は上流のバージョンで変わり得るので、下の `get_cells` は例である。

```bash
uvx --index https://pypi.org/simple --with fastmcp==2.14.5 \
  python scripts/colab_mcp_session.py
```

```jsonl
{"op":"connect"}
{"op":"tools"}
{"op":"call","name":"get_cells","arguments":{"includeOutputs":false}}
{"op":"close"}
```

`connect` を反復入力しても同一プロセスでは接続を再利用する。終了時は `close`、
または標準入力の EOF を使う。ヘルパーは起動だけでは Colab に接続せず、
`call` に `run_code_cell` を渡さない限りセルを実行しない。セルの source や
outputs は `call` の応答に含まれるため、機密値を含むノートブックの応答を
そのままログやコミットに保存しない。

## 3. 計算ランタイムの事前確認

上流のセル操作ツール一覧にはランタイム種別の切替ツールがない。
T4 が必要なときは Colab 画面の **ランタイム → ランタイムのタイプを変更 → T4 GPU**
で選択して接続する。画面を制御できない場合は、ユーザーにこの操作だけを依頼する。
CPU 上で GPU 実験を始めたり、接続成功を T4 の証拠にしたりしない。

実験前にノートブックの Python セルで最小限の情報を確認する:

```python
import json, shutil, subprocess

def output(args):
    return subprocess.run(args, check=True, capture_output=True,
                          text=True, timeout=20).stdout.strip()

assert shutil.which("nvidia-smi"), "GPU のないランタイム。T4 を選択して再接続する"
print("RUNTIME_PREFLIGHT=" + json.dumps({
    "gpu": output(["nvidia-smi", "--query-gpu=name,uuid,memory.total,driver_version",
                   "--format=csv,noheader"]),
    "julia": output(["julia", "--version"]),
}, sort_keys=True))
```

W1g では `Tesla T4` の表示だけでは足りない。
[`sdf_native_w1g_gpu_gridsdf_criteria_2026_09.json`](evidence/sdf_native_w1g_gpu_gridsdf_criteria_2026_09.json)
の G9 と `scripts/t4_backend_identity.py` が、W0b に登録された GPU UUID、
バージョン、T4 `Project.toml` / `Manifest.toml` の SHA-256 を照合する。
Colab が別の T4 を割り当てて UUID が変わった場合、旧 W0b の証拠を編集せず
**新しい W0b バックエンド記録、W1g criteria ラウンド、対応する recorder を
測定前に登録してから**測定する。G9 を緩めて通さない。

## 4. このリポジトリで W1g を実行するとき

1. ローカルで `git status --short --branch` と `git rev-parse HEAD` を確認する。
   上記 W1g criteria と `.sha256`、W0b/W2a の証拠を確認し、実験に使う
   **正確なコミット SHA** を決める。未コミットの実装を測定に混ぜない。
2. T4 ランタイムの新しい作業ディレクトリに公開リポジトリ
   `https://github.com/ramhachi/CFD_opt_sdf.git` を clone し、決めたコミットを
   detached HEAD で checkout する。既存の dirty な clone は上書きしない。
   `git rev-parse HEAD`、`git status --porcelain` を確認する。
3. `julia/CFDSDFWaterLilyT4/Project.toml` と `Manifest.toml` の SHA-256 を
   criteria と照合し、同じ環境で `Pkg.instantiate()` する。解決後もハッシュを
   再確認する。Julia/CUDA/WaterLily のバージョンと GPU 同一性も確認する。
4. 条件がそろった場合だけ、登録済みのコマンドを実行する:

   ```bash
   julia --project=julia/CFDSDFWaterLilyT4 \
     scripts/w1g_gpu_geometry_fixture.jl gpu \
     work/sdf_native_w1g_gpu_gridsdf_2026_09/fixture
   ```

   Colab の Python セルから `subprocess.run` を使い、`stdout` と `stderr` を
   同じファイルへ流し、終了コードを別に記録する。`W1G_SUMMARY_BEGIN`、
   `W1G_SUMMARY_END`、`W1G_FIXTURE_DONE gpu` を含む**完全な** stdout を
   ローカルの `work/sdf_native_w1g_gpu_gridsdf_2026_09/run_stdout.txt` に
   回収する。現行の上流ツールにはファイル取得ツールがないため、少量の
   ログなら別セルから base64 で返し、長ければオフセットを指定して分割取得する。
   Colab 側のバイト長・SHA-256 とローカルで復元した値を照合する。
   出力が途切れた場合は判定しない。
5. ローカルで `scripts/register_sdf_native_w1g_gpu_gridsdf_2026_09.py`
   を実行する。9ゲートと backend identity が全て通った場合だけ不変の
   `docs/evidence/sdf_native_w1g_gpu_gridsdf_2026_09.json` と SHA sidecar が
   作成される。失敗時は生ログを残し、閾値を測定後に変更しない。

W1g は GPU 上の GridSDF **幾何評価**を判定する。CFD 時間積分・力、
W2-T4b、W2b、勾配、形状更新は W1g だけで認定しない。

## 5. トラブル時の停止条件

| 観測 | 処置 |
| --- | --- |
| Codex に固定3ツールがない | 設定とアダプターの所在を確認し、アプリ再起動後の新しい会話でツールを再確認する。現在の会話で有効と推測しない。 |
| `colab_connect_session` が `false` | Colab 画面との接続を直す。ノートブックコードを実行しない。 |
| `true` だが `nvidia-smi` がない | ブラウザー接続だけが成功した CPU ランタイム。T4 を選択して事前確認をやり直す。 |
| GPU UUID・バージョン・Manifest が W0b と違う | 別バックエンドとして停止し、変更前の登録基準と証拠を保全する。 |
| `run_code_cell` がタイムアウト／切断 | Colab 側の実行状態とログを調べる。成功とみなさず、盲目的に同じジョブを再投入しない。 |
| フィクスチャまたはレコーダーが失敗 | stdout と終了コードを保全する。証拠を書かず、原因を調べてから新しい測定ラウンドを計画する。 |

Colab 接続 URL の `mcpProxyToken` とポートは一時接続情報である。
URL 全体をログ、コミット、報告へコピーしない。認証情報をノートブックへ
貼り付けない。GitHub の clone には公開 URL を使う。

## 6. 2026-09-27 の実行記録と再利用する確認コマンド

この節は今回**実行して観測したこと**を残す。第2〜4節のコマンド例は今後の
実行用で、W1g を実行済みという意味ではない。日時は日本時間。

### ローカルの状態と設定

作業ブランチは `feat/sdf-native-rearchitecture`。手順書作成時のコミットは
`d490c221e6d9beffa2d753612dc55e46310eab69` で、`origin` に push 済み。
この記録の追加前にはローカル差分はなかった。状態を再確認するコマンド:

```bash
git status --short --branch
git diff --stat
git log -4 --oneline
git rev-parse HEAD
git show --stat --oneline d490c22
rg -n -C 2 'mcp_servers\.colab-mcp|colab_codex_adapter\.py' ~/.codex/config.toml
shasum -a 256 docs/evidence/sdf_native_w1g_gpu_gridsdf_criteria_2026_09.json
cat docs/evidence/sdf_native_w1g_gpu_gridsdf_criteria_2026_09.json.sha256
```

`config.toml` は該当行だけを見る。接続 URL、トークン、環境変数全体を
出力しない。criteria の登録済み SHA-256 は
`d12943018d7d68e46d2395430e296692e03a2b4e459b5557b428d2223b184841`。
新しいラウンドを作る前に現物と sidecar の一致を確認する。

### Colab への接続と観測

Codex に固定3ツールが見えなかったため、前回は `/tmp/colab_codex_client.py` を
一時作成して、次でアダプターを呼んだ:

```bash
uvx --index https://pypi.org/simple --with fastmcp==2.14.5 \
  python /tmp/colab_codex_client.py
```

この一時スクリプトは呼ぶたびにクライアントを終了し、新しい `scratchpad` を
開く可能性があった。再利用時は第2節の `scripts/colab_mcp_session.py` を使う。
接続結果は `true`。`colab_list_tools` の実測一覧は
`open_colab_browser_connection`、`add_code_cell`、`add_text_cell`、
`delete_cell`、`get_cells`、`move_cell`、`run_code_cell`、`update_cell`。
`get_cells` は空のコードセル1個を返した。`update_cell` 後の
`run_code_cell` で得た事前確認出力は次のとおり:

```json
{"cwd":"/content","gpu":"none (FileNotFoundError)","julia_path":"/usr/local/bin/julia","julia_version":"julia version 1.12.6","platform":"Linux-6.6.122+-x86_64-with-glibc2.39","python":"3.13.15"}
```

したがってこの MCP セル実行は CPU ランタイムの確認まで。Colab 画面では
**ランタイム → ランタイムのタイプを変更 → T4 GPU → 保存 → 接続**を行い、
画面上は `T4（Python 3）` と GPU バックエンドへの接続を確認した。
その T4 上での `nvidia-smi`、GPU UUID、Julia 依存関係のハッシュ、W1g の
フィクスチャ実行は確認していない。最後の切断状態も未確認。

### 前回の文書変更で行った検証

手順書作成後に次を実行した。`compileall` と `pytest` は当時のリポジトリ状態に
対する結果で、今回の変更の結果は別途記録する。

```bash
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest -q
git diff --check
```

当時の `pytest` は **1078 passed, 2 skipped**。登録済み W1g criteria と
旧 W0b backend identity の照合を満たす新しい T4 実測は得られていない。

### この記録と端末ヘルパーを追加した際の検証

Colab への新規接続を作らず、ヘルパーの構文、ヘルプ、起動・終了、未接続時の
操作拒否を次で確認した。`uvx` 起動時には FastMCP/Authlib の
`DeprecationWarning` が出たが、終了コードは 0 だった。

```bash
python3 -m py_compile scripts/colab_mcp_session.py
python3 scripts/colab_mcp_session.py --help
printf '{"op":"close"}\n' | uvx --index https://pypi.org/simple \
  --with fastmcp==2.14.5 python scripts/colab_mcp_session.py
printf '{"op":"tools"}\n{"op":"close"}\n' | uvx --index https://pypi.org/simple \
  --with fastmcp==2.14.5 python scripts/colab_mcp_session.py
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest -q
git diff --check
```

ヘルパーは `ready` → `closed`、および未接続の `tools` を拒否してから
`closed` を返した。`compileall` と `git diff --check` は成功。
`pytest` は **1078 passed, 2 skipped, 7121 warnings**（200.36 秒）。
警告は NumPy 2.5 での VTK の配列 shape 設定に関する非推奨警告だった。
この検証は実際の Colab ブラウザー接続や T4 セル実行の確認を含まない。
