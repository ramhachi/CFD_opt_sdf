# ダウンフォース最適化のためのアーキテクチャ研究ノート

作成日: 2026-09-20
作成: OpenCode (`opencode-go/deepseek-v4.1-flash`)、ユーザー依頼による調査・提案
状態: supporting research note（**authoritative ではない**）
証拠クラス: 本文書は**外部文献・提案・推論**のみ。リポジトリの新しい証拠を主張しない。
位置づけ: [`phase_plan.md`](phase_plan.md) の下位文書。ロードマップ・実行順序・
ゲート・閾値・停止規則を変更しない。矛盾した場合は `phase_plan.md` と
[`problem_register_2026_09.md`](problem_register_2026_09.md) が優先する。

## 0. エグゼクティブサマリ

1. WP6（`evidence/fixed_shape_cross_fidelity_ranking_2026_09.json`）は
   **downforce = no_go（厚さ軸）、drag = unresolved だが符号 37/37 一致**という
   応答・因子特異的な判定を出した。これはアーキテクチャのグローバルな否定ではない。
2. Stage T の downforce は `C = 2/(Aref·U²)·∫ αmax·β·(U·(-ẑ)) dV`
   （`openfoam_extensions/porousDirectionalForce/README.md`、`.C:124`）という
   **体積シンク積分**である。揚力は本質的に界面の**圧力ジャンプ＋循環**で生じる量で
   あり、この推定量は smearing に対して最も不利な形である。
3. 文献は、密度法/Brinkman 法が「圧力場が直接の関心事」のケースで不正確になることを
   一貫して報告している（Kreissl et al. 2011; Theulings et al. 2023; Alexandersen &
   Andreasen 2020）。リポジトリは**速度漏れ**（既に合格）しか測っておらず、
   **圧力表現誤差を一度も測っていない**。これが最大の証拠ギャップである。
4. Brinkman 層の解像基準 `δ=√(ν/αmax)`, `m=δ/h≳1`（Angot 系、Boscolo et al. 2025）
   に対し、現行は `δ=2 mm`, `h=50 mm` → **m=0.04（25倍の未解像）**。αmax を上げると
   δ はさらに縮み、悪化する。αmax=250↔2500 で力が ≤8% しか動かないという WP6 の
   実測は、この「層がそもそも格子に存在しない」ことと整合する。
5. したがって「厚さ軸の代理定式化研究」（WP6 が登録した次手）は、**αmax スイープの
   繰り返しではなく**、(a) 推定量の再定式化、(b) 圧力表現の修復、(c) 界面の sharp 化、
   (d) ランキング統計の再設計、の4系統で行うのが正しい。
6. 最も費用対効果が高い次の一歩は、**既存 WP6 の T1 場（8–11 s/形状で再生成可能）に
   対する推定量比較**である。新しいソルバを書かずに「no_go が推定量の artifact か、
   界面物理の artifact か」を分離できる。
7. FSAE の最終形としては、文献実績のある
   **FFD/体積B-spline + 離散/連続随伴 RANS(SA) による形状最適化**
   （Othmer 2008/2014; Kalinowski & Szczepanik 2021; Granados-Ortiz et al. 2023;
   Beck et al. 2026）を本体に置き、密度法は位相シードに降格する構成が最短である。

---

## 1. 現状の正確な理解（リポジトリ内の事実）

本文書の主張の基礎となる、リポジトリに記録済みの事実。

| 事実 | 出典 |
| --- | --- |
| アーキテクチャは ProblemSpec v2 → Stage T（固定格子 density/Brinkman）→ iso-surface/SDF → Stage S → Stage V（body-fitted） | `docs/phase_plan.md` §2 |
| Stage T の力は `porousDirectionalForce`。`C_dir = 2/(Aref·U∞²)·∫ βmax·β·(U·direction) dV` | `openfoam_extensions/porousDirectionalForce/README.md`; `.C:124,137,146` |
| WP6: 10個の事前登録解析二値形状、same-grid T1（60×32×24, voxel 0.05 m）、αmax=2500、q=0恒等 | `docs/evidence/fixed_shape_cross_fidelity_ranking_2026_09.json` |
| WP6 判定: downforce `no_go`（厚さ軸の1組反転 `plate_a20_nd` vs `plate_a20_t05`: 代理 +0.2316 / 参照 +0.0343）、drag `unresolved_ranking_consistent`（37/37符号一致、rho 0.976, tau 0.911） | 同上 |
| 宣言不確かさ: downforce abs 0.0147、Cd rel 0.034（実測 drift をそのまま継続） | 同上; `fixed_shape_ranking_manifest_2026_09.json` |
| αmax sweep: 250 vs 2500 で downforce 差 ≤7.8%（`plate_a20_nd`: -0.48814 vs -0.52968）、一方 solid-band mean speed ratio は 0.0122 vs 0.00139（約8.8倍） | `fixed_shape_cross_fidelity_ranking_2026_09.json` の `alphamax_sweep`（本文書の派生的観察） |
| 抽出感度: iso 0.50 は anchor と 0.0013 で一致、iso 0.45/0.55 で ±0.03 → 幾何経路はこの実験の交絡ではない | 同上 `extraction_block` |
| Stage V fixed-domain: plain family V1/V2/V3 = 33k/188k/1.35M cells qualified、最細 downforce drift 0.01291（bound 0.005 未達）、wake level-3 併用で 0.01470 | `docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json` |
| 定常/非定常: plain V2 mesh 上の pimpleFoam 15 s は定常点を再現（Δdownforce -8.6e-5、シェッディングなし） | `docs/evidence/stage_v_transient_check_2026_09.json` |
| 運用点は U=1 m/s, ρ=1.0, ν=1e-2（Re≈300 層流）。宣言値 30 m/s・ν=1.47e-5 とは乖離（P4e 未修正） | `docs/problem_register_2026_09.md` P4e |
| 現行 Stage V V3 = 1,260,201 cells、4815 s、case 466 MiB、生成時 peak RSS 9.4 GiB（Apple M4, 32 GiB） | `docs/evidence/stage_v_v3_requalification_2026_09.json` |
| 登録済みの次手: 「厚さ軸に対する Stage T 代理の定式化研究（T2 refinement を登録因子の1つとして）」 | `docs/phase_plan.md` §11 item 1; WP6 manifest の `next` |

