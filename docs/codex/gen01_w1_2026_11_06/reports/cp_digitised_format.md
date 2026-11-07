# TR-00：ユーザーが用意する Cp / Cl(h) の形式

`scripts/topo2d00/digitize_cp.py` は、ユーザーが用意した CSV を読み、中央断面の
**圧力による downforce 係数**と、2 つの独立デジタイズの差に基づく読み取りの感度を
出します。図のデジタイズは行いません。実験の E2 CSV は本 WP には含めていません。
この道具だけでは TR-00 の適格性や TOPO-2D-00 の結果は決まりません。

参照契約は [登録草稿 §§2–4](../../../topo2d00_registration_2026_11_01.md) と、
ユーザーが指定した別 worktree の登録 Amendment 1 §6／Amendment 3 §6、
Table 15 の出所・測定量・限界は
[EVAL-VALID-01](../../../eval_valid01_reference_audit_2026_10_22.md) に従います。
既存 T2-0 の参照・判定・閾値は変更しません。

## 1. 座標、符号、正規化

共通の流れ方向を +X、鉛直上向きを +z とし、downforce = −Fz を正に取ります。
`upper` は**物理的に上側（大きい z）の表面**、`lower` は下側です。圧力面・吸込面の
呼び名とは区別してください。反転翼の下側の吸込みは正の downforce を生みます。
通常の `Cp = (p − p∞)/(0.5 ρ U∞²)` を使い、全要素に同じ基準動圧を用います。

CSV の `x/c` は、**流れと平行な global X 座標**を、その要素の入力で指定する
`abscissa_chord_m` で割った値です。各要素の原点は任意に平行移動して構いません。
`c` が c1 = 0.2234 m なら global X/c1 をそのまま渡します。論文の c = 0.380 m を
使う図なら `abscissa_chord_m: 0.38` と宣言します。列名はどちらも `x/c` です。

全出力は共通の **c1 = 0.2234 m** で正規化します。台形積分は

```text
Cl_down,p = (abscissa_chord_m / 0.2234)
            × [trapz(Cp_upper, x/c) − trapz(Cp_lower, x/c)]
```

です。これは鉛直方向の圧力線積分です。両面の間の点数・内部の x 位置は異なっていて
構いません。各面をそれぞれ積分します。上下面の global X の始点・終点が一致し、
端部が鉛直の線分で閉じる場合、その端部は鉛直力に寄与しません。

**傾いた要素の local chord の x/c は、そのまま入力できません。** local x の積分は
弦に垂直な成分であり、鉛直力へ回転するには圧力の弦方向成分も必要です。表面の y
座標なしに `cos(angle)` を掛けるだけでは一般に正しくありません。図の座標の意味を
一次資料で確認し、必要なら実際の表面幾何から global X に変換して CSV を作って
ください。閉じる端部が傾いていて上下面の投影端点が異なる場合も、この 2 列形式で
黙って閉じず、不足する圧力・幾何を別途解決します。ツールは不一致を拒否します。

E1 の Cl を c1、E2 の Cl を 0.380 m のまま引くと、力の差にはなりません。
例えば、論文の `Cl_c` は `Cl_c1 = Cl_c × 0.380 / 0.2234` に直してから比較します。
出力の要素別 Cl も合計 Cl も、同じ c1 を使います。粘性力・drag はこの CSV からは
求まりません。RANS と比較するときも圧力成分を保持するか、総力との差を明示します。
出力と各参照の `observable` は `pressure_cl` です。各参照には
`h_over_c1 = height_m / 0.2234` と `h_over_c = height_m / 0.380` を両方出します。
100 mm なら約 0.44763 と 0.26316 です。これは入力した物理高さから計算した比で、
原表・図の丸めた 0.448／0.263 をより精密な実験値へ読み替えるものではありません。
原資料の比は `source.source_h_over_c1` などの出典メタデータに残してください。

## 2. Cp CSV と 2 つの読み取り

CSV は UTF-8（BOM 付きも可）、ヘッダは正確に次の 2 列です。

```csv
x/c,Cp
0.0,0.2
0.1,0.4
0.2,0.6
0.3,0.7
0.4,0.8
0.5,0.8
0.6,0.7
0.7,0.6
0.8,0.5
0.9,0.4
1.0,0.2
```

