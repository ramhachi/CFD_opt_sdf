# downforce 本丸の調査と計画 — GLM セッション総括 (2026-09-20)

- 執筆: GLM (OpenCode / GLM session)
- 立場声明: 本書は `docs/phase_plan.md`(唯一のロードマップ) と
  `docs/problem_register_2026_09.md`(問題台帳) に従属する作業記録・判断資料である。
  順位・資格の主張の正は台帳と `docs/evidence/*.json` であり、ここは解釈と方針を追加する。
- 全体限定: 本記録の実験は **縮小層流ケース (U=1 m/s, nu=1e-2 m^2/s, Re(体長)≈75)** での
  証拠である。target physics・FSAE 高 Re への外挿は行っていない。
  測定済み Stage V 不確かさ帯 **downforce 0.0129–0.0147 (abs) / Cd ~0.03 (rel)**
  (`docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json`) は、この文書全体を通じて
  **宣言のまま据え置き**である (ユーザ指示: 縮小ケースをこれ以上掘り下げない)。

---

## 0. 出発点

FSAE 競技では front wing / multi-element wing の downforce が性能の主因子で、drag は従。
ユーザ要求「drag は悪くない、本当に欲しいのは downforce」はこの文脈で自然である。
WP6 の最初の Gate-4 判定で **downforce = no_go** が出たため、壊れる理由をメカニズム実測
まで掘り下げ、閉じ方を決めた。結論を先に:

> **downforce の順位保存は、`minimum_solid_width` 設計政策の内側の設計空間で成立**する
> (8 FSAE 関連形状で V1/V2 とも tau=1.000 の完全一致; 17 形状プールで downforce 121 組 /
> drag 110 組とも解像可能な反転ゼロ)。最初の no_go は、政策が本来的に除外する
> **1 セル厚の下位解像度形状**に局在していた。

---

## 1. 何が測定されたか

### 1.1 第 1 ランキング (WP6 本実験, 事前登録済み manifest)

- 10 個の事前登録された解析的二値形状 (迎角 −20..+30°, 厚さ 0.05/0.10/0.15 m,
  スパン, z オフセット, 鈍頭箱)。**期待順位は仮定しない。**
- **Stage T**: same-grid T1 (60x32x24, voxel 0.05 m), alphaMax 2500, q=0 (二値場では
  RAMP が恒等), 転送演算子なし, フィルタ/射影なし, optimizer なし。
- **Stage V**: 解析 anchor STL を直接 mesh (iso 抽出誤差を幾何から排除), 宣言固定
  domain, V1+V2, クリアランス preflight + 資格プロファイル全通。
- 全 20 実行が mesh profile / residualControl / force-stationarity で qualified。
- Gate 4 判定 (宣言帯 verbatim: downforce abs 0.0147 / Cd rel 0.034):

| 応答 | 判定 | 実測 |
| --- | --- | --- |
| downforce | **no_go** | V2 で解像可能な反転 1 組: `plate_a20_nd` vs `plate_a20_t05` (代理 +0.2316 / 参照 +0.0343, 符号逆)。代理は参照が飽和する差を約 7 倍に誇張 |
| drag | unresolved (符号全一致) | 37/37 組で代理・参照の符号一致 (rho 0.976, tau 0.911) |

- 証拠: `docs/evidence/fixed_shape_cross_fidelity_ranking_2026_09.json`

### 1.2 機構の計量的同定 (既存解の後処理、新規 solver 実行ゼロ)

既存 10 cases の VTK 内部場 (beta, U, p) を再解析した:

1. **porous downforce の発生源**: 力の 100% が `beta >= 0.9` の固体セルから (β<0.1 の
   流れ寄与 ~1e-6)。
2. **内部リークの Darcy 減衰 (決定的)**:
   平均 |U_z| (固体内部) = t05(1 セル厚) 1.63e-3 / t10 1.38e-3 / t15 8.7e-4。
   **薄い物体ほど内部を通過する速度が速い**。porous DF ∝ V_solid × u_leak(内部) で、
   厚さへの一次感度は「体積成長 × リーク減衰」の合成飽和形となり、body-fitted の
   参照クラスタ (V2 で 0.720–0.755, 差 0.014–0.034 ≕ 宣言帯) とは**関数形が構造的に異なる**。
   → 厚さ軸の誤順位はソルバ・格子・alphaMax の不具合ではなく、**目的関数の物理表現
   (体積積分のモメンタムシンク) そのものの性格**である。