### 1.1 本文書が依拠する派生的観察（未登録・要検証）

以下は既存 JSON から読み取れるが、台帳には未記載の**推論**である。Phase 0 で検証する。

- **O1**: αmax を10倍変えても力は ≤8% しか動かない。一方で速度漏れ指標は約9倍動く。
  → 力の誤差は「シーリング（漏れ）」の誤差ではない。
- **O2**: 抗力は V3 で 0.319% 収束、downforce は 6倍未達。→ 抗力は運動量欠損の一次量、
  揚力は差分量。界面smearingへの感度が構造的に異なる。
- **O3**: δ/h = 0.04 のとき、Brinkman 層は格子に存在しない。αmax を上げるほど悪化する。
  → 現行パラメータ帯では、力は「界面そのもの」ではなく「界面の残差（漏れ＋圧力拡散）」
  から出ている。

---

## 2. 診断: なぜ downforce だけ転写しないのか

### 2.1 機構候補（文献）

**M1. 固体内部の圧力拡散（pressure diffusion）— 最有力**

- Kreissl, Pingen & Maute (2011, *Int. J. Numer. Methods Eng.*, doi:10.1002/nme.3151):
  密度法の非物理的artefactは「insufficient resolution of the flow field and an
  **improper representation of the pressure field within solid material**」に由来。
- Kreissl (2011, PhD thesis, Univ. of Colorado): これを "spurious pressure diffusion
  through solid material" と命名し、XFEM への移行理由に挙げる。密度法の欠点として
  (i) spurious pressure diffusion、(ii) パラメータ依存の境界精度、(iii) 境界分解能を列挙。
- Theulings, Langelaar, van Keulen & Maas (2023, *Struct. Multidiscip. Optim.* 66:6,
  doi:10.1007/s00158-023-03570-4): VANS 方程式では圧力項が `−αφ∇⟨p⟩^{iφ}`
  （流体体積率で減衰）になるべきで、NSDP（通常の Darcy ペナルティ）はこの係数を
  落としている。固体領域で `αφ → 0` のとき圧力勾配の駆動力が消え、**流れ漏れが
  圧力勾配に起因する分だけ直接抑えられる**。加えて「第2 Brinkman 補正」が界面応力
  支持を表す。VANS 版は精度同等で局所解への収束傾向が減り、パラメータ感度も低い。
- Alexandersen & Andreasen (2020, *Fluids* 5(1):29, doi:10.3390/fluids5010029):
  「**pressure field が直接の関心のとき、Brinkman penalisation は有意に大きくする
  必要がある**」。
- 平板・薄翼の揚力は上下の Δp で決まる。密度法は Δp を界面1セルで潰す。
  **この誤差は厚さに依存**する。

**M2. 多孔壁の実効スリップと界面遷移層の未解像**

- 界面遷移厚 `δ = √(ν/αmax)`（Angot et al. の Brinkman 層、Neale–Nader の指数減衰解）。
  Boscolo, Lanzoni & Peruzzo (2025, *Phys. Fluids*, doi:10.1063/5.0280584) は
  Da* のスケーリングで解の不変性が決まることを示し、**`Da ≲ 10⁻⁴`（固体速度を
  主流の2桁下げる条件）かつ `h < δ`** を要求する。誤ったスケーリングは「固体への
  過剰な浸透」を生む。
- Angot 系の実装基準: Brinkman 層を `m = δ/h` セルで解像し、**`m ≥ 1`、最適 `m = 1–2`**
  （`η = (m·h)²/ν` 相当）。
- 現行値: ν=1e-2, αmax=2500 → δ = 2.0e-3 m、h = 5.0e-2 m → **m = 0.04**。
  `m=1` にするには αmax ≈ ν/h² = 4、あるいは h = 2 mm（大域的には約25³=15625倍の
  セル数）が必要。**αmax を上げるほど δ は縮み、悪化する。**
- Abdel-Hamid & Czekanski (2023, arXiv:2302.14156): αmax ∝ μ、∝ L_c⁻²、∝ v_c
  （メッシュと流れ条件依存）。αmax=2500 の固定に理論的根拠はない。
- Theulings, Noël, Langelaar & Maas (2025, *CMAME*, doi:10.1016/j.cma.2025.118027):
  Darcy + Forchheimer（DF、DFF）でパラメータ調整を削減。**Forchheimer（速度の2乗）
  項が解精度の予測に必要**で、連続化（continuation）で局所解を回避。
- Beavers & Joseph (1967); Saffman (1971); Ochoa-Tapia & Whitaker (1995):
  多孔/自由流体界面には速度スリップと応力ジャンプが存在。Brinkman 層厚は実効スリップ
  長と同オーダー。

**M3. 力の推定法（体積シンク積分）が揚力に対して不適**

- 体積シンク積分は「界面が完全解像 かつ α→∞」の極限でのみ面力に一致する。
- Bhalla, Bale, Griffith & Patankar, "A moving control volume approach to computing
  hydrodynamic forces and torques on immersed bodies" (*J. Comput. Phys.* 347, 2017):
  界面での traction 直接積分は「noisy derivatives of velocity and pressure」を
  使わざるを得ず、**スプリアス振動を生む**。力/トルクの収支式（検査体積）を使うと
  これが消える。IC/Lagrange 乗数の等価性も示す。
- Goza, Colonius et al. (2016), "Accurate computation of surface stresses and forces
  with immersed boundary methods" (*J. Comput. Phys.*): 界面応力の方程式は
  **第1種積分方程式で ill-posed**。そのため揚力係数に非物理的振動が出る。
  平滑な delta 関数＋フィルタ後処理で収束する応力が得られる。
- Verma et al.（Bhalla et al. 2017 内で報告）: **Brinkman ペナルティ法の実測では、
  界面から2セル離れた "lifted surface" 上で力を評価する**ことが推奨される。
- Liberge & Béghein (2023, *Discrete Contin. Dyn. Syst. Ser. S*,
  doi:10.3934/dcdss.2023200): VP-LBM で momentum exchange 法と stress integration 法を
  比較。抗力は SI の方がわずかに正確、低Reでは SI が優位、高Reでは差が縮む。
