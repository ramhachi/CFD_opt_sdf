# WP4：TOPO-2D-00 の WaterLily 側（幾何系列、厚くする生成器、2D job、campaign、analyzer）

最初に `docs/codex/gen01_w1_2026_11_06/00_README.md` を読み、その規則に従うこと。仕様は `docs/topo2d00_registration_2026_11_01.md`（TOPO-2D-00 ＋ TR-00、registration draft rev 0）。RANS 側は WP5 が別に作る。

## 目的

Zhang & Zerihan（2003）の 2 要素の地面効果翼から 1／2／3 要素の 2D 系列（E1、E2、E3）を作り、要素を BDIM の下限以上に厚くし、WaterLily の 2D で配置位相 16 個の対評価を回す job と campaign、そして一致規則を計算する analyzer（と独立の checker）を作る。**GPU は回さない**。CPU の小さい格子で job が通ることまで。

## 必ず読む（全文）

- `docs/topo2d00_registration_2026_11_01.md`（特に §2 幾何、§3 solver、§5 統計と一致規則、§8 対照、§10 未解決）
- `docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md` §1（幾何の数値、座標の出所：Zerihan 2001 thesis Tables 2〜4、OCR の注意）、§2（1.8.0 の `AutoBody`、`SetBody(min, …)`、`measure!` の μ₀、2D の設定）、§6（BDIM の厚さの下限）
- `scripts/v18_plate.py`（解析 SDF の書き方。stadium 板、`raw_mode`）、`scripts/t20_case.py` の `airfoil_points`（座標の読み方と迎角の約束。編集しない）、`data/t20/tyrrell026s_genua2009.dat`
- `scripts/waterlily_lowdim02_flow32_job.jl`（編集しない。窓、力、位相、ハッシュ検査の約束）、`julia/CFDSDFWaterLily/src/*.jl`（特に `V16PhysicalProfile.jl` の境界条件、`WaterLilyNormalFloorBody.jl`、`Forces.jl`）
- `src/cfd_harness/campaign_schema.py`、`campaign_build.py`、`docs/harness/README.md`、`docs/harness/screen01_campaign.json`（campaign の形。baseline＋direction の state モデル）
- `scripts/screen01/analyze_screen01.py` と `screen01_check.py`、`docs/evidence/screen01_2026_10_30/INTERFACE.md`（analyzer と独立 checker の分け方、written-once、σ_d、片側検定）
- `docs/re01_plan_2026_11_01.md` §3.4（推定量 A／B、窓の式）
- WP1 の `Checkpoint.jl`（インターフェースは WP1 の設計メモ。無ければ `save_checkpoint(path, sim, step, rows)`／`load_checkpoint(path)` を仮定し、報告に書く）と WP2 の `force_readouts(sim, box)`（同様）

## 成果物

1. **幾何** `src/cfd_sdf/topo2d/geometry.py`：
   - Zerihan（2001）の Table 3（主翼素、14.1° の基準姿勢）と Table 4（フラップ）の座標を `data/zz2003/main_element_table3.dat`、`data/zz2003/flap_table4.dat` に **出所と取得方法を記した header 付き**で置く。取得は、thesis の PDF（`https://eprints.soton.ac.uk/426058/1/00192634.pdf`）を取れるなら OCR テキストから転記し、図と照合できない値は `# UNVERIFIED` を付ける。**取れなければ BLOCKED で止める**（推測で座標を作らない）。主翼素は `data/t20/tyrrell026s_genua2009.dat` と同じ断面のはずなので、両者の差を報告に数値で書く。
   - E1／E2／E3 を生成する関数：E2 は overlap 9 mm、gap 12 mm、datum flap、回転中心 x/c 0.567・y/c 0.076、c = 380 mm（仕様 §2 の定義どおり。overlap と gap の符号の定義を docstring に書く）。E3 は仕様の構成規則（弦の等分、総たわみ角の等分、同じ gap/overlap 規則）。高さ h は mm で受け、両方の正規化（c₁ = 223.4、c = 380）を返す。
   - **厚くする生成器**：要素ごとに `t_min`（Δx の倍数で指定、既定 4Δx）を満たすように、キャンバー線の法線 offset で厚さを増やす（前縁半径と後縁位置は保つ）。元の厚さ分布との比（要素ごとの最大）を返す。鋭い後縁の原形も出力する（`*_sharp`）。
   - 解析 SDF：各要素を **閉じた多角形の符号付き距離**（点–線分距離の最小と winding による符号。NumPy、決定的）で表し、`scene_sdf(points) = min_c sdf_c(points)`。Julia 側で同じ関数を評価できるよう、要素の多角形を `.npz`／JSON で渡す。
   - gate：厚さ ≥ t_min、間隙 ≥ g_min（既定 4Δx）、要素の重なりなし（E3 の構成で起きないこと）、地面との clearance、閉じた多角形の自己交差なし。拒否は CFD の前。