上記の数値は**合成の形式例**で、実験値ではありません。各要素について、A の上面・
下面、B の上面・下面の計 4 CSV を用意します。A/B は 2 人、または 2 つのツールで
独立にデジタイズしてください。同じ点列のコピーは独立読み取りになりません。
ツールは各要素の A/B の対応する面（上面同士、下面同士）を、**読み取って昇順に揃えた
数値点列**で比較します。同じ数値内容なら、別名、BOM、LF／CRLF、`0.1`／`0.10`、
`0`／`-0`、昇順／降順の違いがあっても拒否します。値を丸める許容差や再標本化は使いません。
CSV の bytes の SHA-256 は provenance として別に保存します。
Cl の積分値が一致すること自体は拒否理由ではありません。異なる点列が同じ積分値を
持つ場合は受理します。人・ツールの識別子と作業メモも要求しますが、異なる点列や SHA
だけで方法上の独立性を証明するものではありません。独立に読み取った点列を用意してください。

- x は有限値で厳密な昇順または降順。降順は内部で反転します。重複・往復順・NaN・Inf・
  **10 点未満の面**・不正な列数は拒否します。Cp 軸の上下表示が反転していても Cp の符号は
  元の値を保ちます。
- 各要素の**各読み取り**の積分 Cl は downforce 正（厳密に 0 より大きい）である必要が
  あります。0 または負なら、上下面・軸の符号を確認する理由付きエラーにします。
  他の要素や読み取りとの合計が正でも受け付けません。
- `x_extent` に、その表面全体の投影始点・終点を明示します。全 4 CSV の端点がこれと
  一致する必要があります（テキスト表現の許容差は無次元 x/c で 1e−10）。点列の範囲を
  黙って 0–1 に伸ばしたり、上下面の共通区間だけに切ったりしません。
- `coverage_note` に完全な輪郭を覆う根拠を書きます。前縁の吸込みピークや後縁を
  欠いた点列を「全体」と宣言しないでください。補間誤差・疎な圧力孔・未観測ピークの
  誤差は、2 デジタイズの一致だけでは評価できません。
- `source` に論文・図番号・パネル・高さ・迎角・遷移条件・正規化の根拠を残します。
  同じ `Cp` という名前だけで、異なる動圧補正・balance CL・別の高さの系列を混ぜないで
  ください。`transition` が不明なら `unknown` と記録します。

## 3. マニフェスト

下記は**テンプレート**です。`<...>` はユーザーが一次資料と実データから埋める部分で、
数値欄の文字列のままではツールは拒否します。Cp の実験値や未確認の幾何を埋めた
マニフェストは本 WP では生成しません。CSV の相対パスはマニフェストのあるフォルダ
から解決します。絶対パスも使えます。

```json
{
  "kind": "topo2d00_cp_manifest_v1",
  "reference_chord_m": 0.2234,
  "configs": [
    {
      "config": "E1_sharp",
      "method": "tabulated_cl",
      "height_m": 0.1,
      "height_mapping_note": "Table 15 の h/c1=0.448 は h=100 mm 比較で使う丸めた比。source の厳密な h は未同定。",
      "source": {
        "citation": "Zerihan (2001), An investigation into the aerodynamics of wings in ground effect",
        "url": "<一次資料の URL>",
        "location": "Table 15, printed p179 / PDF p197; EVAL-VALID-01 audit",
        "observable": "centre_section_pressure_integrated",
        "transition": "unknown",
        "pdf_sha256": "93a3dd52252c3f5152a2cfba1f8ce7496c98592b4648da2172d9b44ab3c8f6ab",
        "source_h_over_c1": 0.448
      },
      "coefficient_chord_m": 0.2234,
      "coefficient_sign": "downforce=-Fz",
      "Cl": 1.009,
      "reading_sensitivity_abs": 0.0,
      "reading_sensitivity_note": "Printed digits の正確な転記。0 は転記感度だけを表す。表の丸め誤差や総実験誤差を0としたものではない。"
    },
    {
      "config": "E2_sharp",
      "method": "cp",
      "height_m": 0.1,
      "height_mapping_note": "<h/c=0.263 の系列と h=100 mm の対応、丸めと幾何 datum の根拠>",
      "source": {
        "citation": "Zhang & Zerihan (2003), AIAA J. 41(6):1007-1016; or Zerihan (2001)",
        "url": "<実際に読んだ一次資料の URL>",
        "location": "<centre-section Cp の図番号・パネル・datum flap・h/c=0.263>",
        "observable": "centre_section_pressure_integrated",
        "transition": "free",
        "abscissa_provenance": "<global streamwise X/c である根拠、必要なら幾何による変換の記録>"
      },
      "abscissa_direction": "global_streamwise",
      "independence_note": "<A/B が互いの点列を使わずに読み取った手順・日付>",
      "digitizers": [
        {"id": "A", "operator": "<reader A>", "tool": "<tool/version>"},
        {"id": "B", "operator": "<reader B>", "tool": "<tool/version>"}
      ],
      "elements": [
        {
          "id": "main",
          "abscissa_chord_m": 0.38,
          "x_extent": ["<main global X_min/c>", "<main global X_max/c>"],
          "coverage_note": "<全輪郭の圧力を覆い、投影端点が閉じる根拠>",
          "surfaces": {
            "A": {"upper": "main_A_upper.csv", "lower": "main_A_lower.csv"},
            "B": {"upper": "main_B_upper.csv", "lower": "main_B_lower.csv"}
          }
        },
        {
          "id": "flap",
          "abscissa_chord_m": 0.38,
          "x_extent": ["<flap global X_min/c>", "<flap global X_max/c>"],
          "coverage_note": "<全輪郭の圧力を覆い、投影端点が閉じる根拠>",
          "surfaces": {
            "A": {"upper": "flap_A_upper.csv", "lower": "flap_A_lower.csv"},
            "B": {"upper": "flap_B_upper.csv", "lower": "flap_B_lower.csv"}
          }
        }
      ]
    }
  ],
  "increments": [{"from": "E1_sharp", "to": "E2_sharp"}]
}
```

