# FD-08 R5 P1 事後診断

証拠区分: solver_free_post_hoc_calibration_diagnostic_unregistered。
P2判断用の記述的解析であり、criteriaの登録、epsilon・gateの変更、formal ladderの選択、
R5の確定FAILの変更は行っていない。

- R5 criteria SHA-256: 928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c
- 既存R5解析 SHA-256: dc769d6f2b5a2d6dfa45c6a5aeddfde726dd75f6e44ac564b128effecce3fb8b
- runner manifest SHA-256: 1b04c3c2243459d2889dc16aa0f3c02c2ff6a5555a64406bb8177b9ee0b8600e（244 files）
- download dataset inventory SHA-256: 593386fa48e1d004b9ad28ddff1b054c456bb903c8e5ebd83b475ac6a40f6954（89 files）
- 診断スクリプト SHA-256: d8260950f654cded0209537a4270207a93210a6bd8aa211d3a54699b18173f80
- 診断JSON SHA-256: 2b13484f52b63a7504bb34954e3fe18bea45efa65bb7b79f5394118be555ce12
- 描画環境: Matplotlib 3.11.1
- 図のタイトル・軸・凡例・注記の言語: 日本語
- 基準 integration HEAD: 5ee6bd9908974616362ac4992e4f4d601b77d00b

## P2向けの観測

R5 verdictはFAILのまま、登録済み5点selectorはNO_COMMON_PLATEAUのまま。
42/42のdirectional responseは既登録response floorを上回るが、formal ladderは選択されていない。
図はraw historyから再計算したq(epsilon)、探索的なepsilon² suffix fit、S残差、
Float32実現変位、47 stateの半窓stationarity、±応答の半窓感度を示す。

以下の±5%区間は、登録済み7 epsilonのうち3点以上からなる全連続窓について、
窓ごとのq中央値に対する最大偏差を列挙した未登録の説明用集計である。
登録済みの共通5点gateを置き換えるものではない。

| Direction / response | 最長の説明用区間 (mm) |
| --- | --- |
| D0_interface_offset / drag | 該当なし |
| D0_interface_offset / downforce | 0.05–1.5 (4 pts), 0.15–5 (4 pts) |
| D1_filtered_seed11 / drag | 該当なし |
| D1_filtered_seed11 / downforce | 該当なし |
| D2_filtered_seed2026 / drag | 0.05–15 (6 pts) |
| D2_filtered_seed2026 / downforce | 0.5–15 (4 pts) |

この説明用定義でも6系列に共通する区間はない。D1 drag/downforceとD0 dragには
3点以上の区間がなく、D0 downforceとD2の2系列には個別の区間がある。
したがって、局所的な一致が一部に見えてもR5の共通5点失敗は解消しない。

### 大epsilon側のq = q0 + c epsilon² fit（各系列の最後4点、記述値）

| Direction / response | q0 (N/m) | c (N/m/mm²) | RMSE (N/m) | R² |
| --- | ---: | ---: | ---: | ---: |
| D0_interface_offset / drag | -0.13437 | -0.00012852 | 0.02487 | 0.9671 |
| D0_interface_offset / downforce | 0.70248 | -0.00020136 | 0.1011 | 0.8139 |
| D1_filtered_seed11 / drag | -0.061382 | -1.9768e-05 | 0.006413 | 0.9128 |
| D1_filtered_seed11 / downforce | -0.096464 | 4.7093e-05 | 0.01227 | 0.9419 |
| D2_filtered_seed2026 / drag | -0.17234 | 5.764e-05 | 0.002549 | 0.9982 |
| D2_filtered_seed2026 / downforce | -0.096767 | 1.8849e-05 | 0.0008741 | 0.9981 |

suffixは4点だけで、q0は大epsilon側からの外挿である。適合度は方向・responseで異なり、
この表だけで滑らかな曲率やcut/mask切替の機構を判定しない。

### 小epsilon側のS残差

S_ref = q_ref epsilon、q_refは各系列の最初の3点のq中央値とした。
最初の3点のうちqが中央値になる点の残差は定義上0 N（該当点は系列ごとに異なる）。
最初の3点における絶対残差の最大はdragで
3.379e-06 N、
downforceで
2.163e-06 N。
これは一つの固定参照からの差であり、quantizationの証拠やnoise floorとして登録した値ではない。

### 実現変位と格子幅