2. **2D job** `scripts/waterlily_topo2d_job.jl`（新規。既存 job から窓・力・ハッシュ検査の部分を流用）：
   - `Simulation((n, m), (U, 0), L; ν, body=SetBody(min, …), exitBC=true, λ=quick)`。要素は `AutoBody` で、多角形 SDF を Julia で評価（面での解析評価。三線形格子を通さない）。地面は **動く BDIM の半空間**（`V = U`）で、領域の壁にしない。
   - 配置位相は (x, z) の sub-cell shift を環境変数で受け（JOB-02 と同じ変数名の 2D 版）、scene 全体（地面を含む）を一緒に動かす。
   - 力の読み出し：WP2 の `force_readouts` が使えるならそれ（cur／nds／cv の 3 組）、無ければ `cur` のみで列を予約。要素ごとの力も出す（`SetBody` では難しければ、要素ごとの `AutoBody` で別に積分する）。
   - 窓、burn-in、サンプリング、端点補間の time-weighted mean、drift は既存 job と同じ定義。Checkpoint（WP1）の保存・再開に対応。
   - 出力は既存の force CSV の形式に列を足したもの（列名は設計メモで固定）。
3. **campaign** `docs/harness/topo2d00_campaign.json`：harness v1.1 の schema に収まるように、state ＝「E_k ＋ 高さ ＋ Re ＋ 位相」を表す。baseline＋direction の state モデルに収まらなければ、`src/cfd_harness/` に **最小の拡張**（state の `kind: "scene"` と、scene ファイルの SHA）を足し、既存 campaign の検証が変わらないことをテストで示す。kernel は 2 つ（Re 1e3、Re 3e3）＋確認格子 1 つ。
4. **analyzer** `scripts/topo2d00/analyze.py` と独立の `scripts/topo2d00/check.py`：
   - 入力：WaterLily の force table（harness verify の形式）、RANS の結果（WP5 の形式。JSON の schema を WP5 と合わせるため、本 WP で `docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json` を書いて報告に載せる）、freeze の記録。
   - 計算：対差分 Δ_W(1→2)、Δ_W(2→3)（downforce と drag）、σ_d（推定量 A と B の大きい方、上側信頼限界）、90 % 区間、RANS 側の (model, family) ごとの区間と最悪値、TR-00 の判定（`TR00_PASS_RATIO`／`TR00_PASS_SIGN`／不合格）、一致規則（`SIGN_AGREE_12`、`RANK_AGREE`、`DRAG_SIGN_AGREE_12`、`RETENTION_12` の Fieller 区間）、順序付きラベル（仕様 §5 の表。`INVALID` → … → `CONCORDANT`）、対照（決定性、DOMAIN、readout、manipulation）。
   - `analysis.json`／`analysis.md` を 1 回だけ書く（存在すれば拒否）。checker は analyzer のコードを import せずに同じ数値を再計算し、不一致を列挙する。
5. **テスト**：`tests/topo2d00/test_geometry.py`（E2 の overlap/gap が定義どおり、厚くした後の最小厚さ、gate の拒否、SDF の距離性質（勾配の大きさ ≈ 1）、決定性）、`tests/topo2d00/test_analyze.py`（合成データで全ラベル、Fieller 区間、TR-00 の両規則、書き込み拒否、checker の一致）、`scripts/topo2d_selftest.jl`（CPU、小さい格子（例 192×96、Re 200、短い窓）で E1 と E2 が走り、力が有限で、地面が動いていること（地面近傍の速度が U）、位相 shift で scene が一緒に動くこと、checkpoint 再開で窓統計が一致すること）。

## 受け入れ条件

- 座標が転記され（または BLOCKED）、E1〜E3 の図（PNG、`docs/codex/gen01_w1_2026_11_06/reports/topo2d00_geometry.png`）が報告に添えられる。
- CPU の自己テストが通る（数分以内）。
- `pytest -q tests/topo2d00` が通り、全体の失敗集合が base と同一。
- 報告に、厚くした比（要素ごと）、c₁/120 と c₁/180 でのセル数、仕様 §10 の未解決点への回答（分かった範囲）、WP5 との JSON schema を書く。

## やらないこと

- GPU 実行、Kaggle、RANS 側（WP5）、仕様の閾値の変更（4Δx、[0.5, 2]、α 0.05 は仕様の値）、既存 job の編集。

## Amendment 1（2026-11-06。WP5 の Opus review（`docs/codex/gen01_w1_2026_11_06/reviews/wp05_review_1_opus.md`、follow-ups branch）から先回りで決めた点。1 回目の試みが終わった後の 2 回目に適用する。この節が本文より優先する）

1. **幾何の密度。** 要素の多角形は、Zerihan の表の座標を補間 spline で **弧長 ≤ 1 mm** に再標本化したもの（T2-0 の `t20_case.airfoil_points` と同じ規則。可能ならその関数を import して使う）。WP5 の kernel に入った開発 snapshot はフラップが 36 頂点で前縁に 55° の折れがあり、RANS（Re 4.6e5）でも BDIM でも許容できない。cap 以外の頂点の折れ角 ≤ 5° をテストで確認する。幾何ファイル（JSON、SHA-256）が W と R の唯一の出所。
2. **observable。** 共有結果形式と analyzer に `observable`（`pressure_cl`：sharp 腕、Cp 積分との比較／`total_cl`：thick 腕、WaterLily との比較）を足し、analyzer は observable をまたぐ差分を拒否する。h は h/c₁ と h/c（c = 380 mm）の両方。
3. 登録文書の Amendment 1（`docs/topo2d00_registration_2026_11_01.md`、follow-ups branch）を読む。

