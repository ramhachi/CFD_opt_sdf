# CFD_opt_sdf SDF-native handoff bundle

このZIPは、`CFD_opt_sdf` を SDF-native・随伴/逆伝播・トポロジー可変の空力最適化系へ戻すための引き継ぎ資料です。

## 何を渡せばよいか

**原則はZIPごと渡してください。**

ただし、添付数に制約がある場合は **`00_HANDOFF_MASTER.md` だけで実装開始できます。**
このファイルを正本とし、他ファイルは調査根拠・現状スナップショット・実装補助です。

## 読む順番

1. `00_HANDOFF_MASTER.md` — 唯一の正本。方針、数学、実装順、Go/No-Goを統合。
2. `01_CURRENT_REPO_STATE.md` — 2026-09-26時点の現ブランチと保存すべき資産。
3. `02_DEEP_RESEARCH_REARCHITECTURE_PLAN.md` — 関連研究・solver比較を含むDeep Research全文。
4. `03_WATERLILY_DEEP_DIVE.md` — WaterLilyの微分可能性、PR #285、GPU/メモリ制約の詳細。
5. `04_FIRST_IMPLEMENTATION_TASK.md` — 最初のPRをそのままCodex/OpenCodeへ渡せる実装指示。
6. `05_KEY_SOURCES.md` — 重要な外部URL・固定revision。

## 最重要ルール

- 現行 K=16 B-spline Stage S は削除せず `superseded_reference` としてfreezeする。
- S2の24 primal campaignへ進まない。
- P21/OpenFOAM Stage Vのevidenceを変更・削除しない。
- canonical geometry design stateを SDF `phi` にする。
- WaterLilyはまず GPU primal として評価し、GPU reverse ADを既成事実として扱わない。
- FDはgradient verification oracleであり、production gradient backendにはしない。
- topology birthとgradient backendを同時にデバッグしない。
