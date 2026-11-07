# WP4 設計メモ

## Amendment 5 対応設計（attempt 4、2026-11-07）

基点 `db36e4e5`（WP1／WP3 統合済み）、開始差分は空。今回の authority は
follow-ups worktree の登録 Amendment 1–5 と `wp04_review_1_opus.md`。
登録本文、roadmap、旧 evidence、凍結 source、Julia Project／Manifest は変更しない。
commit／push／PR 更新は Claude host が担当する。今回の記録は
`reports/wp04_validation_amend5/` に追加し、過去の実行記録は保存する。

- Julia: 静的 scene の `sim_step!` を `remeasure=false` とし fingerprint に束縛。
  CPU で remeasure=true との場・力・窓の bit 一致、branch 内 WP1 Checkpoint の再開、
  Tuple union の isbitstype、Δt collapse の NUMERICAL 経路を検査する。
  WP2 Force00 が無ければ cur のみ。外部 worktree を指す環境変数は使わない。
- analyzer／独立 checker: 各 Re の Δ12／Δ23 の必要区間から三状態を判定して合成する。
  σ_d=max(A,B) は点推定、90% t 区間は df=P−1。cell severity と研究ラベルの順を分離。
  freeze に束縛された digitisation の数値内容から TR 参照増分・保守的不確かさを再計算し、
  数値内容が同一の二読取は拒否。written-once の `tr00.json` と `SHA256SUMS` を追加する。
- campaign: 既存3 kernel に Re 別 E1／主格子／phase0／520 c1/U の pre-run state を追加。
  `prerun_window.py` は実時系列の endpoint-clipped time-weighted block mean から
  B／S0／W を求め、単位・式・series SHA を持つ record を1回だけ書く。formal は
  record と raw series の再計算・SHA を要求し、手入力の統計値は拒否する。
  B の100 c1/U block の位置と SE の定義はデータを見る前に実装・テストで明示する。
  環境は TOPO2D_*／W4_*／CUDA_* を除去した後、campaign の明示設定だけを適用する。
  freeze admission は UNVERIFIED_OCR source を拒否し、numerical stop は
  (configuration, Re, height, role) ごととする。
- 幾何: 形と sampling 規則は変更せず、E3 半フラップの鼻の薄さを再計算して metadata に
  記録する。scene JSON の `polygon_mm` は終点を重複しない順序付き頂点列で、閉辺は暗黙、
  重複拒否を schema と docstring に明記する。全10 scene を再出力して座標不変を検査し、
  campaign SHA と図を追従させる。

分担: Julia worker／解析 worker／campaign worker は別ファイルを所有し、parent は幾何・
schema・scene／図・統合レビュー・全体検証と報告を担当。OpenCode Go MCP は未提供。
CLI は通常の log 書込みで sandbox エラー、隔離 XDG では `Provider not found: opencode-go`。
追加課金・global 設定変更なしで native worker へ fallback した。

検証は欠陥の targeted regression → `pytest tests/topo2d00` → CPU selftest → compileall →
`.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider`。
指定 base は host `e3dcdf61` の3482 passed／74 skipped／0 failed、失敗 node 集合=[]。
結果側だけを実行して失敗 node 集合を比較し、実行環境・command・SHA を記録する。
GPU 実行・freeze・本測定は行わず、後日の GPU smoke 条件は report に残す。

今回の実装上の明文化（データ取得前）: burn 候補の100 c1/U block は開始0／100／200／300、
候補を除く後続の完全100 block の平均±標本SD/√個数を SE 範囲とする。後続は2個以上、
端点を bracket できない候補は外挿せず skip、B=max(80, 最初の合格blockの開始)。
S0 は B 以後の完全な5／10／20／40／80 block ごとの length×標本分散に対する片側90%の
χ²上限の最大（Bonferroniなし）。これらは工程パラメータの再現可能な離散化であり、
paired σ_d の点推定規則とは別である。formal の手入力 freeze.windows は拒否する。
親 pre-run を `--prerun` で先に選択し [80,520] を保存、正式集合は親を除くので循環しない。
Re ごとの UNRESOLVED は Amendment 5 の列挙どおり Δ12／Δ23 の区間に適用し、
それ以外の並べ替え順位の隣接区間（例:E1↔E3）の resolution は記述として保持する。
E3 の鼻は登録の概数12.9%／6.9%を別項目に保持し、独立に定義した弦方向射影における
paired normal width の最初の線形補間crossingも記録する（概数を厳密再計算値とは呼ばない）。

