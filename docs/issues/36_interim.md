# Issue #36 (FD-04) 中間報告 (2026-09-29)

状態: **中断・未完了**。最終成果物 (再現スクリプト、テスト、証跡 JSON+sidecar、`36_result.md`) は未作成。
本書は探索段階で測定した事実のみを記す。qualified FD oracle / gradient qualified の主張はしない。
共有ドキュメント (phase_plan 等) と既存 evidence/criteria は未変更。Kaggle/GPU は未使用。

## 1. 実施済みの測定 (すべて solver-free、CFD 力応答は未測定)

入力: `work/sdf_native_genesis_v16/sdf_design_state.npz` (主 worktree の gitignored work/。
SHA-256 = `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`。
round5 criteria の `canonical_state_npz_sha256` と一致を確認)。
Fortran 順 float32 phi の SHA-256 = `9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7`
(round5 criteria の `canonical_phi_fortran_sha256` と一致を確認)。
STL: `work/pq4_1_v16_state_v2/sweep/threshold_0.5/iso_surface.stl` (genesis 記録の SHA は
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`。本探索では STL ファイルの
SHA を再計算していない)。

実行コマンド (すべて `scripts/wip_fd04/` の WIP スクリプト。パスは絶対パスで固定、ログ/生データ保存なし):
`PYTHONPATH=src <.venv>/bin/python scripts/wip_fd04/explore{1,2,3,4}_*.py`
(explore3 は trimesh が必要で、主 `.venv` にはあるがシステム python3 には無い)。

### 1.1 phi の構造 (explore1, explore2)
- 形状 61x33x25, float32, 原点 (-1.0,-0.8,-0.6) m, 間隔 0.05 m, `narrow_band_width_m`=0.05。
- min = -0.05 (-0.050000004), max = 1.7131841。負 1420 / 正 48796 / 厳密 0 は 109 点。
- `|phi|<t` の点数: t=1e-12→243, 1e-9→491, 1e-8→1068, 1e-7→1344, 1e-6...1e-2 → いずれも 1344, 0.05→1945。
  すなわち **1e-7 と 0.05 の間に phi 値を持つ節点は存在しない**。
- |phi|<1e-7 の 1344 点の内訳: 正 228 / 負 1007 / 厳密 0 が 109。26 連結で 1 成分。
  インデックス範囲 i 8..31, j 7..25, k 7..17。うち 1149 点が design_mask 内。
- 上記以外の負値 413 点はすべて -0.05 (小数 4 桁丸めで一意)。
- 正側の非零 |phi| は 0.05, 0.0707, 0.0866, 0.1, ... と節点間距離型の離散値 (4 桁丸めで確認)。

### 1.2 STL の格子整合 (explore3)
- 頂点 1344, 三角形 2684, watertight, 体積 0.12925 m^3, bounds は x -0.6..0.55, y -0.45..0.45, z -0.25..0.25。
- 頂点の座標は設計格子節点に対する端数が全軸で 0 (分位点 0/0.5/0.9/1 すべて 0)、全頂点が格子節点上。
- 全三角形の法線が軸整列、各軸整列面の平面位置も節点平面上 (端数 0)。
- 頂点数 1344 は |phi|<1e-7 の節点数 1344 と一致したが、**集合としての一致は未検証**。
- phi の生成経路 (コード読解、未再実行): `src/cfd_sdf/handoff.py` の `_build_sdf_values` が
  `src/cfd_sdf/sdf.py::signed_distance` (trimesh の STL への符号付き距離、負が内側) を点格子で評価し
  `signed_distance.vti` に書く。genesis はその VTI を無加工で phi に採用。

### 1.3 セル中心勾配の分布 (explore4、float64 の解析的トリリニア勾配)
設計セル中心 (= flow_16 の圧力点。設計原点と flow 原点の差が 30,8,6 セルの整数のため。算術による導出で、
コードでの直接照合は未実施) で |∇phi| を評価。
- セル総数 46080。力寄与帯 (セル中心値 |phi|<=0.05) のセル 2470。
- その 2470 セルの |∇phi| 度数: `<1e-6`: 66 / `1e-6..0.25`: 0 / `0.25..0.5`: 181 / `0.5..0.75`: 648 /
  `0.75..0.9`: 152 / `0.9..1.1`: 1423 / 1.1 超: 0。二峰性で中間帯が空。
- `|∇phi|<1e-6` の 66 セルの値は 1.3e-8 ~ 約 3e-7 (昇順先頭 60 個を確認)。
- 8 頂点すべて |phi|<1e-7 のセル (平坦セル) は 43。残り 23 セルは中心勾配が 1e-6 未満だが全頂点零ではない
  (原因は未調査。対称打消しによる勾配ゼロの可能性があるが**未確認**)。
- 暫定診断 (issue コメント) の「43 サイト」と平坦セル数 43 は一致。66 という数は暫定診断に無い新しい測定。

### 1.4 round 5 の既存証跡からの数値 (`sdf_directional_fd_v16_round5_kernel4_postmortem_2026_09.json`)
- baseline (A/B/C 一致, span 0): drag 0.3360177 N, downforce 0.3533732 N。
- D0 の drag: plus/minus/pair_signal は ε=0.0005 で 0.33152/0.33653/0.005009 N。pair_signal は
  ε=0.0005,0.001,0.0025,0.005,0.01 で 0.005009, 0.005036, 0.005173, 0.005033, 0.005316 N とほぼ一定。
- D1 の drag pair_signal: 0.004266, 0.004061, 0.003442, 0.002458, 0.000396 N。
  D1 downforce: 0.002096 ... 0.003193 N。D2 は 0.0008..0.0077 N の範囲 (ε 依存あり)。
- 係数換算 (force_scale = 0.05^2) の比較は未実施。

### 1.5 CPU Julia の実行可否 (bench_cpu_step.jl)
- Julia 1.12.6、WaterLily 1.8.0、8 スレッド。flow_16 (100x48x36) を Float64 GridSDF + Float32 body で
  CPU 実行し、1 step 目 6.8 s (コンパイル込み)、続く 20 steps で 5.87 s (約 0.29 s/step)。sim_time = 0.470。
- 21 step 時点の pressure_force = [107.59, 0.0252, -155.84] (solver 単位、初期過渡で FD 証跡ではない)。
- 登録 T4 実行は Float32 フィールドの GridSDF (`device_copy`) で、この bench の Float64 GridSDF とは演算精度が異なる。
  登録条件の再現には Float32 フィールドの構築が必要 (未実施)。

## 2. 事実から言えること / 言えないこと

言える (測定に直接基づく):
- canonical phi は STL の格子節点整列した階段状面上の節点で |phi|<1e-7 となり、その節点集合と
  それ以外の間に値の空白 (1e-7..0.05) がある。
- 力寄与帯のセル中心 2470 のうち 66 で |∇phi|<1e-6 (うち 43 は全 8 頂点が |phi|<1e-7)。残りは 0.25 以上。
  WaterLily bridge (`WaterLilyBody.jl`) は `n = ∇phi/|∇phi|` を無正則化で返す (コード読解。
  ゼロ勾配のみ early return)。

推論 (仮説であり未証明):
- 上記 66 セルで n が 1e-7 級の勾配の向きで決まり、微小摂動で O(1) 回転する → 力応答のジャンプ。
  round 5 の「pair_signal が ε で縮まない」と整合するが、**力応答への因果は未検証**。
- 原因は phi の Eikonal 崩れではなく、階段状面の節点整列サンプリング (1 セル厚部では 8 頂点すべてが面上) の可能性。
  ただし 23 セル分と、面/ BDIM 速度面 (loc(1..3,I)) の勾配分布は未評価。

## 3. 未実施・未検証 (次にやるべきこと)

1. `|phi|` と (零節点集合からの EDT) の比較 (abs で) → 再初期化 (#28) が no-op かの判定材料。explore2 は
   符号付き phi との差を出しただけで、この用途には使えない。
2. 1344 節点 = STL 頂点の集合一致、109 個の厳密零節点の座標・由来の記録 (issue 手順 1)、flow_16 格子との
   厳密/許容一致の数え上げ (手順 2)。設計節点は flow の cell corner に乗り、圧力点 (cell center) と
   face 点 (loc(1..3)) には乗らない、という点の数値確認。
3. D0/D1/D2 × ε ラダーの 30 摂動 phi を `perturbed_state` で再生成 (SHA を criteria inventory と照合) し、
   Float32 bridge の解析エミュレーションで 66 セルの ±ε 法線ギャップ、n の ε 依存性・符号反転性 (n(+ε) ≈ -n(-ε))、
   臨界 ε* = |g0|/|∇dir| を raw vector で保存。実 Julia bridge (`WaterLily.measure`) との照合。
4. 因果検証 (CPU Julia、縮小時間幅 T≈10 tU/L、0.29 s/step): (i) baseline の p を固定した frozen-pressure 力の
   幾何のみの ε 応答、(ii) `n = g/max(|g|, τ)` (τ=0.1, 二峰性の中間帯に置く事前宣言値) の診断ラッパで
   ±ε の pair_signal が ε に比例して縮むかの比較。ラッパは bridge を変更せず診断スクリプト内のみ。
5. 半セルずらした格子で STL 厳密距離を再サンプルした場合の勾配分布 (solver-free、trimesh 可)。
6. 分類 (a)~(d) の確定、#37 への推奨、`36_result.md`、証跡 JSON+sidecar、テスト
   (`tests/test_sdf_native_fd04_*.py`)、全体 pytest。**いずれも未実施**。

暫定の見立て (データ不足、確定ではない): 現時点では (d) 未確定。データが示唆する候補は
「SDF の格子整合サンプリング / bridge の法線正則化のいずれか」であり、単純な epsilon 範囲変更 (c) では
臨界 ε* が Float32 分解能付近と見積もられるため足りない可能性が高いが、この見積もりは未計算。

## 4. 作成ファイル
- `docs/issues/36_interim.md` (本書)
- `scripts/wip_fd04/explore1_phi_counts.py`, `explore2_near_zero_structure.py`,
  `explore3_stl_lattice_alignment.py`, `explore4_cell_gradient_census.py`,
  `mkphi_canonical_raw.py`, `bench_cpu_step.jl` (WIP。絶対パス固定、証跡/sidecar 無し、テスト無し。
  最終成果物の `scripts/sdf_native_fd04_*` に置き換える予定で、WIP のまま確定成果として扱わないこと)。
  `bench_cpu_step.jl` と `mkphi_canonical_raw.py` は scratchpad の絶対パスを参照する。

## 5. 追記: 因果検証 (CPU Julia、2026-09-29)

入力は登録済み round-5 dataset v5 (canonical phi と 30 摂動 phi の生データ、読み取りのみ)。
bridge 本体は変更していない。診断用に `n = g/max(|g|, TAU)`、`TAU=0.1` の body を別ファイルで用意した
(`scripts/sdf_native_fd04_regularized_body.jl`)。TAU は結果を見る前に固定し、二峰性分布の空白帯に置いた。

- 圧力固定 (`scripts/sdf_native_fd04_frozen_pressure_response.jl`、baseline flow の t=3,8 の圧力場を固定):
  raw の D1/D2 は pair signal が ε に比例しない (D1 Fx: 1.44→1.04、ε を 20 倍にしても)。
  reg では ε に比例する (D1 Fz: 0.112/0.561/2.235 = 1:5:20)。幾何経路だけで非平滑性が再現し、法線正則化で消える。
- フル解析 (`scripts/sdf_native_fd04_full_response.jl`、t=0..2、平均窓 1..2、BDIM と力積分の両方で body を置換):
  raw D0 Fx は -2.15/-2.20/-1.95 と ε に依存しない (round 5 の D0 drag 一定と同型)。reg では
  D1 Fz 0.067/0.323/1.258、D2 Fz 0.128/0.664/2.613 と概ね ε に比例する。baseline の力の変化は小さい (Fx 144.69→144.42)。
- 生データ: `docs/evidence/sdf_native_fd04_{frozen,full}_response_2026_09.csv` (+ `.sha256`)。

限界: 短い時間幅 (登録窓 80..120 ではない)、CPU Float32、各 1 run で noise floor 未測定。qualified FD の主張はしない。

判定: 分類 (b) が機構として支持される。ほぼ零勾配 (canonical phi の節点整列・量子化構造が原因) を
bridge が無正則化で正規化するため、摂動で法線が O(1) 回転し、力応答が非平滑になる。
対策候補: (1) canonical phi を真の SDF として作り直す/再初期化 (#28) して |∇phi|≈1 にする、
(2) bridge 法線に正則化を入れる (primal 演算子が変わるので W1〜W3 の再 qualification が必要)。
#37 は ε を変えるだけでは直らない。(1) か (2) を実施した上で再登録する必要がある。
