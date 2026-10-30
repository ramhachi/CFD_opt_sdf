# LOWDIM-02A 独立レビュー（実行前、read-only の 2 本）

## レビュー 1: lineage / 入力 / runner — blocker なし
job は XFID/W4 job と case 選択・メッセージ以外で同一、W4 round-2 fingerprint の job/src/T4 project・manifest と SHA 一致、flow_32 は登録 case。flow_32 baseline CSV の byte 同一 gate は妥当（同じ flow_32 SHA が W4 round-1/2 で再現、flow_24 では LOWDIM-01 と W4 round-2 が byte 同一）。inventory 再導出一致、sparse checkout は実 clone で全 pin 検証済み、時間予算は約 2500 s（timeout 10800 s）。
反映: (a) branch を push してから kernel を push する、(b) runner が最初の登録 state が唯一の baseline であることを実行時に確認（+test）、(c) 記述的 +2.5 mm の失敗でも DONE を書かず INCOMPLETE であること、(d) `--timeout 10800` が runner の `KERNEL_TIMEOUT_S` と同じ値であること、(e) `W4_CANONICAL_STATE_LABEL=v17` が表示だけであることを prerun_note に追記。

## レビュー 2: analyzer / 契約 / 閾値 / 文言 — 結果を誤らせる bug なし、事前に直すべき論理 2 件・文言 2 件
反映:
1. PASS は reverse control が分解能以上に downforce を**失う**（control < −res）ことを要求（旧: control < gain − res は、reverse も増える純偶関数応答に PASS を与えうる）。
2. SIGN_FLIP は「+1.25 mm が downforce を失った」とだけ述べ、原因（奇関数部の喪失 vs 曲率）は断定しない。奇関数部・偶関数部・`odd_part_resolved_positive` を報告。「flow_24 過適合として停止」を「Stage B はユーザー判断なしに登録しない」に変更。
3. `resolution_source`（nominal_floor / repeat_noise）、`marginal`（gain ≤ 3 × res の PASS）を報告。repeat が byte 同一なら flow_32 の noise 証拠はなく分解能は flow_24 名目 floor のままと明記。
4. INTERPRETATION は repeat の byte 同一性に条件づけ、「deterministic」の断定をやめた。gain = 奇 + 偶と明記。
5. geometry gate 5 項目の集合検査を復元。
6. 記述的比較: 分解能を超えた符号だけ報告、相対変化・奇偶比を追加、+2.5 mm は flow_24 側が分解能すれすれなので比・符号を出さない。
8. 境界テスト（厳密差）、control も増えるケース、SIGN_FLIP で奇関数部が残るケース、drag 境界、control 境界を追加。
未反映（記録のみ）: 7（drag 分解能が repeat noise に比例する点は事前登録どおり）、9（freeze key 欠落は KeyError で止まる。verdict は出ないので fail-closed）。