SDF lattice spacingは25 mm、flow cell幅は33.33 mm。
名目epsilonはSDF幅の0.002〜2倍、
flow cell幅の0.0015〜1.5倍。
42個のplus/minus perturbationでchanged-node countは4718〜4718。
maximum |delta phi| とdirectionへの射影epsilonは名目値にほぼ一致する一方、
changed nodes上のRMS / 名目epsilonの平均は
D0 1.0000, D1 0.2894, D2 0.2897。
全grid上のRMS/名目epsilonはそれぞれ
D0 0.1106, D1 0.0320, D2 0.0321。
direction射影比は0.9999999920〜1.0000000126、
最大点変位/名目epsilonは0.9999999429〜1.0000000534。
したがってepsilon等価性は指標依存であり、RMS比をmax値や射影比と混同しない。
ここでのmax/RMSはphi格子値の変化量であり、zero-isosurfaceの直接移動距離ではない。
滑らかなSDF上では局所的にdelta n ≈ -delta phi/|grad phi|と関係するが、今回その距離場を
別途計測・適格化してはいない。direction射影比だけで方向間RMS等価性は示せない。

### Stationarity

47 stateの最大半窓driftはdrag 1.42038e-05、
downforce 3.36085e-05。
全stateでrunner記録と再計算値が一致した。これは半窓比較の確認であり、
あらゆる時間依存誤差がないことを証明するものではない。各stateの力（約0.33 N）に対する
相対driftが小さくても、plus/minusの差分S（µN級）への相対影響は大きくなり得る。
次表は各epsilonでSを半窓ごとに計算し、|S_first-S_second|/|S_full|をとった事後診断である。
これは新しいgateではなく、時間窓依存の大きさを見る感度指標である。

| Direction / response | 最大相対差 | epsilon (mm) | median相対差 |
| --- | ---: | ---: | ---: |
| D0_interface_offset / drag | 9.493% | 0.05 | 0.223% |
| D0_interface_offset / downforce | 6.431% | 0.05 | 0.127% |
| D1_filtered_seed11 / drag | 13.862% | 0.05 | 0.182% |
| D1_filtered_seed11 / downforce | 72.324% | 0.05 | 0.791% |
| D2_filtered_seed2026 / drag | 1.024% | 0.15 | 0.059% |
| D2_filtered_seed2026 / downforce | 9.928% | 0.15 | 0.461% |

特にD1 downforce ε=0.05 mmでは、S_first=-5.11758475e-06 N、
S_second=-2.39931949e-06 N、
S_full=-3.75845212e-06 Nで、相対差は
72.324%だった。
bit-identical baseline repeatsは同じ計算の再現性を示すが、決定論的な過渡応答や時間窓依存を
除外しない。小epsilonの不規則さをcut切替だけに帰属させる根拠はない。

## P2で残る判断

P1結果はB1/B1-prime/B2/B3のいずれかを自動選択しない。特にD1に3点の±5%区間が
ないことだけでは、5%条件が構造的に達成不能とは証明できず、B1-primeのgate変更根拠
にはならない。逆に一部系列の局所区間やtail fitだけで共通FD oracleを主張できない。
R6登録・submit、gateやladderの変更、FD-08定義やdirectionの変更はP2のユーザー判断待ち。
fresh33は未登録・未実行で、全qualification flagはfalseのまま。

## 図

- q_by_epsilon.png — SHA-256 014ea4ae4acb8f10d6da6d14782f3ef5fd9caaac69fba07ba5e9fc1f0458ec5e
- q_vs_epsilon_squared_tail_fits.png — SHA-256 ae1496e091c4760c14703e137f27fde332d5a40841bb43d402cd0580fb0f9d84
- centered_response_residual.png — SHA-256 78ac68f79e6014e2e4d009db0e206a6e7125c1ff3023e4c0d787533275be18cc
- float32_realized_perturbation.png — SHA-256 7c21ce4593c7c0f4a3b03d245553f3997cfc0020c3f2172c2dd55dffc588e0e3
- stationarity_half_window_drift.png — SHA-256 2b9f4cc50283f14ec45830224e519191784e78aca15985361324b0efe82752e9
- paired_response_half_window_sensitivity.png — SHA-256 4695e90e9847ba9c66327c81e6c9672405b43091ee9f1be57344687a66a74b2e

## P2での停止点

この成果物の範囲はP2のユーザー判断まで。R6は未登録・未submit、fresh33は未登録・未実行。
B1/B1-prime/B2/B3、およびladder・gate・FD-08定義・directionの変更は承認済み計画に従い
ユーザー判断待ち。全qualification flagはfalseのまま。

epsilonごとの値、hash、source binding、Float32変位、stationarity値はdiagnostic_result.jsonを参照。