Table 15 の 1.009 と PDF hash は既存の一次資料監査で確認された値です。再デジタイズで
作った値ではありません。`reading_sensitivity_abs: 0` は「記載された数字をそのまま
転記する」場合の例で、数値の公表桁・圧力積分・実験の誤差を解決しません。
別途根拠がある読み取り幅を使う場合は、その値と根拠を明示してください。
EVAL-VALID-01 が未確定とした各点の trip・総不確かさは未確定のままです。

## 4. Cl(h) 曲線を使う場合

Cp の代わりに `method: "cl_curve"` を指定できます。CSV は正確に次のヘッダにし、
2 つの独立読み取りを用意します。

```csv
h/c,Cl
0.3,1.2
0.5,1.0
```

これも**合成の形式例**です。config の共通欄（`config`, `method`, `height_m`,
`height_mapping_note`, `source`）に、次を加えます。`digitizers` と `independence_note`
は Cp と同じです。Cp 専用の `elements` や `abscissa_direction` は付けません。

```json
{
  "coefficient_chord_m": 0.2234,
  "coefficient_sign": "downforce=-Fz",
  "height_chord_m": 0.2234,
  "digitizers": [
    {"id": "A", "operator": "<reader A>", "tool": "<tool/version>"},
    {"id": "B", "operator": "<reader B>", "tool": "<tool/version>"}
  ],
  "independence_note": "<独立に読んだ根拠>",
  "curves": {"A": "single_A_cl_h.csv", "B": "single_B_cl_h.csv"}
}
```

`height_m/height_chord_m` で求める目標 h/c へ各曲線を線形補間します。外挿は拒否します。
各曲線は 2 点以上で、A/B の昇順に揃えた数値内容は異なる必要があります。Cp と同じく、
表記や改行、方向だけを変えたコピーは拒否し、bytes の SHA-256 は別に保存します。10 点の最低数は
物理的な Cp 表面への規則であり、Cl(h) 曲線や Table 15 の scalar には適用しません。
係数は `coefficient_chord_m/0.2234` で共通 c1 に変換します。曲線が balance CL なら
使えません。単一要素の Table 15 の存在を理由に、別の図の測定量を断面 Cl と推定
しないでください。

## 5. 計算する不確かさと出力

