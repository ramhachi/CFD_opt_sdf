# FD-08 v2 oracle scope record（2026-10-08）

`record.json`（SHA-256 は sidecar）は、R6 PASS 8/8 と formal 24/24 PASS を **範囲つき**で束縛する記録で、
flag の変更ではない。6 つの qualification flag は literal false のまま（`qualification_flags`）。
`fd_oracle` や `*_qualified` の true は書いていない（`criteria_supersession._check_flag_state` を通る）。
flag を true にするには別のユーザー判断と新しい record が要る。

- 範囲: Candidate C（`candidate_c_moment_blend+normal_floor_0.25`）/ canonical v17 / flow_24 /
  D0・D1・D2・P1 × drag・downforce の 8 系列 / ε 0.5〜5 mm の補間のみ。formal は内部 3 点。
- ĝ は Model A の重み付き最小二乗の傾き（N/m）で、単一 ε の差分でも ε→0 の厳密な微分でもない。
  SE は T2 の仮定ノイズ由来の公称値。T2 は arbitrary-provisional で、勾配の誤差基準ではない。
- GRAD-01 への橋渡し（loader は未実装。S3 の判定後に判断）: direction は canonical state から
  `generate_directions` / `generate_p1` で再生成し、登録済み `<f4` hash と一致することを確認したうえで、
  GRAD-01 の f64 hash（`field_direction_sha256`）を計算した。response semantics の hash と FD backend の
  fingerprint は、この record が導出規則とともに初めて定義した値（以前は登録されていない）。
- GRAD-01 の `epsilon` に入れる単一の値は定義していない（ĝ は ε の梯子全体にわたる傾き）。loader を作る際は、梯子の範囲を `epsilon` の意味として明示する必要がある。
  この record は「oracle status」を名乗るが flag の変更ではない（`fd_oracle` は false のまま）。
- **誤差基準 δ（`relative_error_tolerance`、`absolute_noise_floor`）は記録していない。** 決定はユーザー。
  選択肢は `docs/issues/46_fd08_v2_grad03_delta_options_2026_10_08.md`。
- 再現: `.venv/bin/python scripts/build_fd08_v2_oracle_scope_record.py`（canonical NPZ `7a972b33…` が要る）。
