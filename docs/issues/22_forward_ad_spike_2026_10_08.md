# #22 GRAD-02 follow-up: forward-mode AD spike（CPU・結果 PARTIAL、判定はユーザー）

日付: 2026-10-08 / 起草: Claude。証拠: `docs/evidence/grad02_forward_ad_spike_2026_10_08/`（`note.md` が結果、`prerun_note.md` が事前規則）。
6 つの qualification flag は false のまま。Kaggle・T4 は使っていない。#23 の scope と δ は変更・決定していない。

## 問い
reverse が `MixedDuplicated(::Flow, ::Flow)` で止まる（#22）ため、GRAD-03 を (3a) forward AD と FD oracle の比較、
(3b) reverse と forward AD の比較、に分けられるか。そのために、forward-mode AD（ForwardDiff の Dual）が Candidate C 複合 body の
`sim_step!` を通って、phi の摂動方向への微分を返せるかを CPU で調べた。

## 結果（事前登録した規則どおり PARTIAL）
- AD は toy（解析球）と実 canonical v17（D0、flow 150×72×54、2 ステップ）の両方で完走し、tangent は有限。AD の primal は通常 primal と 1e-13 級で一致。
- canonical の一致は FD に対して 1e-5 級（等級 A）。toy は参照 ε=1e-5 が応答の非平滑域に入り等級 C（規則の B に届かず）。
  事後診断で、ε ≤ 1e-6 では AD と FD が 2e-9〜1.4e-7 で一致した。toy では Candidate C の blend は不活性で、blend を通した検証は canonical tier のみ。規則・判定は動かしていない。
- reverse: `mom_step!` を concrete 型で呼ぶと、同じ MethodError だが失敗箇所が `pressure_force` に移った（仮説は否定も肯定もできない。次は力の関数も concrete 化）。

## 示唆
1. （私の見解）forward AD は選択肢として有望。ただし oracle の設定（窓 80〜120、約 8,700 ステップ、Float32、T4）では CPU は非現実的で、
   **GPU（CuArray）上の Dual が動くかが次の未確認事項**（短い T4 run の spike が要る。要承認）。
2. AD は点別の微分、FD-08 の ĝ は ε 0.5〜5 mm の回帰傾き。この差は未定量で、GRAD-03 の δ の設計に影響する。
3. 3b（reverse vs forward）には reverse の復旧が要る。次の候補: `mom_step!` の kwargs を除いた positional 版の書き直し、
   または upstream への報告・custom adjoint（#24 GRAD-04、#39 ADJ-01）。

## ユーザーに決めてほしいこと
- PARTIAL の結果を踏まえて、GPU 上の Dual の spike（Kaggle T4・短時間）に進むか。
- reverse の復旧（positional 化の試行）と #24/#39 のどちらを先にするか。
- δ の選択肢（案 A〜D）に、点別微分とメソスケール傾きの差を織り込む方針でよいか。
