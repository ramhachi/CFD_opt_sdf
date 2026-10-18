# JOB-02 (#59) gate の結果: `JOB02_GATE_PASS`。1 kernel 内の per-state placement が 4 つの parent をバイト単位で再現した

証拠の種別は engineering gate（能力の証拠）。物理・閾値・flag・ranking の根拠にはしない。qualification flag は全 false、`shape_update_allowed=false` のまま。

## 実行
- source commit は `ffc9fb9e7b8a27b4bc064e236d9863e22c2cf05b`（`feat/job02-per-state-placement`）。harness freeze は `docs/harness/job02_gate_campaign.prerun_freeze.json`（SHA `b268080a…`）、gate freeze は `gate_freeze.json`（SHA `5061c266…`）。gate spec（`19c3b542…`）と `scripts/job02_gate.py`（`017a3237…`）の SHA は、結果を出した時点でも `gate_freeze.json` と一致していた（照合は手で行った）。
- smoke: Kaggle kernel `ramhachi888/cfd-opt-sdf-job02-gate-f24-smoke` の version 1。投入から約 4 h queue で待った後に COMPLETE。native flow_24 の CSV は `e62b6bab…` で、`verify --smoke` も通った（`smoke/`）。
- formal: `ramhachi888/cfd-opt-sdf-job02-gate-f24` と `-f32` の version 1 を 2026-10-18 19:34 UTC に同時に投入し、21:10 UTC までに両方 COMPLETE。どちらも `DONE` があり、`ERROR.txt` はない。出力は `kaggle kernels output` で新しい空ディレクトリに落とし、`kernel_output/` にコピーした（`diff -r` で同一を確認）。
- `harness.py verify` は 2 kernel とも integrity pass（`state_force_table.json`）。gate を実行し（`gate_result.json`）、exit は 0。

## 結果
| kernel | run | origin (m) | 出力 CSV の SHA | 参照 | 一致 | downforce / drag (N) | solver 時間 (s) |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| f24（flow_24） | `opt01b__parent` | -1.0,-0.8,-0.6 | `e62b6bab…` | OPT-01 v1 Stage B a の parent | byte 一致 | 0.33188 / 0.32372 | 170 |
| f24 | `opt01b__parent__grid02_shift` | -0.9875,-0.7875,-0.6 | `471ea410…` | GRID-02 s24 の parent | byte 一致 | 0.33738 / 0.32351 | 173 |
| f32（flow_32） | `opt01b__parent` | -1.0,-0.8,-0.6 | `282aceed…` | OPT-01 v1 Stage B b の parent | byte 一致 | 0.36178 / 0.34995 | 410 |
| f32 | `opt01b__parent__grid02_shift` | -0.9875,-0.7875,-0.6 | `667127c5…` | GRID-02 s32 の parent | byte 一致 | 0.32715 / 0.37341 | 414 |

1 kernel の中で、同じ phi を native の placement と shift した placement で順に走らせても、それぞれ別の kernel で走らせた過去の CSV と完全に一致した。順番や前の run の影響はない。2 つの placement の力の差は GRID-02 の placement effect と同じ値になる。

## 言えること・言えないこと
- 言えること: harness（run の `name` ＋ run ごとの `W4_CANONICAL_ORIGIN_M` の x, y）は、1 kernel の中で state ごとの flow-grid placement を扱える。既定の placement は既存の native parent を、shift した placement は GRID-02 の shifted parent を、flow_24 と flow_32 で再現する。M2（UNC-01、#61）は複数の placement phase を 1 kernel で走らせられる。
- 言えないこと: placement 分散 σ_d の値、物理的な downforce／drag、格子収束、z（車高）の変更、他の parent への一般化。新しい parent での確認は UNC-01 の smoke が受け持つ。

## 再現
```
.venv/bin/python scripts/harness.py verify docs/evidence/job02_gate_2026_10_19/kernel_output/job02_gate_f24 docs/evidence/job02_gate_2026_10_19/kernel_output/job02_gate_f32 --campaign docs/harness/job02_gate_campaign.json --freeze docs/harness/job02_gate_campaign.prerun_freeze.json
.venv/bin/python scripts/job02_gate.py --spec docs/evidence/job02_gate_2026_10_19/gate_spec.json --table docs/evidence/job02_gate_2026_10_19/state_force_table.json --kernel-root docs/evidence/job02_gate_2026_10_19/kernel_output
```
テストは `tests/test_job02_per_state_placement.py`。