## Amendment 3 対応設計（attempt 3、2026-11-07）

基点 `ba3164c7`、開始差分なし。README と AGENTS が要求する governing 文書は
read-only worker と分担して全文確認した。登録 Amendment 1–3 は follow-ups worktree
`CFD2026_09/.claude/worktrees/github-local-status-review-66bea1/docs/topo2d00_registration_2026_11_01.md`
の本文を参照し、編集しない。旧 validation は保持し、今回の CPU/software 証拠は
`reports/wp04_validation_amend3/` に新規保存する。commit／push は Claude host が担当する。

- 幾何: source を通る自然 CubicSpline を維持し、source station と均等 station の和集合を
  廃止する（最短 0.005648 mm の原因）。曲率に合わせた再標本化で線分 0.1–1 mm、
  隣接長比 ≤3、TE cap 2頂点以外の折れ角 ≤5° を生成・gate・独立テストで確認する。
  E3 の半弦と thickening 後の曲線でも検査し、最後の線分まで周期的に扱う。
  scene JSON は終点を重複しない閉曲線の頂点列とし、Python と Julia の SDF は
  最後→最初の辺を必ず評価する。元の4Δx、弧長 cap、camber、TE中点、gap規則は維持する。
  全10 scene、SHA を含む campaign、図を再生成する。既存 scipy/numpy 以外は追加しない。
- 高さ: scene の height_mm を export／campaign identity の唯一の出所とし、declared
  configuration／height が一致しなければ CFD 前と verify 時に拒否する。
  h80 scene と両方の正規化を回帰検査する。WP5 generator 自体は変更しない。
- 状態: analyzer／独立 checker の cell 集約を INCOMPLETE > MESH_FAILED > NUMERICAL >
  SETTLED にする。科学的ラベル表と cell state は区別し、新しいラベルは追加しない。
  observable をまたぐ差分、identity不整合、既存written-once規則を維持する。
- PARTIAL: 両側の順位が全て確定一致なら符号も一致するため、片側だけ符号一致する
  データには他側の未解決または順位不一致が必要になる。先行 UNRESOLVED／DISCORDANT
  との整合について、片側の未解決を許す Amendment 3 の解釈をユーザーへ確認中。
  回答前にこの dependent label 変更を確定しない。severity／幾何／高さは独立して進める。

担当: parent は geometry.py／geometry tests／Julia閉辺／scene再生成／図／統合検証・報告。
analyzer worker は analyze.py／check.py／対応tests。height worker は scene_campaign.py／
campaign tests。OpenCode Go MCP は未提供、CLI は通常のlog書込み権限で失敗し、隔離XDGでは
Provider not found: opencode-go。追加課金・global設定変更なしで native worker に fallback。

TDDで欠陥を先に確認し、targeted pytest、CPU selftest（GPU未初期化）、compileall、
`.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider` を完走させる。
base はユーザー指定 host の `e3dcdf61`、3482 passed／74 skipped／0 failed。
結果側の全失敗node集合を記録し、期待の空集合と比較する。旧凍結closure／pinは変更しない。

## Amendment 1・2 対応設計（attempt 2、2026-11-06）

基点は `88fea06e`、開始時の差分は空。今回の authority は follow-ups worktree の
`docs/topo2d00_registration_2026_11_01.md` Amendment 1・2（read-only）とユーザーの
Amendment 2。以下は初回設計の同じ項目に優先する。登録・凍結・GPU 実行・commit/push は
行わない。commit/push と PR #89 本文は Claude の host 作業へ引き継ぐ。

