# XV-01 (#65, M3b-2, L2): independent OpenFOAM verification of the frozen SCREEN-01 finalist — evidence

**Registration status: not frozen** (revision 1, `DRAFT_REVIEWED_REV1`). No OpenFOAM case of XV-01 is funded, queued or run; no OpenFOAM force of the finalist exists. Evidence class of this directory: pre-registration documents and a planning projection (no CFD). All qualification flags are false; `shape_update_allowed=false`.

Registration: [`docs/xv01_registration_2026_10_31.md`](../../xv01_registration_2026_10_31.md). Finalist and handoff: [`docs/evidence/screen01_2026_10_30/xv_handoff.json`](../screen01_2026_10_30/xv_handoff.json) (SCREEN-01 `SCREEN01_GAIN`).

## Files
| path | what |
| --- | --- |
| `decision_memo.md` | Decisions, alternatives and residual risks (companion to the registration). |
| `plan_review/` | The three plan reviews of revision 0 (numerical, governance, strategy), verbatim, and `adoption.md`. |
| `pass_probability.py`, `pass_probability.json` | Planning projection of the expected pass probability (registration §7); visible SCREEN/FID records only; no outcome effect. |
| `SHA256SUMS` | Repo-root relative manifest of the tracked files of this directory (passes `scripts/check_sha256sums_tracked.py`). |

## Reproduce
```
.venv/bin/python docs/evidence/xv01_2026_10_31/pass_probability.py   # rewrites pass_probability.json (seed 20261031); byte-identical on rerun
.venv/bin/python scripts/check_sha256sums_tracked.py docs/evidence/xv01_2026_10_31/SHA256SUMS
```
