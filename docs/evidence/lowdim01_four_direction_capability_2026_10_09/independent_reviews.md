# LOWDIM-01 独立レビュー（実行前）

2 本の read-only レビュー（別 agent、狭いスコープ、T4・push なし）を source commit の前に受け、指摘を反映した。反映後の第 2 ラウンドは行っていない（tests と fake job による runner の fail-closed の確認で閉じている）。

## 1. 入力・geometry gate・runner の lineage
結論: **実害のある欠陥なし**。確認できた事実: 係数勾配は STEP-01 の ±2.5 mm の downforce の centered な差（N/m）で、`c = g/‖g‖₂`、`v = Σ c_i d_i`（float64）、`d = v/max|v|`（max-norm 1）、符号は maximise として正しい（勾配が負の D1/D2/P1 は負の係数）、`(c_i/m)·s` の係数が `s·d_prop` を与える、候補は runner の numpy と `construct_state` が byte 一致（registrar が assert、`--check` で再導出と一致）、`ndimage.label` の既定は面連結、volume の基準は baseline、探索と registrar は同じ関数を使い数値が一致、runner は STEP-01 の reviewed template との差分が意図どおりで残骸なし、SPARSE は十分、DONE は全 state 完了のときだけ。
| 指摘 | 対応 |
|---|---|
| 【中・文書】閾値が候補評価の前に決まったという記述が検証できず、7.5 mm が閾値の縁で落ちるのは出来すぎ | 反映: note に、閾値（丸い値）は探索から決め、候補の正確な geometry は閾値をコードに書いた後に初めて計算したが、候補の大きさ別の volume を粗く見積もっていたこと、7.5 mm が帯の外に出るのは閾値を決めた時点でおおむね予想していたことを明記 |
| clearance・mask の gate は `construct_state` が違反を例外で拒否するので常に真 | 反映: note に明記（違反する候補は registrar が abort する） |
| Eikonal の中央値は薄まりやすい | 変更なし（note に p95 / max を記録のみとした理由を記載。今回の候補は D0 が band の過半を歪めるので効いている） |
| テストが fixture の鏡写し（負の勾配の符号、係数の再構成、線形予測の単位、gate の境界値、探索と inventory の一致、候補の一意性、SPARSE の被覆） | 反映: 全て追加。registrar にも「候補が互いに・baseline と異なる」assert を追加 |

## 2. accept 規則・analyzer・文言
結論: 契約・analyzer の判定ロジックに致命的な欠陥なし（符号、strict `>` と `<=`、同点は小さい step、gate 失敗の候補は選ばれない、予測は判定に入らない、NaN は integrity 失敗、integrity 失敗時は verdict が INCOMPLETE で candidates を出さない、凍結入力は全て照合される）。
| 指摘 | 対応 |
|---|---|
| 【中】「全 reject が likely」は STEP-01 のデータで支持されない（方向ごとの変位は `s·c_i/m` で、s と取り違えていた）。ACCEPT は STEP-01 の曲率からほぼ予見できる／対照がない | 反映: 予想を書き直し（単一方向ごとの 2 次モデルの和で 1.25 / 2.5 mm は +5.0e-4 / +4.2e-4 N なので ACCEPT がありそう。D0+P1 の非加法性、ACCEPT は曲率から予見できること、NO_GO も有効）。freeze の期待も同様。**逆方向の control（1.25、2.5 mm）を追加**（accept・selection に使わず、奇数部・偶数部を記述的に記録） |
| 【低〜中】integrity 通過後の計算が try/except で包まれていない | 反映: STEP-01 と同じガード（`LOWDIM_INCOMPLETE` + 記録）。登録した gate 記録の整合（gate キー集合と `all_hard_gates_pass`）も検査 |
| `select_trial` が空入力で NO_GO を返す | 反映: 空・step 欠落は ValueError |
| freeze builder: inventory と STEP-01 解析の SHA 相互 assert、commit 前提 | 反映: assert 追加、tracked file が clean で source commit が HEAD の祖先 |
| 文言: ACCEPT の証拠範囲、nominal σ0、drag 減、単位、STEP-01 との照合範囲 | 反映: INTERPRETATION と note に追記（単一 trial・flow_24・決定論的 Float32 T4・grid-independent でない・σ0 は nominal・drag の減少は制約を満たす・照合は g_sec と step） |
| テスト: 閾値ちょうど、同点順、全 gate 失敗、空の評価、NaN の CSV、`inventory_canonical_json` 単独の改ざん | 反映: 全て追加（同点は大きい step を先に挿入して順序依存でないことを確認、閾値の境界は base 0 で厳密に） |
