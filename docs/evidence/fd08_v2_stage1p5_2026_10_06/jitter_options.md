# J-1 jitter（3択・未承認）

[既存分析](../fd08_v2_stage1_2026_10_06/design_note_new_direction.md#jitter-2-state-の意味推定できる量と自由度)の定義・自由度・CIを再利用する。追加noise調査は行わない。

| 選択 | 4方向の追加state | 得られる情報 | direction×responseのJ数・自由度 | 予算・依存 |
| --- | ---: | --- | --- | --- |
| 2 state/方向 | 8 | 1 shifted magnitudeの±pair。J=Sobs-Spredが1つ | J=1。平均未知ならvariance推定不可(df0)。ゼロ平均既知の強い仮定ならdf1でCI極大 | 6点calibration49→57。固定fit/cov/modelから予測。σ0を更新しない |
| 4 state/方向 | 16 | εmid(1−.001)とεmid(1+.001)の各±pair。2つのJ | J=2。iid・同分散・平均未知ならdf1だが同じfit/covを共有し相関がある | 49→65。shiftedmagnitudes/byte重複と予測不確かさを事前固定 |
| jitterなし | 0 | micro-jitter sensitivityは測らない。formal interior3点を別に検証 | Jなし、noise variance推定なし | 49。σ0/ρは事前仮定のまま。formalをnoise検証と呼ばない |

**推奨jitterなし**。決定論的ε変動とbiasの分離ができない少数Jでσ0を更新する根拠はない。内挿検証はB-7で実施する案とし、jitterをnoise estimatorとして予算に義務付けない。micro-jitter自体が研究目的なら2/4state案を別目的で選べる。

exact repeatは同一byte入力でbit同一、既存floorのguardは1e-8 N級であり、T2の3µNは実測σではない。微小ε変更、grid-phase変更、time-window分割、model残差は異なる変動源で同じσ0に混ぜない。Jにはmodel bias、fit uncertainty、deterministic ε variationが混ざる。2force signはiid反復2つではなく、centered S=(F+−F−)/2の1観測である。ΣJ_i²や方向間poolを無条件のnoise測定にしない。

4方向×2responseの8Jをpoolするχ² CIは、独立・同分散・正規等の仮定が必要。共通未知平均ならdf7、平均ゼロ既知ならdf8。drag/downforce相関、方向間heterogeneity、共有fitの予測covを無視できない。既存メモのCIはそれらの**条件付き**説明値であり、今回測定されたnoiseではない。

jitter別round案では、もしσ0をそこから決めたいなら estimator/bias/CI/runtimeをR6前に固定して別roundを先に完了する必要がある。R6を先に見てσ0を更新・再判定することはできない。jitterをreport-onlyにするならR6後でもよいがR6のnoise根拠にはならない。
