# FID-01 (#62, M3a): fidelity go/no-go of the central hypothesis on fixed v18 designs — evidence

**Registration status: `REGISTERED_FROZEN` (freeze 2, freeze 3; freeze 1 with amendments 1-3 before any formal run).** Result: **`FID01_GO`**. The human summary is [analysis.md](analysis.md) and the analyzer output is `analysis.json`; both are written once.

Registration: [`docs/fid01_registration_2026_10_21.md`](../../fid01_registration_2026_10_21.md) (revision 3; plan review §12a, source review §13, deviations from #62 §14). All qualification flags false; `shape_update_allowed=false`.

## Files
| path | what |
| --- | --- |
| `prescreen_run1_designs.json` | First design prescreen run: every revision-1 candidate through the MODE-01 v18 gate stack, geometry only. Kept because revision 3 added fallbacks after it (§9). |
| `designs.json` | The registered prescreen (`rows`: every candidate's gate result with the code fingerprint), the X1 STL export gate of the gate-clean candidates in order (`x1`), and the design per slot (`designs`). |
| `states.json`, `inputs/` | The registered states through the harness state model, and their direction raws. The parent and roll use the UNC-01 bytes. |
| `oc.json` | Operating characteristics of the registered rules on synthetic data (§6.10). |
| `p0_probe/` | Pre-registration OpenFOAM timing probe of the parent on V2 and V3, sanitised: statuses, stage times, cells and iterations are kept; force fields are removed, and `EXCLUDED_SHA256.json` holds the hashes of the removed originals. `make_probe.py` built its inputs. |
| `freeze1.json`, `freeze1_amendment{1,2,3}.json`, `freeze2.json`, `freeze3.json` | Freeze records (§11) and engineering amendments, all made before the runs they govern (§10). |
| `wl/smoke/`, `wl/smoke48/` | WaterLily harness smokes (flow_32 and flow_48 parent) and their `verify --smoke` tables. |
| `wl/kernel_output/`, `wl/verify/table_*.json`, `wl/download_*.txt` | WaterLily formal outputs: `fid01_f32k7..10` (flow_32 phases 7-10) and `fid01_f48_f48` (flow_48 phase 7), each with its `.kaggle.log`. Also the per-kernel verify tables (`scripts/fid01/fid01_harness.py verify`) and the download listings. |
| `d_set.json` | Tiers and run sets, derived once from the flow_32 tables and frozen in freeze 3. |
| `wl/budget_decision.json`, `of_levels.json` | The §4.3 flow_48 budget decision (T = 47,293 s, pushed) and the §5.3 V3 contingency (V1, V2, V3 kept), both frozen in freeze 3. |
| `of/export.json` | STL exports (r = 8; EX r = 4), X1 gates, and STL volumes vs the parent and vs the SDF smoothed volume (G5a). |
| `of/criteria/` | The 13 formal OpenFOAM criteria: V1 `v1_1..4`, V2 `v2_49p/49m/50p/50m`, V3 `v3_49p_1..5`. |
| `of/smoke/` | Development smoke criteria and sanitised output (statuses only). |
| `of/output/<kernel>/` | Formal OpenFOAM outputs (local Docker v2512, see below). |
| `analysis.json`, `analysis.md` | The registered analysis and its human summary. |

Each `of/output/<kernel>/` directory holds:
- `local_run.json`: returncode 0 and dpkg matching the lock.
- `local_run.log` and `dpkg_after.sha256`.
- `openfoam_xfid_gridphase_x3/` with `result.json` (read by the analyzer), `environment.json`, `artifact_manifest.json` and `DONE`.
- `cases.tar`: the runner's retained case files, i.e. `case_result.json` and the gzipped logs and `coefficient.dat`. It is packed deterministically (mtime 0, no owner), and `cases_manifest.json` lists the SHA-256 of every file inside it.

Not tracked, re-derivable:
- STLs (about 32 MB each) and the OpenFOAM datasets. Rebuild them with `fid01_build.py of-export` / `of-prepare`; their SHA-256 are in `of/export.json` and the criteria.
- The V3 meshes, which the runner removes.

Harness campaigns and freezes: `docs/harness/fid01_campaign.json` and `docs/harness/fid01_f48_campaign.json`, each with its `.prerun_freeze.json`. Kernels:
- WaterLily: `infra/kaggle/kernel_fid01_*`.
- OpenFOAM: `infra/fid01/*`.

## Reproduce
```
python scripts/fid01/fid01_designs.py prescreen --workers 4    # reuses rows with the same code fingerprint (work/fid01_prescreen/)
python scripts/fid01/fid01_designs.py select --workers 4
python scripts/fid01/fid01_build.py states
python scripts/fid01/fid01_build.py of-export --workers 4
python scripts/fid01/fid01_oc.py --reps 200 --out oc.json
E=docs/evidence/fid01_2026_10_21; O=$E/of/output
python scripts/fid01/analyze_fid01.py main --dset $E/d_set.json --campaign docs/harness/fid01_campaign.json \
  --tables $E/wl/verify/table_f32k7.json $E/wl/verify/table_f32k8.json $E/wl/verify/table_f32k9.json $E/wl/verify/table_f32k10.json \
  --campaign48 docs/harness/fid01_f48_campaign.json --tables48 $E/wl/verify/table_f48.json --kernel-root $E/wl/kernel_output \
  --of $O/v1_1 $O/v1_2 $O/v1_3 $O/v1_4 $O/v2_49p $O/v2_49m $O/v2_50p $O/v2_50m $O/v3_49p_1 $O/v3_49p_2 $O/v3_49p_3 $O/v3_49p_4 $O/v3_49p_5 \
  --out /tmp/analysis.json
python -m pytest tests/fid01 -q
```
The analysis command reproduces `analysis.json`. It refuses to run if any freeze record, campaign, table or OpenFOAM criteria set differs from the frozen ones. Tests: `tests/fid01/test_fid01.py` (24). `SHA256SUMS` is repo-root relative and passes `scripts/check_sha256sums_tracked.py`.
