# 現状確認と研究方向の再検討（2026-10-24）

**位置づけ:** [phase_plan.md](phase_plan.md) に従属する検討記録であり、順序・閾値・登録の権威ではない。新しい CFD・登録・凍結・閾値・計算資源の変更を開始しない。既存の判定（FID01_GO、T2-0b/c/d NO-GO、GEOM03_NO_GO など）は変更しない。本書の数値のうち「概算」「本書の推定」と明記したものは判断材料であって、登録値でも ETA でもない。全 qualification flag は false、`shape_update_allowed=false` のまま。

**依頼:** ユーザー（2026-10-24）「現状のgithub状態とローカルを確認してゴールまでの道筋や研究としての方向性を検討してほしい。調査もしてほしい。論文とかwebサイトとか、数学的な内容とかね」。

**照合した状態:** GitHub `ramhachi/CFD_opt_sdf`、統合ブランチ `codex/kaggle-batch-migration` = `458e2df5`（2026-10-23）、`main` = `bdf65333`（2026-09-11）、open PR #71（head `dcd0d406`）、issue #20–#70、ローカル checkout と worktree 19 件（§1）。

---

## 0. 要約

1. **現在地。** M0〜M3a は完了。M3a FID-01 は `FID01_GO`：事前登録した広いモード（pitch・camber・reflex と組合せ）の downforce 差分は、Re 80 で WaterLily（flow_32/48）から body-fitted OpenFOAM 3 格子へ符号と 0.57–0.77 の保持率で転写した。純 heave は転写しない（z 位相未標本化）。幅規則 R3 の複合ゲート検証は `GEOM03_NO_GO`、高 Re 評価器 T2-0 は b/c/d 三連 NO-GO。次は **SCREEN-01 (#64) の登録 → XV-01 (#65)**、その後 **M4 (#66)**。
2. **GitHub の整備点。** `main` は統合ブランチの 1057 コミット後ろで、トップの README は 2026-09-09 の density/Brinkman 方針を「採用済み」と書いたまま。PR #71（計画同期＋GEOM-03）は mergeable のまま未 merge。PR #9 は 8 月から放置。ローカルには merge 済みブランチ 13 本と worktree 19 件、未 push の UNC-01 中間コミット 5 件（内容は統合済み）。
3. **研究としての論点。** 本プロジェクトは「SDF-native トポロジー最適化」から、事実上「解析的な親形状＋5 個の広いモードの低次元形状最適化を固定格子で安く評価し、独立 CFD で検証する」研究へ移っている。これは敗北ではなく、FID01_GO で初めて実証された**使える部分**である。主張と名称をそこに合わせ、SDF 表現は「任意トポロジーを将来扱える表現層」として残すのが整合的（§3、§6.3）。
4. **数学的な整理の要点（§5）。** (a) 共通位相の対差分は配置分散の 92–99 % を消している（CRN と同じ）。(b) 片側 FD の最適ステップはノイズと曲率から約 3°と推定され、設計振幅と同程度なので「勾配を諦めてスクリーニング＋応答曲面」は Moré–Wild の理論と整合する。(c) **選択バイアス（optimizer's curse）**：WaterLily で K 候補の最大を選ぶと、OpenFOAM へ持ち込んだときの期待利得は σ_disc·E[max_K] だけ目減りする。K=10–30、σ_disc≈0.7–1.5e-3 N で 0.3–1.1 %。SCREEN の最小利得 2.70 %（OF 期待 1.75 %）と XV の床 1.27 % の差 0.5 % と同程度で、**XV-01 の合格確率を左右する**。(d) T2-0 の「ピーク位置の検定」はノイズ 0.020 Cl に対して構造的に検出力不足だった（二次近似から直接出る）。高 Re 評価器の検証契約は「attached 領域の傾き」に置くべき。
5. **提案する道筋（§6）。** 直近は #64/#65 を既定路線で進めつつ、登録に「選択バイアスの開示と上乗せ」「z 位相」「候補数 K の上限」を入れる。M4 では (A) Re 80 の L1/L2 を方法論の成果として閉じる、(B) 高 Re 評価器を「attached 領域・差分契約・固定メッシュ morph・LTS」で再定義する、の二層で進めることを推奨する。SDF-native の将来は「境界法線変位の滑らかな spectral basis（Sobolev 勾配と同値）」として広いモードを一般化する方向が、文献と今回の経験の両方に支持される。

---

## 1. GitHub とローカルの状態

### 1.1 ブランチと PR

| 対象 | 状態（2026-10-24 fetch 後） | 所見 |
| --- | --- | --- |
| `codex/kaggle-batch-migration` | `458e2df5`（2026-10-23、FID-01 merge）。全作業の統合先。CI なし（`.github/workflows/ci.yml` は `main` のみ） | 権威は `docs/phase_plan.md` と `docs/STATE.md`。[branching strategy](git_branching_strategy.md) の「Current practice」どおり |
| `main` | `bdf65333`（2026-09-11、PR #14）。統合ブランチに対して 0 先行 / 1057 後ろ | 既定ブランチが陳腐化。新しいエージェントや検索は別のプロジェクト状態を見る。トップの `README.md` は density/Brinkman を「採用方針（2026-09-09）」と記述 |
| PR #71 `chore/roadmap-evidence-review-2026-10-22` → 統合 | OPEN、MERGEABLE、+9,529/−43、69 files、7 commits、head `dcd0d406` | 内容：計画の同期（STATE/phase_plan/README）、GEOM-03 登録・実行・`GEOM03_NO_GO`、EVAL-VALID-01 監査、SCREEN/XV 準備資料。STATE.md と phase_plan の最新節はこの PR 側にある |
| PR #9 `feat/g2-front-wing-geometry-contract` → `main` | OPEN（2026-08-04 から更新なし） | 旧アーキテクチャ（G2 front-wing contract）。close か明示的な保留の記録が要る |
| PR #34 | CLOSED（draft、do not merge） | 問題なし |
| リモートブランチ | `main`、`codex/kaggle-batch-migration`、`chore/roadmap-evidence-review-2026-10-22`、`feat/g2-front-wing-geometry-contract` の 4 本 | 2026-10-14 の「merge 済みは削除」運用は守られている |

### 1.2 Issue

open 15 件。進行の本線は #63（ROADMAP index）→ #64 SCREEN-01 → #65 XV-01 → #66 M4 → 条件付き #67 L3-01 / #69 EVAL-PT-01。結果付きで open のまま残るもの：#62 FID-01（`FID01_GO` 記録済み、close 可）、#61 UNC-01（`M2_COMPLETE`、close 可）。駐車中（再開条件つき）：#23 GRAD-03、#28 SDF-02、#20 SDF-01、#53 SRCMAP-02、#32 TOPO-01、#33 LOOP-01、#40 PIPE-01。2026-10-22 以降に close：#70 GEOM-03、#68 EVAL-VALID-01、#57 T2-0、#60 MODE-01、#59 JOB-02。

### 1.3 ローカル

| 場所 | 状態 | 所見 |
| --- | --- | --- |
| `/Users/sota/projects/FomulaTMU/CFD2026_09`（主 checkout） | `fix/w3-w4-verifier-bugs` = `fa3a42e0`（統合済み）。未追跡 `docs/issues/45_xfid_openfoam_environment_gate.md` 1 件 | 主 checkout が古い feature branch を向いたまま。未追跡ファイルは #45（XFID）の環境ゲート記録と思われ、commit するか破棄するかの判断が要る（内容未確認） |
| worktree 19 件 | うち detached HEAD 10 件（終了済みセッションの残骸）、ブランチ付き 9 件 | `~/.codex/worktrees/issue45-root-certifier-integration` が統合ブランチを `1ba26684` で checkout（`458e2df5` より古い。codex 側は pull が必要）。`~/.codex/worktrees/roadmap-review-2026-10-22` が PR #71 の head |
| ローカルブランチ | 13 本が統合ブランチに完全に含まれる（削除候補）。`claude/determined-dewdney-cb54d3` のみ 5 コミット（`f60e8108`〜`8c77c022`、UNC-01 の登録改訂・analyzer・regate）が未 push | 5 コミットの成果物（`docs/unc01_registration_2026_10_20.md` 等）は統合ブランチの `c2f1ee29`（M2_COMPLETE）に別経路で入っている。差分を一度 `git diff` で確認した上で、ブランチは削除してよい見込み |
| OpenFOAM | local Docker（LOCAL-OF-01、U3/X3 系は Kaggle と bit 一致）。V3 の 4 並列ジョブは 2026-10-23 に終了、稼働コンテナなし | FID-01 の V3 は 1 case 約 8 h（1 CPU） |
| Kaggle | T4 は週 30 GPU h、同時 GPU セッション 2、同時 CPU セッション 5 | 本書時点の残量は未確認 |

### 1.4 整備の提案（実行していない）

1. **PR #71 を `--no-ff` で統合する。** STATE.md と phase_plan の最新節が PR 側にあるため、未 merge のままだと統合ブランチの `docs/STATE.md` が GEOM-03 と FID-01 の最終状態を反映しない。2026-10-14 の「merge は自由」の運用と整合する。
2. **`main` の扱いを決める。** 選択肢は (a) 統合ブランチを `main` に `--no-ff` で merge して既定ブランチの陳腐化を解消する、(b) 既定ブランチを `codex/kaggle-batch-migration` に変える、(c) 現状維持を README に明記する。(a) か (b) を推奨。CI トリガーも合わせる。
3. **トップ `README.md` を現行方針（SDF-native、2026-09-26）に合わせる。** 現状は外部から見た第一印象が 1 か月半前の方針になっている。
4. **PR #9 を close**（旧 G2 front-wing contract）か、残す理由を PR に記録する。
5. **ローカル掃除。** merge 済み 13 ブランチと detached worktree 10 件の削除、`claude/determined-dewdney-cb54d3` の差分確認後の削除、主 checkout の branch を統合ブランチへ切替、未追跡ファイルの処置。
6. **#61 / #62 を close**（結果コメントは残っている）。

---

## 2. 到達点（証拠ベース）

| 段 | 結果 | 主張の上限 | 根拠 |
| --- | --- | --- | --- |
| 表現・genesis | v17（h=0.025 m、121×65×49）→ v18 解析的 stadium 平板（t=0.1153 m、翼弦 1.219 m、迎角 20.4°、span 0.875 m、地上高 0.65 m） | v18 は新しい親。v17 の力・傾き・ノイズは引き継がない | [v18 plan](v18_mode01_plan_2026_10_19.md) |
| 幾何ゲート | GEOM-02 v2 13 gate、P22-v2 `N_phi<=8272`（v18 では非拘束、slack 728）、smoothed-volume ±10 %、clearance ≥0.15 m | `min_feature_width`（R0, 1.5h）は格子表現性の限界で製造値ではない。R3 複合は `GEOM03_NO_GO`（K2/K4 反例） | [WIDTH-RULE](width_rule_decision_2026_10_20.md)、[GEOM-03](https://github.com/ramhachi/CFD_opt_sdf/blob/dcd0d4066ea9ca34c6de3ca22c4e2fe9704d9a13/docs/evidence/geom03_2026_10_23/result.md) |
| 勾配 | forward AD は tangent が遠方場の角で指数成長（DIAG1–5、`R4_INCONCLUSIVE`）。tie-averaged AD も BLOCKED。FD oracle は補間検証のみ PASS（FD-08 24/24）。OpenFOAM adjoint は SIGFPE | solver map の導関数経路は両 convention で閉塞。原因は未特定 | phase_plan 2026-10-08/09、[T2-0 summary](t20_summary_for_m4_2026_10_22.md) |
| 低次元ステップ | LOWDIM-01 accept +0.12 %（1.25 mm）、LOWDIM-02A drag 制約 FAIL、LOWDIM-04B 最小ステップのみ accept（利得は Stage V 分解能以下）、OPT-01 v1 REJECT（flow_24/32 不一致） | v17 上の局所 4 方向 basis は実用利得に届かない | phase_plan 2026-10-09〜15 |
| 格子・配置 | flow_24 は小応答で符号反転、flow_32 ≈ flow_48（pitch +3.1° で比 0.980 [0.962, 0.999]）。flow_40 は Poisson 交絡。1 セル x 並進は非ゼロ（−1.65e-3 N） | 格子収束の主張ではない。R3「flow_32 で提案、flow_48 で確認」 | [UNC-01](evidence/unc01_2026_10_20/analysis.md)、GRID-02、GRIDRES-01 |
| 不確かさ（M2） | 共通位相の対差分 σ_d = 2.1–5.5e-4 N（downforce、広いモード、flow_32、P=6）、σ_d ∝ |Δ|^0.5。E2 入力 S_b 0.0067 / S_c 0.0101 / S_d 0.0034 | 1 親・選んだモード・in-plane 位相のみ。z（地上高）位相は未標本化 | UNC-01 |
| 忠実度（M3a） | `FID01_GO`：tier A 8/8（camber ±、reflex −、pitch ±0.7、組合せ）が V1/V2/V3 で同符号、V1 保持 0.57–0.77、V3/V1 傾き 1.086 [0.992, 1.181]、Kendall τ 0.85。純 heave ±31.1 は FAIL、局所 bump は判定不能 | 事前登録した設計の差分について。最適化器が選ぶ設計ではない。Re 80 層流 | [FID-01](evidence/fid01_2026_10_21/analysis.md) |
| 高 Re 評価器（T2-0） | a：SA-WF med30 が実験曲線に約 5 %。b：`T20B_NO_GO`（ピーク h/c 0.179 vs 0.134、G3b、G6）。c：`T20C_MORPH_NO_GO`（0.224 では morph で全 gate 通過、0.134 は基準メッシュ依存 26–29 %、0.09 は定常が収束せず）。d：`T20D_NO_GO`（URANS は定常に落ちる、ピーク検定は非診断的、92 分/評価） | 2D 断面・1 Re・SA-WF・Kaggle CPU。評価器は不採用。参照 Table 15 は著者が定性用途に限定（`REFERENCE_INADEQUATE`） | [T2-0 summary](t20_summary_for_m4_2026_10_22.md)、[reference audit](https://github.com/ramhachi/CFD_opt_sdf/blob/dcd0d4066ea9ca34c6de3ca22c4e2fe9704d9a13/docs/eval_valid01_reference_audit_2026_10_22.md) |
| 計算環境 | WaterLily は Kaggle T4、OpenFOAM は local Docker（amd64 noble、Rosetta、bit 一致）。harness・JOB-02 per-run placement は byte gate PASS | gmsh 系（T2-0）はローカル不一致で Kaggle のまま | [LOCAL-OF-01](local_openfoam_env_gate_2026_10_20.md) |

**単位費用（本書の概算、既存記録から逆算）。** flow_32：約 7 分/state-phase（FID-01 の 4 kernel・72 run・約 8.5 GPU h）。flow_48：約 37–39 分/state（GRID-02 の 2,200–2,340 s）。OpenFOAM local：V1 約 1.8 分/case、V2 約 28 分/case、V3 約 8–9 h/case（FID-01 の kernel 時間から）。Kaggle：週 30 GPU h、同時 GPU 2・CPU 5。

---

## 3. 中心仮説の現在地と研究としての論点

### 3.1 何が示されたか

中心仮説「安価な固定格子ソルバーで見つけた改善が独立の body-fitted CFD でも残る」は、2026-09-12 の Brinkman 代理（9/12 で負）以来、初めて **FID-01 で正の登録結果**を得た。ただし成立条件が明確になっている：

- **広いモード**（支持率 ≥0.5、界面変化 ≥5 mm、体積中立）の **対差分**であること。局所 bump（σ 0.05–0.4 m のガウス法線オフセット）は 0.68 % にも届かず判定不能。
- **格子位相を揃えた差分**であること（§5.1）。絶対値は flow_32→48 で 0.8 %（v18）〜8–10 %（v17）動く。
- **z 方向（地上高）に体を動かさない**こと。純 heave は z 位相が未標本化のため転写しない。

### 3.2 何がまだか

- **最適化器が選んだ形状**での転写（L1/L2）。FID-01 自身が「WaterLily の argmax は WaterLily が過大評価する設計を好む」と注記している（§5.4 で定量化）。
- **目標物理**（高 Re・乱流・moving ground）の評価器。T2-0 は三連 NO-GO、代替は未登録。
- **SDF-native の固有の売り**（任意トポロジー、再初期化、全場勾配）は全て駐車・閉塞：#32 TOPO-01 未着手、#28 REINIT-04 は親上で非有界、#23 AD は BLOCKED。

### 3.3 事実上のピボットを認識する

現行の設計変数は、解析的 stadium 平板のパラメータ変換（pitch・camber・reflex・twist・sweep）であり、SDF はそれを格子上に書き出す表現層になっている。これは 2026-09-26 に掲げた「SDF-native トポロジー最適化」とは別の研究に見えるが、評価の仕方（固定格子で差分を測り独立 CFD で検証する、事前登録で判定する）はそのまま活きている。研究の主張をここに合わせると、

- **主張（L1/L2 版）**：「固定格子 immersed-boundary ソルバーは、広いモードの差分という量に限れば body-fitted CFD と符号・順位・一定の保持率で一致し、その範囲内でスクリーニング最適化と独立検証が成立する」。
- **SDF の役割**：形状の表現と幾何ゲート（幅・clearance・体積）の統一的な計算、将来のトポロジー変化への拡張口。設計変数そのものではない。

これは「SDF の節点値を設計変数にする」Yamasaki ら（2010）型から、「SDF は表現、設計変数は滑らかな境界モード」へ重心を移すことに当たり、Kreissl–Pingen–Maute（2011）や Wang & Wang（2006）が場を正則化・パラメータ化した系譜に乗る（§4.6）。この整理は §6.3 の「広いモードを spectral basis として一般化し、SDF 表現を保つ」に繋がる。名称を変える必要はないが、issue #63 の L1/L2 の記述と README の方針記述は、この現状に合わせて書き直す価値がある。

---

## 4. 文献との対応（調査結果）

（§4 は本書作成時に 4 本並列で行った文献調査（Crossref・出版社・arXiv・GitHub API で書誌確認）の要約。確認できなかった項目は `UNVERIFIED`。書誌は付録 A。調査の範囲は 2026-10-24 時点の公開情報で、全文を読んだものは一部に限る。）

### 4.1 多忠実度最適化としての本プロジェクト

本プロジェクトの「flow_32 が提案し、flow_48 と OpenFOAM が確認する」構造は、Alexandrov ら（1998, 2001）の **variable-fidelity model management**（低忠実度モデルで step を提案し、高忠実度の実測/予測比で受理する trust-region）と同型である。保持率 0.57–0.80 は Haftka（1991）と Chang ら（1993）の乗法スケーリング `f_hi ≈ β(x)·f_lo`、Kennedy & O'Hagan（2000）の自己回帰 co-Kriging `f_hi = ρ f_lo + δ(x)` の ρ に相当し、Gano ら（2005）はこの β(x) を Kriging でモデル化する。高忠実度の勾配を持たない本プロジェクトに最も近い形式的枠組みは March & Willcox（2012）の **高忠実度導関数不要の多忠実度 trust-region**（fully-linear な誤差モデル）で、収束の保証がある。Peherstorfer ら（2018）の分類では本方式は「filtering」（低忠実度で絞り、生き残りだけを高忠実度で評価）。Toal（2015）と Fernández-Godino ら（2019）は、忠実度間の相関が低いと多忠実度は高忠実度単独に劣ると警告しており、局所モードで傾き誤差が 50–100 % だった結果はまさにその「使ってはいけない領域」である。順位相関の閾値を与える論文は見つからなかった（UNVERIFIED）。

### 4.2 数値ノイズと有限差分

Moré & Wild（2011）の ECNoise は、等間隔の標本の k 階差分からノイズ水準 ε_f を推定する手法で、本プロジェクトの配置 sweep はそのまま入力になる。Moré & Wild（2012）は片側差分の誤差 `(h/2)|f''| + 2ε_f/h` の最小化から `h ≈ 2√(ε_f/|f''|)`、中心差分は `(h²/6)|f'''| + ε_f/h` から `h* ∝ (ε_f/|f'''|)^{1/3}` を与え、「h を倍にしても推定 f'' が安定しなければ曲率支配」という診断規則を置く。Shi ら（2022）はこの h を二分法で適応的に選ぶ手続きを与えており、STEP-01/#48 で問題になった「ステップ幅の契約」の既製品である。Giunta ら（1994）は格子起因のノイズで勾配最適化が壊れ、低次の応答曲面で回復した古典例で、R5 の選択はこれに倣う。Peter & Dwight（2010）、Martins & Hwang（2013）は FD/AD/adjoint の精度比較の総説。

### 4.3 共通乱数・対差分・選択

Glasserman & Yao（1992）は応答が共有乱数に単調なら CRN が分散を減らすことを証明し、Kleinman–Spall–Naiman（1999）は CRN により FD 型確率近似の収束率が k^{-1/3} から k^{-1/2} に上がることを示す（R4「世代内共通位相」の形式的な利得）。Spall（1992）の SPSA は次元に依らず 2 評価で勾配推定を与え、4–6 次元の安価な代替になる。選択の統計では、Kim & Nelson（2001）の KN 手続きが indifference zone δ で正しい選択確率を保証し（CRN 対応）、Chen ら（2000）の OCBA は僅差の候補へ反復を集中させる（「flow_48 で確認」の原理）。「改善 > 2·max(S_b,S_c)」は片側 α≈2.3 % の z 検定で、閾値ちょうどの真の効果に対する検出力は 50 %、80 % には δ ≥ 2.8 σ_d/√n が要る。K 候補を同じ α でスクリーニングすると偽陽性は約 Kα に膨らむ（Bonferroni）ので、確認段は別の α を持つ二段選択として形式化するのがよい。位相平均を標準手続きとして述べた IB/LBM 文献は見つからず（UNVERIFIED）、同位相の対差分は方法として明示する価値がある。

### 4.4 ノイズ下の微分不要最適化と小予算の計画

Conn–Scheinberg–Vicente（2009）の fully-linear モデル理論の上に、Chen–Menickelly–Scheinberg（2018）の STORM（ノイズ付きモデルと関数推定の確率的 trust-region）があり、対差分に基づく受理の抽象として適切。Cartis ら（2019）の Py-BOBYQA/DFO-LS はノイズ対応（再始動・平均化）を備える既製ソルバー。Moré & Wild（2009）、Rios & Sahinidis（2013）のベンチマークでは小予算ではモデルベース法が勝ち、進化法（CMA-ES）は桁違いの評価数を要する。Santoni ら（2023）は 10D+50 評価で BO が CMA-ES に勝つと報告。20–50 評価・4–6 次元では二次応答曲面は固定計画の一回限り GP/BO と実質同じで、R5 の「CMA-ES/BO を使わない」は費用面で正当化される。Jones & Nachtsheim（2011）の definitive screening design は 2k+1 run（4–6 モードで 9–13 run）で主効果を二次効果から分離して推定でき、スクリーニング段の設計として候補になる。

### 4.5 WaterLily・BDIM・AD の既知の限界

- **BDIM の滑らかさは核幅 ε のスケールまで**（Weymouth & Yue 2011、Maertens & Weymouth 2015）。10 nm の白色ノイズに対する非比例応答は、固定格子法の「離散イベント」（セル状態の切替：Lee ら 2011、Seo & Mittal 2011、Ho & Farhat 2023）と、unfitted 離散化では片側微分可能性しか保証されないという Berggren（2023）の結果で説明できる。
- **WaterLily 自身の位置依存ノイズ**：issue #137（2024-06）「Noisy dependence of the body position」は iD の鋭いカットオフが原因で、PR #283「Type stable kernels and μ₀ threshold」（2026-05-04 merge、v1.7.0）で修正された。**本プロジェクトの固定版 1.8.0（2026-06-26）は修正後**なので、FD-05/06 の非比例性はこの既知バグではない（本書で GitHub API により確認）。v1.9.0〜v1.10.0（2026-09-30〜10-21）の変更は未調査。
- **AD**：Weymouth & Font（2025）の「differentiable」は ForwardDiff による forward-mode で、短い時間窓・スカラーパラメータの例に限られ、長い時間積分や Poisson 反復の tangent 成長は論じていない。reverse-mode は PR #285（Enzyme、CPU のみ、Poisson を IFT で随伴化、既定 tolerance で ForwardDiff と 10 % 不一致、1e-10 で 2.4e-5）が open、issue #358「AD derivative noise on Float32」（2026-10-08）も open で、DIAG5 の「±1 ulp で tangent が 60 % 変わる」と同じ症状である。
- **tangent の指数成長の理論**：非線形反復が収束しても厳密な線形化が不安定（スペクトル半径 >1）な例が Campobasso & Giles（2004）、不完全収束の定常解での随伴発散が Krakos & Darmofal（2010）にあり、本プロジェクトの DIAG1–5 と一致する。Gilbert（1992）と Christianson（1994）は、打ち切った内部反復を微分すると別の写像の導関数になることを示し、「Poisson 反復回数を固定しても遅れるだけで消えない」（DIAG4）はこの帰結。Hückelheim ら（2024）は AD の落とし穴を分類し、本プロジェクトの失敗類型（固定回数の不動点ループ、分岐、線形ソルバー）を網羅する。文献が収束している解決は **unroll せず定常残差を陰的に微分する**（Blondel ら 2022；Buhendwa ら 2025 の discrete-loss；Zhang–Fan–Wang 2026 Warp-Geo）か、tangent を time-marching ではなく安定化した線形解法（RPM/GMRES）で解くこと。遠方場の角から成長が始まる現象に特化した文献は見つからなかった。
- **薄板**：Lauber–Weymouth–Limbert（2022）は薄い膜では Poisson 行列自体の修正（BDIM-σ）が必要と示す。v16/v17 の「面が節点上に乗り |∇φ|≈0」はこの系統の問題で、v18 の解析平板（傾いた面、丸い縁）で回避したのは文献と整合する。
- **Brinkman の転写失敗**：Theulings ら（2023）は Navier–Stokes + Darcy 罰則が「固体」を漏れさせ劣った局所解を生むことを示し（VANS 型の下界で修正）、Kreissl & Maute（2012）は罰則依存性から XFEM へ移った。Alexandersen（2022）は Brinkman 最適解を body-fitted で再評価する明示的な転写検査を行っている。2026-09-12 の 9/12 負の結果はこの既知の機構に該当する。

### 4.6 レベルセット／SDF 最適化、幅制御、低次元パラメータ化

- **SDF を設計変数にする先例。** Yamasaki, Nomura, Kawamoto, Sato, Izui, Nishiwaki（2010）は離散化した SDF の節点値を設計変数にし、更新のたびに再初期化する。Kreissl–Pingen–Maute（2011）は格子 LBM 上で節点レベルセットを設計変数にしつつ、局所感度のノイズを避けるために場を正則化・パラメータ化した。Yaji ら（2014）も LBM 上で φ に Tikhonov 正則化を掛ける。**「力ではなく場を正則化する」のが共通の先例**で、本プロジェクトの広いモードはその極端な形（低次元基底）に当たる。Wang & Wang（2006）の RBF パラメータ化レベルセットは、φ を滑らかな基底で表して CFL・再初期化を不要にした原型で、§6.3 の方向と同じ。Allaire–Dapogny–Frey（2014）はレベルセット（トポロジー）と body-fitted 再メッシュ（精度）を交互に使う方法で、本プロジェクトの「安いソルバー／OpenFOAM」分業の形式化と見なせる。
- **流体の LS/XFEM/CutFEM TO。** Zhou & Li（2008）、Duan ら（2008）、Challis & Guest（2009、要素単位 0/1 の離散レベルセット＝セル数体積の先例）、Kreissl & Maute（2012）、Villanueva & Maute（2017、3D・Re<200・固定背景格子）、Deng ら（2011, 2013、非定常随伴）、Dilgen ら（2018、RANS の完全離散随伴）。Alexandersen & Andreasen（2020）の 186 本の総説は、ほぼ全てが定常層流であることを確認している。トポロジー変化を後から足す現在の答えは Høghøj–Andreasen–Maute（2025）の密度ベース hole seeding。
- **形状微分と離散化精度。** Hadamard の構造定理（Sokołowski & Zolésio 1992；Delfour & Zolésio 2011）により一次変分は境界法線速度だけに依存する。Hiptmair–Paganini–Sargheini（2015）は有限要素離散化で shape gradient の **volume form が boundary form より速く収束**することを示し、固定格子で境界局所の φ 摂動応答がノイジーになる直接の説明を与える。Berggren（2010）は離散随伴を体積（メッシュ変形）表現で書く統一法、Allaire–Dapogny–Jouve（2021）は H¹/Riesz の「拡張・正則化」の現代的な教科書。Nadarajah & Jameson（2000）、Giles & Pierce（2000）は連続勾配が離散モデルと O(h) で不整合であることを示し、immersed ソルバーはまさにその O(h) の中にいる。
- **幅・最小特徴寸法。** Allaire–Jouve–Michailidis（2016）は最小・最大肉厚を SDF のオフセット集合上の積分制約として定式化し（φ が真の SDF であることに依存）、Guo–Zhang–Zhong（2014）と Xia & Shi（2015）は骨格距離、Hermann & Noël（2026）が最新。密度法側では Lazarov–Wang–Sigmund（2016）、Zhou ら（2015）、Wang–Lazarov–Sigmund（2011）が、特徴寸法はフィルタ半径 R と投影閾値で定義され **R が数セル以上でなければ格子独立にならない**ことを示す。Barrera–Geiss–Maute（2022）はレベルセットの零集合を密度フィルタに結び、分解能を格子に対して明示的に論じる。本プロジェクトの「1.5h 規則は格子表現性の限界」（WIDTH-RULE）は、この「約 3–4h 以下は解像不能」という密度法の経験則と一致する。
- **低次元の滑らかなパラメータ化と条件数。** Hicks–Henne（1978）、CST（Kulfan 2008）、FFD（Samareh 2004）、SVD モード（Poole–Allen–Rendall 2015；Masters ら 2017 の比較では SVD が自由度あたり最も効率的）、ライブラリ不要のモードと **曲率・勾配の上限**（Kedward–Allen–Rendall 2020）。Jameson–Martinelli–Pierce（1998）の Sobolev 平滑化は勾配の低域通過フィルタ、Schmidt & Schulz（2009）、Schmidt ら（2013）、Schulz–Siebenborn–Welker（2016）は抗力型汎関数の shape Hessian が正の階数の擬微分作用素であること（高波数ほど悪条件）と、Sobolev／Steklov–Poincaré 前処理がその数学的対処であることを示す。Vertex Morphing（Hojjat ら 2014；Bletzinger 2014）、Kröger & Rung（2015）、Stück & Rung（2011）は、フィルタ核の半径が設計空間そのものを定義することを CFD で実証している。Laplace–Beltrami 固有基底（Vallet & Lévy 2008）を設計変数に使った査読済み CFD 論文は見つからなかった（Dick 2022 の学位論文が Sobolev 平滑化に用いるのみ）。採用するなら新規の方法として提示する。
- **量子化された体積制約。** Osher–Sethian（1988）、Wang–Wang–Guo（2003）の `∫H_ε(φ)`（ε≈1–2h）、Osher & Santosa（2001）の体積を保つ射影速度、Allaire ら（2004）の Lagrange 乗数、Challis（2010）の 0/1 要素体積と二分法乗数（整数体積の先例）、Dunning & Kim（2015）の逐次 LP、Sivapuram & Picelli（2018）・Picelli ら（2021）の整数線形計画（TOBS）。本プロジェクトの smoothed-volume band は前者の標準形で、`N_phi ≤ 8272` を厳密に扱う必要が出たときの選択肢は Challis 型二分法か TOBS 型 ILP。

### 4.7 地面効果翼の検証データと RANS の限界

- **一次データ。** Tyrrell 026 単要素翼の基準は Zerihan & Zhang（2000）、Gurney flap は Zerihan & Zhang（2001）、wake/LDA・PIV は Zhang & Zerihan（2003）、二要素翼は Zhang & Zerihan（2003, AIAA J）、総説は Zhang, Toet & Zerihan（2006）。**trip・不確かさの詳細は Zerihan（2001）の学位論文にしかなく**、Table 15 を傾向用途に限る EVAL-VALID-01 の判断は著者の記述と整合する。Cranfield の系列（Correia ら 2014；Roberts ら 2016, 2017, 2019）は、Re の 0.8e5 の差で downforce が最大 320 % 変わること、**trip 位置だけで層流剥離泡が後縁剥離に変わり downforce が落ちる**ことを示しており、trip が不明なデータに対する絶対 Cl の契約は定義上 ill-posed である。新しい候補として Zhou, Overmars & Westerweel（2026, Exp. Fluids）が Tyrrell 026 断面の高速 PIV と力の再構成を報告している（TU Delft。データと不確かさの提供依頼に値する）。2018 年以降の FSAE スケールで不確かさ付きの公開データセットは見つからなかった。
- **RANS の到達点。** Mahon & Zhang（2005, 2006）では k-ω SST と realizable k-ε が Cp・wake で最良、傾向は再現するが Cl の誤差棒は示されない。**Vogt, Barber & Leonardi（2007）は同じ Tyrrell 断面（Re 458,800）の 2D 定常 RANS が h/c < 0.15 で「固有の非定常性のため収束しなかった」と報告**しており、T2-0c の `T20C_MORPH_NO_GO`（0.134・0.09 で定常が収束せず）は文献の既知の挙動である。ピーク高さの不一致（0.179 vs 0.134）は、後縁剥離の開始がモデル依存（SST / realizable k-ε / SA で異なる）で trip が不明であることから説明でき、必ずしもメッシュ欠陥ではない。低 Re（<1e6）の翼では遷移モデル（γ-Reθ、k-kL-ω）が圧力場・wake に必要（Roberts ら 2019）だが、地面効果の反転翼に特化した γ-Reθ の検証は見つからなかった。
- **安い評価器。** 定常領域（h/c ≳ 0.2）では壁解像 SA/SST の 2D 定常 RANS と TMR 流の入れ子格子族・力の定常判定で数分/点が現実的。非定常領域では pseudo-transient（localEuler/LTS；理論は Kelley & Keyes 1998）が文献上は候補だが、翼での simpleFoam vs pimpleFoam-LTS の査読済み比較はない（EVAL-PT-01 が埋める空白）。パネル法＋鏡像（Katz 1985；Coulliette & Plotkin 1996）は中程度の h/c での順位づけに使えるが、force-reduction 領域での精度の記述はない。AirfRANS（Bonnet ら 2022）は地面なし。adjointOptimisationFoam は定常領域で SA 壁関数つきに対応するが、地面効果での収束問題の先例は見つからなかった。
- **FSAE の先行研究。** Wordley & Saunders（2006, 2007）の実車・風洞、Craig & Passmore（2014）、Pacheco, Marta & Eça（2024：1/3 スケール車の風洞 vs SST、傾向は一致するが「不確かさが定量検証を制限」）など。**最適化した前翼を風洞・走行で検証した査読論文は見つからなかった**。これは本プロジェクトの L2/L3 が埋め得る空白である。
- **検証規格。** ASME V&V 20（E = S − D と u_val、合否判定ではない）、Roache（1994, 1997）の GCI、Celik ら（2008）、Eça & Hoekstra（2014：非単調な格子列に頑健な最小二乗）。地面効果の反転翼で GCI/V&V 20 の形式的な不確かさを付けた RANS 検証論文は見つからなかった。

---

## 5. 数学的な整理（プロジェクトの数値を当てはめる）

### 5.1 共通位相の対差分は共通乱数（CRN）である

同じ配置 p で候補 c と親 b を評価した差 d_p = J_c(p) − J_b(p) の分散は
`Var(d) = σ_c² + σ_b² − 2 ρ σ_c σ_b`。
UNC-01 の測定 σ_d / (√2 σ_F) = 0.11–0.29（downforce）から、配置誤差の候補・親間の相関は ρ ≈ 1 − (0.11…0.29)² ≈ **0.92–0.99** と推定される。つまり共通位相は配置分散の 9 割以上を消している。これはシミュレーション最適化で言う common random numbers（Glasserman & Yao 1992、Fu 2015）そのもので、「差分で判定する」設計は理論的に正しい選択である。なお σ_d ∝ |Δ|^0.5 という測定（加法でも乗法でもない）は、差分が大きいほど配置誤差の相関が落ちることを意味し、大振幅の候補ほど位相数を増やす必要がある（UNC-01 の `phases_needed(r)=ceil(9r²)`）。

判定規則「改善 > 2·max(S_b, S_c)」は片側 α ≈ 2.3 % の z 検定に相当し、閾値ちょうどの真の効果に対する検出力は 50 % しかない。80 % の検出力には δ ≥ 2.8 σ_d/√n が要る。K 候補を同じ α で篩うと偽陽性は約 Kα に膨らむので、flow_48 と OpenFOAM の確認段は別の α を持つ二段選択（Kim & Nelson 2001 の indifference-zone 手続きが形式化）として書くのがよい。

### 5.2 片側 FD の最適ステップはノイズと曲率で決まる

ノイズ水準 ε_f の関数の片側差分の誤差は `(h/2)|f''| + 2ε_f/h` で、最小は `h* ≈ 2√(ε_f/|f''|)`、中心差分は `(h²/6)|f'''| + ε_f/h` で `h* ∝ (ε_f/|f'''|)^{1/3}`（Moré & Wild 2012）。UNC-01 の pitch の偶数部（曲率）−6.4e-4 N @3.1° から f'' ≈ 1.3e-4 N/deg²、ε_f に σ_d = 5.5e-4 N を置くと **h* ≈ 3–4°**（係数の取り方で 2.9–4.1°）。これは設計で使う振幅（0.7–3.1°）と同程度であり、「小さいステップはノイズ支配、大きいステップは曲率支配」で片側 FD 勾配に使える窓がない。STEP-01（片側応答は 2.5–5 mm で曲率支配、中心差分は 12.5 mm まで符号一定）と LOWDIM-01（受理は 1.25 mm のみ）は、この見積りと整合する。中心差分は曲率項を消すので符号は保つが、三次項と ε/h が残る。応答曲面（二次）は曲率を明示的にモデル化するので、R5「スクリーニング＋小さな応答曲面」は Moré–Wild 的にも妥当な代替である。

### 5.3 多忠実度最適化としての位置づけ

WaterLily（低忠実度、L）と OpenFOAM（高忠実度、H）の関係は、FID-01 の数値では **乗法補正** `J_H(Δ) ≈ β J_L(Δ)`、β ∈ [0.57, 0.77]（平均約 0.65）で表せる。Alexandrov ら（2001）の model management では、低忠実度モデルを補正して trust region 内で使い、一次整合（勾配の一致）があれば高忠実度最適解への収束が保証される。本プロジェクトは高忠実度の勾配を持たないので、該当するのは **高忠実度導関数を要しない多忠実度 trust-region**（March & Willcox 2012）か、co-Kriging（Kennedy & O'Hagan 2000）型の補正付き代理である。FID-01 の 8 設計（V1/V2/V3）は、まさにその補正モデル β(設計) を学習するデータになっている。

このとき SCREEN の最小利得は次の不等式で読める：OpenFOAM で床 g_H,min = 1.27 % を期待値で超えるには `β_min · g_L ≥ g_H,min` すなわち **g_L ≥ 1.27/0.57 ≈ 2.2 %**、登録値 2.70 % はこれを満たす（期待 OF 利得 0.65×2.70 = 1.75 %、最悪 1.54 %）。ただし §5.4 の選択バイアスを加えると余裕は 0.3–0.5 % しかない。

### 5.4 選択バイアス（optimizer's curse）の大きさ

K 個の候補を WaterLily の推定で順位づけし最大を選ぶと、選んだ候補の推定値は真値（ここでは OpenFOAM の値を β で戻したもの）より平均で `σ · E[max of K standard normals]` だけ大きい（Smith & Winkler 2006 の「optimizer's curse」）。E[max_K] は K=10 で約 1.55、K=30 で約 2.04（Blom 近似；上界 √(2 ln K)）。σ には候補ごとの WL–OF 乖離の散らばりを置く：FID-01 の V3 残差 SD 1.45e-3 N（配置 SE を含むので上限寄り）、または保持率の設計間散らばり（0.57–0.77、SD ≈0.07）× Δ ≈1e-2 N ≈ 7e-4 N。親 downforce 0.266 N で正規化すると（本書の推定）：

| K | σ=7e-4 N | σ=1.0e-3 N | σ=1.45e-3 N |
| --- | --- | --- | --- |
| 10 | 0.4 % | 0.6 % | 0.8 % |
| 30 | 0.5 % | 0.8 % | 1.1 % |

SCREEN の最小利得 2.70 % を OF に写した期待値 1.75 % と XV の床 1.27 % の差は 0.48 % なので、**最小利得ぎりぎりの候補は選択バイアスだけで XV の床を割り得る**。XV-01 を holdout として置く設計は正しい（バイアスは XV の推定には乗らない）が、合格確率は下がる。SCREEN 登録への含意：(a) K を小さく保つか段階的に絞る、(b) 最終候補の WL 利得に選択バイアス相当の上乗せ（例：g_L ≥ 4 %、OF 期待 2.6 %）を目標にする、(c) 選んだ候補の WL 推定を shrinkage（James–Stein 型）で補正して開示する。いずれも新しい登録事項であり、ここでは数値を置かない。

### 5.5 位相平均は周期関数の数値積分である

力 F(θ) は格子に対する sub-cell 位相 θ ∈ [0,h)² の周期関数で、位相平均は周期トーラス上の積分。F が滑らかなら等間隔点（rank-1 lattice rule）は Fourier 係数の減衰に従って spectral に収束し、Halton や R2 のような低食い違い列（誤差 O(log P / P)）より有利になる（Sloan & Joe 1994）。ただし F は immersed boundary の cell-crossing で C^0 程度の滑らかさしか持たない可能性があり、その場合は差は小さい。実務上の含意は二つ：(1) 世代内で共通位相を使う限り積分誤差は差分で相殺する（§5.1）、(2) **z 位相を標本化していない**ことが heave の転写失敗に直結した。heave を固定する SCREEN 案はこれを回避するが、親と候補が z 方向に異なる占有を持つ組合せ（twist・camber は局所的に z を動かす）では残差が残り得る。XV-01 の 3 軸 shift（±0.5–4 mm）が OF 側でこれを部分的に標本化している。

### 5.6 ピーク近傍の検定は構造的に検出力が低い

Cl(h) ≈ Cl* − ½ κ (h − h*)² の近傍では、ノイズ σ で h* を推定した誤差は δh* ≈ σ/(κ·W)（W は当てる窓幅）。T2-0 の曲線（ピーク余裕 0.022 Cl、0.134→0.179 の間隔 0.045）から κ ≈ 22 Cl/(h/c)²、再メッシュのノイズ σ ≈ 0.020 Cl を入れると δ(h/c)* ≈ 0.02、すなわち候補ピーク位置の間隔の半分。G2 のピーク位置検定が「非診断的」になったのは、データ量や格子の問題以前に二次近似から予測できたことである。高 Re 評価器の検証契約は、導関数が O(1) で定常 RANS が収束する **attached 領域（h/c ≳ 0.18）の傾き dCl/d(h/c)、dCl/dα** に置くのが検出力の面で正しい。T2-0c が h/c 0.224 で全 gate を通したことと整合し、プロジェクトの「差分で判定する」哲学とも一致する。なお Vogt, Barber & Leonardi（2007）は同じ Tyrrell 断面・同じ Re の 2D 定常 RANS が h/c < 0.15 で固有の非定常性のため収束しなかったと報告しており、T2-0c/d の挙動は文献で既知である（§4.7）。

### 5.7 体積制約の量子化

`N_phi = Σ_nodes H(−φ)` は整数で、smoothed volume `Σ H_ε(−φ)`（ε ≈ 1.5h）は微分可能。レベルセット法の標準（Osher–Sethian、Allaire–Jouve–Toader 2004）は後者を用いる。v18 では P22-v2 が非拘束（slack 728）になり、10 % の smoothed-volume band が実質の体積制約になった。shear 型のモード（camber・reflex・twist・sweep・dihedral）は厳密に体積中立なので、制約は能動にならず、応答曲面の設計空間を箱型に保てる。これは §5.4 の K を増やさずに済む副次効果もある。 将来 `N_phi` を厳密に扱う必要が出た場合の先例は、Challis（2010）の 0/1 体積と二分法乗数、Osher & Santosa（2001）の体積保存射影、Sivapuram & Picelli（2018）の整数線形計画である（§4.6）。

### 5.8 なぜ広いモードだけが転写するか（spectral な説明）

Hadamard の構造定理により、形状汎関数の一次変分は境界の法線変位 V·n だけに依存し `J'(Ω)[V] = ∫_Γ g (V·n) ds`。抗力・揚力型汎関数の shape Hessian は正の階数の擬微分作用素として振る舞い（Schmidt & Schulz 2009；Eppler & Harbrecht）、境界摂動の波数 k に対して応答が |k|^α（α>0）で増幅される一方、immersed-boundary 核（幅 ~h）の離散化誤差と sub-cell 配置ノイズは k ~ 1/h に集中する。したがって高波数（局所）モードの応答は離散化アーティファクトに支配され、低波数（広い）モードは解像される。勾配法の文献での対処は **Sobolev 勾配**（Jameson；Schmidt & Schulz）＝勾配の低域通過フィルタで、これは設計空間を広いモードに制限することと同値である。FID-01 の「広いモードは転写、局所 bump は判定不能」はこの枠組みの実測例と読める。§6.3 の提案（境界法線変位の spectral basis）はこの同値性に基づく。

---

## 6. ゴールまでの道筋（提案）

### 6.1 直近：M3b（#64 SCREEN-01 → #65 XV-01）

既定路線（[SCREEN/XV 準備資料](https://github.com/ramhachi/CFD_opt_sdf/blob/dcd0d4066ea9ca34c6de3ca22c4e2fe9704d9a13/docs/screen_xv_preparation_2026_10_23.md)：heave 固定・5 広いモード・R0-clean 有限 pool・manual/random 対照・flow_32 提案 / flow_48 確認）に、本書から次を**登録時の検討項目**として加えることを提案する。

1. **選択バイアスの開示と上乗せ**（§5.4）：候補数 K と使った σ_disc を登録に書き、最終候補の WL 利得目標を g_min より上に置くか、shrinkage 推定を併記する。
2. **位相**：世代内は共通位相、最終候補は未使用位相（k≥11）の全集合。z 位相は WaterLily では標本化しないと明記し、XV の 3 軸 shift に委ねる。
3. **応答曲面**：3 変数 full quadratic（10 係数）なら 15 点以上。1 モードずつの ±A* スクリーニング（10 state）→ 上位 3 モードの応答曲面（15 state）→ 対照（manual 3、random 10）→ 親で、約 40 state × 共通位相 2 ≈ 80 run（flow_32、約 10 GPU h）＋最終候補 3 × 6 位相（2 h）＋ flow_48 3 × 4 位相（約 8 h）＝ **約 20 GPU h**（本書の概算、週 30 h 枠内）。
4. **XV-01**：A′（V1 16 対、V2/V3 各 4 対、96 case）を最初から選ぶ。V2/V3 の自由度 3 は精度保証ではないが、A（df=1）では区間が無意味に広い。費用は V1 約 2 h、V2 約 7.5 h、V3 16 case × 8 h ≈ 128 CPU h（4 並列で約 1.5 日、本書の概算）。
5. **drag 制約**：FID の G5 は drag 制約の PASS ではない。同位相 drag 差分の非増加を片側不確かさ込みで判定する規則を先に固定する。

### 6.2 M4（#66）の選択肢と推奨

| 選択肢 | 内容 | 推奨 |
| --- | --- | --- |
| A. Re 80 の L1/L2 を方法論の成果として閉じる | XV-01 の結果（PASS でも FAIL でも）を「固定格子差分スクリーニングの転写範囲」の登録済み結論として記録し、論文化の核にする | **推奨（必須）**。FAIL なら原因分解（選択バイアスか、保持率か、制約か）を登録して research NO-GO/限定成功を書く |
| B. 高 Re 評価器を再定義する | (i) 主張範囲を attached 領域（h/c ≳ 0.18、剥離前）に限定、(ii) 検証契約を絶対 Cl から **傾き dCl/d(h/c)、dCl/dα** に変更（§5.6）、(iii) 固定メッシュ morph（T2-0c で 0.224 が全 gate 通過）、(iv) 費用は EVAL-PT-01 の LTS で回復、(v) 参照は EVAL-VALID-01 の条件表に基づく attached 領域の点列。trip 位置は一次効果（Roberts ら 2017）なので、絶対 Cl ではなく trip を固定した上での傾きを契約にする。新データ候補として Zhou, Overmars & Westerweel（2026）の Tyrrell 026 PIV（TU Delft）への提供依頼を検討 | **推奨（条件付き）**。新規登録が必要。FSAE 前翼は剥離前の領域で運用するのが設計上も妥当で、ピーク以下は目的関数側の制約（剥離余裕）で避ける |
| C. 評価器を変える（LM 遷移、3D、別 solver、GPU 貸出） | 費用 3.5 h/case 以上、または B6 の発火 | 後回し。B で attached 領域の差分が解像できなければ検討 |
| D. research NO-GO | 評価器が成立せず、Re 80 でも XV が失敗 | 判定規則を今のうちに事前登録しておく（§7） |

### 6.3 SDF-native の将来像：広いモードの一般化

5 個の解析モードは、境界法線変位 V·n の**低波数基底**の手作り版である（§5.8）。一般化の候補：

- 境界（または設計領域）上の Laplace–Beltrami 固有関数、あるいは滑らかな RBF の低次元基底で V·n を展開し、φ はその変位を SDF として再構成する（表現は SDF のまま、設計変数は係数）。
- 広さは固有値（波数）で、幅・clearance・体積はこれまでの幾何ゲートで制御する。R0 の 1 セル occupancy の問題は、基底の最小波長を h の数倍以上に制限することで原理的に回避できる。
- 基底の最小波長（または Vertex Morphing 型のフィルタ半径）を h の数倍以上に置く根拠は Lazarov ら（2016）・Barrera ら（2022）の「数セル未満は解像不能」であり、Kedward ら（2020）の曲率・勾配上限を併用すれば非転写形状を事前に排除できる。幅・肉厚は Allaire–Jouve–Michailidis（2016）型の SDF オフセット積分で物理量として制御できる（R0 の代替）。
- トポロジー変化（#32）はこの基底では表せないので、L1/L2 の後に別契約で扱う。候補は Høghøj–Andreasen–Maute（2025）の hole seeding。再初期化（#28）はこの構成では不要になる（解析的に SDF を再生成するため）。必要になれば Hartmann ら（2010）の零集合・体積を動かさない拘束付き再初期化がある。
- Laplace–Beltrami 固有基底を CFD 形状最適化の設計変数にした査読済み先例は見つからなかった（§4.6）。採用するなら、Vallet & Lévy（2008）を基底の、Burger（2003）・de Gournay（2006）を H¹ 内積の根拠として、新規の方法として提示する。

これは「SDF を設計変数にする」（Yamasaki ら 2010 型）から「SDF を表現に使い、設計変数は滑らかな境界モード」へ重心を移す提案であり、勾配なし（応答曲面）でも勾配あり（将来 adjoint が得られれば Sobolev 勾配）でも同じ基底が使える。

### 6.4 成果物（論文化）の方向

今の証拠で書けるのは、最適化の成功談ではなく**方法論の体系的評価**である：
1. 固定格子 immersed-boundary の差分応答がどの条件（モードの広さ・位相整合・格子）で body-fitted CFD と一致するか（M2/M3a の登録結果、負の結果も含む）。
2. forward AD の tangent 不安定（DIAG1–5）と FD oracle の限界（FD-05〜08、STEP-01）という、差分可能 CFD の実務上の落とし穴。
3. 事前登録・凍結・独立レビューを CFD 最適化研究に適用した運用（PROC-01）。
4. 2D 地面効果 RANS の評価器としての限界（T2-0b/c/d）。調査では最適化した FSAE 前翼を風洞・走行で検証した査読論文は見つからず（§4.7）、L2/L3 が成立すればそれ自体が空白を埋める。
XV-01 の結果が加われば 1 が「最適化器が選んだ形状」まで伸びる。宛先は方法論寄り（Computers & Fluids、Structural and Multidisciplinary Optimization、Journal of Computational Physics の短報）か、FSAE 寄り（SAE Technical Paper）かを M4 で決める。

### 6.5 計算資源

現行の枠（Kaggle T4 週 30 h、OpenFOAM local）で M3b は収まる見込み（§6.1 の概算）。GPU 貸出 API への切替トリガー（週 30 h 超、latency 支配、Kaggle に載らない run）は M3b では発火しない。B（高 Re 再定義）で LTS が 20–30 分/評価に収まれば CPU 側も Kaggle 5 セッションか local で足りる。

---

## 7. リスクと撤退条件

| リスク | 兆候 | 事前に決めておく対応 |
| --- | --- | --- |
| SCREEN が g_min を超える候補を出さない | 5 モードの応答曲面が平坦、または drag 制約が全候補を落とす | `SCREEN01_NO_GAIN` を記録し M4 へ。pool の補充や閾値変更をしない（既定） |
| XV で選択バイアス分だけ目減りして床を割る | WL 利得 2.7–3.5 % の候補が OF で 1.0–1.3 % | 原因分解：保持率 β の設計依存か、選択バイアスか。後者なら SCREEN の K・目標利得の再登録（1 回） |
| heave 以外でも z 占有が変わる組合せが転写しない | twist・camber を含む候補の V1 保持率が 0.5 を割る | XV の 3 軸 shift の z 成分を分離して報告。z 位相の WaterLily 標本化（JOB-02 の拡張）を M5 以降の登録に回す |
| 高 Re で attached 領域でも傾きが基準メッシュ依存 | morph した dCl/dα が base mesh で 10 % 以上ばらつく | B を bounded NO-GO とし、C か D へ |
| 研究全体の終了条件 | XV FAIL（原因分解後の再登録 1 回も FAIL）かつ B が NO-GO | research NO-GO として到達範囲（M2/M3a の正の結果、方法論）を記録して閉じる |

---

## 8. 次アクション（issue 対応表）

| 順 | アクション | issue | 種別 |
| --- | --- | --- | --- |
| 1 | PR #71 を `--no-ff` で統合し、`docs/STATE.md` を最新にする | #63 | 運用 |
| 2 | §1.4 の整備（main、README、PR #9、worktree、#61/#62 close） | — | 運用 |
| 3 | SCREEN-01 の登録起草：準備資料＋§6.1 の 5 項目。3 角度レビュー 1 回、ソースレビュー 1 回 | #64 | 登録（Claude 起草、codex 実装） |
| 4 | SCREEN 実行（約 20 GPU h）→ 最終候補凍結 | #64 | 実行 |
| 5 | XV-01 登録（A′ 96 case、single-finalist SE、drag 制約）→ 実行（約 1.5 日） | #65 | 登録・実行 |
| 6 | M4 判断資料：A（必須）、B（attached 領域・傾き契約・固定メッシュ morph・LTS）の登録案、D の判定規則 | #66, #69 | 計画 |
| 7 | §6.3 の spectral basis を M5 の候補として issue 化（着手は L1/L2 後） | #32/#33 の前段 | 計画 |
| 8 | 論文化の骨子（§6.4）を docs に起票 | #63 | 記録 |

---

## 付録 A. 参考文献

書誌は 2026-10-24 に Crossref / 出版社 / arXiv / GitHub で確認した。確認できなかった項目は `UNVERIFIED` を付す。本文での用途は §4 と §5 に書いた。

**A.1 多忠実度・モデル管理（§4.1、§5.3）**
- Alexandrov, Dennis, Lewis, Torczon (1998). A trust-region framework for managing the use of approximation models in optimization. Structural Optimization 15(1):16–23. doi:10.1007/BF01197433
- Alexandrov, Lewis, Gumbert, Green, Newman (2001). Approximation and model management in aerodynamic optimization with variable-fidelity models. J. Aircraft 38(6):1093–1101. doi:10.2514/2.2877
- Haftka (1991). Combining global and local approximations. AIAA J. 29(9):1523–1525. doi:10.2514/3.10768
- Chang, Haftka, Giles, Kao (1993). Sensitivity-based scaling for approximating structural response. J. Aircraft 30(2):283–288. doi:10.2514/3.48278
- Eldred, Giunta, Collis (2004). Second-order corrections for surrogate-based optimization with model hierarchies. AIAA 2004-4457. doi:10.2514/6.2004-4457
- Gano, Renaud, Sanders (2005). Hybrid variable fidelity optimization by using a kriging-based scaling function. AIAA J. 43(11):2422–2433. doi:10.2514/1.12466
- Kennedy & O'Hagan (2000). Predicting the output from a complex computer code when fast approximations are available. Biometrika 87(1):1–13. doi:10.1093/biomet/87.1.1
- Forrester, Sóbester, Keane (2007). Multi-fidelity optimization via surrogate modelling. Proc. R. Soc. A 463:3251–3269. doi:10.1098/rspa.2007.1900
- Han & Görtz (2012). Hierarchical kriging model for variable-fidelity surrogate modeling. AIAA J. 50(9):1885–1896. doi:10.2514/1.J051354
- March & Willcox (2012). Provably convergent multifidelity optimization algorithm not requiring high-fidelity derivatives. AIAA J. 50(5):1079–1089. doi:10.2514/1.J051125
- Peherstorfer, Willcox, Gunzburger (2018). Survey of multifidelity methods in uncertainty propagation, inference, and optimization. SIAM Review 60(3):550–591. doi:10.1137/16M1082469
- Toal (2015). Some considerations regarding the use of multi-fidelity Kriging in the construction of surrogate models. Struct. Multidisc. Optim. 51(6):1223–1245. doi:10.1007/s00158-014-1209-5
- Fernández-Godino, Park, Kim, Haftka (2019). Issues in deciding whether to use multifidelity surrogates. AIAA J. 57(5):2039–2054. doi:10.2514/1.J057750
- Smith & Winkler (2006). The optimizer's curse: skepticism and postdecision surprise in decision analysis. Management Science 52(3):311–322. doi:10.1287/mnsc.1050.0451（§5.4）

**A.2 数値ノイズ・有限差分・微分不要最適化（§4.2、§4.4、§5.2）**
- Moré & Wild (2011). Estimating computational noise. SIAM J. Sci. Comput. 33(3):1292–1314. doi:10.1137/100786125
- Moré & Wild (2012). Estimating derivatives of noisy simulations. ACM TOMS 38(3):1–21. doi:10.1145/2168773.2168777
- Shi, Xie, Xuan, Nocedal (2022). Adaptive finite-difference interval estimation for noisy derivative-free optimization. SIAM J. Sci. Comput. 44(4):A2302–A2321. doi:10.1137/21M1452470
- Shi, Xuan, Oztoprak, Nocedal (2023). On the numerical performance of finite-difference-based methods for derivative-free optimization. Optim. Methods Softw. 38(2):289–311. doi:10.1080/10556788.2022.2121832
- Giunta, Dudley, Haftka, Grossman, Mason, Watson (1994). Noisy aerodynamic response and smooth approximations in HSCT design. AIAA 94-4376. doi:10.2514/6.1994-4376
- Peter & Dwight (2010). Numerical sensitivity analysis for aerodynamic optimization: a survey of approaches. Computers & Fluids 39(3):373–391. doi:10.1016/j.compfluid.2009.09.013
- Martins & Hwang (2013). Review and unification of methods for computing derivatives of multidisciplinary computational models. AIAA J. 51(11):2582–2599. doi:10.2514/1.J052184
- Conn, Scheinberg, Vicente (2009). Introduction to Derivative-Free Optimization. SIAM. doi:10.1137/1.9780898718768
- Chen, Menickelly, Scheinberg (2018). Stochastic optimization using a trust-region method and random models. Math. Program. 169(2):447–487. doi:10.1007/s10107-017-1141-8
- Cartis, Fiala, Marteau, Roberts (2019). Improving the flexibility and robustness of model-based derivative-free optimization solvers. ACM TOMS 45(3):1–41. doi:10.1145/3338517
- Kelley (2011). Implicit Filtering. SIAM. doi:10.1137/1.9781611971903
- Larson, Menickelly, Wild (2019). Derivative-free optimization methods. Acta Numerica 28:287–404. doi:10.1017/S0962492919000060
- Moré & Wild (2009). Benchmarking derivative-free optimization algorithms. SIAM J. Optim. 20(1):172–191. doi:10.1137/080724083
- Rios & Sahinidis (2013). Derivative-free optimization: a review of algorithms and comparison of software implementations. J. Glob. Optim. 56(3):1247–1293. doi:10.1007/s10898-012-9951-y
- Santoni, Raponi, De Leone, Doerr (2023). Comparison of Bayesian optimization algorithms for BBOB problems in dimensions 10 and 60. GECCO '23 Companion 2390–2393. doi:10.1145/3583133.3596314
- Jones & Nachtsheim (2011). A class of three-level designs for definitive screening in the presence of second-order effects. J. Quality Technol. 43(1):1–15. DOI UNVERIFIED
- Myers, Montgomery, Anderson-Cook (2016). Response Surface Methodology, 4th ed. Wiley.

**A.3 共通乱数・選択・事前登録（§4.3、§5.1）**
- Glasserman & Yao (1992). Some guidelines and guarantees for common random numbers. Management Science 38(6):884–908. doi:10.1287/mnsc.38.6.884
- Kleinman, Spall, Naiman (1999). Simulation-based optimization with stochastic approximation using common random numbers. Management Science 45(11):1570–1578. doi:10.1287/mnsc.45.11.1570
- Spall (1992). Multivariate stochastic approximation using a simultaneous perturbation gradient approximation. IEEE Trans. Autom. Control 37(3):332–341. doi:10.1109/9.119632
- Fu (ed.) (2015). Handbook of Simulation Optimization. Springer. doi:10.1007/978-1-4939-1384-8
- Kim & Nelson (2001). A fully sequential procedure for indifference-zone selection in simulation. ACM TOMACS 11(3):251–273. doi:10.1145/502109.502111
- Chen, Lin, Yücesan, Chick (2000). Simulation budget allocation for further enhancing the efficiency of ordinal optimization. Discrete Event Dyn. Syst. 10(3):251–270. doi:10.1023/A:1008349927281
- Maron & Moore (1993). Hoeffding races. NIPS 6, 59–66.
- Nosek, Ebersole, DeHaven, Mellor (2018). The preregistration revolution. PNAS 115(11):2600–2606. doi:10.1073/pnas.1708274114
- Morris, White, Crowther (2019). Using simulation studies to evaluate statistical methods. Stat. Med. 38(11):2074–2102. doi:10.1002/sim.8086
- Siepe ら (2026). Why, when, and how to (or not to) preregister a simulation study. PsyArXiv preprint（査読前）
- Sloan & Joe (1994). Lattice Methods for Multiple Integration. Oxford Univ. Press. doi:10.1093/oso/9780198534723.001.0001（§5.5）

**A.4 検証規格（§4.7、§6.2）**
- ASME V&V 20-2009 (R2016). Standard for Verification and Validation in Computational Fluid Dynamics and Heat Transfer.
- Roache (1994). Perspective: a method for uniform reporting of grid refinement studies. J. Fluids Eng. 116(3):405–413. doi:10.1115/1.2910291
- Roache (1997). Quantification of uncertainty in computational fluid dynamics. Annu. Rev. Fluid Mech. 29:123–160. doi:10.1146/annurev.fluid.29.1.123
- Celik, Ghia, Roache, Freitas (2008). Procedure for estimation and reporting of uncertainty due to discretization in CFD applications. J. Fluids Eng. 130(7):078001. doi:10.1115/1.2960953
- Eça & Hoekstra (2014). A procedure for the estimation of the numerical uncertainty of CFD calculations based on grid refinement studies. J. Comput. Phys. 262:104–130. doi:10.1016/j.jcp.2014.01.006
- Oberkampf & Roy (2010). Verification and Validation in Scientific Computing. Cambridge Univ. Press. doi:10.1017/CBO9780511760396

**A.5 WaterLily・BDIM・immersed boundary・AD（§4.5、§5.8）**
- Weymouth & Yue (2011). Boundary data immersion method for Cartesian-grid simulations of fluid-body interaction problems. J. Comput. Phys. 230(16):6233–6247. doi:10.1016/j.jcp.2011.04.022
- Maertens & Weymouth (2015). Accurate Cartesian-grid simulations of near-body flows at intermediate Reynolds numbers. CMAME 283:106–129. doi:10.1016/j.cma.2014.09.007
- Lauber, Weymouth, Limbert (2022). Immersed boundary simulations of flows driven by moving thin membranes. J. Comput. Phys. 457:111076. doi:10.1016/j.jcp.2022.111076
- Weymouth (2022). Data-driven multi-grid solver for accelerated pressure projection. Computers & Fluids 246:105620. doi:10.1016/j.compfluid.2022.105620
- Weymouth & Font (2025). WaterLily.jl: A differentiable and backend-agnostic Julia solver for incompressible viscous flow around dynamic bodies. Comput. Phys. Commun. 315:109748. doi:10.1016/j.cpc.2025.109748
- WaterLily.jl GitHub: issue #137（2024-06-27 → 2026-05-11 close）、PR #283（2026-05-04 merge）、PR #285（open）、issue #358（2026-10-08 open）；release v1.7.0 2026-05-11、v1.8.0 2026-06-26、v1.9.0 2026-09-30、v1.10.0 2026-10-21（GitHub API で確認）
- Gilbert (1992). Automatic differentiation and iterative processes. Optim. Methods Softw. 1(1):13–21. doi:10.1080/10556789208805503
- Christianson (1994). Reverse accumulation and attractive fixed points. Optim. Methods Softw. 3(4):311–326. doi:10.1080/10556789408805572
- Griewank & Walther (2008). Evaluating Derivatives, 2nd ed., SIAM, Ch. 15.
- Blondel ら (2022). Efficient and modular implicit differentiation. NeurIPS 35. arXiv:2105.15183
- Campobasso & Giles (2004). Stabilization of linear flow solver for turbomachinery aeroelasticity using recursive projection method. AIAA J. 42(9):1765–1774. doi:10.2514/1.1225
- Krakos & Darmofal (2010). Effect of small-scale output unsteadiness on adjoint-based sensitivity. AIAA J. 48(11):2611–2623. doi:10.2514/1.J050412
- Wang, Hu, Blonigan (2014). Least squares shadowing sensitivity analysis of chaotic limit cycle oscillations. J. Comput. Phys. 267:210–224. doi:10.1016/j.jcp.2014.03.002
- Schmid (2007). Nonmodal stability theory. Annu. Rev. Fluid Mech. 39:129–162. doi:10.1146/annurev.fluid.38.050304.092139
- Hückelheim, Menon, Moses, Christianson, Hovland, Hascoët (2024). A taxonomy of automatic differentiation pitfalls. WIREs Data Min. Knowl. Discov. 14(6):e1555. doi:10.1002/widm.1555
- Lee, Kim, Choi, Yang (2011). Sources of spurious force oscillations from an immersed boundary method for moving-body problems. J. Comput. Phys. 230(7):2677–2695. doi:10.1016/j.jcp.2011.01.004
- Seo & Mittal (2011). A sharp-interface immersed boundary method with improved mass conservation and reduced spurious pressure oscillations. J. Comput. Phys. 230(19):7347–7363. doi:10.1016/j.jcp.2011.06.003
- Yang, Zhang, Li, He (2009). A smoothing technique for discrete delta functions with application to immersed boundary method in moving boundary simulations. J. Comput. Phys. 228(20):7821–7836. doi:10.1016/j.jcp.2009.07.023
- Bao, Kaye, Peskin (2016). A Gaussian-like immersed-boundary kernel with three continuous derivatives and improved translational invariance. J. Comput. Phys. 316:139–144. doi:10.1016/j.jcp.2016.04.024
- Peskin (2002). The immersed boundary method. Acta Numerica 11:479–517. doi:10.1017/S0962492902000077
- Mittal & Iaccarino (2005). Immersed boundary methods. Annu. Rev. Fluid Mech. 37:239–261. doi:10.1146/annurev.fluid.37.061903.175743
- Ho & Farhat (2023). Aerodynamic optimization with large shape and topology changes using a differentiable embedded boundary method. J. Comput. Phys. 488:112191. doi:10.1016/j.jcp.2023.112191
- Berggren (2023). Shape calculus for fitted and unfitted discretizations: domain transformations vs. boundary-face dilations. Commun. Optim. Theory 2023:27. doi:10.23952/cot.2023.27
- Burman, Elfverson, Hansbo, Larson, Larsson (2018). Shape optimization using the cut finite element method. CMAME 328:242–261. doi:10.1016/j.cma.2017.09.005
- Alhashim, Hausknecht, Brenner (2025). Control of flow behavior in complex fluids using automatic differentiation. PNAS 122(8):e2403644122. doi:10.1073/pnas.2403644122
- Buhendwa, Bezgin, Karnakov, Adams, Koumoutsakos (2025). Data-driven shape inference in three-dimensional steady-state supersonic flows: optimizing a discrete loss with JAX-Fluids. Phys. Rev. Fluids 10:084902.
- Zhang, Fan, Wang (2026). Warp-Geo: differentiable geometry representation for dynamic-boundary simulation and shape optimization. arXiv:2609.20964（全文未読）
- Schmidt & Schulz (2009). Impulse response approximations of discrete shape Hessians with application in CFD. SIAM J. Control Optim. 48(4):2562–2580. doi:10.1137/080719844（§5.8）
- Jameson (2004). Efficient aerodynamic shape optimization. AIAA 2004-4369. doi:10.2514/6.2004-4369（Sobolev 勾配、§5.8）

**A.6 Brinkman / 多孔質モデルの転写（§4.5）**
- Theulings, Langelaar, van Keulen, Maas (2023). Towards improved porous models for solid/fluid topology optimization. Struct. Multidisc. Optim. 66:133. doi:10.1007/s00158-023-03570-4
- Kreissl & Maute (2012). Levelset based fluid topology optimization using the extended finite element method. Struct. Multidisc. Optim. 46(3):311–326. doi:10.1007/s00158-012-0782-8
- Kreissl, Pingen, Maute (2011). An explicit level set approach for generalized shape optimization of fluids with the lattice Boltzmann method. IJNMF 65(5):496–519. doi:10.1002/fld.2193
- Villanueva & Maute (2017). CutFEM topology optimization of 3D laminar incompressible flow problems. CMAME 320:444–473. doi:10.1016/j.cma.2017.03.007
- Alexandersen & Andreasen (2020). A review of topology optimisation for fluid-based problems. Fluids 5(1):29. doi:10.3390/fluids5010029
- Alexandersen (2022). Topography optimisation of fluid flow between parallel plates of spatially-varying spacing. Struct. Multidisc. Optim. 65:152. doi:10.1007/s00158-022-03243-8
- Dilgen, Dilgen, Fuhrman, Sigmund, Lazarov (2018). Topology optimization of turbulent flows. CMAME 331:363–393. doi:10.1016/j.cma.2017.11.029

**A.7 地面効果翼・RANS・FSAE（§4.7、§5.6、§6.2）**
- Zerihan & Zhang (2000). Aerodynamics of a single element wing in ground effect. J. Aircraft 37(6):1058–1064. doi:10.2514/2.2711
- Zerihan & Zhang (2001). Aerodynamics of Gurney flaps on a wing in ground effect. AIAA J. 39(5):772–780. doi:10.2514/2.1396
- Zerihan & Zhang (2001). A single element wing in ground effect; comparisons of experiments and computation. AIAA 2001-0423. doi:10.2514/6.2001-423
- Zhang & Zerihan (2003). Off-surface aerodynamic measurements of a wing in ground effect. J. Aircraft 40(4):716–725. doi:10.2514/2.3150
- Zhang & Zerihan (2003). Aerodynamics of a double-element wing in ground effect. AIAA J. 41(6):1007–1016. doi:10.2514/2.2057
- Zerihan (2001). An investigation into the aerodynamics of wings in ground effect. PhD thesis, Univ. Southampton. eprints.soton.ac.uk/426058
- Zhang, Toet, Zerihan (2006). Ground effect aerodynamics of race cars. Appl. Mech. Rev. 59(1):33–49. doi:10.1115/1.2110263
- Mahon & Zhang (2005). Computational analysis of pressure and wake characteristics of an aerofoil in ground effect. J. Fluids Eng. 127(2):290–298. doi:10.1115/1.1891152
- Mahon & Zhang (2006). Computational analysis of a inverted double-element airfoil in ground effect. J. Fluids Eng. 128(6):1172–1180. doi:10.1115/1.2353268
- Vogt, Barber, Leonardi (2007). Flow field phenomena about lift and downforce generating cambered aerofoils in ground effect. 16th Australasian Fluid Mechanics Conference（本文確認済み）；Vogt & Barber (2012). Int. J. Numer. Meth. Heat Fluid Flow 22(2). doi:10.1108/09615531211199809
- Ahmed, Takasaki, Kohama (2007). Aerodynamics of a NACA4412 airfoil in ground effect. AIAA J. 45(1):37–47. doi:10.2514/1.23872
- Correia, Roberts, Finnis, Knowles (2014). Scale effects on a single-element inverted wing in ground effect. Aeronaut. J. 118(1205):797–809. doi:10.1017/S0001924000009544
- Roberts, Finnis, Knowles (2016). Characteristics of boundary-layer transition and Reynolds-number sensitivity of three-dimensional wings of varying complexity operating in ground effect. J. Fluids Eng. 138(9):091106. doi:10.1115/1.4033299
- Roberts, Finnis, Knowles (2017). Forcing boundary-layer transition on a single-element wing in ground effect. J. Fluids Eng. 139(10):101205. doi:10.1115/1.4037036
- Roberts, Finnis, Knowles (2019). Modelling boundary-layer transition on wings operating in ground effect at low Reynolds numbers. Proc. IMechE D 233(11):2820–2837.
- Zhou, Overmars, Westerweel (2026). An accelerating inverted wing with ground effect: downforce measurement and reconstruction. Exp. Fluids 67(6):75. doi:10.1007/s00348-026-04191-5
- Langtry & Menter (2009). Correlation-based transition modeling for unstructured parallelized computational fluid dynamics codes. AIAA J. 47(12):2894–2906. doi:10.2514/1.42362
- Kelley & Keyes (1998). Convergence analysis of pseudo-transient continuation. SIAM J. Numer. Anal. 35(2):508–523. doi:10.1137/S0036142996304796
- Diskin, Thomas, Rumsey, Schwöppe (2015). Grid convergence for turbulent flows (invited). AIAA 2015-1746.
- Bonnet, Mazari, Cinnella, Gallinari (2022). AirfRANS. NeurIPS 2022 Datasets & Benchmarks. arXiv:2212.07564
- Katz (1985). Calculation of the aerodynamic forces on automotive lifting surfaces. J. Fluids Eng. 107(4):438–443. doi:10.1115/1.3242507
- Papoutsis-Kiachagias & Giannakoglou (2016). Continuous adjoint methods for turbulent flows, applied to shape and topology optimization: industrial applications. Arch. Comput. Methods Eng. 23(2):255–299. doi:10.1007/s11831-014-9141-9
- Pacheco, Marta, Eça (2024). Wind tunnel testing of a Formula Student vehicle for checking CFD simulation trends. Proc. IMechE D 238(14):4347–4363. doi:10.1177/09544070231203076
- Craig & Passmore (2014). SAE Int. J. Passeng. Cars–Mech. Syst. 7(2):575–585. doi:10.4271/2014-01-0596
- Karthikeyan & Radhakrishnan (2024). Optimizing high-lift airfoils for Formula Student vehicles. SAE 2024-01-5059. doi:10.4271/2024-01-5059
- Suvanjumrat ら (2025). AI-assisted CFD optimisation of multi-element wing angle of attack. Int. J. Thermofluids 30:101440. doi:10.1016/j.ijft.2025.101440

**A.8 レベルセット／SDF 最適化・形状微分・幅制御・パラメータ化（§4.6、§5.7、§5.8、§6.3）**
- Yamasaki, Nomura, Kawamoto, Sato, Izui, Nishiwaki (2010). A level set based topology optimization method using the discretized signed distance function as the design variables. Struct. Multidisc. Optim. 41(5):685–698. doi:10.1007/s00158-009-0453-6
- Wang & Wang (2006). Radial basis functions and level set method for structural topology optimization. IJNME 65(12):2060–2090. doi:10.1002/nme.1536
- Allaire, Jouve, Toader (2004). Structural optimization using sensitivity analysis and a level-set method. J. Comput. Phys. 194(1):363–393. doi:10.1016/j.jcp.2003.09.032
- Allaire, Dapogny, Frey (2014). Shape optimization with a level set based mesh evolution method. CMAME 282:22–53. doi:10.1016/j.cma.2014.08.028
- Allaire, Dapogny, Jouve (2021). Shape and topology optimization. Handbook of Numerical Analysis 22:1–132. doi:10.1016/bs.hna.2020.10.004
- Yamada, Izui, Nishiwaki, Takezawa (2010). A topology optimization method based on the level set method incorporating a fictitious interface energy. CMAME 199(45–48):2876–2891. doi:10.1016/j.cma.2010.05.013
- Sussman & Fatemi (1999). An efficient, interface-preserving level set redistancing algorithm and its application to interfacial incompressible fluid flow. SIAM J. Sci. Comput. 20(4):1165–1191. doi:10.1137/S1064827596298245
- Hartmann, Meinke, Schröder (2010). The constrained reinitialization equation for level set methods. J. Comput. Phys. 229(5):1514–1535. doi:10.1016/j.jcp.2009.10.042
- Delfour & Zolésio (2011). Shapes and Geometries, 2nd ed. SIAM. doi:10.1137/1.9780898719826
- Sokołowski & Zolésio (1992). Introduction to Shape Optimization. Springer. doi:10.1007/978-3-642-58106-9
- Hiptmair, Paganini, Sargheini (2015). Comparison of approximate shape gradients. BIT Numer. Math. 55(2):459–485. doi:10.1007/s10543-014-0515-z
- Berggren (2010). A unified discrete–continuous sensitivity analysis method for shape optimization. In Applied and Numerical PDEs, Springer, 25–39. doi:10.1007/978-90-481-3239-3_4
- Nadarajah & Jameson (2000). A comparison of the continuous and discrete adjoint approach to automatic aerodynamic optimization. AIAA 2000-0667. doi:10.2514/6.2000-667
- Giles & Pierce (2000). An introduction to the adjoint approach to design. Flow Turbul. Combust. 65:393–415. doi:10.1023/A:1011430410075
- Zhou & Li (2008). A variational level set method for the topology optimization of steady-state Navier–Stokes flow. J. Comput. Phys. 227(24):10178–10195. doi:10.1016/j.jcp.2008.08.022
- Duan, Ma, Zhang (2008). Shape-topology optimization for Navier–Stokes problem using variational level set method. J. Comput. Appl. Math. 222(2):487–499. doi:10.1016/j.cam.2007.11.016
- Challis & Guest (2009). Level set topology optimization of fluids in Stokes flow. IJNME 79(10):1284–1308. doi:10.1002/nme.2616
- Challis (2010). A discrete level-set topology optimization code written in Matlab. Struct. Multidisc. Optim. 41(3):453–464. doi:10.1007/s00158-009-0430-0
- Deng, Liu, Zhang, Liu, Wu (2011). Topology optimization of unsteady incompressible Navier–Stokes flows. J. Comput. Phys. 230(17):6688–6708. doi:10.1016/j.jcp.2011.05.004
- Yaji, Yamada, Yoshino, Matsumoto, Izui, Nishiwaki (2014). Topology optimization using the lattice Boltzmann method incorporating level set boundary expressions. J. Comput. Phys. 274:158–181. doi:10.1016/j.jcp.2014.06.004
- Høghøj, Andreasen, Maute (2025). Density-based hole seeding in XFEM level-set topology optimization of fluid problems. Struct. Multidisc. Optim. 68. doi:10.1007/s00158-024-03956-y
- Allaire, Jouve, Michailidis (2016). Thickness control in structural optimization via a level set method. Struct. Multidisc. Optim. 53(6):1349–1382. doi:10.1007/s00158-014-1141-8
- Guo, Zhang, Zhong (2014). Explicit feature control in structural topology optimization via level set method. CMAME 272:354–378. doi:10.1016/j.cma.2014.01.010
- Xia & Shi (2015). Constraints of distance from boundary to skeleton: for the control of length scale in level set based structural topology optimization. CMAME 295:525–542. doi:10.1016/j.cma.2015.07.015
- Hermann & Noël (2026). Length scale control for level set-based topology optimization through spread skeletons. Struct. Multidisc. Optim. 69. doi:10.1007/s00158-026-04312-y
- Barrera, Geiss, Maute (2022). Minimum feature size control in level set topology optimization via density fields. Struct. Multidisc. Optim. 65:94. doi:10.1007/s00158-021-03096-7
- Lazarov, Wang, Sigmund (2016). Length scale and manufacturability in density-based topology optimization. Arch. Appl. Mech. 86:189–218. doi:10.1007/s00419-015-1106-4
- Zhou, Lazarov, Wang, Sigmund (2015). Minimum length scale in topology optimization by geometric constraints. CMAME 293:266–282. doi:10.1016/j.cma.2015.05.003
- Wang, Lazarov, Sigmund (2011). On projection methods, convergence and robust formulations in topology optimization. Struct. Multidisc. Optim. 43:767–784. doi:10.1007/s00158-010-0602-y
- Hicks & Henne (1978). Wing design by numerical optimization. J. Aircraft 15(7):407–412. doi:10.2514/3.58379
- Kulfan (2008). Universal parametric geometry representation method. J. Aircraft 45(1):142–158. doi:10.2514/1.29958
- Samareh (2004). Aerodynamic shape optimization based on free-form deformation. AIAA 2004-4630. doi:10.2514/6.2004-4630
- Poole, Allen, Rendall (2015). Metric-based mathematical derivation of efficient airfoil design variables. AIAA J. 53(5):1349–1361. doi:10.2514/1.J053427
- Kedward, Allen, Rendall (2020). Towards generic modal design variables for aerodynamic shape optimisation. AIAA 2020-0543. doi:10.2514/6.2020-0543
- Kedward, Allen, Rendall (2020). Gradient-limiting shape control for efficient aerodynamic optimization. AIAA J. 58(9):3748–3764. doi:10.2514/1.J058977
- Masters, Taylor, Rendall, Allen, Poole (2017). Geometric comparison of aerofoil shape parameterization methods. AIAA J. 55(5):1575–1589. doi:10.2514/1.J054943
- Jameson, Martinelli, Pierce (1998). Optimum aerodynamic design using the Navier–Stokes equations. Theor. Comput. Fluid Dyn. 10:213–237. doi:10.1007/s001620050060
- Schmidt, Ilić, Schulz, Gauger (2013). Three-dimensional large-scale aerodynamic shape optimization based on shape calculus. AIAA J. 51(11):2615–2627. doi:10.2514/1.J052245
- Schulz, Siebenborn, Welker (2016). Efficient PDE constrained shape optimization based on Steklov–Poincaré-type metrics. SIAM J. Optim. 26(4):2800–2819. doi:10.1137/15M1029369
- de Gournay (2006). Velocity extension for the level-set method and multiple eigenvalues in shape optimization. SIAM J. Control Optim. 45(1):343–367. doi:10.1137/050624108
- Burger (2003). A framework for the construction of level set methods for shape optimization and reconstruction. Interfaces Free Bound. 5(3):301–329. doi:10.4171/IFB/81
- Hojjat, Stavropoulou, Bletzinger (2014). The Vertex Morphing method for node-based shape optimization. CMAME 268:494–513. doi:10.1016/j.cma.2013.10.015
- Kröger & Rung (2015). CAD-free hydrodynamic optimisation using consistent kernel-based sensitivity filtering. Ship Technol. Res. 62(3):111–130. doi:10.1080/09377255.2015.1109872
- Stück & Rung (2011). Adjoint RANS with filtered shape derivatives for hydrodynamic optimisation. Computers & Fluids 47(1):22–32. doi:10.1016/j.compfluid.2011.01.041
- Vallet & Lévy (2008). Spectral geometry processing with manifold harmonics. Comput. Graph. Forum 27(2):251–260. doi:10.1111/j.1467-8659.2008.01122.x
- Osher & Sethian (1988). Fronts propagating with curvature-dependent speed. J. Comput. Phys. 79(1):12–49. doi:10.1016/0021-9991(88)90002-2
- Wang, Wang, Guo (2003). A level set method for structural topology optimization. CMAME 192(1–2):227–246. doi:10.1016/S0045-7825(02)00559-5
- Osher & Santosa (2001). Level set methods for optimization problems involving geometry and constraints I. J. Comput. Phys. 171(1):272–288. doi:10.1006/jcph.2001.6789
- Dunning & Kim (2015). Introducing the sequential linear programming level-set method for topology optimization. Struct. Multidisc. Optim. 51(3):631–643. doi:10.1007/s00158-014-1174-z
- Sivapuram & Picelli (2018). Topology optimization of binary structures using integer linear programming. Finite Elem. Anal. Des. 139:49–61. doi:10.1016/j.finel.2017.10.006
- Sigmund (2007). Morphology-based black and white filters for topology optimization. Struct. Multidisc. Optim. 33:401–424. doi:10.1007/s00158-006-0087-x（#70 が参照）

## 付録 B. 本書で使った数値の出所

- σ_d、σ_F、S_b/S_c/S_d、flow_32/48 比、親の downforce 0.26374/0.26578 N：[UNC-01 analysis](evidence/unc01_2026_10_20/analysis.md)。
- 保持率 0.57–0.77、V3 残差 SD 1.45e-3 N、g_min 2.70 %、OF 床 1.27 %、Δ_lit 5.363e-3 N：[FID-01 analysis](evidence/fid01_2026_10_21/analysis.md)、[handoff](https://github.com/ramhachi/CFD_opt_sdf/blob/dcd0d4066ea9ca34c6de3ca22c4e2fe9704d9a13/docs/fid01_to_screen_xv_handoff_2026_10_23.md)（PR #71）。
- 偶数部 −6.4e-4 N @ pitch 3.1°：UNC-01 Q1。
- T2-0 の曲線余裕 0.022、再メッシュ σ 0.020、92 分/評価：[T2-0 summary](t20_summary_for_m4_2026_10_22.md)。
- 単位費用：FID-01 analysis「As run」、GRID-02 の記録（phase_plan 2026-10-16）。
- E[max_K] の近似：Blom の順序統計量近似 Φ⁻¹((K−0.375)/(K+0.25))。
