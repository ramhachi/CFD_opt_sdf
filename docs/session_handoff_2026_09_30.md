# セッション引き継ぎ: 2026-09-29〜10-01 (SDF-native / v17)

新しいエージェント (Claude、Codex、OpenCode など) 向けの現状メモ。
実行順序の正式な記録は `docs/phase_plan.md` §11、課題台帳は GitHub issues。
このファイルは、それらを読む前に押さえておくべき要点をまとめたもの。

## 1. ブランチ運用 (ユーザー決定)

- 統合先は `codex/kaggle-batch-migration`。`main` は 9/11 で止まっており、現時点で統合には使わない。
- merge は `--no-ff` のみ。rebase / squash / force-push はしない。
  登録済みの criteria や証跡が source commit SHA に結び付いているため、履歴を書き換えると壊れる。
- 共有ドキュメント (`phase_plan.md`、`README.md`、`problem_register_2026_09.md`、`opencode_handoff_2026_09.md`) は、統合担当だけがまとめて更新する。
  issue ごとの作業結果は `docs/issues/<番号>_*.md` に書く。
- 既存の evidence JSON / sidecar と閾値は書き換えない。訂正は append-only のファイルで行う。
- Colab は撤退済みで、GPU の実行は Kaggle T4 のみ (CLI 認証済み、ユーザー名 `ramhachi888`)。
- OpenFOAM のコードは撤去する方針。
  - 復元元は tag `archive/pre-openfoam-removal-2026-09-29`。
  - `docs/evidence/` は残す (ユーザー決定)。
  - 撤去作業のブランチは中間状態で**壊れている**ので、merge 禁止 (§4)。
- サブエージェントを起動するときは、`model: "sonnet"` を明示する (ユーザー指定)。

## 2. 技術的な到達点 (2026-10-01 更新)

