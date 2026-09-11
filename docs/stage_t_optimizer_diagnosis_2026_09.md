# Stage T optimizer diagnosis — 2026-09-12

## 判定

native ISQP経路の不動は、**3つの独立した欠陥**による。いずれもOpenFOAM v2512の
ソース（`objectiveTopOVolume.C`、`ISQP.C`、`topODesignVariables.C`、
`fieldRegularisation.C`、`tanhInterpolation.C`）と実測で確認した。

最適化はPythonへ移し、OpenFOAMはprimal/adjoint評価器に限定することを推奨する。

## 欠陥(a)：体積制約が原理的に充足不能

`topOVolume`の目的関数は次である。

```text
J = (1 - <beta>_V - percentage) / percentage
constraint: weight * J <= 0
```

`<beta>_V`は**メッシュ全体**での平均であり、`percentage`は**流体率の上限**である。
したがって`percentage 0.462`、`weight 1`は「流体が全メッシュの46.2%以下」、すなわち
「固体が53.8%以上」を要求する。

しかし`fixedZeroPorousZones`の6つのbuffer zoneは8192 cell中5283 cell（64.5%）を占め、
強制的に流体である。設計可能な2909 cellが全て固体になっても、固体率は最大35.5%にしかならない。

```text
min J = (1 - 0.355 - 0.462) / 0.462 = +0.396 > 0
```

**この制約は達成不能である。** 観測された`J = 1.1497`（`<beta> = 0.007`）は
上式と厳密に一致し、診断を裏付ける。

## 欠陥(b)：固着した乗数は実行不能性の署名

`includeExtraVars true`によりISQPはelastic変数`y`を導入し、KKT条件
`c - lambda - z = 0`、`z >= 0`（`ISQP.C:873`）を持つ。したがって常に`lambda <= c`であり、
`lambda = c`はQPが実行不能でelastic項が違反を吸収したことを意味する。ログの
`Constraint penalization variables (y) 1(1.12193)`がこれを示す。

制約が設計場を見ていないのではない。2909 cell全てで勾配は非ゼロである。単に達成できない。

cycle 1の感度実測：

| 項 | cellあたり平均 \|.\| |
| --- | --- |
| drag | 0.75（最大8.8） |
| downforce | 0.27 |
| volume | 8.5e-5（x lambda = 2 で1.7e-4） |

比は約4000:1であり、体積項はQP内で不可視である。2008/2909 cellで正のdrag項が
材料を排出する方向に働く。

## 欠陥(c)：`function linear`が射影を無効化する

`linear`は恒等写像（`res = arg`）であり、Heaviside射影が効かない。したがって
0.5を跨ぐ交差が構造的に生じない。tutorialは`tanh; b 20`を使う。

linear補間下では0.1–0.3のgray cellが`beta = 250–750`となり、流れに対しては既に固体である。
これが観測された「わずかな密度変化が大きな力変化を生む」硬さの正体である。

原因ではなかったもの：`maxInitChange`、`meanRadiusMult`、`c`そのもの（(b)経由でのみ影響）。
初期点の実行可能性は、上限が達成不能である限り無関係である。

## 修復後のnative実行

downforce最大化、設計領域の30%を固体上限とする`percentage 0.893469, weight -1`、
`tanh`、`includeExtraVars`無効。

| run | seed / 変更 | cycles | beta>0.5 cells | 設計成分faces | watertight | volume | downforce |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 退化（run40 / maxdf20） | plate 0.5, linear | 27–40 | 0 | 0 | no | — | 固着 |
| R1 | plate 0.5, b 20 | 20 | 118 | 312 | yes | 0.063 | 0.108 -> 0.317 -> 0.110 |
| R4 | plate 1.0 | 19 | 264 | 468 | yes | 0.164 | 0.234 -> 0.178 |
| R7 | R4, b 8 | 18 | 563（設計域の19%） | 1072 | c8 yes / c18 no | 0.35 -> 0.22 | 0.277 -> **1.029** -> 0.60 |

修復すればnative経路でも実形状が生成される。ただしどの実行も収束しない。固定`eta`と
b=20射影に対するL-BFGSでは、予測方向微分（-106）が実現値と一致しない。Armijo line searchを
加えたR6は毎サイクル「line search reached max iterations」となり、**ISQPの探索方向が射影後の
問題に対して降下方向になっていない**ことを示す。勾配自体の誤差ではない
（`docs/fixed_grid_backend_decision.md`のFD検査：drag 0.045%、downforce 7.5%）。

## Stage Sへの含意

5120面・6成分のSTLは、iso-surface writerが常に計算領域境界を出力するためである。
**Stage Sは範囲がゼロの成分を除去しなければならない。** 除去しない限り、実設計成分が
存在しても境界パッチに埋もれる。

## 推奨

1. 最適化はPythonへ恒久的に移す。同じ勾配に対するOCは12反復で単調前進した。native ISQPは
   3箇所の修正を経てなお振動する。
2. OpenFOAM templateはprimal/adjoint評価器として維持する。`vol`と制約としての`downforce`の
   adjoint solverを削除し、`drag`と`downforce`を独立したadjoint solverとして残す。
   射影をPythonが持つなら`function linear`のままでよい。
3. 定式化は体積上限付きdownforce最大化を先に行う。`L/D >= 3`（`drag - downforce/3 <= 0`）は
   設計が存在してから加える。現在のplateはL/D 0.19–0.37であり、Re 100では実行不能で、
   Python側で欠陥(a)と同じ状況を再現してしまう。

実験一式は`work/stage_t_formulation/`（R1–R7、`mkcases.py`、`launch.sh`）にある。
