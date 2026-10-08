# G2-DIAG2 結果: **DIAG2_LOCALIZED**（反事実の診断。修正ではない。gradient の qualification ではない）

事前登録（`prerun_note.md`、`prerun_freeze.json` SHA `7077cff6…`）どおりに T4 で 1 回実行し、host の terminal 検証（manifest の SHA、DONE/ERROR の排他、source・pin・入力 hash・runtime source hash・flag false・dryrun false・登録した fork/end/slope 区間）が PASS した出力に対して
`scripts/analyze_grad_g2_diag2.py` を 1 回だけ実行した（`diag2_analysis.json`、SHA `1f126dcc…`）。bridge の値・δ・GRAD-03 verdict は存在しない。reverse は未着手。6 flag は false。Float64 と D1/D2/P1 は走らせていない。

- kernel: `ramhachi888/cfd-opt-sdf-grad-g2-d0-tangent-diag2` version 1、source `6742b68`、Tesla T4。straight 再生（980 step）66 s、変種 12 本は 1 本 7〜30 s、全体で約 9 分。preflight（全 region の device/host 一致、device 間 copy）成功。
- **V0 は straight 再生と 200 step すべてで bit 一致**（fork の復元と介入なしの経路が正しい）。baseline の成長を再現した（傾き 0.1009 decade/step。DIAG1 の 0.0975、post-hoc の 0.093 と整合）。

## 変種の結果（傾き = `[880,980]` の log10(max|tangent u|)、全体 / 角の箱、decade/step）
| 変種 | 全体 | 箱 | 分類 | 980 step の全体の max |
|---|---|---|---|---|
| V0 baseline | 0.1009 | 0.1009 | baseline | 1.0e15 |
| V1a Poisson 4 反復 | 0.1713 | 0.1713 | no_effect（**悪化**） | 1.0e24 |
| V1b Poisson 16 反復 | 0.0394 | 0.0394 | reduces | 2.1e12 |
| **V1c Poisson 32 反復** | **−0.0003** | 0.0006 | **suppresses** | **21.0**（物体近傍の定常値のまま） |
| V2 Δt の tangent 固定 | 0.1009 | 0.1009 | no_effect | 1.0e15 |
| V3 角の箱の tangent を殺す | −2e-8 | −8e-6 | suppresses | 21.0 |
| V4a x-min スラブ | 0.0005 | 0.0026 | suppresses | 21.0 |
| V4b y-min スラブ | −3e-7 | −0.0049 | suppresses | 21.0 |
| V4c z-max スラブ | −1e-6 | −0.0057 | suppresses | 21.0 |
| V4d 3 スラブ同時 | −3e-6 | −0.0033 | suppresses | 20.9 |
| V5 ghost 層（外側 2 セル） | 0.0917 | 0.0917 | no_effect | 1.5e13 |
| V6 exit スラブ | 0.1009 | 0.1009 | no_effect | 1.1e15 |

Poisson の相対残差（`|r|/|z|`、最後の 50 step の平均、1 回目の projection）: baseline（1 反復）は primal 1.0e-3・tangent 2.0e-2。V1a（4 反復）は 1.1e-6・4.3e-5。V1b（16）は 3.8e-8・9.2e-7。V1c（32）は 2.9e-8・4.6e-7。

## 事前登録した仮説の機械的な分類
**H11（tangent の Poisson 解が primal の停止判定のため未収束）supports**（V1c が suppresses、V1b が reduces）。**H8（境界・角の tangent 経路）supports**（V3 と V4d が suppresses、面ごとの V4a/b/c は 3 つとも suppresses）。
**H12（Δt のフィードバック）refutes**、**H7（exit 側）refutes**、**H13（ghost 層の tangent の BC）refutes**。

## 読み方と限界（post-hoc の注意。因果の証明ではない）
- Poisson の反復数を 32 に固定すると tangent の成長が消える（980 step で 21、物体近傍の定常値）。**最も強い手がかり**は H11 だが、V1 は primal も同時に変える（primal の相対残差 1e-3 → 3e-8）。primal は baseline で既に定常なので、成長が tangent だけに現れる事実から tangent の解の精度が効くと読むのが自然だが、この実験では primal の収束と tangent の収束を分離していない。
- **単調ではない**: 4 反復は tangent の相対残差が baseline の約 1/500（4.3e-5）なのに成長は**悪化**（0.171）し、16 反復で減り、32 反復で消える。したがって「残差が小さければよい」という単純な説明では足りない。有限反復の反復解法を微分した結果は、反復数に非自明に依存する。メカニズムは未解明。
- 角の箱・3 つのスラブのどれを殺しても成長が消えるのは、モードが 3 つの面の**共通部分（角）**に局在しているため（各スラブは角を含む）。どの面が原因かは区別できない。ghost 層・exit 側・Δt の tangent は寄与していない。
- kill 系の「suppresses」は、その領域を毎 step 殺しても他所で再成長しないこと（全体の max が物体近傍の定常値に留まること）を示す。床（約 21）より下の再成長は検出できない（事前に開示した限界）。
- 増幅は DIAG1 の追補と同じく 2 つの BDIM stage（pre_scale→predict_bdim ×2.36、project1_bc→correct_bdim ×2.65）で作られ、projection（×0.57、×0.69）が部分的に打ち消す（角の箱の max、最後の 50 step の平均）。
- コスト: 32 反復でも 1 step あたり約 0.15 s（V1c は 200 step で 30 s）。登録済みの窓（約 8,740 step）を全部走らせても 1 run 約 20 分の見込み（未測定の外挿）。

## 保存した証拠
`kernel_output/`（12 変種の CSV、straight の checksum、index、manifest、run_identity、log）、`diag2_analysis.json`、`cpu_dryrun_diagnostic/`（code-path の確認のみ）、`independent_reviews.md`、`identity_free_check.json`、`prerun_freeze.json`。DIAG1・G2 の namespace は変更していない。

## 次のユーザー判断（推測で進めない）
1. **tangent の収束を含む Poisson の停止規則**の事前登録 diagnostic（反復数の走査 20〜64 と、primal と tangent の両方の残差で止める規則。長い horizon で成長の再発がないかも見る）。DIAG2 の最有力の続き。
2. 角に局在する理由（BDIM と角の境界処理の内部分解 = 第 2 弾）。1 が効くなら優先度は下がる。
3. Float64 の precision discriminator（成長を作る機構が Poisson の反復なら、dtype では解決しない可能性が高い）。
4. long-window forward bridge の断念（現時点では早い）。