3. **naive wake-plane 復元は効かない**: 固定 x 平面のモメンタム束 (rho·u_x·u_z) の単純
   積分は tau 0.69–0.78 と porous (0.822) より悪化。真の lift 分離には far-field 分解
   (Betz/Squire 型, 壁面修正込み) が必要で、それは研究級の実装である。
4. **p·d(beta)/dz の単純圧力トラクション後処理**も porous と同等のランキング構造
   (tau −0.889; 符号規約の差のみ) であり、手早な修正手段としては不十分。

### 1.3 WP6-2 到達可能集合の第 2 決定実験 (主結果)

`docs/evidence/reachable_set_cross_fidelity_ranking_2026_09.json`:

- **定義**: `minimum_solid_width` 設計政策 (T1 voxel の 3 セル = 0.15 m) を満たす 8 形状を
  新規事前登録。FSAE 関連軸 (キャンバー折り板 / gurney / 弦長スケール / 2 エレメント /
  エンドプレート / タンデム位置 / 同厚さコントロール) を**期待順位を仮定せず**変えた。
- **結果**:
  - 8 形状: downforce **tau 1.000 / rho 1.000**、V1 と V2 の両方で完全一致、verdict **pass**。
  - 合成 17 形状プール (政策内): downforce **121 組**で解像可能な反転**ゼロ**
    (tau 0.88–0.90, rho 0.973); drag 110 組 0 反転 (tau 0.87–0.88, rho 0.96)。
  - 最初の no_go は設計政策の外側 (1 セル厚) に**局在**。
- 実務的帰結: **downforce の順位保存性は、登録済み min solid width 設計政策の内側で成立**
  する。no_go は本来的に除外されるべき低解像度圈でのみ現れることが、最も管理された条件
   (binary, same-grid, 転送なし, 幾何抽出なし) で示された。

### 1.4 magnitude が示すこと (較正の現状)

Stage T |DF| / Stage V |DF| は形状により 0.05–1.06 (中央 ~0.6)。**絶対値較正は存在せず、
順位のみが主張**である (`docs/problem_resolution_plan_2026_09.md` §6.5 の原則どおり)。

---

## 2. 文献による精緻化 (web 調査)

### 2.1 Brinkman 体積力式 surrogate の既知の構造限界 — 実測と整合

- Borrvall & Petersson (2003) 以降の固定格子 fluid TO の標準は Brinkman/Darcy 体積力付き
  NS。固液界面は多孔として滑らかに表現され、**no-slip は明示できない**。
- Yonekura & Kono, J. Comput. Phys. 2021 (S0021999121005258): Brinkman では **界面近傍の
  速度/圧力分布が Darcy 係数に受動的に決定され、格子細分でも消えない** — 本日の
  「内部リーク Darcy 減衰による厚さ感度」の実測と整合する。
- Munz & Schäfer, ECCM-ECFD 2018 (p1222): NURBS+固定格子+Brinkman の代表研究で、カットセル
  の体積分数が α を決め、界面は数格子に blur すると明記。
- FSI 分野でも同一直線: Abdelhamid 2024, IJNME (Wiley `nme.7368`) は力結合を
  **surface integral と volume integral の両形**で書き下し、体積形は (発散定理変形で)
  圧力一階微分・速度二階微分を含むため感度の性質が変わることを数式で示す。
   「**表面積分で定義される力を体積積分の形に落とすと情報が滑る**」は既知の現象で、
   我々の初回 no_go の構造と正確に符合する。
- 補助参考: arXiv:2508.04261 (2025, narrow-band TO) — Stokes–Brinkman でも filtering なしで
  binary designs が得られる系統の現行 SOTA 研究の存在。

### 2.2 FSAE front wing の実物理 (本丸に必要な目標規模)

