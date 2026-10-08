# G2-DIAG3 結果: **TANGENT_ONLY_NO_SUPPORT**（診断。gradient の qualification ではない。Stage B は走らず）

事前登録（`prerun_note.md`、`prerun_freeze.json` SHA `42ccd790…`）どおりに T4 で 1 回実行し、host の terminal 検証（manifest の SHA、DONE/ERROR の排他、status COMPLETE、source・pin・入力 hash・runtime source hash・自分自身の analyzer の SHA・flag false・dryrun false・登録した fork/end/slope 区間・arm の一覧）が PASS した出力に対して
`scripts/analyze_grad_g2_diag3.py` を 1 回だけ実行した（`diag3_analysis.json`、SHA `30cbe150…`）。bridge の値・FD-08 の ĝ との比較・δ・GRAD-03 verdict は存在しない。reverse は未着手。6 flag は false。Float64 と D1/D2/P1 は走らせていない。

- kernel: `ramhachi888/cfd-opt-sdf-grad-g2-d0-tangent-poisson-diag3` version 1、source `f097dcd`、Tesla T4。全体で約 16 分（straight 66 s、24 arm で計約 500 s）。smoke（production の経路）と補助の演算子の一致検査は成功。
- **A0 は straight 再生と 200 step すべてで bit 一致**し、baseline の成長を再現した（傾き 0.1009 decade/step、floor = 20.98）。

## 主結果（primal の値は全 step で plain 再生と bit 一致の arm）
| arm 群 | tangent 残差（活性集合の平均除去後、`max|δr|/max|δz|`） | 成長の傾き（decade/step） | 判定 |
|---|---|---|---|
| A0 baseline（primal 停止のみ） | 約 2.7e-2（継続前の値） | 0.1009 | baseline |
| **A1 固定 cycle 数 1, 2, 4, …, 64**（tangent-only、1 projection あたり最大 64 cycle） | 1e-3（n=1）→ 1.6e-7（n=48〜64） | **0.1006〜0.1058（全て）** | **no_effect（14 個全て）** |
| **A1 τ = 1e-4, 1e-5, 1e-6, 1e-7** | 4e-5 → 1.7e-7（τ=1e-7 は約 22% の projection が cycle 上限 64 に達した） | 0.1007〜0.1008 | **no_effect（4 個全て）** |

tangent の Poisson 残差を 2.7e-2 から 1e-7 まで下げても、primal の bytes を保ったまま継続しても、成長は**まったく変わらない**（980 step の全体の max はどれも約 5e14、baseline 1e15）。onset も同じ（箱の max が 1 を超える step: baseline 838、A1 n32 836）。
plateau（連続 3 個以上の suppresses）は threshold・count のどちらの family にも存在せず、事前登録の規則で **TANGENT_ONLY_NO_SUPPORT**。選択される候補はなく、Stage B（長い horizon）は走らなかった（`SKIPPED_NO_CANDIDATE`）。

## 副の arm（primal も変わる）と drift
- **D（Dual 停止: primal と tangent の両方の残差が小さくなるまで Dual 反復）τ = 1e-4〜1e-7**: primal の相対残差 1e-6〜4e-8、tangent の残差 4e-5〜1e-7、1 projection あたり 4〜24 反復。傾き 0.19 / 0.148 / 0.085 / 0.115 → **no_effect（4 個全て）**。ただし τ=1e-7 では箱の max が 1 を超える step が 865（baseline 838）に遅れ、980 step の値は 1e7（baseline 1e15）。
- **F32（強制 32 Dual 反復、DIAG2 の V1c の再現）**: 傾き −0.0003、980 step の全体の max 21.0（箱 3.4e-2）→ suppresses。DIAG2 の結果が再現した。
- **primal の変化量（dual/F32 とも同程度）**: u の相対 L2 差 最大 3.3e-6、p の相対 L2 差 最大 5e-4（2.4e-4〜5.8e-4）、力は fx で 4e-5、fz で 8e-5（相対）。つまり「32 反復」は FD-08 の観測量の primal を 1e-4 のオーダーで動かす。

## 読み方（post-hoc。登録した規則の外）
- **tangent の Poisson 解の収束（H11）は成長の原因ではない**: 残差を 1e-7 まで落としても（primal の値は不変）、primal も tangent も収束させる Dual 停止の arm でも、成長は消えない。DIAG2 で「supports」と分類した H11 は、tangent-only の継続では支持されなかった。DIAG1 追補の H11（primal だけの停止判定が原因）も同様に支持されない。
  したがって「tangent を含む停止規則」は修正にならない（D arm が事実上それ）。
- **gauge（定数モード）は無関係**: 活性集合の平均は `max|δz|` の 2e-13 倍で、平均を除く前後の残差は同一（H14 は production では重要でない。fixture では Dual の経路が平均を除かないことを確認しただけ）。
- **F32 だけが抑える理由は残差の大きさでも primal の変化量でも説明できない**: F32 と D（τ=1e-7、1 projection あたり 22〜24 反復）は primal の変化量も残差も同程度（むしろ D のほうが tangent 残差は小さい）なのに、傾きは −0.0003 と 0.115。DIAG2 の反復数の走査（4: 0.171、16: 0.039、32: −0.0003）も単調ではない。
- **「抑制」は onset の遅れである可能性がある**（未検証）: D（τ=1e-7）は傾きが同じでも onset が約 27 step 遅れ、F32 は 200 step の窓の中で箱の max が 3.4e-2 のまま（onset が窓の外かもしれない）。DIAG2 と DIAG3 の窓は 200 step しかなく、F32 が成長を**消す**のか**遅らせる**だけなのかは区別できない。
- 成長率（約 ×1.26/step）は A の主 arm の全てで同じで、tangent の線形化された時間発展の不安定モードの性質に見える。primal の状態が onset の時刻（step 約 800〜840）を決めているらしい。

## 保存した証拠
`kernel_output/`（24 arm の CSV、straight の checksum、drift、index、manifest、run_identity、log）、`diag3_analysis.json`、`fixture_results.json`（CPU の数学の検証）、`cpu_dryrun_diagnostic/`（code-path の確認のみ）、`independent_reviews.md`、`identity_free_check.json`、`prerun_freeze.json`。DIAG1・DIAG2・G2 の namespace は変更していない。

## 次のユーザー判断（推測で進めない）
1. **F32（強制 32 反復）を長い horizon（例: step 1500 まで）で再生**: 成長が消えるのか遅れるだけなのかを切り分ける。onset の時刻と、onset を決める primal の事象（step 約 800〜840 に角の箱の近傍で何が起きるか）を特定する材料にもなる。DIAG3 の次の自然な 1 手。
2. 角に局在するモードの線形化の内部分解（BDIM・`conv_diff!` の境界の閉包・角）— tangent の Poisson が原因でないので優先度が上がった。
3. Float64 の precision discriminator（tangent の Poisson が原因でないなら、dtype でも直らない可能性が高いことは変わらない。ただし丸め誤差のシードの違いを見る意味はある）。
4. long-window forward bridge の断念（現時点では早い）。
