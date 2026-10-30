# B-4 coverage 選択肢（提案・未承認）

証拠区分 `solver_free_contract_design_unregistered`。#23 と direction 登録を変更しない。

| 項目 | COV-A: 全登録方向 | COV-B: 一般的な部分 coverage |
| --- | --- | --- |
| 方向の qualification | 方向ごとに drag/downforce 両方 PASS が必要 | 同左。片方だけPASSの方向をqualifiedに数えない |
| campaign 集約 | 登録した全方向で両応答PASS。resolved failureがあればFAIL、failureなしで未解決があればUNRESOLVED | 例: 固定4方向中3以上が両応答PASS。数・分母・失敗/未解決の集約・許可集合を観測前に固定 |
| D1 | 他方向と同じ必須方向 | D1を特別除外しない。失敗した方向名に依存しない一般規則のみ |
| #23 | every registered direction を維持 | qualified方向だけ比較するなら every registered direction の意味が変わる。別途明示的scope承認が必要 |
| optimizerへの情報 | 4個の方向テストはfield gradient全体の精度証明ではない | 使用できるのは固定qualified spanに限る。観測後のspan変更は選択バイアス |

**推奨 COV-A**。D0/D1/D2 + 将来承認される1つのローブの計4方向×drag/downforce=8系列すべてを要求する。D1の失敗確率を下げるためにcoverageを変えない。R6の判定とformalの判定を別に残す。

2026-10-06取得の [#23](https://github.com/ramhachi/CFD_opt_sdf/issues/23) は、正準stateと固定方向、drag/downforceの別field gradients、全登録方向でg_field·dとqualified centeredFDの比較、Poisson等solver toleranceの結合、非有限・符号不一致・登録error gate失敗でfail closedを要求する。本文に数値δはなく、最新コメントはFD-02 prerequisiteをCandidate C上のFD-08 PASSへ置換する。COV-Bはこの全方向条項と整合しない。

Dを非直交方向の列とすれば、方向観測はD^T Gの情報であり、full-field Gの全成分を同定しない。係数空間を使うならbasisのrank/Gram・係数尺度・固定span・投影を別契約にする。qualified方向の部分集合を使うことをfull-field qualificationと呼ばない。[LOWDIM-01 #48](https://github.com/ramhachi/CFD_opt_sdf/issues/48) は固定basisの2N primalという保険経路で、OPT-01を閉じず、代替にはphase_planでの正式supersessionが必要。現phase_plan:4939、4956–4957も同じ位置づけ。本作業はその変更を行わない。