文献値として記録 (リポ内の実測では**ない**):

- **運転点**: 競技コーナー exit 速度 30–40 km/h (8–11 m/s)、top ~100 km/h。
  全車 force 系数の Re 依存は 30→100 km/h で <3% (UTAS 2009 thesis)。
- **要素ごとの Re**: F1 の解析では chord 0.1–0.2 m で Re ~1e5–5e5 (AIAA 2023-4311,
  SajT)。FSAE front wing 要素 chord 0.1–0.25 m (Palanivendhan: main 250 mm) で同程度。
- **断面**: NACA 4412 系の 12–15% 厚 → **要素厚 ~0.02–0.04 m**。
  高 DF 系では S1210 系の high-lift 翼形が使われる (Castro & Rana 引用)。
- **形状因子**: 要素数 2–4 が基本 (Ratterman & Paul 2024: overlap / vertical gap /
  incidence を主要原因と確認; Utah FSAE は 4 要素 25–45°)、gurney 高度 2–5% chord、
  endplate/gurney は FSAE の一次因子 (Wu & Agarwal, AIAA 2023-1007: 全車 drag 2.3% 減)。
- **ground effect**: 地面効果で DF 最大 ~2x、ただし pitch 感度に注意 (McBeath 系
  rules-of-thumb)。FSAE front wing は ride height 0.05–0.15 m の**地上近接 interference
  が一次効果**であり、front wing は車両全 DF の約 1/3 を担う (IRJET 引用)。

### 2.3 我々の格子スケールへの含意

- FSAE 要素の厚み (~0.02–0.04 m) は T1 fixture voxel 0.05 m では **< 1 セル** — 本日の
  障害軸と同数値帯。ただし**本番では設計格子を翼箱 (例: chord 0.4 m × span 0.9 m ×
  高さ 0.25 m) に縮小し voxel 0.0125–0.02 m とする**。すると 3 セルの min solid width
  **0.0375–0.06 m** が翼要素厚と同オーダーになり、**政策内の到達可能集合として
  FSAE 翼設計が入る** (セル数 ~10–50 万で現インフラで実行可能)。
- したがって現 fixture の障害区間は FSAE スケールでは (a) 政策で排除、(b) 本番格子では
  政策内の通常形状、であり、「本番ではまず起きない」設計が可能である。
- 一方で現 evidence は Re≈75 なので、要素ごとの Re 1e5–5e5 での B3 乱流照合が
  downforce 主張への必須橋である (kOmegaSST 含む)。

---

## 3. 本丸 (downforce) の計画

**結論**: downforce 順位保存は「`minimum_solid_width` 設計政策的空間」で成立と判定。
したがって本丸は以下の 3 条で進める。

### Route 1 (推薦, 即実行可): 政策固定の WP7 + FSAE 要素への scale-out

1. **WP7 進入 (すぐ)**:
   - Stage T (same-grid) を `minimum_solid_width_m` 政策固定で開始。
   - 目的: downforce 主 + drag 制約 (Gate-4 band と宣言帯を acceptance/rollback に内蔵)。
   - Stage V anchor-STL 検定を V2 で対候補に続け、両応答の qualified 参照を維持。
   - 絶対値スケール差 (0.45–0.75x) は「順位」評価に入れない (ranking-only claim 順守)。
2. **B2/B3 (要素レベル Re)**: 要素 wing 断面 (S1210-like camber, multi-element gap /
   overlap / incidence) に対して element-wise Re 1e5–5e5 で同じ Gate-4 再検定 —
   縮小→実機の段階橋。
3. **B5 (front wing in ground effect)**: moving ground + ride height 0.05–0.15 m、
   地面干涉スイープを含むヘッドに到達 (文献ベース: 地面効果 DF ~2x, pitch 感度)。

### Route 2 (Route 1 が政策内で失敗したときの surrogate 置換)

- 分割型: "porous は topology 空間探索のみ、**力は coarse body-fitted (V1 級 ~30k
  cells) surrogate**" に Stage T の役割を置換。実行コストは ~4–15 分/件 (現行 10 s から増)
  で、勾配評価も FD suite で担保済みの枠組みを流用する。