- `src/cfd_sdf/topo2d/` を `src/cfd_gen/topo2d/` へ移し、旧 closure 内に bytes を残さない。
  `cfd_gen/__init__.py` と 2–3 行 README を置く。過去の frozen source／例外は変更しない。
- 表座標を T2-0 と同じ自然境界の弧長パラメータ補間 CubicSpline で再標本化する。
  `airfoil_points` は入力が固定で有限 TE を閉じて消すため直接 import せず、既存 SciPy の
  `CubicSpline` を使う。弧長 ≤1 mm、非 cap 頂点の折れ角 ≤5° を独立 gate とする。
  必要な局所細分化は角度と長さの双方を満たすまで決定的に行う。頂点番号で cap を定めない。
  各面の LE から弧長 2 % c を保持し、camber の弧長 smoothstep で元の最大厚さ位置へ移行する。
  後方の実多角形法線幅 ≥4Δx、同じ camber と TE 中点、gap／clearance の gate を維持する。
  W/R 共通 scene JSON 全件・SHA と図を再生成し、実弦長／姿勢、厚さ比、両 h 正規化を記録する。
- Julia helper を `julia/CFDSDFWaterLily/gen01/Topo2D.jl` に移し、job から
  `Base.include(CFDSDFWaterLily, ...)` で読む。全 path／hash pin と CPU 自己テストを追従する。
- RANS force record と reference に `observable` を明示し、sharp は `pressure_cl`、thick と W は
  `total_cl` とする。差分の前に両端を検査し、不一致は入力拒否。checker は共有評価コードを
  import せず独立に検査する。両 h 正規化、SHA-distinct realisations と digitizations、
  sharp→thick の記述用差分も登録 Amendment 1 の範囲で更新する。

担当: parent は geometry／scene 再生成／図／統合レビューと最終報告。独立 worker は
analyzer/checker/schema/tests と Julia/harness/path/tests に分担し、同じ実装を繰り返さない。
OpenCode Go MCP は未提供、CLI の現在モデル一覧取得はログ先の sandbox permission で失敗。
追加課金／設定変更をせず native workers へ fallback。

検証: 新規 regression を先に実行、`.venv/bin/python -m pytest -q tests/topo2d00`、
CPU 小格子 selftest、compileall、最後に
`.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider`。
base はユーザー指定 host 実行 `e3dcdf61` の 3482 passed／74 skipped／0 failed を参照する。
結果側の全失敗 node を記録し、空集合との一致を検査する。凍結 evidence の変更はしない。
初回 validation は歴史記録として保持し、attempt 2 の証拠は別のディレクトリへ保存する。

### 実装・統合時の確定事項（2026-11-07、登録ではない）

全 governing docs（handoff、README、phase_plan、problem_register、resolution_plan、
GEN plan）は read-only worker が省略のない分割で全文確認した。登録 Amendment 1・2 は
follow-ups worktree で確認し、その本文は変更していない。

元の厚さと floor の hard max は接続部に約6°の折れを生むため、bulk 幅の smooth L8 envelope
`(t_original^8 + t_min^8)^(1/8)` を使う（overflow を避けた scaled form）。camber-normal offset、
cap／TE 中点保存、独立 normal-ray 幅 ≥4dx の gate は維持する。前縁も細分化して、2つの
有限 TE cap corner 以外の全頂点で5°以下を検査する。WP5 実 loader は10 scene×2 familyを
修復なしに受理した。元 spline の区間弧長は速度積分、出力 polygon は実 segment 長で検査する。

CPU の頂点格納を Vector、未実行 CUDA 経路を Tuple とした。883／651頂点の長さを型に
持たせた CPU 統合試験は1805.96秒、Vector版は113.19秒で同じ56検査を完了した。SDF の式、
probe／sample／窓／検査数は変えていない。GPU の実行・性能の証拠ではない。