- 定式化の対極として far-field 法が確立している:
  - 運動量収支（Betz/Van der Vooren/Destarac）: 検査体積上の欠損積分。**界面を
    解像しなくても、後流の欠損が解像されていれば力が得られる**。
  - Trefftz 面（誘導抗力）: `D_i = ½ρ∫∫(v̂² + ŵ²)dS`。後流の trailing vorticity
    から評価。表面圧力積分は「subtractive cancellation」で不正確になりやすく、
    far-field が代替になる（Stanford AA200b 講義ノート; Monsch et al. 2007,
    doi:10.2514/6.2007-1079）。
  - Lamb ベクトル法: `F = ∫ lamb vector`（Wu 1981, doi:10.2514/3.50966;
    Marongiu & Tognaccini 2010, doi:10.2514/1.j050326; Marongiu, Tognaccini & Ueno
    2013, doi:10.2514/1.j052104; Mele & Tognaccini 2014, doi:10.1063/1.4875015）。
    束縛渦（bound vorticity）と自由渦（wake）への分解が可能。
    Minervino & Tognaccini (2023, doi:10.1063/5.0164384) は、渦度を陽に数値微分
    する代わりに Crocco の式を数値運動量方程式から評価する hybrid 法を提案し、
    衝撃波がある場合の精度劣化を回避する。**数値微分で作った Lamb ベクトルは
    離散運動量収支を満たさず不正確になりうる**という警告も重要。
- **含意**: 体積シンク積分（現行）に代えて、検査体積運動量収支 + Trefftz/Lamb を
  同一 T1 場から計算し、Stage V に対する順位を比較するのが、最も安い切り分けになる。

**M4. 薄体・サブセル幾何の階段近似**

- "Immersed boundary simulations of flows driven by moving thin membranes"
  (*J. Comput. Phys.* 2022, PII S0021999122001383): **薄い物体では、圧力境界条件を
  陽に扱わない IB 法は圧力・速度の境界条件を同時に破る**。そして
  「**the pressure jump across the thin body is the dominant contribution to the
  overall force の場合、誤差は大きく、力の予測誤差が大きい**」。
  厚さ d = D/16 の例で、修正なしには収束した力が得られない。
- 現行 T1 は cell-center バイナリ占有なので、`plate_a20_t05`（0.05 m 厚, 20°）は
  法線方向 1–2 セルの階段近似。実効的な濡れ面積・キャンバーが格子ごとに変わる。
- **`trimesh` の signed distance が既にある**ので、セル体積率 `f ∈ [0,1]` の
  厳密評価は既存資産で可能。`α = αmax·f`（fractional penalty）へ置換すれば、
  階段近似を単一因子で除去できる。体積率と Darcy 項を独立に選べることは
  文献的に正当（*Pressure-Tight and Non-stiff Volume Penalization for Compressible
  Flows*, *J. Sci. Comput.* 2022, doi:10.1007/s10915-021-01747-x）。

**M5. 参照側の解像限界（0.005 bound と 0.0147 band の同オーダー）**

- WP6 の厚さクラスタの参照差は 0.014–0.034 で、宣言帯 0.0147 と同オーダー。
  **参照自体がこの軸の差を解像していない**。
- `docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json` は
  「drift は wake 解像度ではなく global refinement family の離散化効果」と結論。
  これは「格子収束を bound 内で示す」路線の限界を示す。

**M6. ランキング統計（均等配分と二値判定）**

- WP6 は 10形状 × V1+V2 の**均等配分（Equal Allocation）**。競合ペア（厚さ軸）に
  予算を寄せていない。OCBA はまさにこの状況（best と区別しにくい競合個体）で
  3–10倍の効率改善を報告する（Chen et al. 2000; Glynn & Juneja 2004; Li & Gao 2023;
  Cao et al. 2023, arXiv:2304.02377）。
- MO²TOS（ordinal transformation + optimal sampling）は
  「LF の**順序情報だけ**を使い、HF 予算を順位グループへ最適配分する」枠組みで、
  本アーキテクチャの前提をそのまま正しく実装したもの（Xu et al. 2014,
  doi:10.1109/coase.2014.6899354; Xu et al. 2016,
  doi:10.1142/s0217595916500172）。

### 2.2 機構の切り分け表

| 機構 | 予測される観測 | 最小の検証 | 対応 Track |
| --- | --- | --- | --- |
| M1 圧力拡散 | 薄板の Δp が body-fitted より大幅に小さい。厚さ依存 | 平板チャネルの Δp 比較（解析解あり） | B2 |
| M2 層未解像 | m=δ/h を上げると力が動く。αmax 増では動かない | m を 0.04→1 へ（h を 2 mm へ局所細分化 or αmax を 4 へ） | B1/B4 |
| M3 推定量 | 別推定量で順位が変わり、厚さ軸の反転が消える/残る | 同一 T1 場で CV 運動量収支・Trefftz・Lamb を計算 | A1–A3 |
| M4 階段近似 | 体積率ペナルティで厚さ軸の差が縮む | `α = αmax·f` の単一因子比較 | B3 |
| M5 参照限界 | V を細かくしても差が帯内 | V3+/多点・高次スキームの事前登録 | E4 |
| M6 統計 | 予算を競合ペアへ寄せると判定が確定 | OCBA 配分の再解析（既存データでシミュレート可能） | C1/C2 |

---

## 3. アーキテクチャ選択肢

### Track A — 推定量の再定式化（T はそのまま、読み取り方を変える）

**A1. 検査体積（CV）運動量収支**〔最安・最優先〕

- 一様 Cartesian では CV 面が格子面に一致するため積分は厳密。
  `F = ∮_S (ρ u u + p I − τ)·n dS`（定常）。
- 界面を解像する必要がない（Bhalla et al. 2017 の主張の核心）。
- 注意: 現行固定 domain は x ∈ [−1, 2]（物体 0.4–0.7）で後流が短い。運動量収支は
  domain 内で閉じる必要があり、far-field/Trefftz は後流長の宣言変更が必要。
  これは**閾値緩和ではなく事前登録の宣言変更**として扱う。
- 検証: CV サイズを 2–3 水準変えて力の CV 非依存性を確認する（far-field 法の
  標準的な健全性検査）。

**A2. Lamb ベクトル / 渦度モーメント**〔安〕

