# UNC-01 (#61, M2): paired placement-phase uncertainty sigma_d on the v18 parent — evidence

**Registration status: `REGISTERED_FROZEN` (freeze 2) with `REGISTERED_AMENDED` (amendment 2: U3 in the local OpenFOAM environment).** Result: **`M2_COMPLETE`**; summary in [analysis.md](analysis.md), the analyzer output in `analysis.json` (written once). Registration: [`docs/unc01_registration_2026_10_20.md`](../../unc01_registration_2026_10_20.md) (rev. 3 + §14 amendment 1 + §15 + §16 amendment 2; plan review §12, source review §13). All qualification flags false; `shape_update_allowed=false`.

## Files
| path | what |
| --- | --- |
| `states.json`, `inputs/` | the 17 registered states (harness state model; prescreen bytes reproduced), 16 direction raws |
| `regate.json` | prescreen gate stack on every state: 17/17 pass, identical to the prescreen rows |
| `freeze1.json`, `freeze1_amendment1.json`, `freeze2.json`, `amendment2_u3_local.json` | freezes and amendments (file hashes, source commits) |
| `u01/smoke/` | U01 harness smoke (flow_24 parent), `verify --smoke` table, U0 smoke check |
| `u01/kernel_output/`, `u01/state_force_table.json`, `u01/u0_gate.json`, `u01/u1_selection.json` | U01 formal (exploratory): U0 gate (`U0_PASS`), selection L = pitch, L2 = reflex, L_mid = pitch +1.3 deg; `verify_attempt_per_kernel_*.stderr` = the failed one-kernel harness verify that led to amendment 1 |
| `u2/smoke/` | U2 harness smoke (flow_24 parent, phase 1) and its `verify --smoke` table |
| `u2/kernel_output/`, `u2/verify/table_*.json`, `u2/budget_decision.json` | U2 formal outputs (six kernels, Kaggle T4), per-kernel verify tables (`scripts/unc01_verify.py`), the §4 flow_24 decision |
| `u3/u3_criteria.json`, `u3/export.json`, `u3/smoke/` | U3 criteria (256 cases) and STL export record; Kaggle development smoke criteria, export record and sanitised output (no force values) |
| `u3/output/` | U3 formal output (local Docker OpenFOAM v2512, `local_run.json`: returncode 0, dpkg matches the lock) |
| `analysis.json`, `analysis.md` | the registered analysis and its human summary |

Harness campaigns and freezes: `docs/harness/unc01_u01_campaign.json` (+ `.prerun_freeze.json`), `docs/harness/unc01_u2_campaign.json` (+ `.prerun_freeze.json`); kernels `infra/kaggle/kernel_unc01_*`.

## Reproduce
```
python scripts/unc01_build.py states                      # re-derives states.json and the raws (refuses on any difference)
python scripts/harness.py verify docs/evidence/unc01_2026_10_20/u01/kernel_output/unc01_u01_f24 .../unc01_u01_f32 .../unc01_u01_f48 --campaign docs/harness/unc01_u01_campaign.json --freeze docs/harness/unc01_u01_campaign.prerun_freeze.json
python scripts/unc01_verify.py docs/evidence/unc01_2026_10_20/u2/kernel_output/unc01_u2_f32a --campaign docs/harness/unc01_u2_campaign.json --freeze docs/harness/unc01_u2_campaign.prerun_freeze.json --out /tmp/t.json
python scripts/analyze_unc01.py u2 --campaign docs/harness/unc01_u2_campaign.json --u1 docs/evidence/unc01_2026_10_20/u01/u1_selection.json --budget docs/evidence/unc01_2026_10_20/u2/budget_decision.json --tables docs/evidence/unc01_2026_10_20/u2/verify/table_*.json --kernel-root docs/evidence/unc01_2026_10_20/u2/kernel_output --u3 docs/evidence/unc01_2026_10_20/u3/output/openfoam_xfid_gridphase_x3/result.json --u3-criteria docs/evidence/unc01_2026_10_20/u3/u3_criteria.json --out /tmp/analysis.json
```
The last command reproduces `analysis.json` except the `u3_input` paths. Tests: `tests/test_unc01.py` (28). `SHA256SUMS` is repo-root relative.
