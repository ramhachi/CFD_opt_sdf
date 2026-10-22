# 次回実行計画 (2026-10-23) — GEOM-03 exact prospective design の完遂と FID 依存スケジューリング

**位置づけ:** 本文書は [phase_plan.md 2026-10-22 並列準備 amendment](phase_plan.md#2026-10-22-parallel-preparation-and-primary-reference-audit) に**従属**する作業計画であり、第二の権威ではない。順序・閾値・登録・判定の変更権限は phase_plan と各登録文書にある。計画の統合時には親が phase_plan の最新節と状態投影を同期する。既存の不変 evidence は変更せず、新たな数値物理閾値・retuning・最終 scope 決定・計算 ETA を新設しない。

**実行完了:** 180base+354K6の一試行は[GEOM03_NO_GO](evidence/geom03_2026_10_23/result.md)で終了した。全534記録の登録された独立照合を完了（E2の数値一致は記述的対照のまま）、K2/K4に反例各1件、301.39秒/観測906.39MiB、attempt1/resume0。三角度計画レビュー、一度のソースレビューと指摘解消、開発25件PASS、全回帰3117PASS/73SKIPの後、sourcece95612fとfreeze/release29bcfc4aを順にpushしてから実行した。登録仕様・seed・閾値は変更しない。R3は採用せず、次は[SCREENのR0-clean fixed-pool/parent経路](screen_xv_preparation_2026_10_23.md)。以下はこの試行の事前計画と依存判断の履歴を保持する。前日のdraft、初回3110PASS/73SKIP、未完了worker出力の記録も保持し、正式レビューや科学的成功へ読み替えない。

**GitHub refresh (2026-10-23 00:30 JST、直近スナップショット比較):** integration `codex/kaggle-batch-migration` = `1467af14`、FID `claude/m3a-fid01` = `78e1e76f`、当方の open PR #71 head = `73802a5b`（前回 catch-up の `e2f7b5f9` から docs 側作業分のみ前進）。前回スナップショットからのリモート変化なし。Issue: #68 は closed（参照監査完了、`REFERENCE_INADEQUATE`）、#62–#67 / #69 / #70 は open。Claude が #62 FID-01 を所有し、V3 docker 4 jobs が稼働継続（各 ~100% CPU、約 20h）。Host は 32 GiB / swap 23 GiB / loadavg ~14。最終 FID verdict は未確認、現行 force 出力は非開示のまま維持する。

---

## Live update — FID完了後の適用（02:47JST）

統合は458e2df5、正式結果はb2314d9dのFID01_GO（analysis.json SHA-256 b89203d0c8ec588bfa83a87d67f81e2a731edd37655265d0a3f8cd6f9d863dd1）。4本のOF処理は終了、Dockerに稼働containerなし。以前の時刻付きsnapshotは履歴として残す。SCREEN最小gain2.70%、XV OF最小gain1.27%、純heaveのTIER_B_FAILとSUPPORT_UNTESTABLEを引継ぐ。flow格子のR3_CONFIRMEDは形状幅R3の検証ではない。

R0が既知のoptimizer-like組合せの大部分をoccupancy aliasで遮るため、次はR3複合ルールの検証経路を選ぶ。計画レビュー前に定めた180形状と乱数系列はFID結果を見た後にも変更しない。ソースレビュー・全回帰・source commitの後にfreeze/releaseを作り、資源gate後にCPUのみの有限な一試行へ進む。FID依存が作業中に解消したため、当初のimplementation-only sliceをここまで拡張する。合格前にR3を採用せず、NO_GO/INCOMPLETEで閾値・ケースを調整しない。

## 1. 主 deliverable（今スライスで完了させるもの）

GEOM-03 #70 の **exact prospective design → plan review → 実装 → source review → 全回帰 → source commit/push → freeze/release → 資源gate → 一度の有限検証**を進める。正式ゲートは計画レビューとその指摘解消、ソースレビュー、検証、freeze の順。実装草稿の執筆のみ計画レビューと並行させたため、元の逐次執筆順からの差分を [review record](evidence/geom03_2026_10_23/plan_review.json) に記録した。計測や凍結を先行させたものではない。

1. **§12 REQUIRED_BEFORE_FREEZE 5 項目の確定**（前日案を保持し、2026-10-23 の新しい文書へ反映）:
   1. 全 fixture の明示的な phi-field formula（合成場は厳密な距離関数とは限らない）・寸法・方向・位置・parent state・**nonempty** frozen-node mask・期待 label triple のバインド。抽象的な形状名だけでは bytes を決定しない。empty frozen-mask の扱いを明示（passing infinity を推論しない）。
   2. K5 spanning-slab の boundary/P1 contract の事前解決。ordinary finite-body halo rule を slab に機械適用しない。chosen finite-array convention を study と checker が共有し、claim に文書化し、freeze 前 review で確認する。データ例外は禁止。
   3. K1(b) の coverage: 現行 analytic 変形群は WIDTH-RULE D3 の non-SDF linear phi-space mode combination を覆わない。disjoint combination protocol を**事前**バインドするか、D-3 と整合する形で claim を狭めるかを明記選択する。
   4. §8 historical controls の source hash と recorded R0 status の pin。検証不能な行は推測せず drop。
   5. §9 実装（下記）と freeze 時に凍結する exact enumeration / byte hash、exploratory 入力（seed 20261020 系）との disjointness 確認を freeze フローに組み込む（seed 不一致だけでは bytes 分離を示さない、draft §12 前提の通り）。
2. **Formal plan review（一度のみ・三角度）** — 2026-10-23 の具体化案を対象に、(A) prospective 正確性と byte 級 binding 完全性、(B) claim 境界と登録規律（retune 禁止・verdict 意味論・K1'–K6' と WIDTH-RULE 主張の対応・D-3 整合）、(C) 実装最小性と資源/回帰適合（2 scripts + 1 test、scipy.ndimage のみ、budget/state machine、agreement→INCOMPLETE 経路）の三角度で一度だけ実施し、findings と resolution を日付付きで記録する。実施記録は [plan_review.json](evidence/geom03_2026_10_23/plan_review.json) と原文スナップショットを参照。**形成段階の revision はこの review の通過として数えない。**
3. **最小実装** — draft §9 の通り: `scripts/geom03_run.py`（`width_rule_study` の `r0`/`r3`/constants を import、既存の成分重なりによる event rule、明示バインドした fixture formula/mask、fixture framework は作らない）、`scripts/geom03_check.py`（**scipy.ndimage のみ**: `distance_transform_edt` / `binary_dilation` / `label` 26-connectivity、独自 signed-distance から R3・node-graph・dense・analytic label を計算、measured gate を自己 oracle にしない）、`tests/test_geom03.py`（5 tiny fixtures の run-vs-checker 一致、P1境界 h/2 pass / 0.3 h block、K6 scaling 等価、halo/clip と void/empty 約定）。新依存・別フレームワークは追加しない。
4. **Source review（一度のみ）** — freeze 前に一度。§9 の independence（checker が study を再利用しない計算経路）、fixture 実装と §7 表の prospective label の対応、budget/state 設計を確認し、blocker を解消して記録する。
5. **Validate / commit / push** — `.venv/bin/python -m compileall src tests`、`.venv/bin/python -m pytest -q`（BLAS/OMP/MKL=1 を指定して回帰の負荷を抑える）、`git diff --check` を実施し、結果を記録。意図したファイルのみを現行 feature 分岐（PR #71 系）に commit/push。freeze commit は parent-owned。上のlive updateに従い、FID完了を受領した後はレビュー/検証を終えてfreeze/releaseと一度のbounded CPU validationへ進む。

## 2. FID完了後の依存関係

| 実行可能（FID 出力・CFD・GPU 不要） | Dependency-blocked（開始しない） |
| --- | --- |
| 完了したFID-01 #62のowner記録をハッシュで受領（解析の再実行なし） | SCREEN-01 #64の実行はgeometry-admissibility pathと自身の登録待ち |
| 三角度 plan review（一度） | SCREEN-01 #64 の登録/実行（`FID01_GO` と geometry-admissibility path が前提） |
| 2 scripts + 1 test の実装と unit レベル検証（開発用の既知 tiny fixtures は回帰確認であり held-out study ではない） | XV-01 #65 freeze（final FID record hash と SCREEN freeze hash が前提） |
| source review（一度）と validate/commit/push | M4 #66 の最終 evaluator/product 決定（適用 M3 結果待ち） |
| M4 判断資料の delta 整理（outcome/cause/secondary-label → 分岐の対応表。決定はしない。既存 [t20 summary](t20_summary_for_m4_2026_10_22.md) と [参照監査](eval_valid01_reference_audit_2026_10_22.md) を参照） | EVAL-PT-01 #69（M4 の新研究選択と validation inputs の後） |
| 公開同期チェック（§5）の実施手順整備 | #67 L3（新規登録 high-Re evaluator GO と M4 scope 決定の後） |
| | **GEOM-03はGEOM03_NO_GOで終端済み。再launch/resume/retuningしない** |

## 3. FID-01 との分離原則（成果物・資源）

- Claude が #62 の登録分析を**正確に一度**書いた。完成した b2314d9d の記録を読む。当方は解析器・force集約を再実行せず、不変出力を書き換えない。完了前の `78e1e76f` から結果を推論したものではない。
- GEOM-03 の入力形状・seed・期待labelはFIDのforce結果を使わずに定めた。同じ定義を維持し、FID01_GOは分岐選択の依存入力としてのみ使う。
- 依然としてFIDなど他ownerの資源を保護する。CPU処理は単一スレッド、GEOM本試行はfreeze後の資源gateを要求する。新規CFD/GPU/Kaggle session・有償資源は開始しない。

## 4. 依存駆動の資源スケジューリングと GEOM 実行要否の事前決定

- 実行結果:03:46JSTにfreeze/release公開と資源gateを満たして開始し、03:51JSTにGEOM03_NO_GOで完了した。以下の待機・分岐条件はlaunch前の判断記録。現在の次段はR0-clean fixed-pool/parentである。
- **00:30JSTの履歴snapshot**（32 GiB / swap23 GiB / loadavg約14、V3 4 jobs active）はlaunch条件を満たさなかった。02:47JSTにはDocker jobが終了し、FID01_GOを受領した。freeze前の現段階を「資源待ちの実行結果」とは呼ばず、実際のlaunch直前にFID container不在・load<=4・利用可能メモリを再取得する。未達なら **`WAITING_FOR_RESOURCES`**（attempt消費なし、科学的verdictなし）。
- **2 時間（≤2 h wall / ≤200 rows / ≤3 GiB RSS、単一の数値処理 child と軽量 watchdog、数値ライブラリは単一スレッド、draft §11 の値を再設定しない）を支出する前に、実行要否を先に決める。** 判断順序:
  1. FID-01 が完成し登録 verdict が得られる。
  2. `FID01_GO` の場合のみ、M3b が R3 composite（represented-width + frozen-node margin + fixed topology）を採用するか、registered R0-clean fixed set / parent choice に留まるかが決まる。
  3. R0-clean 経路を選ぶなら GEOM-03 の held-out 試行は不要（その固定集合の登録は別作業）。R3 経路を検証候補として選ぶ場合、freeze commit 後、resource gate 通過時に一度だけ実行する。**R3 の採用は GEOM03_PASS と SCREEN 自身の登録の後**であり、検証前に採用済みにしない。
  4. `FID01_NO_GO` / inconclusive 系では M4 分岐（§5）が先行し、GEOM 試行の採用動機が消える可能性が高い。この場合 frozen + waiting 状態を維持し、attempt を消費しない。
- freeze 自体は上記判断を待たず §1 のレビュー完了後に parent-owned で可能（reviewable/mutable な設計を確定させるため）。ただし**実行は採用動機と資源の両方を要求する**。

## 5. FID outcome / cause / secondary label の分岐トリガーと handoff 契約

定義元はFID登録 §6.5/§6.6/§8と、完成した[owner記録](evidence/fid01_2026_10_21/analysis.json)。[ハッシュに束縛した引継ぎ](fid01_to_screen_xv_handoff_2026_10_23.md)に実際の値と単位を示す。[xv01_registration_requirements](xv01_registration_requirements_2026_10_22.md)、[STATE](STATE.md) のbranch rulesも維持する。

| FID outcome / label | SCREEN #64 への影響 | XV #65 への影響 | M4 #66 への影響 |
| --- | --- | --- | --- |
| `FID01_GO` | geometry-admissibility path（GEOM-03 PASS 採用、または登録 R0-clean fixed set）の後に SCREEN 登録・実行 | `REQUIRED_FROM_FID` cells を final record から記入、`REQUIRED_FROM_SCREEN` cells を SCREEN freeze から記入 | 適用 M3 結果が揃った範囲で最終決定へ |
| `FID01_NO_GO`, cause `WL_OF` | — | — | 既存 pre-commit の one-shot smooth-advection WaterLily study（登録は trigger 後のみ） |
| `FID01_NO_GO`, cause `OF_MESH` | — | — | reference/evaluator choice へ戻す。自動 WaterLily study は起動しない |
| `INCONCLUSIVE_*` / `INCOMPLETE` / `INVALID` | FID 自身の分類と retry cap を保持。shadow retry しない | unresolved として保持 | retry cap 後に M4 が明示記録 |
| `R3_CHALLENGED` or flow48 `NOT_MEASURED` | **SCREEN 義務**: whole pool（親/候補だけでなく pool 全体）の flow_48 P>=2 確認 | SCREEN の遵守を検査。非遵守は事後代替で修復せず handoff outcome を block | 分岐材料 |
| `EXPORT_SENSITIVE` / `EXPORT_UNRESOLVED` | — | registration に predeclared export-resolution check（label は `EXPORT_UNRESOLVED` の正確な綴り） | 分岐材料 |

Handoff は hash 単位で行う（値の口頭転記禁止）: final FID record の hash、`S_d`（無次元 paired grid-sensitivity 項）と `S_d_OF`、`sigma_d`/per-run SE（N 単位、`S_d` 系と混同しない）、`g_min`（WL/OF それぞれの登録形）、`x*`、R3/EXPORT の登録 label、SCREEN の geometry version + parent/finalist SHA-256 + campaign input hash、constraint set と margins、grid 一覧（WL は flow_32/48 のみ、OF XV arm は V1/V2/V3 のみ）、backend 適用条件、XV の budget/rerun cap（registration 時）。

Unresolved の扱い（不変）: 欠落・不確実な入力は PASS へ解決しない。`n<3` の cross-design 再利用不可は `UNRESOLVED_DATA`（SE=0 推論禁止）。G5b fidelity PASS を constraint pass に写像しない。WL `sigma_d` を OF arm に借用しない。SCREEN/M3b mesh は optimization data、XV OF mesh は judgment-only holdout（一度使用、feedback 禁止）。

## 6. 公開同期（live Claude との整合）の確認手順

commit/push の直前に [github_catchup.json](evidence/parallel_preparation_2026_10_22/github_catchup.json) の手順を新日付で繰り返す: `git fetch origin` + `git ls-remote --heads`、`gh pr list` / `gh issue list`、`git worktree list --porcelain` と各 worktree の status、active Claude プロセスの cwd/所有確認。比較対象は integration / `claude/m3a-fid01` / PR #71 head の hash と issue body の updated_at。**FID branch head が直前スナップショットから動いていたら、push を止め、#62 側の新規状況を再読してから続行する。** FID worktree に当方起因の tracked/nonignored 変更がないことを確認し、意図したファイルのみを PR #71 系 feature 分岐へ push する（`claude/m3a-fid01` への push・force・reset・無関係 worktree の上書きは禁止。merge 先の運用は [git_branching_strategy.md](git_branching_strategy.md) Current practice の通り integration は `codex/kaggle-batch-migration`）。

## 7. 有限停止規則

- GEOM-03: freeze 後 **one attempt**。resume は同一 hash の append-only cache からのみ。budget stop → `INCOMPLETE`。adaptive width 追加禁止（`k5_degenerate` → `INCOMPLETE`）。`GEOM03_NO_GO` 後に second attempt なし。`r`/`tau`/`k`/`pad`/seed/label の事後変更は新登録。
- Review: plan review 一度・source review 一度。freeze 前の設計変更は revision として記録し、freeze 後の変更は新登録。計画レビューで特定した入力存在条件、数値順序、境界条件、再開予算、重複確認は今回の修正に統合した。
- 当初の終点は pushed implementation commit + validation記録だった。FID完了後のlive updateに従い、条件が揃えば一度のGEOM検証まで進め、結果と停止理由を記録する。CFD・GPU・新フレームワークは範囲外。

## 8. 最小有用受理証拠

- 新日付の具体化案（未確定設計の解消、最小実装との対応）+ 三角度 plan review 記録（findings/resolution、日付付き）+ source review 記録。
- implementation commit（2 scripts + 1 test のみ）+ compileall/pytest/`git diff --check` の実施結果記録 + 公開同期 snapshot（新日付、`github_and_worktree_catchup_v1`）。
- 完了証拠: [freeze](evidence/geom03_2026_10_23/registration.json)、[終端results/rows/全入力archive](evidence/geom03_2026_10_23/run/)、[結果受領とhash](evidence/geom03_2026_10_23/result_receipt.json)。全件完了のNO_GOなのでbudget stopファイルはない。

## 9. 回帰と負荷管理 / 明示的非作業

回帰はrepo標準のfull pytestを単一スレッド・低優先度で実施し、他ownerのactive jobを保護する。GEOM budget値は再設定しない。非作業（意図的）: FID分析の重複・partial force開示・shadow verdict、FID active中のnew held-out GEOM run/seed、不変evidence変更、T2-0の再スコア、新数値閾値・retuning・最終scope/evaluator決定、計算ETA想定、新依存・新フレームワーク、有償計算資源、`main`マージ操作。

## 10. 重要な未解決判断（後続を gating）

1. FID-01はFID01_GOとして受領済み。登録分析はownerが一度だけ書いた不変記録を読む。
2. R3 compositeを一度検証しGEOM03_NO_GOで終端。採用せず、R0-clean fixed-pool/parent経路を選択済み。
3. K5のfinite-array、P1のfrozen fluid planes、28新規phi-space combinationsは登録通り検証した。K1/K3/K5/K6/H0成功とK2/K4失敗を保持し、成功部分だけでR3を採用しない。
4. SCREEN finalist の存在、XV の SINGLE_FINALIST SE rule と budget 数値（registration 時）。
5. M4 の high-Re path（現状 option なし。EVAL-PT-01 は conditional）。
6. PR #71 の merge タイミング（parent/integration 判断）。

## 11. 先行研究と公式仕様から実装へ渡す注意

[Schevenels & Sigmund (2016), 著者所属機関の要旨](https://orbit.dtu.dk/en/publications/on-the-implementation-and-effectiveness-of-morphological-close-op/)は、close/open を順に適用するフィルタが、先行する操作の効果を壊し、solid と void の両方の長さ尺度を同時には保証しない例を報告している。今回の R3 は物体を書き換えるフィルタではなく、元の表現物体とその補集合を別々に測る診断である。同論文を R3 の不合格や合格の証拠へ流用せず、両相を独立に検証し、形態操作を並べただけで両相の保証を主張しないという設計上の注意として使う。

公式 SciPy の [label](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.label.html) は接続を structuring element で定義し、[binary_erosion](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.binary_erosion.html) は structuring element と border 条件を API として持つ。[distance_transform_edt](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.distance_transform_edt.html) の距離は配列上の背景点への距離である。したがって checker では 26近傍・物理間隔・有限配列の境界を明記し、未指定の default を独立性の根拠にしない。別の実装経路による一致は実装確認であり、それ自体を連続形状の真値とはしない。実行環境の版は freeze 時に固定する（準備時の実環境: Python 3.12.13、NumPy 2.5.2、SciPy 1.18.1）。

全 qualification flag は false のまま、`shape_update_allowed=false`。
