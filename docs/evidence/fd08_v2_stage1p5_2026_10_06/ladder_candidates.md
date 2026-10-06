# L-1 ladder候補（未確定）

入力だけのdesign conditioning。responseやR5を使用しない。WLS条件数はpilot/重み依存なので、以下のOLS条件数だけから精度・検出力を保証しない。numeric experimentにはweighted condも保存した。

| 案 | epsilon mm | span | full/holdout dof | 内部holdout | formal ε mm | N1 cond A/B | N3 cond A/B |
| --- | --- | ---: | --- | ---: | --- | --- | --- |
| L6 | 0.5, 0.792446596231, 1.25594321575, 1.99053585277, 3.1547867224, 5 | 10 | 4/3 | 4 | 0.629462705897, 1.58113883008, 3.97164117362 | 44.9275/14.5577 | 4.34405/6.47518 |
| L8 | 0.3, 0.448405649938, 0.670225422986, 1.00177622133, 1.49734039206, 2.23805297226, 3.34518532541, 5 | 16.667 | 6/5 | 6 | 0.36677199318, 1.22474487139, 4.08973429785 | 42.3846/13.9412 | 4.23966/6.32036 |
| L15 | 0.5, 0.881367191634, 1.55361625298, 2.73861278753, 4.82744692303, 8.50950667462, 15 | 30 | 5/4 | 5 | 0.663840037823, 2.06270534428, 11.2979024655 | 439.549/43.7625 | 4.5156/6.58466 |

**推奨L6: geomspace(.5,5,6)**。2係数full fit dof4、内部holdout4、holdout fit dof3、sign末尾3drop後も3点。最低限を満たす小さな回帰設計として選び、PASS率で選ばない。L8は8点/より小さい下端で曲率/低εの情報が増えるがSNR/Float32解像度と費用tradeoff。L15は曲率の形の差を拡大する比較案であり、非線形・model misspecificationのリスクも増える。上端を単に上げても真のε→0導関数を保証しない。

旧7点以上/100倍spanの所在はsrc/cfd_sdf/fd08_calibration.py:28–29、:225–233。旧gateは多数のcontiguous5点plateau窓を探索する設計だった。v2は全点で2係数回帰・subset stability・内部holdoutを行うため、100倍spanはfull rankや回帰identifiabilityの必要条件ではなく、長いspanはモデルが局所近似である条件を損ない得る。6点を採る理由は自由度とholdoutを持つ事前モデル設計であり、R5FAILを覆すためではない。新v2にだけ別validator/criteriaが必要で、旧validatorは変更しない。

nominal εはmax-normalized scalar phiへの係数[m]。法線変位とは別で、canonical gradientとの変換をdirection_designに示す。Float32では点ごとの最小変化はlocal phiのULPと|d|次第で、ε/hやmax(d)=1だけでは全supportが変更されるとは保証できない。将来の登録前に全calibration/formalの±byte列、changednode数、actualmax/RMS、zero-margin/mask、effectivecentered direction L2≤0.05/abs cosine<.95を検査する案。今回はsignedstateを生成せず、その合否は未測定。gate失敗なら登録停止し、force結果を見てladderを調整しない。

formal εは全案でcalibration端点の内部、未使用点の幾何平均。旧formal部分集合を使わない。承認後にFloat32 byte uniquenessを確認し、formalやjitterとの重複は登録を止める。N3 εrefは承認ladderから決まるまでproduction候補として確定しない。
