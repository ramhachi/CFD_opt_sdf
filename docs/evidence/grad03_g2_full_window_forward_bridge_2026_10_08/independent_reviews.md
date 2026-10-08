# G2 実行前の独立レビュー（T4 投入前）

仕様と実装だけを渡し、primary の結論は渡していない。レビューは読み取り専用（Julia は実行していない）。モデル出力であり、ユーザーの発言ではない。

## Review A — 科学的な同一性: **PASS**（P0・P1 なし）
- Candidate C の body 構築、canonical v17 phi、4 方向（SHA と順序）、flow_24 の case が、登録済み job と一致。
- 測定の意味（remeasure 既定、warm-up を step 1 に数える、8 ステップごとの採取、candidate のみの `-(pressure+viscous)`、drag=Fx・downforce=−Fz、窓の端点の線形補間、台形の時間加重、
  等時刻の枝、1/900 のスケール）が、Julia・Python・登録済み実装の 3 者で一致。
- AD の意味（`phi0+α·d`、α は m、tangent は N/m、符号）が ĝ と整合。δ・verdict・refit・reverse・flag に触れていない。
- 時刻の tangent を伝播する版が「FD oracle の観測量の微分」として正しい（時刻固定版は参考）。
- P2: Poisson の有限反復と CFL の枝の微分、最終サンプルの選択、等時刻の枝の端の例、非定常なら時刻 tangent の寄与が増えうること → `prerun_note.md` の追記に反映。

## Review B — AD・実装: **PASS**、「T4 に 1 回投入して安全: yes」（P0・P1 なし）
- alpha=0 の primal、seed、Dual の剥がれなし、方向ごとに clean な simulation、`GC.@preserve`、CUDA の scalar 例外なし、fail-closed（Julia は exit 2、runner は ERROR.txt・DONE なし・exit 1）、
  host の再計算と Julia の同一アルゴリズム、gate の実装、引数順、sparse checkout を確認。
- P2 と対応:
  - script の timeout が kernel の timeout を超えうる → runner を残り時間で clamp（`remaining()`、テスト追加）。
  - summary が欠けると verifier が例外 → 構造化された FAIL にし、label と real_type も検査（テスト追加）。
  - analyzer が verification の SHA を検査しない → sidecar を検査。
  - runner の pin の commit と freeze の作成 → 本 commit。
  - run 間に `GC.gc()` なし → 影響は想定されず、対応しない（記録のみ）。
  - plain と baseline_v17 の 1e-6 gate は reduction の決定論に依存 → 登録済みの規則どおり（不一致なら G2-BLOCKED）。