WP1 最新 API の restore は `identity` keyword が必須であり、最初の統合試験で欠落を検出した。
fingerprint と検証済み column mask から expected identity を再構成して渡すように修正した。
WP2 は gen01/ へ移動済みの実 source を読み取り専用 snapshot から使い、出所と SHA を保存した。
snapshot は provider 2ファイルだけで、repo の /tmp clone は作っていない。

WP5 の実 raw diagnostics は sharp／thick 双方の pressure と total を含む。厚肉化のみの対照は
primary force record を跨いで引かず、同一 observable の raw pair から独立再計算する。
各 observable の収束と config／model／family／mesh identity を検査し、8対・独立meshが揃わない
ときは点推定／未利用を明示する。collector の事前集計値は算術に使わず、ラベルにも使わない。

campaign の同じsceneを位相ごとに再検査する重複は、同じ generation／pin 集合内でのみ排除する。
CFD 前の scene SHA と幾何 gate、formal verifier の確認は維持する。canonical な旧 campaign
schema／runner／凍結 closure に例外は追加しない。

状態: implementation design, 2026-11-06。登録・凍結・科学的判定ではない。
基点: `e3dcdf6188df6079e197eb28f7fcba1451ec512d`、branch
`feat/gen01-w1-04-topo2d-waterlily`。開始時の tracked/untracked diff は空。

## 読んだ文書と境界

最初に `../00_README.md` を全文読んだ。AGENTS の5文書、STATE、branching
strategy、GEN-01 rev3.1、TOPO-2D-00 registration rev0、research facts を全文確認した
（長い authority 文書の全文確認は read-only worker と分担）。指定された既存 Python/
Julia source、campaign、SCREEN analyzer/checker も確認した。SCREEN の INTERFACE は
指定の evidence directory にはなく `scripts/screen01/INTERFACE.md` にある。

`phase_plan.md` だけが順序・状態の authority。登録文、既存 evidence、pin された job、
Julia Project/Manifest は編集しない。GPU、Kaggle、RANS、凍結、課金は実行しない。
OpenCode Go MCP はなく、通常 CLI は log permission、隔離 XDG CLI は provider not
found で利用できなかった。native workers で非重複の作業を分担する。追加課金 API は使わない。

## 幾何と source

公式 thesis PDF の indexed OCR が取得できた。直接 PDF download は401/403、ページ画像は
取得できていない。Table2/3/4 の数値を推測せず転記し、未照合行は `# UNVERIFIED` とする。
Table3/4 は c=380mm、Table2/T20 は c1=223.4mm 基準。Table2 と T20 は同じ44行なので
同順に比較し、Table3 も c/c1 を掛けて比較する。異なる reference attitude の名称だけを
理由に二重回転しない。T20 は XFOIL-sharpened variant で source の有限厚TEと区別する。

生成器の座標は mm、流れは +x、上向きは z。h は主翼素の最低点から地面までの距離とし、
同じ格子・高さでは E1/E2/E3 の主翼素の座標を同一にする。overlap は upstream TE x minus
downstream LE x（正なら下流要素LEが上流へ重なる）、gap は下流 suction の最小z minus
上流TE midpoint z（有限TEの中心、厚くしても位置不変）。raw tables の9.006mm overlapと
10.032mm lower-suction-TE gap / 9.196mm midpoint-TE gap をそのまま12mmと呼ばず、最終配置で
9mm/12mmに平行移動する。pivot=(.567,.076)cを保持する。

E3 は既存 flap の弦方向姿勢を除いた同じ local profile を各1/2弦で二つ使い、main-to-flap
chord の総角度を二等分し、順に同じ gap/overlap で配置する決定的な構成とする。E3 は
構成例であり公開三要素の再現ではない。メタデータに変換と弦長を全て保存する。

