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
