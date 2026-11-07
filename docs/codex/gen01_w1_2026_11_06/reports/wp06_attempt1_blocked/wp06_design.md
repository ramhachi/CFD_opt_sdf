# WP6 GEOM-S1 設計メモ

作成日：2026-11-06。開始点：`e3dcdf6188df6079e197eb28f7fcba1451ec512d`。
ブランチ：`feat/gen01-w1-06-geom-s1`。開始時の tracked / untracked 差分は空。

**状態：BLOCKED（距離関数の仕様の選択待ち）。** 本メモは設計と負の再現例の記録であり、フェーズ A の実装完了を表さない。

## 読んだ文書と継承する契約

共通 README を最初に読み、AGENTS と指定の五文書、STATE、branching strategy、GEN-01 rev 3.1 全文を確認した。長い履歴文書は read-only worker に分担し、欠落範囲を補って全文の確認を完了した。WP6 が指定する v18、SDFDesignState、geometry_gates v1/v2、volume_semantics_v2、v2 geometry/topology/width 文書、ProblemSpec v2 と例、harness schema/build/template/README、研究 F §2・6、研究 E §1 も確認した。Issue [#32](https://github.com/ramhachi/CFD_opt_sdf/issues/32) は `gh issue view 32` で取得した。

- `phase_plan.md` が状態と実行順序の唯一の authority。今回の source-only 作業は登録、凍結、物理 gate の採用を伴わない。
- `phi < 0` が solid、exact zero は solid に数えない。node occupancy、八頂点の Float32 平均で判定する cell-centre occupancy、連続体／mesh の体積を区別する。
- design lattice と flow grid は別物。scene bbox と h から設計格子を作っても、WaterLily の flow domain を決定したことにはならない。
- v2 gate と ProblemSpec v2、既存 evidence/pin、WaterLily job、author 管理の仕様本文は変更しない。
- R3 の定義を新しい開発用 scene 検査で再利用しても、既存の `GEOM03_NO_GO` は変わらない。既存 R0 の occupancy alias と R3 の偽陰性を隠さない。
- P22-v2 の 8272 上限は特定の v17 格子の契約である。任意の scene に移植しない。
- #32 の正式な Birth-1 は actual primal response と registered improvement / rollback を要求する。WP6 の event 分類テストは、そのソフトウェア準備に限る。

## 先に解決する数式上の不整合

WP6 成果物 1 は、非零 camber/reflex、v18 `plate_phi` と同じ式、厳密な SDF を同時に要求する。GEN-01 §3.1 も「各要素はパラメタごとに厳密な SDF」とする。

局所 chord 座標を u、法線座標を v、s=2u/L とする。端の丸みと span tip から離れた `|u| < L/2` の領域では、v18 の式は

```text
f(u) = C (s^2 - 1/3) + R (s^3 - 0.6 s)
phi  = |v + f(u)| - t/2
f'(u) = (4 C/L) s + (2 R/L) (3 s^2 - 0.6)
|grad phi| = sqrt(1 + f'(u)^2)
```

である。剛体回転はこのノルムを変えない。C または R が非零なら一般に 1 にならず、滑らかな表面の近傍でも厳密な距離関数ではない。既存 gate の中央値許容差を通ることや AutoBody の局所的な `phi / |grad phi|` 正規化では、この契約を満たせない。

`wp06_sdf_preflight.py` を本メモの後に追加し、既存関数の直接呼び出し、中央差分、解析勾配、より近い境界点の witness を独立に照合する。既存 source を修正せず、正の基準として camber=reflex=0 も測る。この診断の成功は「矛盾を再現した」という意味であり、scene acceptance の成功ではない。

再開の選択肢は次の二つである。どちらも黙って選択しない。

1. 厳密な距離を優先する。v18 の零等位面を保ち、非零 camber/reflex の距離を最近点から求める。最近点の数値解法と許容差を認め、「同じ式」との一致は無変形 stadium に限定する。非零変形の phi 値は変わるため、WP4 比較の基準も明示する。
2. v18 の値の互換性を優先する。非零 camber/reflex を analytic implicit field と明記し、厳密 SDF 要件とテストを変更する。

共通 README 最終行の「仕様が矛盾している」場合の停止規則に従い、この選択まで production code を作らない。ゼロ変形だけを実装してフェーズ A 完了とすることもしない。

## フェーズ A の条件付き設計とインターフェース

実装時には以下の新規ファイルを使う。現時点ではこれらの API は提供していない。

| ファイル | 役割と再利用 |
| --- | --- |
| `src/cfd_sdf/scene/primitives.py` | frozen な PlateElement / EndplatePlate / BoxBody / MeshBody。点配列を SI 距離へ写像。入力の NaN、非正寸法、未知の型は拒否。BoxBody の超楕円体も単なる implicit 値を距離と呼ばず、距離評価法を定義してから実装する。 |
| `src/cfd_sdf/scene/scene.py` | `Scene(components, fixed, ground)`、min union、argmin labels、JSON と SHA、bbox/h から `SDFDesignState` を構築。状態 hash は既存型へ委譲。 |
| `src/cfd_sdf/scene/events.py` | seed / knockout / merge の有限提案、二 checkpoint の履歴検査、N の外側ループ。評価・採否・予算消費を実装しない。primitive の identity と voxel component 数を分けて記録する。 |
| `src/cfd_sdf/scene/gates.py` | 厚さ、gap、solid/void の R3、連結、cavity、endplate 接合、宣言された包絡と clearance。候補を変更せず理由を列挙。未知／未測定は通さない。 |
| `tests/scene/` | 距離、符号、hash、Birth と事象、位相、各 gate の合成反例。既存の scientific qualification とは別の開発テスト。 |

2D と 3D は同じ x-z 断面距離を共有する。無変形 stadium は v18 と同じ断面式を使う。3D の flat-tip extrusion は `dy=abs(y)-span/2` として

```text
min(max(d2, dy), 0) + hypot(max(d2, 0), max(dy, 0))
```

を使う。d2 が真の断面距離であることが前提である。2D の点列は x-z、3D は x-y-z と明示し、3D 専用の SDFDesignState への 2D 保存規約は別途宣言する。singleton 軸に暗黙の体積を与えない。

scene の `min phi_c` は要求どおりの CSG union である。符号と零等位面は正しくても、重なり内部では一般に union 境界までの厳密な負の最短距離ではない。primitive の距離性と scene の union の符号テストを分離する。これは min union 自体を変更する理由ではない。

MeshBody は固定 STL の winding sign と triangle までの unsigned Euclidean distance を分離する。`trimesh.proximity.signed_distance` を使うなら inside-positive を反転する必要があるが、名称だけで winding 法と推定しない。watertightness、winding、非有限／曖昧な符号の失敗を定義し、#53 の signer 未適格を docstring に残す。任意の固定 STL の適格化を合成 fixture から主張しない。

## Julia / WP4 との接続

Python は種類・単位・パラメタ・固定 STL の SHA を含む deterministic JSON を渡す。Julia 側は同じ定義を `AutoBody` の callable として直接評価し、`SetBody(min, ...)` で合成する。field 値と符号、局所／世界座標をテストで合わせる。動く地面は scene と同じ位相を受ける半空間として扱う。GPU 実行や job の変更は WP4 側である。

WP4 の多角形距離は別の幾何 oracle であり、同じ零等位面と離散化誤差の契約が必要である。WP4 が未完の場合は v18 の無変形 stadium を対照にする。非零 camber/reflex に対して真の距離を再定義する選択をした場合、v18 の phi の一致をそのまま acceptance にしない。今回は E2 比較を実行していない。

## h、r_c、gate の長さ

GEN-01 §3.2 が指定する開発時既定値は `t_min=4h`、`g_min=4h`。これは BDIM での物理解像を保証する値ではなく、後の登録梯子で検証する値である。R3 は width-rule 文書の trilinear body、h/4 refinement、erosion/opening、defect 閾値をそのまま再利用し、solid と void の双方を測る。R0 の repeated occupancy にすり替えない。

WP6 が要求する部品ごとの `r_c` と h の関係は、引用された rev 3.1 §3.2 には定義されていない。r_c を曲率半径、filter radius、R3 の erosion radius のいずれかと推定しない。意味・単位・h との関係・出典はフェーズ B までに明示が必要である。FSAE/FSG の箱も規則の版と座標基準を確認してから宣言し、値を推測しない。

## テスト計画と段階

1. 今回は source-bound な負の距離診断だけを追加し、判明した不整合を短い CPU 実行で再現する。src / tests / immutable evidence は変更しない。
2. 数式の選択後、距離の独立 oracle、符号、位相、gate 反例、Birth の順に TDD。median だけで厳密性を判定せず、非微分点を除いた複数点で調べる。
3. `pytest -q tests/scene`、compileall、全体 pytest、diff check。baseline の失敗 ID 集合と比較する。受け入れたフェーズ A を commit/push して PR を出す。
4. その後にだけフェーズ B。v3 は別モジュールとして v2 parser を保持する。harness は version を明示して scene / events / z 位相を追加し、旧 campaign の出力には新規 key や tool hash の変更を混入させない設計にする。旧 verifier の table は tool hash を含むため、byte 同一要件は version 文字列だけを残しても満たせない。

今回の全体 pytest は開始点の無変更コードに対して先に起動したが、仕様矛盾により実装を止めたため、901 passed / 24 skipped、778.01 秒で中断した。code 不変は Git と hash で別に記録し、完走した baseline の代用にはしない。再開時には baseline と最終の完走した失敗 ID 集合の比較が必要である。追加 probe 自体は個別に実行し、出力と SHA を保存する。

## 実行資源

OpenCode Go MCP ツールはこのセッションに存在しなかった。CLI 1.19.3 のモデル確認は通常経路では sandbox 外の log を開けず、writable な一時 XDG directories での再試行は `Provider not found: opencode-go`。provider/model の利用可否を確認できず、native read-only worker へ文書確認と独立数式レビューを分担した。Go への委譲成功や quota 枯渇とは扱わない。global config、認証、追加課金は変更していない。
