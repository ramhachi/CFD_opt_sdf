# FID-01 (#62, M3a): fidelity go/no-go of the central hypothesis on fixed v18 designs — evidence

**Registration status: freeze 1 pending (see `freeze1.json` once present).** Registration: [`docs/fid01_registration_2026_10_21.md`](../../fid01_registration_2026_10_21.md) (plan review §12a, source review §13, deviations §14). All qualification flags false; `shape_update_allowed=false`.

## Files
| path | what |
| --- | --- |
| `prescreen_run1_designs.json` | first design prescreen run (every revision-1 candidate through the MODE-01 v18 gate stack; geometry only); kept because revision 3 added fallbacks after it (§9) |
| `designs.json` | the registered prescreen (`rows`: every candidate's gate result with the code fingerprint), the X1 STL export gate of the gate-clean candidates in order (`x1`), and the design per slot (`designs`) |
| `states.json`, `inputs/` | the registered states through the harness state model and their direction raws (parent and roll: the UNC-01 bytes) |
| `of/export.json` | STL exports (r = 8; EX r = 4), X1 gates, STL volumes vs the parent and vs the SDF smoothed volume (G5a) |
| `oc.json` | operating characteristics of the registered rules on synthetic data (§6.10) |
| `p0_probe/` | pre-registration OpenFOAM timing probe of the parent on V2 and V3 (sanitised: statuses, stage times, cells, iterations; force fields removed, `EXCLUDED_SHA256.json` holds the hashes of the removed originals); `make_probe.py` built its inputs |
| `freeze1.json` ... | freeze records (§11), when written |

STLs (about 32 MB each) and the OpenFOAM datasets are not tracked (re-derivable with `fid01_build.py of-export` / `of-prepare`); their SHA-256 are in `of/export.json` and the criteria.

## Reproduce
```
python scripts/fid01/fid01_designs.py prescreen --workers 4    # reuses rows with the same code fingerprint (work/fid01_prescreen/)
python scripts/fid01/fid01_designs.py select --workers 4
python scripts/fid01/fid01_build.py states
python scripts/fid01/fid01_build.py campaign
python scripts/fid01/fid01_build.py of-export --workers 4
python scripts/fid01/fid01_build.py of-prepare                  # V1 kernels (stage v1); --smoke for the development smoke
python scripts/fid01/fid01_oc.py --reps 200 --out oc.json
python -m pytest tests/fid01 -q
```
