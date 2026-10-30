# #46 FD-08 契約 v2 Stage 1

## 実行前に転記した受け入れ条件

- **A1**: シナリオ a・b（σ ≤ 3 µN）で、既定 tolerance の PASS 率 ≥ 95%。各シナリオ・各 ladder で確認する。
- **A4**: **全シナリオ**で、既定 tolerance での誤通過率 < 5%。ただし曲率比 100% 以上の d は**報告のみ**（検出の限界を測るための範囲外）。
- **A2（報告のみ、合否なし）**: d の曲率比ごとの PASS 率と、PASS 率が 20% を下回る曲率比を報告する。曲率比 25% の検出を要求しない。
- **A3（報告のみ）**: c・e の結果。
- A1 または A4 を満たさなければパラメータ・tolerance・シナリオを調整しない。他の成果物を完成させ、**Stage 1 FAILED** と記録して #46 に報告し、止まる。

この節は最初のシミュレーション実行より前に記録した。実行前のファイルの bytes/hash は `prerun_freeze.json` に保存する。

## 範囲・前提

証拠区分: `solver_free_design_and_simulation_unregistered`。
基準 HEAD: `82cb953`（integration を pull し、そこから `exp/issue46-fd08v2-stage1`）。
指示: [Stage 1 指示文 v2](../../issues/46_fd08_v2_stage1_instruction_2026_10_06.md)。背景: [B 計画 v2](../../issues/46_fd08_B_decision_plan_2026_10_06.md)。

暫定パラメータは未承認。sigma0=3 µN は仮定であり実測ノイズではない。
B-3〜B-7、ladder、被覆規則、予算の変更は未決。この実装・測定はそれらを承認・登録しない。
R5 は FAIL のまま。評価器を R5 に適用しない（dry-run も禁止）。既存の登録コード・criteria・証跡を変更しない。
新規 src/scripts/tests は `docs/evidence/fd08_candidate_c_calibration_*` を読まない。
評価器は `cfd_sdf.fd08_*` を import しない。
R6/formal 登録、criteria/dataset 作成、Kaggle 操作、solver 実行、#23 のスコープ変更、direction 登録、epsilon_m 意味の変更は実施しない。
全 qualification flag は false: shape_update_allowed=false, fd_oracle=false,
field_gradient=false, reverse=false, optimizer=false, topology=false
（登録コードの6 flagを照合、変更しない）。

## 実行前に固定する計算設計

- numpy `2.5.2`、Python `3.12.13`。乱数は `Generator(PCG64(seed_ij))`。
- base_seed=461006、seed_ij=base_seed+1000×scenario_number+ladder_point_count。scenario_number は 1 始まり、順番 a1,a2,b（a1→a2、σ=1.5,3,4 µN）,c（a1→a2、w=.04,.07）,d（g=-.104→-.17、曲率比=.10,.15,.25,.50,1,1.5,2）,e。
- 各点で絶対ノイズを先に、相対偏差を後に引く。ノイズなし・相対偏差なしでも二つの標準正規乱数を消費する。c の算式は S_true×(1+w×z)+絶対ノイズ。
- 各シナリオ・ladder 2000 試行。同一観測に既定 tolerance と同時 5/10/15/20% 感度を適用。sigma0,rho,nested_drop,k_mag は変えない。
- ladder は geomspace(.5,5,6)、geomspace(.3,5,8)。上端比較は d のみ geomspace(.5,15,7)。d の k は 5 mm 基準で固定し、15 mm 比較でも同じ真の係数を使う。
- 固定20合成入力は別 seed base_seed+900000+1000×scenario_number+ladder_point_count から生成し、a1,a2,b,c,d,e と6/8点へ配分する。対応表を保存する。既定値を添付する。
- JSON は sort_keys=True,allow_nan=False、floatは有効数字12桁。JSON hash は同一環境内の再現確認用で、機種間では参考値。図は作成を要求されていないため数値表で報告する。
- WLS は OLS pilot→重み→WLS の1回のみ。共分散は公称値を使い、chi²/dof のスケールを使わない。反復の2回目と1回目で g が約1e-4異なる例が仕様書に報告されており、この変更は採用しない（本成果物の測定値ではない）。
- 符号項目の部分集合は指示文の括弧 k=1,…,3、入れ子安定性は nested_drop=2。n<4 は UNRESOLVED。計算可能な項目1〜5の不合格は項目6より優先して FAIL。

## Git 運用

ユーザー指定の integration=`codex/kaggle-batch-migration` と `--no-ff` merge を使う。
これは `docs/git_branching_strategy.md` の trunk 運用とは異なる、今回の明示的な運用指示である。
意図した新規ファイルのみを commit/push し、#46 に報告して止まる。
