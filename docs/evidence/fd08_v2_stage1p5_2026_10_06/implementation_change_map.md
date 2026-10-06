# 承認後のv2実装変更候補（今回変更0）

現HEADをsource anchorで再検索した。旧関数のthresholdを差し替え、旧evidenceを新gateで読み替える方式は採らない。新契約・inventory・registration・hostverifierを別versionに分け、旧コード/criteriaの意味を保つ。

| 現source anchor | 承認後に別v2経路が必要な理由 |
| --- | --- |
| `src/cfd_sdf/fd08_calibration.py:24` | formal の 5 点固定と calibration 部分集合条件 |
| `src/cfd_sdf/fd08_calibration.py:25` | D0/D1/D2 の固定 inventory。B-4/B-6 は未決 |
| `src/cfd_sdf/fd08_calibration.py:28` | 7 点以上と 6 点案の衝突 |
| `src/cfd_sdf/fd08_calibration.py:29` | 100 倍以上と 10/16.7 倍案の衝突 |
| `src/cfd_sdf/fd08_calibration.py:225` | 点数・span 制約と新 ladder の別契約 |
| `src/cfd_sdf/fd08_calibration.py:236` | 5 点固定・calibration 部分集合から内部新点へ |
| `src/cfd_sdf/fd08_calibration.py:530` | median-slope 5% から WLS と 6 項目への別契約 |
| `src/cfd_sdf/fd08_calibration.py:550` | 3 方向共通の連続 5 点窓、全 6 系列の gate |
| `src/cfd_sdf/fd08_calibration.py:608` | 5 点窓を列挙する旧 gate の停止規則 |
| `src/cfd_sdf/fd08_calibration.py:657` | 5 観測・floor・plateau 固定 |
| `src/cfd_sdf/fd08_calibration.py:699` | 全 6 系列固定。B-4 の被覆規則は未決 |
| `src/cfd_sdf/fd08_calibration.py:205` | baseline span の床と jitter に基づく σ 推定は異なる |
| `src/cfd_sdf/fd08_contract.py:17` | 33 state 固定と predict-then-run 24 state |
| `src/cfd_sdf/fd08_contract.py:18` | 5% 固定。新 tolerance は暫定案・未承認 |
| `src/cfd_sdf/fd08_contract.py:19` | 3 plateau 点と v2 gate の点数要件 |
| `src/cfd_sdf/fd08_contract.py:48` | 3 baseline + 3×5×2 の固定矩形 |
| `src/cfd_sdf/fd08_contract.py:27` | fresh33 固定。disjoint inventory は維持 |
| `scripts/register_fd08_formal.py:111` | calibration の連続 5 点部分集合・旧 sources と gate の hash 結合 |
| `scripts/verify_fd08_formal.py:87` | fresh33・3 方向・calibration の 5 baseline・全旧 gate の再計算 |
| `scripts/register_fd08_calibration.py:367` | 旧 ladder 検証、D0/D1/D2、baseline 5、signed inventory、criteria 結合 |
| `scripts/analyze_fd08_calibration.py:95` | 旧 pair 分母・baseline floor・共通 plateau selector・新 jitter roles |

Stage1表のjitter依存floor案は今回の推奨では採らない。baseline5→1では旧derive_response_floorのspan推定を呼ばず、T2σ0/ρを明示的な仮定として扱う。旧response_floor semanticsは維持する。formalは25stateの別v2inventory、既存fresh33を改変しない。

epsilon_mはmax-normalized scalar phiへの名目係数[m]。v2 fitに渡すepsilon_mm=1000*epsilon_m、effectiveFloat32 motionは別診断。旧centered_pairのq分母やSDF値をeffectiveεへ置換しない。新方向のphysicalnormal変位はdirection_designの一次関係とsurface監査で別に記録する。

固定3方向/33run/5点を前提とするsourceは一覧のほか保護generate_directions/validate_directions、registrarstatecount、kernelmetadata/bundle/source-inputmanifestを含む。D0/D1/D2のsource/array hashesを保持し、新方向は別inventory項目。v2hostverifierは全8系列＋formal未使用byte列、C5/C4、全qualification/停止branchとaggregate budgetsを再検証する。

数値実験・設計scriptは既存登録器を実行せず、R5 force/result/analysisを読み込まない。変更対象を承認した後にのみ新sourceとhashを固定する。
