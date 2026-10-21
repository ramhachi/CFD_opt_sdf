# FID-01 (#62, M3a): fidelity go/no-go of the central hypothesis on fixed v18 designs — evidence

**Registration status: PLAN (pre-freeze).** Registration: [`docs/fid01_registration_2026_10_21.md`](../../fid01_registration_2026_10_21.md). All qualification flags false; `shape_update_allowed=false`.

## Files (so far)
| path | what |
| --- | --- |
| `designs.json` | design prescreen (§3.2): every candidate of every slot through the MODE-01 v18 gate stack (`rows`), the X1 STL export gate of the gate-clean candidates in order (`x1`), and the chosen design per slot (`designs`); geometry only, no solver |
| `p0_probe/` | pre-registration engineering probe (§9): the v18 parent on the V2 and V3 mesh levels at one shift, sanitised (statuses, stage times, cell counts, iterations; force fields removed, `EXCLUDED_SHA256.json` holds the hashes of the removed originals); `make_probe.py` built its inputs |

## Reproduce
```
python scripts/fid01/fid01_designs.py prescreen --workers 4
python scripts/fid01/fid01_designs.py select --workers 4
```
