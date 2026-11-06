# WP5：TR-00／TOPO-2D-00 の RANS 側（T2-0 パイプラインの多体化、Cp の積分、結果の形式）

最初に `docs/codex/gen01_w1_2026_11_06/00_README.md` を読み、その規則に従うこと。仕様は `docs/topo2d00_registration_2026_11_01.md` §3（R 側）、§4（TR-00）、§7（run）。WaterLily 側は WP4。

## 目的

T2-0 の 2D RANS パイプライン（gmsh → OpenFOAM v2512、`scripts/t20_case.py`／`t20_foam.py`。**編集しない**）を、主翼素＋フラップ（＋第 2 フラップ）の 2〜3 体に対応させた **新しい生成器**として作り、Zhang & Zerihan の 2 要素の中央断面 Cp（図からデジタイズ）を積分して TR-00 の参照値と不確かさを出す道具と、WP4 の analyzer が読む結果 JSON を出す集計器を作る。**OpenFOAM の実行は、ローカル Docker（`scripts/local_openfoam.py`）での mesh-only と短い smoke（≤ 200 反復）まで**。Kaggle には push しない。本番の run はユーザーが Kaggle CPU で回す（LOCAL-OF-01 により gmsh のパイプラインは Kaggle）。

## 必ず読む（全文）

- `docs/topo2d00_registration_2026_11_01.md`
- `scripts/t20_case.py`、`scripts/t20_foam.py`、`scripts/t20c_case.py`、`scripts/t20d_case.py`、`scripts/build_t20b_kernel.py`（または t20c）、`infra/kaggle/kernel_t20b_cpu/runner.py`、`docs/evidence/t20c_registered_2026_10_20/README.md`（fine30 の設定、morph、realisation のノイズ、convergence の規則）、`docs/t20_summary_for_m4_2026_10_22.md`
- `docs/local_openfoam_env_gate_2026_10_20.md`（gmsh は実行ごとに変わる。Kaggle で回す理由）、`scripts/local_openfoam.py`
- `docs/eval_valid01_reference_audit_2026_10_22.md`（参照データの扱い方、Table 15 の由来）
- `docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md` §1（Zhang & Zerihan 2003 の幾何、自由遷移、中央断面 Cl、2 要素の Cl は図のみ、Zerihan の 2D CFD の +5〜17 % の偏り、Heyder-Bruckner の −7 %）

## 成果物

1. `scripts/topo2d00/t2d_multibody_case.py`：`t20_case.py` の関数を import して（コピーではなく）、複数の閉曲線（WP4 の幾何 `.npz`／JSON、または `*_sharp` の原形）を gmsh で 1 つの 2D メッシュにする生成器。各要素に boundary layer（fine30 と同じ ds／y1／g）、鋭い後縁には既存の fan、厚くした後縁（鈍い）には fan なしの扱い（設計メモで決め、checkMesh の proxy で確かめる）。地面、領域、patch 名は T2-0 と同じ。マニフェスト（入力の SHA、mesh.msh の SHA、品質指標）も同じ形式。
2. `scripts/topo2d00/t2d_foam_case.py`：`t20_foam.py` を使って、SA-WF と SST-WF、fine30 と第 2 の格子族（`med30` または新しい base realisation。設計メモで選ぶ）、5000 反復、T2-0c の収束・継続規則、自由遷移（trip なし）の case を書く。要素ごとの力（`forceCoeffs` を patch ごとに）を出す。
3. `scripts/topo2d00/digitize_cp.py`：デジタイズした Cp の CSV（x/c, Cp；上面・下面別；2 人／2 ツール分）を読み、中央断面の Cl を台形積分で出し、2 つのデジタイズの差から不確かさを出す。入力の CSV は **ユーザーが用意する**（Codex は図をデジタイズしない）。形式を `docs/codex/gen01_w1_2026_11_06/reports/cp_digitised_format.md` に書く。単一要素の参照（thesis Table 15 の h/c₁ 0.448 の値、または Cl(h) 曲線）も同じ道具で扱う。
4. `scripts/topo2d00/collect_rans.py`：Kaggle の出力（T2-0 の `case_result.json` 相当）を集め、(config, model, family, realisation) ごとの Cl・Cd（要素ごとと合計）、収束の状態（settled／limit cycle／diverged、T2-0d の分類を流用）、mesh の SHA を、**WP4 と合わせた schema**（`docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json`。WP4 が先に置いていればそれに従い、無ければ本 WP が置く）で `rans_results.json` に出す。
5. kernel のレンダリング：`scripts/topo2d00/build_tr00_kernels.py` で、Kaggle CPU 用の kernel（TR-00 の E1_sharp／E2_sharp × 2 モデル × 2 格子族 × 8 realisation、本番の E1〜E3 厚い版）を **ローカルに生成するだけ**。5 セッションの枠に合わせた分割（1 kernel ≈ 12 時間以内）。
6. ローカル smoke：`scripts/local_openfoam.py` で E2_sharp と E2（厚い版）の **mesh-only** と、SA-WF の 200 反復 smoke を 1 realisation ずつ回し、checkMesh と force の有限性を確かめる（gmsh の非再現性は LOCAL-OF-01 のとおり。結果は smoke としてだけ報告）。
7. テスト：`tests/topo2d00/test_multibody_case.py`（gmsh が無ければ skip（conftest の `_NO_GMSH` と同じ流儀で、新しい pin を増やさない）、2 体の閉曲線で patch 名と要素数、manifest の SHA、品質 proxy）、`tests/topo2d00/test_digitize_cp.py`（合成 Cp で既知の Cl、2 デジタイズの不確かさ）、`tests/topo2d00/test_collect_rans.py`（schema、収束の分類、欠け run の扱い）。

