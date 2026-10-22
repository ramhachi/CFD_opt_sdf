# GEOM-03登録結果 — GEOM03_NO_GO

**全534記録を独立検証して完了、反例2件。R3複合ルールは採用しない。**
[登録仕様](../../geom03_registration_2026_10_23.md)に従って一度だけ実行し、
[独立チェッカーの終端結果](run/results.json)をそのまま受領した。
結果SHA-256は`bb65314b8382ac3743f7632739552da18b4ca0e76ff0d61e425b60f7bae6d8bd`。
本稿はその人間向け記録であり、再判定・再計測・変更した基準による救済ではない。

## 実行と再現性

- ソース`ce95612fec50965b97a30cba52338f066b4629ce`をpush後、
  freeze/releaseを`29bcfc4a3efe30a75344ccf1c4eeaab4aef8576c`でpushしてから開始。
- 2026-10-23 03:46:18–03:51:19 JST、累積301.389954秒。
  attempt=1、resume=0、観測最大child RSS=950419456bytes（906.390625MiB）。
  累積2h・観測3GiB・200base以下・単一数値child/threads1の登録上限内。
  RSSはサンプリングした値であり、サンプル間のspikeを否定するOS保証ではない。
- 180base+354K6=534記録の登録された再構成・照合を完了、`complete=true`、`incomplete_reasons=[]`。
  E2はhelper-onlyの記述的対照で、その数値は合否の一致条件にしないという事前仕様も維持した。
  既知99native・再構成した旧250combo・新28comboの分離確認を新判定前に実施。
  source/runtime/grid/mask/parent/phi/NPZのbinding、halo、feature存在、component overlapを検証した。
- 開発25件PASS、全回帰3117PASS/73SKIP、compileall・明示的script compilation・差分checkは
  [ソフトウェア検証記録](validation.json)。これらと実験のNO_GOは別の判定。

## 登録基準ごとの結果

| 基準 | 登録された期待を満たした件数・観測 | 結果 |
|---|---|---|
| K1 | analytic24+新combo28、52/52 composite pass | PASS |
| K2 | thin feature36件中35件non-pass、W40_th1_q0がpass | FAIL |
| K3 | thick/tolerated control28/28 pass | PASS |
| K4 | margin/topology/transition20件中19件適合、T1_th0_q0がfail | FAIL |
| K5 | 40slab、両曲線単調。R0 lo=1.25h/hi=1.5h、composite lo=1.5h/hi=1.75h | PASS |
| K6 | 354/354、positive scalingでR0/R3/P2・sign body・composite不変 | PASS |
| H0 | 既知parentのphi hashとR0 solid0.09762812094883319m/passを再現 | PASS |

K5のqはwidth={1,1.25,1.5,1.75,2}hに対し、
R0={0,.25,.5,.75,1}、composite={0,0,0,1,1}。
8配置の離散crossing bracketであり、連続肉厚・確率区間・格子収束の推定ではない。

## 二つの反例

[元の行を抜粋したJSON](run/counterexamples.json)。両方ともordinary halo、P1、P2がpassし、
coarse/refined solidは1component。実装間の不一致はなかった。

| ID | 事前期待 | 実際のR3/複合判定 | 反例の内容 |
|---|---|---|---|
| W40_th1_q0 | K2 non-pass | solid欠損0.023385358667337135m=0.935414h、void0.00625m、composite pass | 40°wedgeを45°回転、Q2の第1配置。thin-tip領域に12負ノードを確認したうえで誤受理。P1/P2に禁止された接続変化はなく、この複合化では幅の誤受理を防げない |
| T1_th0_q0 | K4 passまたはunmeasured | solid欠損inf、void0、composite fail | 厚さ1.625hのtransition control、0°/同じQ配置。eroded solidが空となる登録上のinf約定によって棄却され、許容した遷移ラベルを満たさない |

欠損の大きさ、接続、連続的な最小幅は同じ概念ではない。
この結果は、今回登録したopening-defect+margin+node-topologyの規則が、
今回のK2/K4要求を同時には満たさないことを示す。
製造上の欠陥、連続トポロジーやCFDの不合格を直接測ったものではない。

新28comboは全件composite passだった。記述的なR0列は1pass/27fail。
探索に似た入力での受理改善は見られるが、登録した反例2件を除外して合格へ読み替えない。
新しい配列・乱数系列であり、形状族・規則の発想は既知WIDTH-RULEに基づくという開示も維持する。

## 保存した証拠と停止

- [results](run/results.json)、[全行](run/rows.jsonl)、[測定前manifest](run/premeasurement_inputs.json)、
  [終端state](run/state.json)、[受領・完全性記録](result_receipt.json)。
- [全入力アーカイブ](run/run.tar.xz)：534個の元NPZと上記4ファイル、計538member。
  原入力321545834bytesを75,801,524bytesの標準tar.xzへ保存。
  SHA-256 `efc99fa2ad610adfe845264b8765ef3fc4c108e3c65f40e97aa3611c8b27c299`。
  全memberを展開せず読み戻し、元byte streamのhash一致を確認した。
  tarのuid/gid/mtimeのみ正規化し、NPZ内部と各元ファイルのbytesは変更していない。
- 元cacheは`work/geom03_2026_10_23/`にも保持。アーカイブは任意の空の監査用directoryへ
  `tar -xJf run.tar.xz -C <audit-directory>`で展開できる。これは既知データの閲覧用であり、
  終端試行に`--run`/`--resume`を再実行しない。

登録通り、半径・tau・refinement・padding・label・case・seedを調整せず停止する。
次は[SCREENのR0-clean fixed-pool/parent経路](../../screen_xv_preparation_2026_10_23.md)を具体化する。
R0の保守性とselection biasを開示し、finite pool/geometry filterをforce閲覧前に登録する。
本NO_GOを使って新しいR3補正を自動起動しない。
FID01_GOはその既存のRe80比較範囲で維持し、全qualification flagとshape_update_allowed=falseを保持する。
