# WP6 GEOM-S1 フェーズ A 報告（Amendment 4）

## 状態

**DONE（フェーズ A：第2回 Opus review の N1〜N4 を修正・重点再検証）**。開始点は `6dcd7c6287f5b2d4fa61361c42de8ffdaf63ef99`、branch は `feat/gen01-w1-06-geom-s1`。今回の最終 `tests/scene` は **251 passed / 0 failed / 0 errors**、関連する既存 gate・topology・volume は **81 passed**、SDF state は **9 passed**。失敗 node 集合はそれぞれ `[]`。compileall と diff-check も成功。フェーズ B は未着手。

全体 pytest は **Amendment 4 §5 に従って実行していない**。前回の全体結果 **3680 passed / 74 skipped / 0 failed** と host base `e3dcdf61` の空失敗集合との一致は、前回 source の歴史的記録として保持する。今回の全体失敗集合を測定したという主張はしない。今回の変更からの source closure への影響は byte 照合で別に確認した。

この DONE は作業ツリー上の solver-free software 受け入れであり、科学的登録、物理／BDIM qualification、Birth-1 primal の完了ではない。Amendment 4 §6 に従い、Codex は git add／mv、commit、push、index/ref 更新、PR 編集を行っていない。HEAD は開始点のまま。Claude が host で一覧のファイルを commit・push し、既存 PR [#82](https://github.com/ramhachi/CFD_opt_sdf/pull/82) を更新する。

## 作ったもの（今回 commit すべき完全な一覧）

今回は移動なし。`6dcd7c62` からの変更8ファイル、新規9ファイルをすべて列挙する。過去の移設・Amendment 3 のログは今回の追加物ではない。

| 区分 | 完全なパスと内容 |
| --- | --- |
| 変更 | `src/cfd_gen/scene/gates.py`：厚さ・接合を可動部品に限定、context の別記録、共有 gap guard、16 位相の全件合格検査。 |
| 変更 | `src/cfd_gen/scene/events.py`：merge overlap、未収束 pair の局所 skip と記録、scalar floor の削除、guard 付き split gap。 |
| 変更 | `src/cfd_gen/README.md`：制約範囲、事象の使い方、merge の計算時間の既知の限界。 |
| 変更 | `tests/scene/test_gates.py`：fixed STL＋端板の正負対照、16 位相の不合格・unmeasured・入力検査。 |
| 変更 | `tests/scene/test_events.py`：斜め merge の16 位相、迎角・camber 付き30設計、scalar 拒否と未収束 pair の継続。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_design.md`：コード編集前に Amendment 4 の設計・検証・host delivery 境界を追記。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_report.md`：今回の報告、条件を限定した主張、完全な commit 対象一覧。 |
| 変更 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_validation.json`：今回の結果・コマンド・SHA と過去 Amendment 3 の検証を別区画で保持。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_amendment4_review_checks.json`：review 入力 SHA、N1〜N4 とテストの対応、130/13 source の byte 照合。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-scene-pytest.log.gz`：今回のログ／JUnit（圧縮 bytes と展開 bytes の SHA は validation）。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-scene-pytest.xml.gz`：今回のログ／JUnit（圧縮 bytes と展開 bytes の SHA は validation）。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-related-pytest.log.gz`：今回のログ／JUnit（圧縮 bytes と展開 bytes の SHA は validation）。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-related-pytest.xml.gz`：今回のログ／JUnit（圧縮 bytes と展開 bytes の SHA は validation）。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-state-pytest.log.gz`：今回のログ／JUnit（圧縮 bytes と展開 bytes の SHA は validation）。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-state-pytest.xml.gz`：今回のログ／JUnit（圧縮 bytes と展開 bytes の SHA は validation）。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-compileall.log.gz`：今回のログ／JUnit（圧縮 bytes と展開 bytes の SHA は validation）。 |
| 新規 | `docs/codex/gen01_w1_2026_11_06/reports/wp06_test_artifacts/wp06-amendment4-red.log.gz`：実装前の TDD red ログ4本。資格判定ではない。 |

`src/cfd_sdf`・`julia/`・`scripts/` に差分なし。列挙される Python 130 source と Julia 13 source は host base `e3dcdf61` とすべて byte 一致し、追加の source もない。`src/cfd_sdf/scene/` は存在しない。v2 parser／gate、harness、登録済み evidence、author-managed 計画本文は変更していない。旧 attempt、旧 band 診断／表、旧ログは変更せず、前回 validation 全体は `previous_amendment_3` に保存した。

## 修正と対応する確認

| review 項目 | 実装と検証 |
| --- | --- |
| N1 | 厚さ gate と joint の翼側・端板側を `scene.components` に限定。fixed STL タイヤ＋2h の fixed 端板＋翼が、幅の外部宣言や fixed 接合宣言なしで全 gate を通る。fixed 幅・h に対する下限幅・solid node 数は `context_resolution` に別記録し、STL の未知の幅を推測しない。fixed に design joint の gap 免除を与える宣言は拒否し、可動 vs fixed の overlap/gap 検査は維持する。 |
| N2 | 既定 overlap δ を小さい板の厚さの 1/2 とした（厚さが適合する板なら t_min/2 以上）。生成器は提案だけを返す。`evaluate_scene_gates_phases` は caller が宣言した共通16位相すべての合格を要求し、拒否・unmeasured を含め全結果を残す。角度差 0.35 rad の非同一 main＋flap が2D／3Dとも16/16合格。 |
| N3 | gap を省略する分割は h と policy/dimension を受け、`g_min + gate の guard + 変形余裕` を使う。gate と同じ helper から guard を算出し、明示 gap の従来経路は保持する。子弦 `(L-t-gap)/2` による親 footprint の保存を維持。下記の限定条件で N=1..5 の30設計すべて合格。 |
| N4 | scalar thickness floor を削除し、per-ID mapping／時点別 snapshot のみ受ける。snapshot が揃っていても scalar 指定を拒否。最近点探索の専用 `NearestBoundaryConvergenceError` だけを捕捉し、その対を skip、ID／理由を diagnostics list（省略時は WARNING）へ記録して他の対を続ける。不正入力・無関係な ValueError は伝播する。review 観測の所要時間を README と本報告に記録。 |

**N3 の合格条件**：h=0.025 m、親の直線弦 L=2.4 m、t=4.1h、camber/c=0.0125、reflex=0、span=4h。迎角 **0°・−10°・−20° × 2D／3D × N=1..5**、計30設計。t_min=g_min=4h の開発既定に対し、既定 split gap は2Dで **4.414h**、3Dで **4.767553h**。camber による normal width を満たすため、生の t を4hより少し大きくした。任意の角度・camber・厚さ・分割数で合格するという主張ではない。前回の「t=4h, gap=4h で N=1..5 合格」は**無変形・迎角0°・2Dの AABB 分離で認証される fixture**の結果に限る。

**N2 の合格条件**：h=0.025 m、main/flap の直線弦1.2／0.4 m、厚さ6h／7h、span=6h、角度差0.35 rad。x,z の4×4位相 `(i/4,j/4)`、3Dのy位相 `((i+j)%4)/4`（2Dは0）。共有する16位相を明示し、各寸法で16/16合格。これは有限 fixture の標本化 gate の結果で、全 merge の位相不変性や連続形状の保証ではない。

## インターフェース（他 WP が使うもの）

- `merge_candidates(scene, *, max_gap=None, overlap=None, diagnostics=None)`：最近点方向への gap＋δ の移動と child provenance を保持。既定 δ は小さい厚さの1/2。diagnostics の各項目は `{"pair_ids":[a_id,b_id],"reason":"nearest_boundary_refinement_did_not_converge"}`。提案生成は CFD・採否・予算消費を行わない。
- `evaluate_scene_gates_phases(scene, *, h, dimension=3, policy, phases)`：16個の相異なる有限の x,y,z 位相（各軸 [0,1)、2Dはy=0）を検査前に検証。`phase_reports` の各項目は `phase` と単一位相の `result`。どれか1つの拒否／unmeasured で全体を拒否し、全位相の結果・理由・scene SHA を保存する。単一 `evaluate_scene_gates` は位相ごとの診断。
- `element_count_designs(scene, n_max, *, gap=None, h=None, dimension=3, policy=None)`：明示 gap または共有 guard 付き既定 gap の有限 warm start。既定 gap の場合は正の h が必須。子の相対 camber/reflex を維持する。体積保存・最適化・採択は行わない。
- `thickness_knockout_ids(history, minimum_thickness=None, *, tolerance=...)`：per-ID の床、または各行の `parameter_floors` snapshot を使う。scalar は例外。床は `thickness_parameter_floors` と対応する checkpoint scene を一緒に保存する。出力は parameter ID で、merged child の ID もあり得る。

2D／3D は同じ x,z 断面と3Dの flat-tip extrusion を共有する。距離計算・scene JSON/hash は今回変更していない。無変形板だけが v18 field 値と1e-3c以内（実テストは1e-14）の比較対象。変形板は v18零面への2面×6始点×13 Newton射影で、下記の既存の距離診断を保持する。Julia/WP4はこの射影を `AutoBody` 内で直接評価し `SetBody(min,...)` で合成する必要がある。polygon SDF は近似表面が異なるので別の比較が要る。Julia job は未編集、Float32/AD/GPU の費用・精度は未測定。

WaterLily 主線に r_c はない。h は標本化と開発時の特徴寸法の床に使い、変位フィルタ半径ではない。t_min=g_min=4h は開発既定、登録値は RES-00 の梯子で決める。ProblemSpec v3 と harness v1.2 はフェーズ B の別 PR。

## テスト

| 今回の対象 | コマンド | 結果 |
| --- | --- | --- |
| scene／Birth-0／Birth-1 software preparation | `.venv/bin/python -m pytest -q tests/scene -p no:cacheprovider --junitxml=/private/tmp/wp06-amendment4-scene-pytest.xml` | **251 passed、0 failed/errors、終了0、23.86 s**。 |
| 既存 gate／topology／volume | `.venv/bin/python -m pytest -q tests/test_sdf_native_geometry_gates.py tests/test_geometry_gates_v2.py tests/test_sdf_topology_policy.py tests/test_sdf_topology_policy_research.py tests/test_sdf_native_volume_semantics_v2.py -p no:cacheprovider --junitxml=/private/tmp/wp06-amendment4-related-pytest.xml` | **81 passed、0 failed/errors、終了0、30.28 s**（既存依存由来の deprecation warning 159件）。 |
| SDF state | `.venv/bin/python -m pytest -q tests/test_sdf_design_state.py -p no:cacheprovider --junitxml=/private/tmp/wp06-amendment4-state-pytest.xml` | **9 passed、0 failed/errors、終了0、0.34 s**。 |
| compileall | `.venv/bin/python -m compileall src tests` | 終了0。 |
| whitespace | `git diff --check` | 終了0。 |
| source closure | `wp06_amendment4_review_checks.json` | host base と Python130／Julia13すべて byte 一致。protected tree に差分なし。 |
| 全体 pytest | **今回実行せず**（Amendment 4 §5） | 前回3680 pass／74 skip／0 failは歴史的記録のみ。base 再取得も行わない。 |

今回の failure node 集合は scene `[]`、関連 `[]`、state `[]`。ログ／JUnit は gzip(mtime=0)で保存し、圧縮 bytes と展開 bytes の SHA256 を `wp06_validation.json` に記録。TDD red は expected failure として別 artifact に保存した。最終 source の SHA はテスト後に読み戻した。前回の全体 pytest を今回の測定に数えず、CPU profile plugin、CFD／GPU の実行はない。

### 保持した既存の距離診断（今回再実行していない）

Amendment 3 の50ケースと表を保持する。`primitives.py`／`scene.py`／診断コードとJSONは開始点と byte 一致。以下を今回の新しい band 測定とは扱わない。

c=1 m、t=.1 m、h=.025 m、各条件1700 query、seed=610。band は |computed phi|≤2h。独立にパラメタ化したv18零面（片側50001点＋caps）への最近点距離と比較し、3Dは flat-tip extrusion を検査。gradient errorは2D/3Dの中央値の大きい方。以下は Amendment 3 で再生成した結果。

| camber/c (%) | reflex/c (%) | band 点数 2D / 3D | 最大距離差/t 2D | 最大距離差/t 3D | 最大 median gradient error |
| ---: | ---: | ---: | ---: | ---: | ---: |
| -6 | -4 | 1004 / 762 | 5.841e-06 | 2.449e-06 | 1.967e-12 |
| -6 | -2 | 1014 / 763 | 2.817e-05 | 3.474e-06 | 1.879e-12 |
| -6 | +0 | 1016 / 761 | 4.558e-06 | 1.280e-05 | 1.856e-12 |
| -6 | +2 | 1006 / 758 | 3.035e-06 | 8.754e-07 | 1.793e-12 |
| -6 | +4 | 1002 / 758 | 1.237e-05 | 2.326e-05 | 2.107e-12 |
| -3 | -4 | 1008 / 759 | 1.563e-05 | 2.838e-06 | 1.897e-12 |
| -3 | -2 | 1009 / 751 | 2.677e-06 | 4.132e-06 | 1.848e-12 |
| -3 | +0 | 1004 / 753 | 1.847e-05 | 2.109e-06 | 1.743e-12 |
| -3 | +2 | 1006 / 752 | 1.160e-06 | 1.437e-06 | 1.750e-12 |
| -3 | +4 | 1014 / 756 | 1.885e-06 | 8.857e-06 | 1.899e-12 |
| +0 | -4 | 1014 / 766 | 2.593e-06 | 1.069e-05 | 1.753e-12 |
| +0 | -2 | 1018 / 765 | 1.716e-06 | 3.506e-05 | 1.821e-12 |
| +0 | +0 | 1011 / 761 | 1.135e-05 | 6.392e-06 | 1.000e-12 |
| +0 | +2 | 1002 / 759 | 3.000e-06 | 5.224e-06 | 1.726e-12 |
| +0 | +4 | 995 / 754 | 2.067e-06 | 1.684e-06 | 1.733e-12 |
| +3 | -4 | 1014 / 762 | 5.041e-05 | 2.928e-06 | 1.809e-12 |
| +3 | -2 | 1005 / 757 | 1.330e-05 | 1.291e-05 | 1.846e-12 |
| +3 | +0 | 999 / 761 | 5.001e-06 | 1.386e-05 | 1.889e-12 |
| +3 | +2 | 1003 / 767 | 1.949e-06 | 4.682e-05 | 1.815e-12 |
| +3 | +4 | 1004 / 767 | 2.704e-06 | 4.150e-06 | 1.847e-12 |
| +6 | -4 | 1015 / 768 | 6.485e-06 | 1.372e-05 | 2.102e-12 |
| +6 | -2 | 1018 / 759 | 5.250e-06 | 5.856e-06 | 1.844e-12 |
| +6 | +0 | 1005 / 762 | 3.059e-06 | 1.745e-05 | 1.803e-12 |
| +6 | +2 | 1002 / 765 | 7.046e-06 | 9.430e-06 | 1.920e-12 |
| +6 | +4 | 1003 / 764 | 1.574e-06 | 8.354e-06 | 2.079e-12 |

最大距離差/tは **5.040873270172855e-05**（許容0.02）、最大 median |∇φ|偏差は **2.107147789587316e-12**（許容0.10）。無変形板は非微分集合を避けて |∇φ|=1 を atol=1e-8 で検査する。有限標本・固定t/c,h/cの開発診断であり、全パラメタ空間の距離保証やBDIM資格ではない。

## 仕様からの逸脱と理由

新たな矛盾はない。Amendment 4 の指定どおり phase A の package とそのテストだけを修正し、README と実装記録を更新した。proposal-only の境界を保つため、16位相の採否検査は生成器へ埋め込まず、明示的 gate 関数として提供する。厚さの scalar 互換経路は指定どおり廃止した。

OpenCode Go MCP は存在しない。CLIの通常 log は sandbox 外書込制限に当たったが、task-local XDG runtime と既存 auth への read-only symlink で現行 catalog を取得した。DeepSeek V4.1 Flash の実 worker は45 s timeout、同階層 MiMo-V2.5 は401 `api_key_expired`。Go成果は返っていない。認証・global設定・追加課金は変更せず、native worker が events/test_events、親が gates/test_gates・統合・検証を担当し、差分を相互レビューした。model 切替理由は validation に保存。

## 未確認の仮定・既知の限界

- Birth-1 は software preparation のみ。実 primal 応答、採択、改善、physical/BDIM/GPU資格は未検査。qualification flag／shape_update_allowedは変更していない。
- Merge の最近点探索は8始点の数値探索で大域最短距離の証明ではない。**review 2 の観測は1〜2 s／対、|camber|/c=6% では24〜26 s／対**。今回この所要時間を再 benchmark していない。未収束を skip しても計算の上限時間を短縮するものではない。高速化は MW-01 前の別 WP。
- sampling は2,000,000 node、R3は8,000,000 refined nodeで unmeasured。1.4 m span・h=5 mm の例 `[281,1137,57]` は18,211,329 nodeでcap超過。小さい3Dfixtureの成功をMW-01規模での gate 利用可能性とは呼ばない。
- MeshBody は O(P×T)：P=1,000,000／T=100,000なら10^11対、phi毎にSTL全bytesを再read/hashし、境界標本化もPython triangle loop。車両mesh規模の速度・メモリは未資格。SRCMAP-02 #53 の target signer も未資格。
- merged overlap は band距離契約の例外で、`distance_contract_exemptions` に記録。BDIM影響は未測定。一般BoxBodyの内部continuationはray単調でなく、距離値による一般gap判定は未資格。
- R3、連結性、空洞、接合は宣言した標本規約の検査。16位相は有限集合であり、すべての連続位相・製造可能性を保証しない。GEOM03_NO_GO／R3未採用の歴史を変更しない。
- review の `scratchpad/wp06r2/*.py` は指定worktreeには存在しなかった。レビュー本文の反例を独立した回帰fixtureで再現・修正した。実規則の箱、STL/hash、parameter bounds/刻み、ProblemSpec v3、harness v1.2 は後続のフェーズ B。

## Claude／ユーザーへの提案する追記

author-managed 本文は未編集。追記案：

> GEOM-S1 phase A の第2回 source review N1〜N4 を修正。設計厚さ・wing/endplate joint は movable に限定し、fixed 解像度は情報記録とする。merge は checkpoint の共通16位相すべての scene gate 合格が必要。既定split gapは g_min に sampling guard と変形余裕を足す。厚さ履歴はper-IDの床または時点別snapshotとし、mergeの未収束pairは理由を残してskipする。今回scene251・関連90テスト合格。全体pytestはAmendment4で免除、物理資格は更新しない。

`docs/harness/README.md` への追記案（本文未編集、v1.2未実装）：

> harness v1.2は新規wrapperを優先し、scene geometry SHAとSTL SHA、明示的Julia引数、checkpointごとの有限event候補、zを含む3軸位相を扱う。各merge候補は同じ16位相の全scene gate結果と未収束pair診断を保持する。transport JSONのファイルSHAとgeometry SHAを区別し、v1.1のvalidate/verifyのbyte不変を検査する。

## 次に要るもの

Claude が host で上の17ファイルだけを stage／commit／pushし、既存 PR #82 を更新する。新規 PR／auto-merge は作成していない。フェーズ B はまだ始めない。MW-01 の前に3D資源設計、MeshBody高速化、Julia projection/Float32/AD検査と merged band の BDIM 影響を別 WP で扱う。