- `F = ∫_V lamb-vector-based formula`。束縛渦と後流渦への分解が可能で、揚力の
  物理が直接見える。
- **警告**: 渦度を速度場の数値微分で作ると離散運動量収支を満たさず不正確になる
  （Minervino & Tognaccini 2023）。Crocco 式ベース（運動量方程式から Lamb ベクトルを
  作る）の変種を使うこと。
- 実装は T1 場の post-process。

**A3. 圧力プローブ Δp と循環 Γ**〔最安〕

- 平板中点の上下プローブから Δp、mid-span 周りの閉曲線積分から Γ（Kutta–Joukowski:
  `L' = ρ U∞ Γ`）。3つの独立な「代理 downforce」定義になる。
- M1（圧力拡散）の直接検定。

**A4. 推定量の再選択は「登録済みの次手」の範囲内**

WP6 manifest の `next` は「Stage T surrogate formulation study for the thickness axis
（例: near-cell resolution effects、T2 refinement を登録因子の1つとして）」と明記して
おり、A1–A3 は**代理の定式化研究**に該当する。最適化器を調整して結果を逆転させる
行為（停止規則）には該当しない。ただし、事前登録・単一因子分離・不確かさ帯の継承は
必須。

### Track B — 代理の物理を直す（固定格子・密度法のまま）

**B1. Darcy 数・層解像の文献則に従う**〔安・単独では不足〕

- 現行 m=0.04。`m ≥ 1` を満たす最小変更は h の局所細分化（B4）または αmax の適正化。
- **αmax を上げる方向は誤り**（δ が縮む）。文献の整理では、
  (i) `h ≤ δ` まで細分化、(ii) VANS/Forchheimer で圧力と速度の抑制を分離、
  (iii) sharp interface、のいずれかで解く。
- 事前登録する単一因子: `αmax ∈ {4, 25, 250, 2500}` を m ∈ {1, 0.4, 0.13, 0.04} と
  対応させ、力と Δp の変化を測る。WP6 の 250↔2500 は m の範囲では両方未解像域。

**B2. VANS 型・圧力ペナルティ付き Brinkman**〔中〕

- 運動量式の圧力項を `αφ∇p` にし、第2 Brinkman 補正を加える。Theulings et al. 2023。
- OpenFOAM テンプレートの運動量式への1–2項追加で試せる（`fixed_grid_primal.py` の
  ソルバ生成部）。**「圧力場が関心のときの標準的な最小修復」**。
- 注意: 第2 Brinkman 補正は体積平均の仮定（スケール分離）が破れる固体壁では
  単独では不十分という議論もあり（Whitaker 1986 の議論、同論文内）、
  実装時は「界面セルでのみ有効」等の処方が要る。

**B3. サブセル体積率ペナルティ（fractional penalty）**〔中〕

- `α = αmax·f`、`f` は解析 SDF から厳密なセル体積率。占有が sub-cell 精度になり、
  階段近似（M4）を単一因子で除去できる。
- `trimesh.proximity.signed_distance` は既存（`analytic_candidate_shapes.py:316-325`）。
- 連結性・discreteness ゲートとの整合（体積率は連続値だが設計は二値のまま）を
  明記する必要がある。

**B4. 多解像度（MTOP / dp-adaptive）と局所細分化**〔中〕

- 設計格子（canonical 46k）と解析格子を分離し、界面・後流だけ細分化。
  Nguyen, Paulino, Song & Le (2010, doi:10.1007/s00158-009-0443-8; 2012,
  doi:10.1002/nme.4344); Gupta, van Keulen & Langelaar (2019,
  doi:10.1002/nme.6217)。
- 制約: 1要素あたりの設計点数の上界（Gupta et al. 2016,
  doi:10.1002/nme.5455）を守らないと解の非一意性が出る。
- 「same-grid」の定義を「幾何と設計格子は同一、解析格子は階層」に明示的に
  再宣言する必要がある（既存の same-grid 主張と衝突しない書き方）。

**B5. Robust formulation + 最小寸法**〔中〕

- Wang, Lazarov & Sigmund (2011) の erosion/dilation。P15 の厚さ病理と、
  「鋭い tanh 射影がフィルタ長さスケールを打ち消す」というリポジトリ自身の観察
  （P15 注意節）に対する文献的な閉じ方。
- 製造制約（最小肉厚）として FSAE の 3D プリント／CFRP 製作に直結。
- Sigmund & Petersson (1998) の well-posedness も同時に確保。
- **注意**: P15 の実測では robust erode（半径4セル）は物体を消す逆効果だった。
  フィルタ半径・η_e・射影の組み合わせを事前登録で掃引する必要がある。

**B6. ハイブリッド density + sharp interface（CutFEM/XFEM）**〔重〕

- Villanueva & Maute (2017, *CMAME* 320, doi:10.1016/j.cma.2017.03.007):
  3D 層流 CutFEM 流体TO。level set + XFEM + Nitsche + face-oriented ghost penalty。
  孤立流体ポケットの平均圧力拘束も必要（特異系になる）。
- Jenkins & Maute (2016, *SMO* 54, doi:10.1007/s00158-016-1467-5)。
- Høghøj, Andreasen & Maute (2025, *SMO*, doi:10.1007/s00158-024-03956-y):
  密度法で hole seeding → level-set/XFEM へ連続的に移行。
  **Nitsche ペナルティと ghost 安定化に逆透過率項を入れないと、界面で速度・圧力の
  非物理モード（チェッカーボード）が出る**ことを数値的に実証。
- 圧力不連続を構成上解像するため、M1 に対する根本解。実装コストは最大。

### Track C — 「T は順位モデルにすぎない」を統計的に正しく扱う

**C1. Ordinal transformation / MO²TOS**〔中・純統計〕

- OT: LF の順位で全候補を1次元順序空間へ写し、等分位でグループ化。
- OS: HF 予算をグループへ最適配分し、最良グループの PCS を最大化。
- 利点: **LF の値のバイアスに依存しない**。OT によりグループ内分散が下がり、
  グループ間距離が上がるため、同じ HF 予算で PCS が上がる（論文の理論解析）。
- 欠点: LF の順位が完全にランダムだと OT は無効（探索にフォールバックする）。

