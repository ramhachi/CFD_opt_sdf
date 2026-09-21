# PQ3 — 最初の限定 OpenFOAM closed loop record（2026-09-22）

Status: **first bounded closed loop achieved**. Baseline `0c07845`（PQ0.2）。

## 結果（`docs/evidence/pq3_first_closed_loop_v5_2026_09.json`）

| iter | parent downforce | trial downforce | 改善 | bracket d_adj / d_fd | ratio |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.3934 | 0.8766 | +0.4832 | -90.45 / -86.61 | 0.958 |
| 2 | 0.8766 | 0.9525 | +0.0759 | -28.01 / -27.61 | 0.986 |
| 3 | 0.9525 | 0.9951 | +0.0426 | -18.37 / -18.03 | 0.981 |

- accepted 3 / rejected 0。volume 制約は全 accepted state で維持（最終 g_V = -0.00188）。
- counts: parent 4（初期 1 + accepted ごと 1）、bracket 3、value 9、gradient extraction 0（parent fast path）。
- resume が第1反復 trace を完全再現（追加 parent 評価 1 回のみ）。
- magnitude 補正は不使用。bracket の符号一致と実 primal 改善だけで受理。

## 途中で必要になった登録済み修正（v2–v5）

1. v2: Path B 受理プロファイル（`trust_veto=false`）— adjoint magnitude を信頼しないため、
   low trust は move を縮めるが拒否しない。
2. v3: bracket ε のバックオフ（対称点が作れるまで ε を縮小、方向は不変）。
3. v4: seed を「body 近傍 2 セル膨張のみ floor」に変更（物理レジームを元の body に近づける）。
4. v5: **bound margin 1e-4 の両側マスク** — centered bracket は perturb される全セルが
   両境界から ε 以上離れている必要があり、境界近傍セルは符号によらず方向を 0 にする。

各版は manifest を先に登録して実行し、失敗 evidence も記録として残した（v2/v3/v4）。

## 言えること / 言えないこと

- 言える: production path（compiler + transform + 分割 oracle + Path B bracket + 受理 +
  checkpoint）が実 OpenFOAM 上で reduced problem を単調改善できる。符号一致と実 primal 再評価が
  受理根拠として機能した。
- 言えない: grid independence、target physics、絶対力校正。seed の floor が作る porous
  neighbourhood レジームは空力的に意味のある最適形状ではない（loop capability の検証）。
- 次の判断: PQ1.1（gradient 資格化の続き）と PQ4（抽出・Stage S）のどちらを先にするか。
  Stage S へ進むには PQ3 candidate の抽出 Gate と surface FD が必要。