## 受け入れ条件

- E2_sharp と E2 の mesh-only がローカルで通り、checkMesh proxy の指標が報告にある（鈍い後縁で fan を外した扱いの妥当性を含む）。
- SA-WF の 200 反復 smoke が走る（収束は問わない）。
- `pytest -q tests/topo2d00` が通り（gmsh なしの環境では skip）、全体の失敗集合が base と同一。
- 報告に、Kaggle での run 数と推定時間（T2-0c の実績：fine30 13〜21 分/5000 反復）、5 セッション枠での日数、ユーザーが用意する CSV の形式を書く。

## やらないこと

- `t20_case.py`／`t20_foam.py` の編集、Kaggle への push、5000 反復の本番、Cp 図のデジタイズそのもの、参照の帯の変更（[0.5, 2]、5 % は仕様の値）。

## Amendment 1（2026-11-06。1 回目の試み（PARTIAL、Draft PR #87、`cb4df650`）への Opus source review の回答。この節が本文より優先する）

review 全文：`/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1/docs/codex/gen01_w1_2026_11_06/reviews/wp05_review_1_opus.md`（読む。別 worktree なので読み取りのみ）。登録文書の判断は `docs/topo2d00_registration_2026_11_01.md` の **Amendment 1**（同じ場所の worktree で読む：`.../github-local-status-review-66bea1/docs/topo2d00_registration_2026_11_01.md`）。verdict は INTEGRATE_AFTER_FIXES。次を直す。

1. **幾何の guard（A1）。** `load_geometry` は、cap 以外の頂点の折れ角が 5° を超える多角形、または線分長が family の `ds` を超える多角形を拒否する（理由付き例外）。密な多角形は WP4 が spline 再標本化（≤ 1 mm、`t20_case.airfoil_points` と同じ規則）で作るので、WP5 は再標本化しない。**kernel は再生成しない**（WP4 の密な幾何が来てから Claude が指示する）。既存の `infra`／`work` の render は「開発 render」と明記し、`ready_for_execution` は 7 項の規則を満たすまで false にする。
2. **収束分類（A2）。** T2-0c の規則（登録 §3：block plateau、raw-tail 相対 std 0.5 % 超だけ UNSTEADY、非収束は NUMERICAL）に揃える。T2-0d の `urans_stats`／`steady_stats`（1e-3）は使わない。`limit_cycle` ラベルを廃止する。manifest と collector の閾値を一致させ、review の 3 つの反例（周期 2 の交互、周期 7 の正弦、0.2 % の白色雑音、いずれも 0.3 % 以下）が T2-0c どおり settled になるテストを足す。
3. **BL 層数（A3）。** family ごとの層数を、宣言した構成集合（E1／E2／E3 の thick と sharp）の最小 gap から **1 回だけ**計算して plan に記録し、全構成・ground block に同じ値を使う。collector は集計する run の `n_layers` が等しいことを assert する。
4. **realisation（A4）。** collector は cell の 8 mesh SHA が pairwise distinct であることを要求し、重複があれば cell を `DEGENERATE_REALISATIONS`（点推定は出す、区間は出さない、ratio test は INCOMPLETE）にする。
5. **observable と h（A5）。** 共有形式に `observable`（`pressure_cl`／`total_cl`）を足し、WP4 の schema と合わせる（schema ファイルを更新し、WP4 側に伝える差分を報告に書く）。h は h/c₁ と h/c（c = 380 mm）の両方を出す。E*_sharp と E* の差（thickening alone）を記述量として出力する。
6. **Cp 入力（C1、C2）。** 2 読み取りの CSV は SHA が異なることを要求（同一なら拒否）。各要素の積分 Cl が downforce 正でなければ拒否。10 点未満の面は拒否。不確かさの推定量は要素ごとの |d1 − d2| の和（現行のまま、登録 Amendment 1 §6）。
7. **render の規則（B3）。** `ready` は clean tree かつ freeze 1 に束縛された commit からのみ。dirty tree や `UNVERIFIED_OCR` の幾何からの render は `development` と記録し、push 用の plan に含めない。
8. **結果とインフラの区別（B1、B2）。** gmsh の品質 proxy は情報のみ（T2-0 の意味）で、checkMesh が mesh の採否を決める。非有限の係数行は `diverged`（結果）であり、`RUNNER_EXCEPTION`／INFRA_LOSS にしない。生成器・mesh の失敗は `MESH_FAILED` として `NUMERICAL` と区別する。
9. **出典コメント（B4）。** `.012`／`.03`／`ds/3`／wake 0.2／`0.4·gap`／`MAX_RUNS=12`／`223.4`／`460000`／`100` に出典（T2-0 の該当行、登録文書の節）を書く。壁 `Distance` の標本化は T2-0 の spline 200 点相当に戻す（密な多角形の頂点を使う）。
10. **報告（E1）。** `merge-tree` の主張は artifact を付けるか削る。A1／A3／A2 の相違点を報告に明記する。
11. **全体 pytest**：結果側だけを `--ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` で完走させ、失敗 node 集合（期待：空）を報告に書く。base は Claude の host 実行（e3dcdf61、3482 passed / 74 skipped / 0 failed）。
12. **commit／push は Claude が host で行う。** `work/wp05/publication.git` の経路は使わない。報告に commit すべきファイルの完全な一覧を書く。worktree は `cb4df650` に同期済み。PR #87 の本文は Claude が更新する。