前縁を持つ閉曲線の chord-normal 厚さは鼻端で0になるため、全閉曲線にわたる点ごとの
正の最小厚さを主張しない。最初の3対の source vertices のLE capを保持し、その終端から元の最大厚さ位置まで
smoothstepでnormal offsetを増やす。元の最大厚さ位置以後の thickness-controlled regionを
camber-normal offsetで >=4dx とする。E3は元の最大厚さ自体がfloor未満なので、最大厚さ位置を
保持領域に含めない。最初の3点の形状/曲率proxy保持と、連続曲線のradiusを独立に適格化した
こととは区別する。保持領域・検査領域を明示し、
後方の最小厚さ、各要素の最大厚さ比、真の polygon gap/clearance/self-intersection を記録する。
核の位相検査は別に行い、前縁を保持したことを一様な全域4dxの証明にしない。
`*_sharp` は registration の unthickened-original arm 名であり、原表の有限TE厚を
消さずに保持する。数学的にzero-TEとは異なることを出力と報告に明記する。

SDF は点–線分の最小距離と winding の符号、scene は要素のmin。多角形を JSON/NPZ
で export し、Julia は解析的に同じ点–線分関数を直接評価する（設計格子補間を使わない）。
JSON のschemaは `topo2d-scene-v1`、`elements` は `{name, polygon_mm}` の配列。
`configuration`, `height_mm`, `dx_mm`, `normalizations`, `gates`, `thickening` を持つ。

## Job と harness

新規 `waterlily_topo2d_job.jl` は2D Float32 CPUを既定とし、AutoBody elements と
V=Uの地面半空間の SetBody(min,...) を使う。scene/ground を同じ sub-cell shift で動かす。
位相は既存名 `W4_CANONICAL_ORIGIN_M` の x,z（y=0）から mm/solver単位へ変換する。
場の力は wing-only の各要素から積分し、ground を total force に含めない。

最初の13 CSV列は既存 FORCE_COLUMNS の順序を保ち、cur/nds/cv と element ごとの
Cartesian/drag/downforce を追加する。2D の第2成分を既存zへ写し、yは0。
固定した追加列名は `{readout}_{axis}_solver`：readoutはcur, nds, cvの順、axisは
fx, fy, fz, drag, downforceの順。続いてJSONの要素順main, flap1, flap2（存在するものだけ）で
`element_{name}_{axis}_solver` を同じaxis順に置く。E1/E2/E3は計33/38/43列となる。
実装開始時、この checkout にはWP2 `force_readouts` とWP1 Checkpoint がなく、cur fallback と
unavailable nds/cv 列、Julia Serialization のCPU fallbackを設計した。以下の最終interface追補が
この初期仮定に優先する。fallback は全simとrowsを保持し、source/scene/runtime/contract一致を
再開前に要求する。

窓は endpoint-clipped time-weighted trapezoid、drift は前後半平均の差 / 全平均絶対値。
Re と時刻の共通弦は c1=223.4mmとし、要素数でνを変えない。2D physical force scale は
rho U^2 dx (N/m)、coefficient は2F/(rho U^2 c1)。3D rho U^2 dx^2 を流用しない。

legacy harness のphi stateを変更せず、scene state branchとJSON SHA、2D force readerを
最小追加する。CPU smoke と将来のformal GPU outputのbackendを区別し、偽のT4 identityを
入れない。campaign は Re1000/Re3000 と c1/180 confirmation の3 kernels。
未実行・未凍結のdraftで、窓はparent pre-runからのfreezeを必須にする。

## 統計入力と独立実装

analyzer と checker は実装を共有しない。共通するのはこの入力契約と定数だけ。
WaterLily table は harness の formal-table gate を通し、各runに `topo2d` identity
`{configuration,height_mm,reynolds,grid,phase,role}` と `readouts` を持つ。
`readouts[cur|nds|cv]` は `{downforce,drag,batches}`（共通c1の係数）、batches は
同時間幅batchの `{downforce,drag}` 配列（>=4）。未利用readoutはnull。

normalized input `topo2d00-input-v1`:
`{schema,identity_valid,cap_hit,waterlily:[runs...],rans:{...},controls:{...}}`。
各W runは上記 identity とreadouts、`ok`, `finite`, `complete`, `scene_sha256` を持つ。
R schema は `topo2d00-rans-results-v1`、共通c1係数、referenceの measured `delta_cl` と
absolute `digitizing_uncertainty`、cellsは `{model,family,realisations:[...]}`。
各realisationは `id`, `mesh_sha256`（configごとのSHA）、`status`（configごと
SETTLED/NUMERICAL/INCOMPLETE）、`forces`（E1/E2/E3/E1_sharp/E2_sharpの
`{downforce,drag}`）を持つ。8 realisationsを要求する。WP5向けJSON Schemaを別途固定する。

