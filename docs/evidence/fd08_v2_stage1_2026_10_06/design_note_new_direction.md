# B-6 新 direction と jitter の設計メモ（未決・未登録）

証拠区分は `solver_free_design_and_simulation_unregistered`。全 qualification flag は false。新 direction を加えるかは B-6 の未決事項であり、本メモは direction、hash、dataset、criteria を登録しない。D0/D1/D2 の配列と hash を保護履歴として維持する。R5 に新 gate を適用していない。

## 滑らかな低次ローブの生成案

入力は正準 state の phi、origin、spacing、変更を許す 4718 ノードの集合、外向き法線 `n=+∇phi/|∇phi|`。4718 は指示文 §5 の設計入力条件であり、本作業では canonical artifact を読み出して測定していない。固定・禁止・root ノードは従来どおり除外する。中心、主軸、各軸の幅を事前に数値と単位で固定し、solver の応答を見て選ばない。

1. 各許可ノードの正準座標で `r²=Σ_j((x_j-center_j)/width_j)²` を計算し、低次ローブ `a(x)=max(1-r²,0)³` を作る。境界で 2 階微分まで連続であり、高周波のランダム場を導入しない。幅を数 grid spacing より十分広くする条件、中心の選択、node mask 端の滑らかさは新しい生成契約で固定する必要がある。
2. `u=a*n` を希望する法線変位とする。`phi<0=solid` の規約では、一次の level-set 変化は `δphi≈-u·∇phi=-a|∇phi|`。正準 phi の局所 gradient から magnitude を求め、外向き法線の向きを照合する。`|∇phi|≈1` は保証せず、低 gradient のノードをどう扱うかも事前決定する。これは SDF 値の変位と幾何的法線変位を同一視しないための設計である。
3. 従来の narrow-band taper と許可 mask を掛け、`d_raw=-a|∇phi|*taper*mask`。全ゼロ・非有限を拒否し、`d=d_raw/max(abs(d_raw))` とする。`np.ascontiguousarray(d,dtype='<f4')` で float32、C 順の全格子 scalar direction にする。max=1 を float32 変換後にも検査する。新ローブと D0 の cosine が大きい場合は独立な情報が乏しい。現行 duplicate 検査の境界を使うかも未決で、測定後に幅を変えて合格させない。
4. 今後の事前登録時には `phi±=float32(phi0±epsilon_nominal_m*d)` を構成し、各符号の実現 max、許可 node RMS、全格子 RMS、変更ノード数、支持外 phi の byte 同一性、margin と masks の保持を記録する。`epsilon_nominal_m` は最大 SDF 値変位の係数であり、実現した物理的法線変位は `-δphi/|∇phi|` の一次近似および零等値面の位置で別に評価する。support 入力が 4718 でも、ローブのゼロと float32 丸めにより実変更数は小さくなり得る。
5. direction hash は既存 `direction_sha256` と同じ、little-endian float32 C 順の bytes に対する SHA-256 とする。`(phi+−phi−)/(2*epsilon_nominal_m)` と requested d の support 上の相対 L2 誤差・cosine、非ゼロ変更の両符号、実現 max を検査する。現行 float32 direction 相対 L2 limit は 0.05 (`src/cfd_sdf/fd08_calibration.py:31`)。新契約での採否は未決。本 Stage 1 は生成器・配列・hash を作成しない。

実在 source: `src/cfd_sdf/gradients/directional_fd.py:43` (hash)、`:47` (active mask)、`:51` (taper)、`:61` (max normalization)、`:96` (保護された D0/D1/D2)、`:115` (固定 3-direction validation)、`:177` (signed state)、`:243` (単方向検査)、`src/cfd_sdf/fd08_calibration.py:461` (effective float32 direction audit)。これらを編集せず、新方向を採用する場合だけ別の生成契約と inventory を設計する。

| 選択肢 | 実装量・予算 | 期待される利点 | 未検証・限界 |
| --- | --- | --- | --- |
| 新ローブなし | 新 direction/hash/生成契約を追加しない | 現行の固定方向を保持しやすい | 滑らかな方向の多様性を増やさない |
| 新ローブ 1 種 | 新 generator、source/array hash、max/float32 gate、方向 inventory と登録器の別契約。追加 state は `2*ε点数+2` | 低周波の異なる空間分布で方向ごとの頑健さを調べられる可能性 | force 応答の大きさ、g の安定、D0 との非重複は solver なしでは分からない |