要素 e の 2 読み取りを aₑ, bₑ とすると、中心は `(aₑ+bₑ)/2`、読み取り感度は
`uₑ = |aₑ−bₑ|` です。合計は各要素の中心の和、感度は `Σuₑ` とします。要素間の符号が
打ち消し合って読み取り感度を小さくしないため、合計 2 読み取りの差も別に保存します。
Table 15 では入力した読み取り感度、Cl(h) では 2 曲線の補間値の絶対差を使います。
TR-00 の増分 `Δ = Cl_E2−Cl_E1` の 5% 比較には、登録 Amendment 1 §6 に従って
**E2 の `u_to = Σuₑ`** を使います。`increments[].digitization_sensitivity_abs` と
`to_digitization_sensitivity_abs` はこの値です。E1 の感度は
`from_digitization_sensitivity_abs`、差全体の記述的な読み取り感度 `u_from+u_to` は
`reference_difference_reading_sensitivity_abs` に別々に残します。
`threshold_uncertainty_basis` は `to_reference_digitization_sensitivity_abs` です。
初回の実装では E1+E2 を 5% 比較へ足していましたが、この Amendment で上記に揃えました。

**これは統計的な信頼区間でも、真値を覆う保証のある上限でもありません。** 2 人／
ツールに共通する読み取りの偏りや、疎な圧力点・未観測ピーク・風洞・2D/3D・幾何・
遷移の差は残ります。全参照の `uncertainty.total_reference_abs` は `null`、
`covers_total_reference` は `false` にして、総不確かさを既知に見せません。
自由遷移の天秤誤差 ±0.003 や旧図読み取り幅 ±0.005 は流用しません。

増分について、登録の固定値 `u > 0.05 × |Δ|` かどうかを
`digitization_exceeds_5_percent` に出します。Δ = 0 の場合は比較値・比を `null` にして
`zero_increment: true` とします。この比較は読み取りだけについての記述で、
`TR00_PASS_SIGN` / `TR00_PASS_RATIO` は発行しません。RANS の実現値の区間、符号、
登録の [0.5, 2] の比の帯は analyzer が別に扱います。

出力 `kind: "topo2d00_pressure_reference_v1"` は、次を持ちます。

| key | 内容 |
| --- | --- |
| `normalization` | c1、符号、圧力断面 Cl、global streamwise と物理的上下面 |
| `manifest` | 読んだ JSON のパスと SHA-256 |
| `observable` | `pressure_cl`（normalization にある詳細な圧力断面の表記も保持） |
| `references` | config ごとの Cl、読み取り感度、方法、出所、`observable`、物理高さと両 h 比、未確定の総誤差 |
| `references[].elements` | Cp の要素ごとの Cl、2 積分、上下面 CSV のパス・SHA・点数 |
| `references[].digitizations` | Cl(h) の各補間値と CSV hash（Cp は各要素の下に保存） |
| `increments` | 明示的に要求した差、感度、5% の記述的比較 |
| `qualification_decided` | 常に false |

## 6. 実行と API

WP4 に渡す共有 `rans_results.json` では、各参照の `source.url` も必要です。
`<...>` のまま使わず、実際に確認した一次資料の URL を記入してください。集計器は
元 manifest の所在を基に各 CSV の絶対パスと SHA、読み取り者／ツール／面の方法を
出力し、WP4 の study freeze が実ファイルを入力一覧に束ねられる形式にします。
集計時にも元 manifest と CSV から参照を再計算して照合するため、古い参照 JSON や
手編集した hash で数値コピーの guard を迂回できません。
その freeze の作成・資格判定はこの積分器の機能には含みません。

```bash
.venv/bin/python scripts/topo2d00/digitize_cp.py /path/to/cp_manifest.json \
  --out /path/to/tr00_reference.json
.venv/bin/python -m pytest -q tests/topo2d00/test_digitize_cp.py
```

出力ファイルが既にあれば上書きせず停止します。修正したデータは新しい出力名で
再計算して provenance を残してください。欠けたファイル、未知のキー・方式、
Cp の局所弦座標、balance CL、非有限値、欠けた範囲、異なる高さの増分は拒否します。
コピーされた読み取り、10 点未満の Cp 面、0 または負の要素 Cl も拒否します。

Python API は `build_reference(manifest_path) -> dict`、
`read_csv(path, columns=("x/c", "Cp")) -> list[tuple[float, float]]` と、
`integrate_cp(upper_csv, lower_csv, *, abscissa_chord_m, reference_chord_m, x_extent)`
です。低水準の `integrate_cp` は任意の正の参照弦長を許しますが、TR-00 用の
`build_reference` は c1 = 0.2234 m を要求します。`integrate_cp` でも Cp 面は 10 点以上を
必要としますが、符号付きの数学的な積分値（0 や負も含む）を返します。翼の参照として
各要素を downforce 正に制限するのは `build_reference` です。API も CLI も図やネットワークに
アクセスしません。