**C2. OCBA（Optimal Computing Budget Allocation）**〔中・純統計〕

- 標準配分則（Chen et al. 2000、正規・既知分散近似）:
  `N_i/N_j = (σ_i·δ_bj / (σ_j·δ_bi))²`, `δ_ij = μ_i − μ_j`,
  `N_b = σ_b·√(Σ_{i≠b} N_i²/σ_i²)`。
- 直感: ノイズが大きい個体、および best と平均が近い個体へ多く配分する。
- WP6 の厚さクラスタはまさに「best と区別しにくい競合個体」。
  **現在の 20 V ランを競合ペアへ再配分すれば、同じ予算で判定が確定する可能性がある。**
- 報告指標: PCS（正しく選ぶ確率）、EOC（誤選択時の機会費用）。
  Gate 4 を `PCS ≥ 0.95` 等の事前宣言へ拡張。

**C3. 記述子ベースの多忠実度補正（discrepancy / co-kriging / MF trust-region）**

- Kennedy & O'Hagan (2000); Forrester, Sóbester & Keane (2007,
  doi:10.1098/rspa.2007.1900); Alexandrov, Dennis, Lewis & Torczon (1998,
  doi:10.1007/bf01197433); Kontogiannis et al. (2019,
  doi:10.1016/j.ast.2019.105592)。
- 本件では `V − T` を**幾何記述子**（t/c, AoA, span, z, chord, 占有体積）の関数として
  回帰する。WP6 の 10 形状 × 2 水準で 1 次元 `δ(t/c)` は即座にフィット可能。
- 代替: LF 出力を入力特徴に加えた GPR で HF を予測し、CV（=σ/μ）閾値で HF を発火
  （arXiv:2603.17057, 2026; 12 パラメータ CST 翼、Re=6e6、HF 発火率 9.5–14.8%）。
- **これは「厚さ軸の代理定式化」の最も安い具体解**であり、登録済み T2 細分化因子の
  上位集合。

**C4. 無関心帯（indifference zone）と PCS 報告**

- 差が宣言帯以下のペアは `unresolved` として扱う（現行 Gate 4 と同じ思想）。
- 追加で PCS を報告し、判定の統計的な強さを可視化する。
- **「全3格子で方向一致」は弱い主張**であり、PCS で表現すると何%なのかを示すのが誠実。

### Track D — 形状側を本物にする（T は種、V 級の形状最適化が本体）

**D1. Level-set / Hadamard 形状勾配**〔重〕

- Allaire, Jouve & Toader; Wang, Wang & Guo; Osher & Santosa。
- 宣言済み Stage S（P10）の正しい実装。hole nucleation は密度法シードで補う
  （Høghøj et al. 2025 がまさにこの統合）。

**D2. 産業実績のある経路: FFD/体積B-spline + 随伴 RANS(SA)**〔中・実績多数〕

- Othmer (2008, *IJNMF* 58(8), doi:10.1002/fld.1770; 2014,
  *J. Math. Industry* 4(6), doi:10.1186/2190-5983-4-6)。
- Papoutsis-Kiachagias & Giannakoglou (2014, *Arch. Comput. Methods Eng.*):
  乱流の連続随伴（SA, k-ε, k-ω SST）、トポロジー最適化、ロバスト設計。
  **凍結乱流は誤った符号の感度を生みうる**。
- Karpouzas et al. (2016, *JSAE IJAE*, doi:10.20485/jsaeijae.7.1_1):
  体積 B-spline + 連続随伴。VW XL1 で drag −2% / **lift +30%**、
  Audi ミラー −7%、DrivAer fastback −0.2%。
  **DES/時間平均 primal の後流感度は RANS と大きく異なる**（Audi A7 の後部）。
- FSAE/レースカーへの直接適用例:
  - Kalinowski & Szczepanik (2021, *IOP Conf. Ser. Mater. Sci. Eng.* 1037:012058,
    doi:10.1088/1757-899x/1037/1/012058): レーシングカー前翼の随伴形状最適化
    （downforce/drag 比）。
  - Granados-Ortiz, Morales-Higueras, Ortega-Casanova & López (2023, *Machines*
    11(2):231, doi:10.3390/machines11020231): 5要素F1前翼、17パラメータ、
    パラメトリック最適化 + RBF メッシュモーフィング随伴のハイブリッド。
    局所的に最大25%改善。FIA 規則の境界ボックスを設計制約として使用。
    **計算予算が小さい場合の現実解は2D断面最適化 → 3D へ展開**。
  - Beck, Halila, Sanjaya & Azevedo (2026, AIAA, doi:10.2514/6.2026-4343):
    多要素モータースポーツ翼、RANS(SA) + 離散随伴 + FFD + SLSQP、
    downforce 制約付き drag 最小化、効率最大 +50%。
  - AAU 修士論文 (2018): 実車ボディキットに対する離散随伴 + 自動モーフィング。
- **示唆**: FSAE のダウンフォース最適化は、文献的には「固定格子トポロジー」ではなく
  「FFD/B-spline + 随伴 RANS」が支配的であり、実績も出ている。
  本リポジトリの Stage V は既に OpenFOAM なので、この経路への接続コストは低い。

**D3. FSAE 形状語彙への昇格**〔安〕

- `src/cfd_sdf/analytic_candidate_shapes.py::reachable_set_definitions` の
  camber, gurney, tandem, endplate, chord, z-offset は既に良い語彙。
  これをランキング用固定具から**設計変数**へ昇格させ、随伴勾配で回す。
- 5–20 変数で実用域（Granados-Ortiz の 17 パラメータ、Beck の FFD と同水準）。

**D4. Topology-to-shape ハイブリッド**〔中〕

- T は「どこに材料を置くか」だけに使い、iso-surface を初期形状として D1/D2 に渡す。
- V をループ内に置くので、**代理の値の正しさに依存しない**。
  現行アーキテクチャの T→S→V の意味を保ったまま、S の役割を「SDF 精緻化」から
  「形状最適化」へ実質化する。

### Track E — FSAE へ向けた物理忠実度ラダー

**E1. Re の橋**

- 現状 Re≈300 層流 → 宣言 Re≈6e6。P4e 未修正。
- 文献的には **SA（Spalart-Allmaras）+ 連続随伴による 3D 高Reトポロジー最適化**が
  既に存在（Papoutsis-Kiachagias 博士論文 Ch.6、拡張ラグランジュ制約付き）。