4 方向 ×6 ε、baseline 1、各方向 jitter 2 は 57 state、solver 約 6195.9 s、経過約 10413.9 s。現行 solver 上限 5400 s を超える（詳細は `design_tables.md`）。新方向の smoothness だけでは FD-qualified と呼べず、B-4 の被覆規則や #23 の scope を変えない。

## jitter: 2 state の意味、推定できる量と自由度

指示文 §5 の「`epsilon_m*(1+δ)`、δ=1e-3 の ±1 ペア」を、**1 つのずらした magnitude `epsilon_j=epsilon_mid*(1.001)` における 2 符号の state** と読む。odd centered response は `S_j=(F(+epsilon_j)-F(-epsilon_j))/2`。これで各 direction,response に 1 個の J が得られる。偶数点 ladder の中央は中 2 点の幾何平均、奇数点は中央の点を候補とし、選択規則と signed state hash を実行前に固定する必要がある。

背景 B 計画 §4 の `epsilon*(1±1e-3)` は 2 magnitude とも読める。両 magnitude の centered S を得るなら **4 state/方向** が必要であり、2 state/方向とは両立しない。本表は指示文の 2 state 案のみを数え、この曖昧さを次の登録前の判断事項として残す。異なる magnitude の片側 force を引き算して同じ ε の centered S と扱わない。

model A は jitter を全て除外した元 ladder 全点で、一度の pilot→WLS、非 scale 共分散 C を使って固定する。`epsilon_j` を mm に換算して `x_j=(epsilon_j,epsilon_j³)`、`S_hat_j=x_j*(g_hat,c_hat)`、`J=S_j-S_hat_j`。単純な `S(epsilon*(1+δ))-(1+δ)*S(epsilon)` は cubic 成分があると `c*epsilon³*((1+δ)³-(1+δ))≈2δ*c*epsilon³` を残すため使わない。指示文の D0 drag・5 mm で約 0.26 µN はこの式の説明用であり、本作業の R5 再計算・noise 測定値ではない。

`sigma0_n` は **S の**絶対ノイズの仮定であり、個々の F のノイズではない。独立な両 sign force の variance が v なら centered S の variance は v/2。sign が相関するなら `(v_plus+v_minus-2*Cov(F_plus,F_minus))/4`。J にはさらに fit uncertainty `x_j^T C x_j`、model misspecification、δ による決定論的離散化変動が入る。baseline が bit 同一でも jitter が「再現しない noise」を単独で同定するわけではなく、σ0 をそのまま置き換えるには根拠が要る。

4 方向 ×2 応答で 8 個の J を pool する案の条件付き推定は以下である。

- **独立・同分散・正規、共通の未知平均 μ**を仮定すると、`s_J²=Σ(J_i−J_bar)²/7`、自由度 ν=7。95% 区間は `sqrt(7*s_J²/χ²_7(.975)) ≤ sigma_J ≤ sqrt(7*s_J²/χ²_7(.025))`、すなわち `[0.661174149, 2.035272091]*s_J`。これは未知の共通平均を引いた **J の pooled scale** の区間である。
- **平均が厳密に 0 と既知**で独立・同分散・正規なら、`sigma_hat_J²=ΣJ_i²/8`、ν=8。95% 区間は `[0.675457034, 1.915770883]*sigma_hat_J`。未知平均を推定した ν=7 と混ぜない。
- 各 direction,response は J が **1 個のみ**。ゼロ平均を既知とする強い仮定なら `J²/sigma_J²~χ²_1` で ν=1、区間は `[0.446149185,31.910159350]*abs(J)` と極めて広い。平均も未知なら 1 個から variance は推定できず ν=0。2 force state は別の符号・別の形状であり、同じ response の iid 反復 2 個ではない。
- direction ごとの drag/downforce 2 個を同じ未知平均・同 variance の独立な標本として扱えば ν=1 だが、同じ 2 solver state から出る force components には相関があり、尺度も違う。この仮定は未検証。方向ごとの「自由度 1」を無条件の noise measurement として記載しない。

同一 ladder fit を共有する予測誤差、方向ごとの不均一性、drag/downforce の相関がある場合、単純な χ² CI の coverage は保証されない。将来は共分散 V が既知なら `J^T V^{-1}J` (既知ゼロ平均) または GLS の平均残差から conditional χ² を作れるが、8 個だけから V を安定に推定できない。model bias と noise の分離には同一 state の追加反復または別に固定された noise model が要る。本メモはそれらを実行・登録していない。

χ² quantile は既存 SciPy の `scipy.stats.chi2.ppf` で計算した説明値。実行で σ を測定したという主張はしない。B-3〜B-7、ladder、jitter の定義と pooling の採否は未決のまま停止する。
