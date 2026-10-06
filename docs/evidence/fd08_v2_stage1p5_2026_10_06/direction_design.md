# B-6 analytical lobe design / canonical diagnostics (Stage 1.5, 未登録)

証拠区分: `solver_free_design_and_numeric_contract_unregistered`。全6 qualification flag は false。B-6 は未承認。

この文書の以下の preset を cosine/support 診断実行前に固定した。旧 Stage 1 設計メモを具体化する設計診断であり、新 direction の生成・登録ではない。
解析定義 freeze SHA-256: `2b38c7be0151a5a4fe1864d8b5cf83a0d33a8fb653c9f156d0ba0d281a249acb`。再現可能な定義は `direction_diagnostics.json` の `frozen_definition`。

```json
{
  "a_rule": "sum coefficient*max(1-sum(((x-center)/width)^2),0)^3",
  "array_restriction": "temporary Float64 active-node expressions only; no new full-grid direction, Float32 array, candidate hash, signed state or dataset",
  "coordinate_rule": "centers=active_min+fraction*active_span; widths=fraction*active_span",
  "gradient_rule": "second-order central differences on interior nodes; first-order one-sided at box edges; zero-gradient raw remains zero",
  "normal_convention": "n=+gradient_phi/norm(gradient_phi); negative phi is solid; delta_phi=-u dot gradient_phi",
  "phi_rule": "raw=-a*norm(gradient_phi)*interface_taper; active_node_values=raw/max(abs(raw))",
  "presets": [
    {
      "centers_fraction": [
        [
          0.25,
          0.5,
          0.5
        ]
      ],
      "coefficients": [
        1.0
      ],
      "id": "P1_upstream_lobe",
      "widths_fraction": [
        0.6,
        0.8,
        0.8
      ]
    },
    {
      "centers_fraction": [
        [
          0.75,
          0.5,
          0.5
        ]
      ],
      "coefficients": [
        1.0
      ],
      "id": "P2_downstream_lobe",
      "widths_fraction": [
        0.6,
        0.8,
        0.8
      ]
    },
    {
      "centers_fraction": [
        [
          0.5,
          0.5,
          0.75
        ],
        [
          0.5,
          0.5,
          0.25
        ]
      ],
      "coefficients": [
        1.0,
        -1.0
      ],
      "id": "P3_vertical_signed_pair",
      "widths_fraction": [
        0.8,
        0.8,
        0.6
      ]
    }
  ],
  "recommendation_before_diagnostics": "P1 as simplest single localized normal mode, conditional on future approved artifact/float32/geometry gates; no change after correlations"
}
```

中心/幅は canonical の unconstrained active-node coordinate bbox の割合。診断を見た後に位置・幅・符号を変えない。P1 を低実装量の第一候補とする原理は単一の局在モードの簡単さであり、force または cosine の最良値による選択ではない。P2 はstreamwise位置を変える比較、P3 は上/下の signed低次モードの比較。ユーザーの採否は別判断。

`a=max(1-r²,0)³` は境界で C²、各 width は bbox span の 0.6〜0.8倍。解析ローブは低周波だが mask/taper と canonical gradient の非滑らかさを乗じた後の場が同じ smoothness を持つとは限らない。最終 geometry/Float32 gate は将来の契約。

負値が solid、n=+∇phi/|∇phi|。外向き変位 u=a*n に対し δphi≈−a|∇phi|。normalized scalar coefficient が max=1 であっても physical normal displacement の max/RMS は ε とは異なる。以下は active nodes だけにおける解析値の統計・離散内積であり、新しい full-grid Float32 direction を生成/保存しない。

## 実行と入力の確認

canonical NPZ SHA-256: `7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`。Float32 Fortran raw phi SHA-256: `e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431`。両者は現 HEAD の fd08_contract 定数と照合済み。異なる hash の表記を混同しない。
shape=[121, 65, 49]、spacing=0.025 m、active nodes=107415、gradient magnitude min/max=0/1.11904988。
旧 Stage 1 メモの4718 nodeは当時の設計入力の記述であり、本作業では上書きしない。今回のcanonical active maskは107415 node、再生成した保護済みD0/D1/D2の非ゼロsupportは各8339 node。active mask、taper後の非ゼロsupport、特定εのFloat32 signed状態で実際に変わるnode数は異なる集合。4718との同一性を仮定せず、signed stateを作らないため実現changed-node数は未測定。今後の生成契約ではsupportと実現変化集合を区別して固定する必要がある。

```sh
PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python scripts/design_fd08_v2_stage1p5_directions.py
```

NumPy 2.5.2。protected direction generator source SHA-256: `ac49c4e3a6f3b14a6c254c6cbdf7dcda26da7e3c62d40d7c735ae473cbc52837`。
診断 JSON SHA-256: `c2a216ac78b4df67ec644e5da2b013b508dbd5dade8cf691ff6546e338a51b8e`。初回計算前の freeze 文書 SHA-256: `57d54c0fb4deb2bdafc9b926af06434896a7f3165ae45fee7d134124cbed024c`。定義の hash と初回文書 hash は内容が異なるため別値。

既存 D0/D1/D2 は許可された正準 regenerate のみ。各 hash と support/RMS/max は JSON に記録し、新 direction の hash は null。R5 の force/result/analysis/dataset direction raw は読み込んでいない。source bytes と canonical state が同じ条件での再生成であり、R5 raw との照合を行ったという主張ではない。

## 固定 preset の診断値