CLI はforce tables/RANS/freezeを読み、path/SHA/expected identitiesを確認してからnormalize。
freeze違反はINVALID、smoke/unverified tableは解析入力として拒否。出力先存在を先に全件確認し、
analysis.json/mdをexclusive-createする。checkerはnormalized inputから数値を独立再計算する。

formal CLIの追加条件として、RANSの `provenance.component_by_config` は
E1_sharp/E2_sharp=`pressure_only`、E1/E2/E3=`pressure_plus_viscous` を要求する。
これは公開Cp積分の参照値にtotal-forceのsharp armを混ぜないためのobservable検査で、
synthetic normalized APIでは省略可能。WP5の `collect_rans.to_wp4` が実際に出す構造と一致する。
WP4/WP5双方の共有schema bytesは2026-11-06確認時点で同一、SHA256は
`04ebcf764568f206071c2d81bf9a32318f0f3283c9cdae596e43f93f0a8016b4`。

各available readoutのwhole meanは等長batch meansの算術平均と
`1e-9 * max(1, abs(whole), abs(batch_mean))` 以内で一致することを要求する。
determinism PASSには値/SHA一致に加えprimary/repeat双方のcomplete/finite/okを要求する。

Aは同位相の差のSD、Bは各runのbatch mean SEを二乗和してphase平均のSEへ伝播し、
sqrt(P)倍でSD相当に戻す。sigma_d=max(A,B)。alpha=.05の上側限界はAとBにalpha/2を
割り振り、Bの各run varianceにBonferroni配分してchi-squareで上側を取り、最大を使う。
90%区間はt_.95,P-1 * sigma_upper/sqrt(P)。この保守的実装定義は登録前にレビュー対象。
Rは8 paired realisationsの90%t区間。TRはsharp-arm difference/refの90%区間が[.5,2]
に含まれ、符号一致ならRATIO、digitizing uncertainty>5%ならSIGNだけで判定する。
合格したmodel/familyのみ一致規則へ入り、最悪cellを併記する。

`UNRESOLVED` のrequired intervalsはdownforceの12/23差と、各solverの平均値で
並べた隣接順位の区間とする。dragの差・90%区間・DRAG_SIGN_AGREE_12は全て報告するが、
drag区間が0を含むことを追加のacceptance gateにしない。§4のSIGN-only時は明示的に
SIGN_AGREE_12/RANK_AGREEだけを使い、§5の順序付きlabel表にもdragの判定条件がないため、
RATIO経路にも同じ解釈を適用する。§5の「required interval」は未定義なので、これは
literal label解釈として記録し、登録前のclarification提案とする。閾値・順序は変更しない。
TR-00結果はuser指定のanalysis.json/mdに埋め込み、草稿§9の別tr00.jsonは本WPで作らない。

NUMERICAL transportでは、harnessがsource/runtime/scene/manifestを照合したexit42の
`numerical_failure.json` だけを実際のfailureとして認める。analyzerはformal verifierを
再実行して一致したtableから、finite/ok/complete=false・全readout=nullの実failure rowを
残す。後続の `SKIPPED_NUMERICAL` は未実行を非有限測定と呼ばずnormalized rowsから除き、
kernel/run/topo2d/scene SHA/prior failure SHAをprovenanceへ保存する。実failure rowが
NUMERICALを発火するため、全phase数検査より先に終わる。欠測の合格への昇格ではない。
§5の「a WaterLily run was non-finite」はroleを限定していないため、実際の非有限runは
secondary/DOMAIN/determinismもNUMERICALとする。従って非有限repeatはearly labelとなり、
未完了・finite=trueのrepeatだけが後段controlのpass=falseへ進む。