| 項目 | 状態 | 記録 |
|---|---|---|
| FD-02 round 5 | fail-closed | #16 (close 済み) |
| FD-04 診断 (#36) | 原因を特定: v16 の薄板の面が h = 0.05 の節点に乗り、66 セルで勾配 ≈ 0。bridge の `n = g/|g|` が不安定になる | `docs/issues/36_interim.md` |
| genesis v17 (#43) | 登録済み。h = 0.025、121×65×49。同じコードを h = 0.05 で走らせると v16 とビット単位で一致 | `docs/issues/43_result.md`、`evidence/sdf_native_genesis_v17_2026_09.json` |
| v17 のローカル FD | 今の bridge のまま ε に比例 (CPU の短時間計算。正式な判定ではない)。**flow_24 の正式な FD-05 では再現しなかった** | 同上、`issues/37_fd05_*.md` |
| FD-05 (#37) | **terminal FAIL**。v17 / flow_24 で 6/6 の組み合わせが plateau FAIL。原因の候補は、band 内の平坦点 348 個での法線の反転 (診断のみ) | `issues/37_fd05_result.md`、`issues/37_fd05_solver_free_diagnosis.md` |
| W3 v17 (Kaggle) | **PASS** (T0〜T10)。drag 0.223 N / downforce 0.253 N (v16 は 0.336 / 0.353) | `docs/issues/43_w3_result.md`、`evidence/kaggle_w3_v17_primal_result_2026_09.json` |
| v16 と v17 の差 | 減少は圧力成分が中心。v16 の drag が Stage V に近いのは偶然の打ち消し合いという仮説 (未検証)。**方針は v17 を採用** | `43_w3_result.md` の追記 |

W3 の一連の処理 (job、runner、verifier、dataset 準備) は、canonical state のラベル、形状、間隔、hash を criteria から読むように汎用化した。
v16 の過去の criteria もそのまま動く。v17 用の registrar は `scripts/register_kaggle_w3_v17_primal_2026_09.py`。

## 3. 次の作業 (推奨順)

1. **W4 v17 sensitivity completed PASS.** Kaggle T4 exact kernel `/1` passed
   host verification T0-T10 against source `4c20787c`; four cases and the
   flow/domain response are recorded in [`issues/43_result.md`](issues/43_result.md)
   and `phase_plan.md`. This does not qualify grid convergence or physical
   forces.
2. **FD-05 (#37) は実行済みで terminal FAIL (2026-09-30)。**
   - v17 + flow_24 の新しい契約（round 1）で、Kaggle で 33 本を実行した。T0〜T9 は PASS、T10/T11 の plateau gate は 6 組すべて FAIL。
   - strict host 検証も fail-closed だった（`ERROR`、DONE なし、criteria hash の食い違い）。再試行はしていない。
   - 正本は [`issues/37_fd05_result.md`](issues/37_fd05_result.md)。
   - solver を使わない追加診断を [`issues/37_fd05_solver_free_diagnosis.md`](issues/37_fd05_solver_free_diagnosis.md) にまとめた（2026-10-01）。
     - 流れは完全に定常である。
     - 粘性の力は ε→0 でもベースラインに戻らない。
     - flow_24 の band 内で、φ≈0 かつ |∇φ|≈0 の 348 点では、どんな摂動でも法線が反転する。
   - 次は FD-06 の前に、法線を正則化するか、サンプル平面と面の平面の一致を崩すか、ユーザーが判断する。
3. **Volume reference:** remeasure v17 `V_phi_0` before OPT-01.
4. **Gate definition revision (#29):** make force-band gradient gate v2 and
   exclude the solid-interior medial axis at the band edge. Three v17 cells
   remain below the current 0.25 threshold.
5. W4 の verifier の `remote_inventory_sha256` の名前衝突は修正済み (§6)。
6. FD の runner/host verifier の criteria hash の扱い（outcome はファイルの SHA、host は canonical SHA）を揃える。FD-06 を実行するより前に直す。


## 4. 未 merge のブランチ (2026-09-29 に途中で止めた WIP。中間報告は各ブランチの `docs/issues/*_interim.md`)

| ブランチ | 状態 |
|---|---|
| `feat/issue-28-sdf-reinit` | 演算子は実装済み。契約 doc のハッシュが古い。v16 の問題の解決策ではないと判明 (#28 のコメント参照) |
| `feat/issue-29-geom-gates` | 12 種の gate を実装したが、**一度も実行していない** |
| `feat/issue-17-19-infra-preflight` | 設計メモと、未検証の runner / job の差分のみ |
| `chore/remove-openfoam` | **壊れた中間状態で merge 禁止**。219 ファイルを削除済みだが、`cli.py` の import が未修正 |
| `feat/issue-42-w0b-kaggle` | WIP。#42 の前提はほぼ既に満たされている (Kaggle の W1g round 2 は PASS 済み)。close してよいか要判断 |

## 5. 既知の落とし穴

- **登録は codex ブランチの clean な HEAD でのみ可能**。registrar がブランチ名を検査し、Kaggle の runner は codex から depth 16 で source を取得する。
- **host 検証は、登録した source commit を取り出した worktree で行う**。登録後にファイルを直すと、source の hash 検査で止まる。
- **W3 の verifier のバグ** (`HOST_VERIFIER` が未定義) は修正済み (§6)。過去の round を検証するときは、登録した commit の verifier を `scripts/verify_kaggle_w3_v16_host_compat.py` 経由で使う。
- **全 pytest のベースライン失敗は 37 件**。gitignore された `work/` の fixture がないことによるもので、Stage V / OpenFOAM 系が中心。検証は「新規の失敗が 0」で判定する。
- Kaggle の kernel は、`infra/kaggle/kernel_w3_v17/kernel-metadata.json` と `infra/kaggle/kernel_w3/runner.py` を一時フォルダにコピーして push する。
- **Kaggle 上の力は solver 単位**。N への換算係数は ρU²h² で、flow_16 (h=0.05) では 0.0025、flow_24 (h=1/30) では 1/900。報告と判定は N ベースで行う (ユーザー方針)。

## 6. 追加の決定 (2026-09-30)

- **FD と最適化に使う flow 解像度は flow_24** (ユーザー決定)。
  - W4 v17 では、flow_16→24 で drag +46% / downforce +31%、flow_24→32 でも +7% / +9% 動く。値は収束していない。
  - 1 run の計算時間は flow_24 で約 100 s、flow_32 で約 340 s。
  - 最終的な形状の評価と ranking の確認は、別途 flow_32 以上で行う前提。
- 検証ツールのバグを修正し、回帰テストを追加した。
  - W3 の verifier: `HOST_VERIFIER` が未定義だった。
  - W4 の verifier: 引数名 `remote_inventory_sha256` が同じ名前の関数を隠していた。
  - 過去の round を検証し直すときは、今後も**登録した commit** の verifier を使う (host-compat ラッパー経由)。
- `infra/kaggle/kernel_w4_v17/runner.py` と `docs/evidence/w4_v17_criteria.json` は中身が同一のコピーだが、W4 v17 の criteria で束縛されているので削除しない。