| option | center(s) m | width m | phi max | active RMS | full-grid RMS | support | physical normal max/ε | physical normal RMS(active)/ε |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P1_upstream_lobe | [[-0.1125, 0.0, 5.55111512313e-17]] | [1.47, 0.68, 0.6] | 1 | 0.10074818 | 0.053189054 | 8339 | 1.0017375 | 0.10900815 |
| P2_downstream_lobe | [[1.1125, 0.0, 5.55111512313e-17]] | [1.47, 0.68, 0.6] | 1 | 0.050443638 | 0.026631245 | 5562 | 1.0324651 | 0.05501974 |
| P3_vertical_signed_pair | [[0.5, 0.0, 0.1875], [0.5, 0.0, -0.1875]] | [1.96, 0.68, 0.45] | 1 | 0.076598986 | 0.040439715 | 8324 | 0.99999999 | 0.083482041 |

上表の physical displacement は `−δphi/|∇phi|` の一次近似であり、surface relocation 測定値ではない。例えば nominal ε を掛ければ同じ単位の予測変位になるが、signed phi を作って確認した値ではない。zero-gradient nodes は raw=0、physical係数=0。L2内積は node の離散内積、volume weighted は h³を掛けた離散体積積分。全格子 RMS は明示的 full-grid 配列を作らずゼロ延長のノルムと総node数から計算。

| option | protected | L2 inner product | cosine | support intersection/union | Jaccard |
| --- | --- | ---: | ---: | --- | ---: |
| P1_upstream_lobe | D0_interface_offset | -1971.63062 | -0.869314487 | 8339/8339 | 1 |
| P1_upstream_lobe | D1_filtered_seed11 | -15.7370191 | -0.0239745666 | 8339/8339 | 1 |
| P1_upstream_lobe | D2_filtered_seed2026 | -1.71332041 | -0.00260716546 | 8339/8339 | 1 |
| P2_downstream_lobe | D0_interface_offset | -627.614225 | -0.552681519 | 5562/8339 | 0.666986449 |
| P2_downstream_lobe | D1_filtered_seed11 | 19.7330125 | 0.0600416317 | 5562/8339 | 0.666986449 |
| P2_downstream_lobe | D2_filtered_seed2026 | 27.9372009 | 0.0849070395 | 5562/8339 | 0.666986449 |
| P3_vertical_signed_pair | D0_interface_offset | 128.463047 | 0.0744978544 | 8324/8339 | 0.998201223 |
| P3_vertical_signed_pair | D1_filtered_seed11 | 50.2278856 | 0.100643881 | 8324/8339 | 0.998201223 |
| P3_vertical_signed_pair | D2_filtered_seed2026 | 18.2785916 | 0.0365836404 | 8324/8339 | 0.998201223 |

この幾何学的 cosine/support は scalar phi の方向類似性であり、force gradient の類似性、solver response magnitude、qualification を表さない。符号反転でも同じ一次空間なので重複判断は abs(cosine) を見る。診断の最大cosineに合わせてpresetを変更・再選択しない。

## 将来承認時だけ実施する artifact / Float32 契約

1. direction inventory と generator の数値的 arithmetic、中心/幅、narrow-band taper、gradient stencil、zero-gradient の扱いを事前登録する。既存 D0/D1/D2 と source/array hash は保護し、新ローブを採用するなら別契約にする。
2. 初めて full-grid max=1 direction を作る際は little-endian float32 C順、support 外0、max after cast、finiteを検査。SHA-256 は既存 direction_sha256 と同じ C順 bytes に対して生成する。本作業ではその配列・hashを生成しない。
3. nominal ε ごとに将来 `phi±=float32(phi0±ε*d)` を構成し、両符号の changed-node数/max/active RMS/full-grid RMS、support外byte同一、masks、marginを監査する。float32 roundaway は失敗として残し、力の結果でεを後から変更しない。
4. effective centered direction `(phi+−phi−)/(2ε)` の requested とのcosine・relative L2、現行 limit 0.05を使うか、新contractの採否を事前に決める。実現 normal displacement はscalar SDF増分と別に零面/gradientを用いて測る。

実在 source locations（現 HEAD で再検索）:

- `src/cfd_sdf/gradients/directional_fd.py:43`
- `src/cfd_sdf/gradients/directional_fd.py:47`
- `src/cfd_sdf/gradients/directional_fd.py:51`
- `src/cfd_sdf/gradients/directional_fd.py:96`
- `src/cfd_sdf/gradients/directional_fd.py:115`
- `src/cfd_sdf/gradients/directional_fd.py:243`
- `src/cfd_sdf/fd08_contract.py:21`
- `src/cfd_sdf/fd08_contract.py:22`
- `src/cfd_sdf/fd08_calibration.py:461`
- `src/cfd_sdf/fd08_calibration.py:31`

## 判断と未実施事項

P1 は単一局在ローブの実装量が小さいための条件付き第一候補。P2 は局在位置の別案、P3 は2つのsigned低次モードの別案。相関が高いものでもここで調整しない。どの方向を加えるか/加えないか、#23のcoverage、必要state数・予算・ladder・B-3〜B-7 はユーザー判断。新方向がsmoothだから gが安定・応答が十分大きいとは言えない。

新方向、signed states、R6 criteria/dataset、formal、force応答、Float32 perturbation audit は生成/実行していない。solver/Kaggleを実行せず、R5/Stage1 evidenceとphase_planを変更せず停止。JSONは12有効数字、sort_keys=True、allow_nan=False。hashは同一環境再現用、機種間では参考値。
