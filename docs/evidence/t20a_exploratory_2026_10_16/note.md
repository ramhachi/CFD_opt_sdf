# T2-0a（#57）探索結果: 2D 地面効果翼断面 RANS（Kaggle CPU、OpenFOAM v2512）

区分: PROC-01 `EXPLORATORY_COMMITTED`（判定・flag・閾値には使わない。引用するには登録した再実行が必要）。
対象: Zerihan & Zhang の単一翼（Tyrrell 026 主翼、XFOIL で後縁を尖らせた Genua 2009 の座標）、Re_c = 4.6×10⁵、移動地面、2D（1 セル押し出し）。

## 経過（4 回の Kaggle CPU 実行）
- attempt 1: OpenFOAM の lock が jammy 用だけで、Kaggle の noble イメージに合わず停止（ケース 0）。lock を OS で選ぶ形に修正。
- attempt 2: インストール成功、SA/SST の smoke は動作、kOmegaSSTLM が発散。checkMesh が不合格（未使用点 1024、歪んだセル）。
- mesh-only 検査: メッシュ生成器を修正後、25 通り（5 仕様 × 5 車高）すべて checkMesh で Mesh OK。numpy の代替検査も一致。
- attempt 3: 13 ケースすべて完了（`attempt3_r3/`、表は `attempt3_r3/analysis.md`）。

## 結果（Cl は downforce 係数、反復末尾 20 % の平均）
| モデル | h/c 0.224 の Cl（実験 1.286） | h/c 0.09 の Cl（実験 1.371） | 最大 Cl の車高 | 1 ケースの時間 |
| --- | --- | --- | --- | --- |
| SA 壁関数（med30、約 1.5 万セル） | 1.345（+4.6 %） | 1.312（−4.3 %） | 0.134（実験・Genua と一致） | 約 6 分 |
| k-ω SST 壁関数（med30） | 1.405（+9.3 %） | 1.221（−11.0 %） | 0.134 | 約 6 分 |
| SST → kOmegaSSTLM（wr2、約 13 万セル） | 1.332（+3.6 %） | 1.386（+1.1 %） | 0.134 | 約 2.4 時間 |

- Genua の OpenFOAM Med30（SA）に対して −5〜+7 %。Genua の SST は h/c 0.09 で +30 % だったが、本計算は −11 %。
- drag は Genua より 18–35 % 小さい。drag の実験値との比較はしていない。
- LM は 2000 反復で力が平坦に達しておらず（plateau = false）、値は暫定。どのケースも残差の目標には未達で、力の平坦性で判断している。

## 言えること・言えないこと
- 言える: Kaggle CPU の 2D RANS で、この単一翼の downforce の実験値を、5 つの車高のうち比較できた 2 点で 5 % 程度（SA）以内に再現し、最大 downforce の車高を正しく置いた。1 ケース数分で回せる。
- 言えない: 評価器の適格性、メッシュ収束、乱流モデルの不確かさの定量、3D（翼端・エンドプレート）や FSAE 車両での妥当性。比較した実験は有限幅の翼の値で、2D 計算との比較には限界がある。実験の Cl(h/c) 曲線は 3 点しか使っていない（図からの数値化は未実施）。

## 次（T2-0b、登録段階の候補）
実験の Cl(h/c) と Cp の数値化、メッシュ感度（coa30/med30/fine30）、モデル間のばらつき、LM の収束、迎角の確認、SA adjoint（adjointOptimisationFoam）の実行可否。