- テンプレートが既に OpenFOAM porous なので接続コストは低い。
- 凍結乱流の誤差範囲を必ず宣言（勾配精度の主張に直結）。

**E2. 多点・ロバスト設計**

- ライドハイト / yaw / pitch。adjoint-based robust design
  （Papoutsis-Kiachagias & Giannakoglou 2014 に章）。
- FSAE は地上高・ヨー依存が支配的なので単点最適化は誤った設計を返す。
- Granados-Ortiz et al. 2023 も「3D への展開」を将来課題として明記。

**E3. 予算の算術**

- V3 = 1.26M セル / 4815 s（Apple M4, 32 GiB）。
- 100候補 × 2水準 = 数日。勾配法なら 10–50 反復 × (primal + adjoint) で同オーダー。
- **V 評価を意思決定が変わる点にだけ使う = Track C が必須**。
- 「5Mセルで主問題＋随伴15分」は `development_plan_2026_09.md` の挑戦目標。
  現行は 1.26M で 80分（4815 s）なので、**約 200倍のスループット不足**。
  GPU/AMR/多重格子は物理ではなく**スループット要件**。

**E4. 高次スキーム・参照側の限界**

- 非構造格子 + 随伴は、界面・後流の解像を上げるほど V の絶対値が動く
  （P16 の離散化 family 効果）。高次スキーム（2次精度の limited から
  WENO/高解像度へ）や、CV/far-field 推定を V 側にも適用して
  「V の系統誤差」を分離することも選択肢。

---

## 4. 推奨ロードマップ（フェーズ・ゲート・停止規則）

| Phase | 内容 | コスト | ゲート（Go 条件） | 証拠クラス |
| --- | --- | --- | --- | --- |
| **0** | 既存 WP6 T1 場に対する A1–A3 の推定量比較 + 既存 V データに対する δ(t/c) 回帰（A4 の範囲内、単一因子、事前登録） | <1日 | 厚さ軸の符号が推定量/補正で直るか。直れば no_go は「推定量の artifact」、直らなければ「界面物理の artifact」と確定 | numerical（既存場の再解析） |
| **1** | 圧力修復フィクスチャ: 平板をチャネルに置き解析 Δp と比較。NSDP(α=2500) / VANS圧力ペナルティ / fractional penalty / h 細分化（m→1）/ body-fitted の5水準 | 数日 | **Δp 誤差が文献則（m, Da*）どおりにスケールするか**。速度漏れは既に合格しているので圧力指標を新設 | numerical |
| **2** | ランキング基盤の統計化: OCBA 配分 + ordinal transformation + 記述子 discrepancy + PCS/無関心帯。既存 20 ランで PCS を再計算、必要なら追加ランを事前登録 | 1週間 | PCS ≥ 0.95（または宣言閾値）で厚さ軸の順位が決まるか | numerical |
| **3** | 物理トラックの選択: (i) B4+B5（多解像度＋robust）、(ii) B6（cut-cell/XFEM）、(iii) D2/D3（形状随伴、T はシード） | 中大 | Phase 1 の結果で判定。FSAE の時間軸では (iii) を推奨。(i) は位相探索を残すための部品 | capability → numerical |
| **4** | FSAE プロファイル: 多点（ride height/yaw）、ground + wheels、RANS(SA)、多要素翼語彙、前後バランス（CoP）制約、製造最小寸法 | 大 | G3/G4/B5 ゲート通過後 | target physics |

### 4.1 停止規則・禁止事項（既存文書の継承）

- 0.005 の grid bound を緩めない（`docs/phase_plan.md`, P16）。
- WP6 の固定形状結果を逆転させるために最適化器を調整しない（WP6 stop rules）。
- 事前登録のない閾値変更・事後的な因子追加をしない。
- 生の `checkMesh` 出力を clean pass として扱わない。
- `execution_ready`、プロセス exit code、force file の存在を物理資格として扱わない。
- **本文書の推奨は Phase 0 の結果が出るまで実装しない**（切り分けなしの実装は
  「因子を同時に動かす」禁止に触れる）。

### 4.2 Phase 0 の具体的な設計（実装可能な粒度）

1. **入力**: `work/fixed_shape_ranking_2026_09/` の T1 場（10形状, 8–11 s/形状で再生成
   可能）。`analytic_candidate_shapes.py::anchor_mesh` の解析 STL。
2. **推定量の実装**:
   - E1: 体積シンク積分（現行、ベースライン）
   - E2: 検査体積運動量収支（物体を囲む格子整合ボックス 2–3水準）
   - E3: Trefftz 面の渦度積分（後流断面）
   - E4: mid-chord 上下プローブの Δp
   - E5: 閉曲線積分による Γ（Kutta–Joukowski）
3. **判定**: Stage V V1/V2（既存 20 ラン、anchor STL）に対する Spearman / Kendall /
   符号反転数 / 宣言帯（0.0147）での resolvability を、E1–E5 で比較。
4. **記録**: 推定量ごとの JSON、実装 hash、入力場 hash、宣言帯の継承、
   「どの推定量がどの機構を示唆するか」。
5. **期待される意思決定**: 
   - E2–E5 のいずれかが厚さ軸で Stage V と符号一致 → **M3 が主因**。
     Phase 1 は不要、Phase 2/3(iii) へ進む。
   - すべて反転 → **M1/M2/M4 が主因**。Phase 1 の圧力フィクスチャへ直行。

---

## 5. リポジトリへの最小実装マップ

ponytail 原則（新規モジュールは3つまで、既存の再利用を優先）に従った最小案。