- あるいは IBM + explicit no-slip + topological derivative (文献 Route 3)。
  リポには `fixed_grid_backend_decision.md`, `openfoam_extensions/`,
  custom-objective-library staging の足場が既にある。

### Route 3 (研究枠・保留): 力関数の再定式化

- 単純 wakeplane 集成は**却下** (本記録 §1.2.3 probe, tau が悪化)。
- 実施する場合: FSI surface-integral 型の体積結合力の固定格子安定化
  (Wiley `nme.7368` の数式構造) を基に adjoint 設計、または IBM/level-set
  (Yonekura 2021, arXiv 2508.04261) で no-slip 表現を物理的に直す方向。OpenFOAM の
  custom adjoint objective を足場にする実装可能性は既存 `openfoam_extensions/` + 
  `src/cfd_sdf/handoff.py` パスで確認済み (実装は研究級)。

### しないこと (stop rules の継承)

- WP6 の **no tuning rule** の継承: 固定形状反証を optimizer 調整で覆さない。
- downforce 向けの乱流・Re 階層の代替部品への読み替えは、B3/B4/B5 laddering
  に従って行う (縮小ケースでの即座の tuning はしない)。

---

## 4. 主張の格付け台 (宣言のまま運ぶ)

| 項目 | 位置 | 補助 | 境界 |
| --- | --- | --- | --- |
| downforce 順位保存 | **pass** (policy-bounded, WP6-2) | Stage T vs anchor STL Stage V (V1/V2 両qualified); 17-pool 0 inversions | 最重要成果 |
| drag 順位保存 | sign-consistent (tau 0.87–0.88) | same fixture | 完全一致順位は同意しない |
| 下限解像度 (1 セル) 軸の順位 | 反転あり (政策外) | WP6 first no_go | 政策で banned。FSAE 要素スケールの設計格子では再確認が要る |
| Stage V 不確かさ帯 | downforce 0.0129–0.0147 / Cd ~0.03 | **宣言のまま** | 縮小収束掘削はしない |
| 対象物理 (Re へのスケール) | 未実施 | B3+ での課題 | FSAE 車体主張に接続しない |

---

## 5. 証拠・コミット索引

- `docs/evidence/stage_v_domain_clearance_2026_09.json` — WP1/P17 Clearance gate
- `docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json` — WP3 grid study (帯の源泉)
- `docs/evidence/stage_v_transient_check_2026_09.json` — steady output form valid
- `docs/evidence/fixed_shape_ranking_manifest_2026_09.json` — プログラム manifest
- `docs/evidence/fixed_shape_cross_fidelity_ranking_2026_09.json` — WP6 first ranking
- `docs/evidence/reachable_set_cross_fidelity_ranking_2026_09.json` — WP6-2 decisive
- コミット: `9b73ef7` P7, `6684f97` C1, `2bfbcbb` C2, `d9cf697` shapes+ranking modules,
  `493e602` WP6 first, `3d334d9` WP6-2, `57b9d5d`, `e1a7be1` fixed-domain ladder,
  `b2c37d4`, `5809c95`
- 実行成果物: `work/fixed_shape_ranking_2026_09/`
  (shapes, shapes_reachable, stage_t_results*, stage_v_*_results*, ranking*,
  extraction_block_results, alphamax_sweep_results, wake_probe/)

### 本書の主張の限界 (最重要)

1. **Re≈75 の縮小層流の証拠である**: FSAE 高 Re・乱流・回転輪・地面効果の順位保存への
   外挿主張は、B3/B4/B5 階層が通るまでしない。
2. 形状は矩形/複合箱の組合せであり、真の翼形や乱流モデルの照合はまだない。
3. Stage T の |DF| 絶対値は未較正 (ranking-only の主張枠)。downforce の N 数の
   較正や絶対値の受理判断は WP7 で Stage V qualified 値に対して行い、代理値を
   代用しない。
4. 文献値 (FSAE 要素規模, Re, ground effect 倍算) は**設計の scale-out 目標**であり、
   本記録の実測値ではない。
5. 意思決定 (Route 選択、WP7 進入) はユーザが行う。