cap/timeoutも実verifierのbudget receipt検査を通ったtableだけを利用する。tableの
`cap_hit` とkernel別 `cap_receipts`（receipt SHAとvalidated record）を照合した後、
`INCOMPLETE_TIMEOUT` / `UNRUN_CAP` はfinite flagやforceを作らずnormalized measurements
から除き、元のidentity/status/receipt SHAをprovenanceへ保存する。完了rowは保持する。
normalized cap_hitは認証されたtableのcapとstudy freezeの既存study-wide cap記録のOR。
実failureがあればNUMERICALが先、capだけならphase cardinality検査より先にINCOMPLETE。
未知の非budget errorや偽造receiptはraw verifier rejectionでINVALIDとなる。

retentionは(relative W increment)/(relative R increment)。各relative incrementのvarianceは
paired mean covarianceのdelta法（WのBは保守的な対角上側項）を明記し、その二量にFiellerを
適用する。有限・非有界・分離・全実数・空集合をJSONで表現し、無限端点はnullとする。
これは入れ子の比の厳密なfinite-sample区間という主張ではない。
baselineの平均downforceが厳密に0ならその側のrelative increment/varianceはnullとし、
相手側が定義できればその値を保持する。どちらかが未定義ならRETENTIONのFieller recordは
`{kind: "undefined_zero_baseline", intervals: []}` とする。RETENTIONは報告用なので、
この未定義だけを理由に符号・順位の解析やラベル計算を中断しない。near-zero閾値は設けない。
共分散のPSD検査は単位依存の絶対許容誤差を使わず、両分散が正なら
`abs(cov)/sqrt(var_num)/sqrt(var_den) <= 1/sqrt(1-64*machine_epsilon)`、
どちらかの分散が0ならcovも0を要求する。積のunderflow/overflowを避けた数学的な
入力妥当性の検査であり、studyの有意水準やacceptance thresholdは変更しない。

§5のラベルは文字どおり順序付きfirst-match。resolved rank mismatchはDISCORDANTが先。
global AND rank解釈ではPARTIALが到達不能になる場合をraw-data反例で検査し、整合しない
flagsを捏造してcoverageを稼がない。DOMAINは同じexpanded domainのE1/E2対がなければ
NOT_JUDGED。determinism/readout/manipulationも入力の有無を区別して報告する。

## 所有ファイルと検証

geometry worker: `src/cfd_sdf/topo2d/`, `tests/topo2d00/test_geometry.py`、plot helper。
job/harness worker: 新Julia job/selftest/helpers、scene-only harness追加と必要最小のdispatch、
campaign、harness tests。analyzer worker: `scripts/topo2d00/analyze.py`、synthetic/analyzer tests、
RANS schema。parent: source data、design/report、独立 `check.py` とchecker tests、統合レビュー。

TDDで最小sliceを検査する。CPU selftestは小格子・Re200・短窓、E1/E2、finite forces、
moving ground、common phase、checkpoint再開の窓一致。GPUは実行しない。
最後にcompileall、pytest topo2d00/full、diff check。baseline full pytestを
`/private/tmp/topo2d00_base_pytest.log` に開始済み。既存pin不変をhash/diffで確認する。

## 最終 interface 追補（2026-11-06、科学的freezeではない）

WP2 sibling の実装と後のAmendment1をread-onlyで全文確認した。後者は凍結pinを保つため
追加実装を新規Force00.jlへ移し、既存Forces.jlを元に戻す。新jobは同じcheckoutにある
Force00.jlだけをopt-inでincludeし、そのSHAを追加でpinする。gen01/を優先し、過渡期のsrc/配置へ
fallbackする。統合後にこの実装が
`validate_force_box(sim,box;body=wing)` と
`force_readouts(sim,box;body=wing,validate_box=false)` を提供すれば、地面を除いたwing unionと
余白付きpressure-cell boxを一度検証し、cur/nds/cvを実際に読む。既存Forces.jlもsource pinに含める。
CVは完了stepのstorageを要するので、このproviderを使うと最初のsampleはstep1以後になる。
このcheckoutでは既存Forces.jlを変更せずcur fallbackを使う。実APIのCPU統合確認はselftestの
明示的 `TOPO2D_WP2_TEST_SOURCE` でsourceを注入し、外部path/SHAを別に記録する。