| 目的 | 追加/変更 | 再利用 | 備考 |
| --- | --- | --- | --- |
| 推定量比較（Phase 0） | `src/cfd_sdf/force_estimators.py`（新規・小） | `cross_fidelity_ranking.py` の ranking/pair 機構、`analytic_candidate_shapes.py` の SDF | 出力は既存 response スキーマに合わせる |
| 記述子（Phase 0/2） | `analytic_candidate_shapes.py` に descriptor 出力を追加 | `ShapeDefinition` | t/c, AoA, span, z, chord, 占有体積 |
| ランキング統計（Phase 2） | `src/cfd_sdf/mf_ranking.py`（新規・小） | `cross_fidelity_ranking.py` | OCBA 配分、PCS、無関心帯 |
| 事前登録 | `docs/evidence/` の manifest 拡張 | `fixed_shape_ranking_manifest_2026_09.json` の形式 | 新規 campaign として登録 |
| 圧力フィクスチャ（Phase 1） | 新規 fixture（`examples/` または `work/`） | Stage V の case 生成 | 解析 Δp は平面 Poiseuille/平板の理論解 |
| **延期** | cut-cell/XFEM、T2 大格子、FSAE 車両形状、GPU 経路 | — | Phase 1 の結果が出るまで着手しない |

既存実装との整合:

- Stage V の preflight（`stage_v_domain_preflight.py`）と profile
  （`stage_v_qualification_v1`）は**変更しない**。
- `porousDirectionalForce` 拡張は**追加の objective 型**として実装し、既存の
  downforce 定義を置換しない（後方互換と証拠の連続性のため）。
- `fixed_grid_primal.py` のソルバ生成部に B2/B3 を試す場合、`regularise` の
  二重射影の再発に注意（P14 の閉止条件を壊さない）。

---

## 6. 反証条件とリスク

| 提案 | 反証条件（出たら捨てる） |
| --- | --- |
| A1–A3（推定量） | CV/Trefftz/Lamb/Δp の**すべて**が Stage V に対して厚さ軸で反転する → 推定量の問題ではない |
| B1（層解像） | m を 0.04→1 にしても Δp 誤差が厚さ依存のまま → 層解像は主因でない |
| B2（VANS 圧力ペナルティ） | 圧力ペナルティ導入後も Δp が body-fitted と不一致 → 界面応力の扱いが本質 |
| B3（分数ペナルティ） | 体積率化で力の厚さ依存が消えない → 階段近似は副次的 |
| C1–C3（統計） | δ(t/c) が10形状で汎化しない → 記述子不足 or 順序情報自体の破綻 |
| D2–D4（形状随伴） | FFD/随伴で得た最適形状が V の別格子・別モデルで改善しない → モデル差（DES vs RANS 等）が支配 |
| E1（乱流） | 凍結乱流の感度が符号から誤る → 乱流随伴の完全微分が必要 |

追加リスク:

- **計算予算**: FSAE 全車は現行の約200倍のスループット不足（E3）。GPU/AMR の導入は
  物理ではなくスループットの投資であり、`development_plan_2026_09.md` の
  後続機能導入条件に従う。
- **モデル差**: レースカーの後流・後翼感度は RANS と DES で異なる
  （Karpouzas et al. 2016）。FSAE のディフューザ／後翼を扱う段階で必ず再検証。
- **規約の罠**: FIA/FSAE 規則の境界ボックスを設計制約に使う例
  （Granados-Ortiz et al. 2023）は、本リポジトリの `design_domain` /
  `forbidden_region` ロールに対応させられる。規則は毎年変わるため、
  規則を ProblemSpec の外にハードコードしない。

---

## 7. 参考文献

### 7.1 流体トポロジー最適化とペナルティ法

| 文献 | DOI/出典 | 本文書での用途 |
| --- | --- | --- |
| Borrvall & Petersson (2003) | *Int. J. Numer. Methods Fluids* | 流体TOの原典 |
| Kreissl, Pingen & Maute (2011) | doi:10.1002/nme.3151 | 非定常流TO、圧力拡散の指摘 |
| Kreissl (2011) PhD thesis, Univ. of Colorado | — | XFEM への動機、密度法の欠点整理 |
| Alexandersen & Andreasen (2020) | doi:10.3390/fluids5010029 | レビュー、「圧力が関心のときペナルティ大幅増」 |
| Theulings, Langelaar, van Keulen & Maas (2023) | doi:10.1007/s00158-023-03570-4 | VANS、圧力ペナルティ、第2 Brinkman 補正 |
| Theulings, Noël, Langelaar & Maas (2025) | doi:10.1016/j.cma.2025.118027 | Darcy + Forchheimer(DFF)、チューニング削減 |
| Boscolo, Lanzoni & Peruzzo (2025) | doi:10.1063/5.0280584 | Da* スケーリング、`h < δ`、`Da ≲ 1e-4` |
| Abdel-Hamid & Czekanski (2023) | arXiv:2302.14156 | αmax ∝ μ, L_c⁻², v_c |
| Li, Wang et al. (2023) | PMC10647552 | 密度法 vs level-set の得失レビュー |
| Angot et al. | *J. Comput. Phys.* 系 | Brinkman 層 δ=√(ην)、m≥1 |

### 7.2 Sharp interface / cut-cell / XFEM

| 文献 | DOI | 用途 |
| --- | --- | --- |
| Villanueva & Maute (2017) | doi:10.1016/j.cma.2017.03.007 | 3D CutFEM 流体TO |
| Jenkins & Maute (2016) | doi:10.1007/s00158-016-1467-5 | 埋め込み境界形状・位相最適化 |
| Høghøj, Andreasen & Maute (2025) | doi:10.1007/s00158-024-03956-y | 密度 hole seeding + XFEM、Nitsche/ghost の逆透過率項 |
| Schott & Wall (2014); Gammanpila et al. (2025) | doi:10.3390/math13172853 | 圧力不連続の XFEM 安定化 |

### 7.3 多解像度・robust 定式化

| 文献 | DOI | 用途 |
| --- | --- | --- |
| Nguyen, Paulino, Song & Le (2010) | doi:10.1007/s00158-009-0443-8 | MTOP |
| Nguyen, Paulino, Song & Le (2012) | doi:10.1002/nme.4344 | iMTOP |
| Gupta, van Keulen & Langelaar (2019) | doi:10.1002/nme.6217 | dp-adaptive MTO |
| Gupta et al. (2016) | doi:10.1002/nme.5455 | 設計/解析分離の上界 |
| Wang, Lazarov & Sigmund (2011) | *SMO* | robust formulation |
| Sigmund & Petersson (1998) | — | well-posedness |

### 7.4 力推定・far-field・Lamb ベクトル

