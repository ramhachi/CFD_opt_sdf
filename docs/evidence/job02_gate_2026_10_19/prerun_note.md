# JOB-02 (#59) gate 事前登録メモ — 1 kernel の中で state ごとに flow-grid placement (x, y) を変える機能の byte 一致 gate

実行前に固定する。結果を見た後で比較対象・比較方法・合否規則を変更しない。
証拠の種別: engineering gate（能力の証拠）。PROC-01 の科学的な登録（`REGISTERED_FROZEN`）ではなく、物理・閾値・flag・ranking の根拠にはしない。手続き（比較対象の事前固定、hash による凍結、独立ソースレビュー 1 回、fail-closed）は省略しない。
権限: ユーザーの 2026-10-13 の全委任（人間の判断は不要、手続きは省略しない）を解釈として読む。qualification flag と `shape_update_allowed` は変更しない（全 false のまま）。

## 変更（`feat/job02-per-state-placement`）
- harness（`src/cfd_harness/`、version 表記は v1.1 のまま）: kernel の `runs[]` に任意の `name` を追加。同じ state を 1 kernel の中で複数回（placement ごとに）走らせるときの出力名（index、`states/<name>/`、state-force table のキー）。既定（`name` なし）は今と同じく state 名。`name` は他の state 名と重ならず、kernel 内で一意。
- placement は既存の run ごとの `W4_CANONICAL_ORIGIN_M`（canonical origin の x, y）で与える。z は車高なので kernel 内で 1 値に固定し、run ごとに変えると schema が拒否する。
- Julia job・測定の窓・force の積分・換算・budget 規則は変更しない（measurement contract 不変）。各 state は従来どおり別の Julia プロセス。
- 既定の挙動の不変: 名前なしの campaign は run 名 = state 名で、既存の harness テスト（runner が grid02 runner と同じ job env を作る、GRID-02 の 5 kernel 出力の replay が `grid02_analysis.json` と bit 一致）が変更なしで通る。新規テスト `tests/test_job02_per_state_placement.py`。

## 凍結する比較（`gate_spec.json`）
campaign `docs/harness/job02_gate_campaign.json`: parent（OPT-01 v1 parent、phi Fortran SHA `2f23be78…`）だけを、各 kernel で native → shifted の順に 2 run。

| kernel（case, job） | run | origin (m) | 参照 CSV | SHA-256 |
| --- | --- | --- | --- | --- |
| f24（flow_24, `waterlily_xfid_candidate_c_job.jl`） | `opt01b__parent` | -1.0,-0.8,-0.6 | `opt01b_stage_b_2026_10_15/.../opt01b_a/states/opt01b__parent/flow_24.forces.csv` | `e62b6bab…` |
| f24 | `opt01b__parent__grid02_shift` | -0.9875,-0.7875,-0.6 | `grid02_trend_2026_10_16/.../grid02_s24/states/opt01b__parent/flow_24.forces.csv` | `471ea410…` |
| f32（flow_32, `waterlily_lowdim02_flow32_job.jl`） | `opt01b__parent` | -1.0,-0.8,-0.6 | `opt01b_stage_b_2026_10_15/.../opt01b_b/states/opt01b__parent/flow_32.forces.csv` | `282aceed…` |
| f32 | `opt01b__parent__grid02_shift` | -0.9875,-0.7875,-0.6 | `grid02_trend_2026_10_16/.../grid02_s32/states/opt01b__parent/flow_32.forces.csv` | `667127c5…` |

参照の 4 run は、今回の pin と同じ job・`julia/CFDSDFWaterLily/src`・Manifest・Project・parent raw・Julia 1.12.6 で計算された（各 `run_identity.json` の pins と照合済み）。
比較: ダウンロードした force CSV のバイト列が参照 CSV と完全に一致し、かつ `harness.py verify` の table の `forces_csv_sha256` が参照 SHA と一致すること（`scripts/job02_gate.py`）。許容幅なし。summary は GPU UUID と wall time を含むので比較しない（verify が identity・origin・窓・host 再計算を別に検査する）。
合否: 4 行すべて一致で `JOB02_GATE_PASS`。1 行でも違えば `JOB02_GATE_FAIL` で fail-closed: 原因を診断して記録し、閾値を緩めたり再実行で通したりしない。verify が通らなければ gate は判定しない（integrity failure として記録）。

## 手順
1. 実装・テスト・この登録を commit し push（`feat/job02-per-state-placement`）。sonnet の独立ソースレビューを 1 回行い、指摘を反映。
2. `harness.py build` / `smoke`（cheapest kernel = f24、first run = native）→ Kaggle T4 で smoke → `kaggle kernels output` を新しい空ディレクトリへ → `verify --smoke`。
3. `harness.py freeze`（smoke table、identity-free check、clean tree）→ `gate_freeze.json`（gate spec・gate script・harness freeze の SHA-256）を commit・push。gate script は spec・campaign・table（kernel ごとの output manifest の SHA）を照合し、table の source commit と freeze SHA を結果に写す。`gate_freeze.json` との照合（gate script・spec・freeze の SHA）は記録時に手で行い、結果のメモに書く。
4. formal の 2 kernel を投入（同時 2 まで）。出力を新しい空ディレクトリに落とし、evidence にコピー → `verify` → `job02_gate.py` → `SHA256SUMS` と `scripts/check_sha256sums_tracked.py`。`.log` は追跡する。
smoke は f24 の native run だけを通すので、`name`・shift した origin・flow_32 の job を Kaggle で初めて通すのは formal である（offline では `tests/test_job02_per_state_placement.py` が、履歴の出力を再生して runner → verify → gate を通している）。formal の失敗をそのまま harness の退行と読まず、原因を診断する。
予算（見積もり）: flow_24 約 175 s/state、flow_32 約 400 s/state、setup を含めて smoke + formal で 1.5 GPU h 程度。

## #61（UNC-01）との関係
STATE.md は「#59 の byte 一致 gate は UNC-01 の smoke に統合」と書いているが、#61 は #60 の B1（parent の選択、ユーザー判断待ち）で止まっている。この gate の参照は既存の parent（OPT-01 v1 parent の native と GRID-02 shifted）で、B1 の選択に依存しない。したがって #59 を先に閉じ、UNC-01 の smoke は新しい parent での自分の確認だけを行えばよい。HARNESS-01 の flow_16 smoke はこの gate の証拠ではない（#59 の 2026-10-18 コメント）。

## 言えること・言えないこと
言える（PASS の場合）: harness の runner が 1 kernel の中で同じ geometry を別の (x, y) placement で走らせ、既定の placement では既存の native parent を、shift した placement では GRID-02 の shifted parent を、flow_24 と flow_32 の両方でバイト単位で再現する。
言えない: 物理的な downforce／drag、placement 分散 σ_d の値、格子収束、他の parent や z の変更への一般化。