WP1 sibling のCheckpoint.jl、設計、selftestとAmendment2もread-onlyで確認した。最終配置は
`julia/CFDSDFWaterLily/gen01/Checkpoint.jl`（旧src/からbyte不変で移動）。実APIは
`Checkpoint.save_checkpoint(path,sim,step,rows;identity=...)`、`load_checkpoint(path)`、
`restore_checkpoint!(fresh_sim,payload)`。同じcheckoutのgen01/を優先し、旧src/へfallbackして自動includeし、
選択sourceをfingerprint/pinに追加する。WP1がfinite rowsを要求するため、欠測readout列を省いた
finite payloadと列mask/幅/versionをidentityに保持し、load後に欠測列だけNaNへ復元する。
同一body/configを新規構築しrestoreし、全solver stepは既定remeasure=trueを使う。moduleが
なければ上記CPU fallbackとする。実sibling APIをselftestの明示的
`TOPO2D_WP1_TEST_SOURCE` からread-onlyで注入し、source SHAと再開窓を記録する。
GPUでのcheckpoint動作をCPU試験から適格化しない。
他WPの作業中の移動と競合しない最終CPU試験は、明示許可された/private/tmpのread-only input
snapshotを使う。copy前/後と保存bytesのSHA一致、元pathとsnapshot pathをorigin recordに残し、
自己テストJSONからそのrecordのSHAを結ぶ。外部実装をWP4 source treeへコピーしない。

scene extensionは新規 `cfd_harness.scene_campaign` のvalidate/render/run-frozen/verifyで提供し、
既存harness sourceは変更しない。将来のlocal CUDA runnerはsource commit/pins、外部の
LOCAL-GPU-01 PASS artifact/UUID、実runtime、E1 parent記録からの窓formulaを要求する。
このWPでGPUを初期化・実行せず、承認・freezeを生成しない。

明示的非有限失敗はexit42とsource/runtime/scene/phase/windowを持つfailure JSONで保存する。
同じkernel/Reの同configurationを以後SKIPPED_NUMERICALとし、他configurationを続ける。
verifierはraw failure/manifest/pins/先行failureへのlinkを検証し、実失敗はfinite=false、未実行は
finite=null、readoutsは全nullで返す。欠測を0へ置換しない。別kernel間のstop調停は外部実行側の
責務で、このrunnerの機能とは主張しない。malformed proofは科学的ラベルにせず入力拒否する。

予算による停止は別のcap_receipt.jsonへsource/campaign/limit/elapsed/停止対象を記録する。
job開始時にsource/runtime/scene/phase/windowのpreflightを保存し、そこまで到達したtimeoutは
観測runtimeのhashを結ぶ。JIT等の途中でtimeoutした場合はruntime_observed=nullとし、
外部freezeのexpected runtimeと区別する。verifierは固定予算と経過時間、完了prefixの実CSV、
未完了suffixとreceiptを再検証し、cap_hit=trueを返す。未測定行はINCOMPLETE_TIMEOUT /
UNRUN_CAPというidentity/proof markerだけで、finite/force/readoutsを捏造しない。analyzerは
markerをprovenanceへ保持し、verified cap_hitからINCOMPLETEを判定する。不明なprocess errorは
予算超過へ読み替えない。
subprocessが成功を返しても実測wallが固定limitを超えればWALL_TIME_OVERRUNのreceiptを作る。
その実測rowは保持し、後続だけを未実行にする。最後のrowでの超過もcap_hitを立て、閾値を
緩めてCOMPLETEにしない。

campaignのdomainは地面以上のfluid boxと8cellのsolid paddingを区別する。jobは実際の
flow_origin_m=(-2c1,0,-8dx)をsummaryへ記録し、verifierがgridごとに再計算する。