## Amendment 2（2026-11-06。1 回目の試み（PARTIAL、Draft PR #89、`88fea06e`）への回答。Amendment 1 と合わせて適用する。この節が本文より優先する）

1. **`src/cfd_sdf/` は登録済みの source closure**（`scripts/analyze_grid02.py` と `analyze_lowdim03.py` が現在の tree から `src/cfd_sdf/**/*.py` を列挙して凍結 `file_hashes` に含まれることを要求する。1 回目の残り 2 件はこれ）。歴史テストの例外は不要・不許可。**`src/cfd_sdf/topo2d/` を `src/cfd_gen/topo2d/` に移す**（WP6 も `src/cfd_gen/scene/` を使う。`src/cfd_gen/__init__.py` と `README.md` は WP6 が作るので、存在しなければ同じ 2〜3 行の README を作る）。`src/cfd_sdf/` に 1 byte も残さない。
2. **Julia の置き場所**：`julia/topo2d/Topo2D.jl` を **`julia/CFDSDFWaterLily/gen01/Topo2D.jl`** に移す（README の規則。WP1 の `gen01/Checkpoint.jl` と同じ場所。job から `Base.include(CFDSDFWaterLily, …)` で読む）。
3. **Amendment 1 を適用する**：表の座標を補間 spline で弧長 ≤ 1 mm に再標本化（`t20_case.airfoil_points` と同じ規則。import できればそれを使う）。厚くする生成器は頂点番号ではなく **弧長**で書き直す（前縁 cap は LE から弧長 2 % c、smoothstep で最大厚さ位置へ、以後 4Δx）。cap 以外の頂点の折れ角 ≤ 5° をテストする。scene JSON を再生成し、図も更新する。
4. **datum の判断は登録文書の Amendment 2**（`.../github-local-status-review-66bea1/docs/topo2d00_registration_2026_11_01.md`、Amendment 1 と 2 を読む）。1 回目の解釈（公称 9／12 mm の後配置、TE 中点基準、c と迎角の記録、`mathematically_sharp=false`）はそのまま採用された。
5. **observable**：共有 RANS 形式に `observable`（`pressure_cl`／`total_cl`）を足し、analyzer は observable をまたぐ差分を拒否する。WP5 の 2 回目が同じ登録文（Amendment 1 §5）から同じ schema を更新中なので、WP4 の schema ファイルは登録文の定義だけに従い、WP5 との byte 一致は Claude が統合時に揃える。
6. **全体 pytest**：結果側だけを `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` で完走させ、失敗 node 集合（期待：空）を報告に書く。base は Claude の host 実行（e3dcdf61、3482 passed / 74 skipped / 0 failed）。
7. **commit／push は Claude が host で行う。** `/tmp` の clone は使わない。報告に commit すべきファイルの完全な一覧（移動元→移動先、変更、新規）を書く。worktree は `88fea06e` に同期済み。PR #89 の本文は Claude が更新する。

## Amendment 3（2026-11-07。2 回目（PR #89、`ba3164c7`）への回答。Amendment 1・2 の上に適用する。この節が本文より優先する）

1. **sliver。** 再標本化した多角形に 5.6 µm の線分がある（WP5 の review が (27.3, 127.1) mm 付近で検出。`polygon_mm` の最小線分は 0）。登録 Amendment 3 §1 の規則に合わせる：線分長 ∈ [0.1 mm, 1 mm]、折れ角 ≤ 5°（cap 2 頂点のみ免除）、隣接線分比 ≤ 3、閉じる線分は隣に併合（終点の重複なし）。`geometry.py` の gate と `tests/topo2d00/test_geometry.py` に 4 条件を足し、全 10 scene を再生成して図を更新する。
2. **cell state の順序**を `INCOMPLETE > MESH_FAILED > NUMERICAL > SETTLED` に（WP5 と共通）。
3. **高さ。** `E1_h80.json` が `E1` として読まれ export が 100 mm を hard-code している。scene JSON の高さを唯一の出所にし、export と campaign はそれを使う。宣言した高さと scene の高さが違えば拒否。
4. **`CONCORDANT_PARTIAL`**：登録 Amendment 3 §5 の定義（SIGN_AGREE_12 が片方の Re だけ真、RANK_AGREE は両側 resolved の範囲で真）に analyzer と checker を合わせ、8 ラベルの到達性テストを更新する。
5. **全体 pytest**：結果側だけを `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` で完走させ、失敗 node 集合（期待：空）を報告に書く。
6. **commit／push は Claude が host で行う。** worktree は `ba3164c7`。報告に commit すべきファイルの一覧を書く。