| 文献 | DOI/出典 | 用途 |
| --- | --- | --- |
| Bhalla, Bale, Griffith & Patankar (2017) | *J. Comput. Phys.* 347 | 移動検査体積による力・トルク。界面 traction 直接積分の振動 |
| Goza, Colonius et al. (2016) | *J. Comput. Phys.* | IB の界面応力は第1種積分方程式で ill-posed |
| Liberge & Béghein (2023) | doi:10.3934/dcdss.2023200 | VP-LBM の ME vs SI |
| 薄体 IB の圧力境界条件 | *J. Comput. Phys.* 2022, PII S0021999122001383 | 薄体では圧力ジャンプ支配 → 誤差大 |
| Monsch, Figliola, Thompson & Camberos (2007) | doi:10.2514/6.2007-1079 | Trefftz 面による誘導抗力 |
| Stanford AA200b 講義ノート | aero-comlab.stanford.edu | 表面圧力積分の cancellation と far-field |
| Wu (1981) | doi:10.2514/3.50966 | 粘性流の力・モーメント理論 |
| Marongiu & Tognaccini (2010) | doi:10.2514/1.j050326 | Lamb ベクトル far-field（RANS へ拡張） |
| Marongiu, Tognaccini & Ueno (2013) | doi:10.2514/1.j052104 | 揚力・誘導抗力の Lamb 積分 |
| Mele & Tognaccini (2014) | doi:10.1063/1.4875015 | 圧縮性 Lamb ベクトル |
| Minervino & Tognaccini (2023) | doi:10.1063/5.0164384 | Crocco ベースの Lamb 計算（数値微分の回避） |
| Wu, Liu & Liu (2018) | doi:10.1016/j.paerosci.2018.04.002 | 力の理論レビュー |

### 7.5 多忠実度・ランキング統計

| 文献 | DOI | 用途 |
| --- | --- | --- |
| Xu, Zhang, Huang, Chen, Lee & Çelik (2014) | doi:10.1109/coase.2014.6899354 | ordinal transformation |
| Xu et al. (2016) | doi:10.1142/s0217595916500172 | MO²TOS |
| Chen et al. (2000) | — | OCBA |
| Glynn & Juneja (2004) | — | 大偏差による rate-optimal allocation |
| Li & Gao (2023) | — | OCBA の収束解析 |
| Cao, Wang, Chew, Li & Tan (2023) | arXiv:2304.02377 | budget-adaptive 配分 |
| Kennedy & O'Hagan (2000) | — | モデル較正・discrepancy |
| Forrester, Sóbester & Keane (2007) | doi:10.1098/rspa.2007.1900 | co-kriging |
| Alexandrov, Dennis, Lewis & Torczon (1998) | doi:10.1007/bf01197433 | trust-region model management |
| Kontogiannis et al. (2019) | doi:10.1016/j.ast.2019.105592 | MF trust-region vs EI の比較 |
| arXiv:2603.17057 (2026) | arXiv | LF 出力を特徴にした GPR + 不確かさで HF 発火 |

### 7.6 空力形状最適化（産業・レース）

| 文献 | DOI | 用途 |
| --- | --- | --- |
| Othmer (2008) | doi:10.1002/fld.1770 | 連続随伴トポロジー感度 |
| Othmer (2014) | doi:10.1186/2190-5983-4-6 | 車空力の随伴レビュー |
| Papoutsis-Kiachagias & Giannakoglou (2014) | *Arch. Comput. Methods Eng.* | 乱流随伴・ロバスト設計 |
| Zymaris, Papadimitriou, Giannakoglou & Othmer (2009) | doi:10.1016/j.compfluid.2008.12.006 | SA 随伴 |
| Karpouzas et al. (2016) | doi:10.20485/jsaeijae.7.1_1 | 体積 B-spline + 随伴、DES 感度差 |
| Kalinowski & Szczepanik (2021) | doi:10.1088/1757-899x/1037/1/012058 | 前翼の随伴形状最適化 |
| Granados-Ortiz et al. (2023) | doi:10.3390/machines11020231 | 5要素F1前翼、ハイブリッド最適化 |
| Beck, Halila, Sanjaya & Azevedo (2026) | doi:10.2514/6.2026-4343 | 多要素翼、離散随伴 + FFD + SLSQP |
| Hogea, Hogea & Agarwal (2026) | doi:10.2514/6.2026-1898 | FSAE 全車反復パラメータ最適化 |
| Suvanjumrat et al. (2025) | doi:10.1016/j.ijft.2025.101440 | GA–ANN 多要素翼 AoA 最適化 |
| Lai et al. (2025) | doi:10.1007/978-981-96-5527-4_6 | 分割前翼・渦発生器 |

---

## 8. 本文書が主張しないこと

- 新しい物理証拠、格子収束、target physics、benchmark 資格を主張しない。
- 「Brinkman 代理が一般的に無効」とも「有効」とも主張しない。
- downforce の格子独立参照、FSAE 高Re・全車への外挿を主張しない。
- αmax の妥当値、VANS 採用、cut-cell 採用を決定しない。
  それらは Phase 0/1 の結果に基づく事前登録された判断である。
- WP6 の no_go 判定を「覆した」とは主張しない。本文書は**切り分けの設計**を提案する
  だけである。
- 本文書の数値（m=0.04、δ=2 mm 等）は SI 値からの計算であり、リポジトリの記録値
  （δ がセル幅の 37–50 倍という P11 の記述）と整合する。ただし Δp 誤差の大きさは
  未測定である。

## 9. 未検証・要確認事項

- Boscolo et al. (2025) の `Da*` の正確な定義（本文書では `O(1e-4)` の閾値のみ引用）。
  実装前に原論文で定義式を確認すること。
- Angot 系の `η = (m·h)²/ν` の表記は MDPI 論文経由の引用。原典（Angot et al.）の
  記号定義を確認すること。
- Verma et al. の "lifted surface"（界面から2セル）の推奨は Bhalla et al. (2017) 内の
  引用であり、原典（Verma et al.）の条件を確認すること。
- 薄体 IB の圧力境界条件論文の DOI（本文書では PII のみ）。
- FSAE 固有の地上高・ヨー・タイヤ回転条件の文献（本ノートでは未調査）。
- CUDA/Metal 経路のスループット見積りは未実施（`development_plan_2026_09.md` の
  後続機能条件に従う）。
