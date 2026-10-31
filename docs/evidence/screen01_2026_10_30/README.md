# SCREEN-01 (#64, M3b-1): quadratic response surface on three analytic modes of the v18 plate, finalist judged on fresh phases — evidence

**Registration status: `REGISTERED_FROZEN` (freeze 1, 2, 2.1, 3; each written before the runs it governs).** Result: **`SCREEN01_GAIN`** (2026-10-31). The human summary is [analysis.md](analysis.md); the analyzer output is `analysis.json` and the XV-01 handoff is `xv_handoff.json`. All three are written once by `analyze_screen01.py main` and cross-checked against the independent `screen01_check.py` (no discrepancy).

Registration: [`docs/screen01_registration_2026_10_30.md`](../../screen01_registration_2026_10_30.md), revision 2, SHA-256 `fa3e5f7e…dcdc81`. Its header still reads `DRAFT_REVIEWED_REV2` because the text became immutable at freeze 1; the frozen status lives in the freeze records. The plan review is in §12 and `plan_review/`, the source review in §13 and `source_review/`. All qualification flags are false; `shape_update_allowed=false`.

## Result

The finalist is `v18__camber_m29.55_pitch_p0.155_reflex_p16.115`, written in `finalist.json` before any confirmation force existed. Each Δ̄ below is the mean of paired same-phase differences against the parent.

| grid | phases | P | Δ̄ downforce (N) | SE_eff (N) | % of J_b,48 | Δ̄ drag (N) |
| --- | --- | --- | --- | --- | --- | --- |
| flow_32 | 13-16 | 4 | +1.077e-2 | 2.92e-4 | 4.05 | -1.99e-3 |
| flow_48 | 13, 14 | 2 | +1.036e-2 | 4.46e-4 | 3.90 | -2.79e-3 |

**Rule labels**

- **G:** `PASS`. The flow_32 gain is 1.50 g_min: the threshold is g_min J_b,48 = 7.184e-3 N (2.70 %). The gain also exceeds 3 SE_eff, and `GAIN_RESOLVED_ABOVE_MIN` holds.
- **D:** `PASS_RESOLVED`. The drag 90 % interval is [-3.26e-3, -0.72e-3] N.
- **R3:** `R3_CONFIRMED`. Ratio in band; `G48_ABOVE_MIN` holds with a margin of 3.17e-3 N; E2 is not exceeded; drag has the same sign on both grids.

**Controls on flow_32**

| control | Δ̄ downforce (N) |
| --- | --- |
| hand design M `v18__camber_m19.7_pitch_m0.38` | +7.71e-3 |
| random-control best R-best `v18__camber_m28.656_pitch_m0.68_reflex_p2.727` | +5.86e-3 (flow_48: +6.34e-3) |

The resulting labels are `OPT_BEATS_MANUAL`, `OPT_BEATS_RANDOM`, `RANDOM_FEASIBLE_GAIN` false and `K_MISMATCH` false (K_opt = K_rand = 19). The hand design is also above g_min J by its point estimate.

**Chain controls**

- NC (roll) is `CONSISTENT` at G1 (z 0.48) and at F (z 0.05).
- Determinism (g1k11, f32a) and generation drift both show a difference of 0.

**Descriptive labels:** `RS_FIT_POOR`, `POOL_LIMITED` false.

**§5.7 planning projection (not a result)**

- The selection bias b_K is 1.03e-3 N (central) and 2.67e-3 N (upper).
- The expected OpenFOAM V1 gain is 2.40 % (central) and 1.74 % (pessimistic). Both clear the XV floor of 1.27 %, so `XV_MARGIN_ADEQUATE` holds for both.
- The exploration estimate of the finalist was +1.083e-2 N; the confirmation estimate is +1.077e-2 N.

**Claim ceiling (registration §1).** This is one finalist's paired same-phase differences against the parent, inside WaterLily at Re = 80 (reduced laminar, Kaggle T4). It is:

- not independent verification (that is XV-01, #65);
- not physical downforce;
- not grid independence;
- not FSAE or high Re.

Two limits from the handoff apply in particular:

- The finalist lies in the camber extension (u = -1.5, -29.55 mm), where FID-01 has no fidelity evidence; XV-01 decides that fidelity.
- Its drag neutrality relies on the OpenFOAM drag retention of camber, which FID-01 did not test.

Consequence (registration §7): XV-01 becomes eligible for registration. There is no second SCREEN round and no finalist retuning.

## Files
| path | what |
| --- | --- |
| `decision_memo.md` | The registration's decision memo (revision 2), companion to the registration text. |
| `plan_review/` | The three plan reviews of revision 0 (numerical, governance, strategy), verbatim, and `adoption.md`. |
| `crosscheck_reconciliation.md` | Reasons for the §5.11 readings decided where the analyzer and the checker differed. |
| `source_review/` | The three source reviews (rules, pool/OC/checker, build/harness), verbatim, and `adoption.md` (work orders). |
| `pool_prescreen/` | Revision-0 P0 record (geometry only). |
| `pool_prescreen_rev1/` | The P0 record bound by freeze 1. It holds `rows.jsonl`, `summary.json`, `design_check.json`, `pools.json` and `p0.log`, and its README records both runs. |
| `oc.json` | Operating characteristics of the registered procedure on the visible-data surrogate (§5.10). |
| `states.json`, `inputs/` | The registered G1 states and their direction raws (36), from the P0 record. |
| `states_g2.json`, `inputs/v18__camber_m29.55_*` | The four G2 proposal states (from `rs.json`) and their raws. |
| `infra_signatures.json` | The §9 kernel-loss signature table. No loss occurred. |
| `freeze1.json`, `freeze2.json`, `freeze2_1.json`, `freeze3.json` | Freeze records (§10); each binds the previous one. |
| `rs.json` | The response-surface fit, the constrained optimum, the gating record and the proposals, written once after G1 (`RS_FIT_POOR`, 4 proposals). |
| `finalist.json` | The finalist, R-best, K and the candidates' exploration estimates, written once after G2. |
| `wl/smoke/`, `wl/smoke_g2/`, `wl/smoke_f/`, `wl/smoke_f48/` | Harness smokes (g1k11, g2, f32smk, f48smk; parent only) with their `verify --smoke` tables and download listings. |
| `wl/kernel_output/` | Raw Kaggle output of the seven formal kernels, byte for byte, each with its JSON kernel log. |
| `wl/verify/table_*.json`, `wl/verify/verify_*.stderr` | Per-kernel harness verify tables (`scripts/fid01/fid01_harness.py verify`) and their empty stderr. |
| `wl/download_*.txt` | Download listings. `download_g1k11_attempt1_timeout.txt` is a read timeout after 8 of 39 states: the partial directory was deleted and downloaded again (a download failure, not a kernel loss). |
| `wl/g1_push.txt`, `wl/g2_push.txt`, `wl/f48_push.txt`, `wl/f32_push.txt` | Push records (UTC, command, kernel timeout, CLI version). |
| `wl/budget_g2.json`, `wl/budget_f.json`, `wl/budget_f32.json` | §4.3 budget records before the G2, first F and f32 pushes; all are go. |
| `analysis.json`, `analysis.md`, `xv_handoff.json` | The registered analysis, its summary and the XV-01 handoff. |

Formal kernels: one Kaggle T4 session each and no rerun; all were harness-verified.

| kernel | phases | runs | session wall (s) |
| --- | --- | --- | --- |
| g1k11 | 11 | 39 | 15,966 |
| g1k12 | 12 | 38 | 15,797 |
| g2 | 11, 12 | 10 | 4,258 |
| f48k13 | 13 (flow_48) | 3 | 7,727 |
| f48k14 | 14 (flow_48) | 3 | 8,220 |
| f32a | 13, 14, replay 11 | 12 | 5,240 |
| f32b | 15, 16 | 10 | 4,683 |

The formal total is 61,891 s (17.2 GPU h) against the 86,400 s cap.

Harness campaigns are `docs/harness/screen01_campaign.json`, `screen01_g2_campaign.json`, `screen01_f_campaign.json` and `screen01_f48_campaign.json`, each with its `.prerun_freeze.json`. Kernels are in `infra/kaggle/kernel_screen01_*`. Kaggle CLI 2.2.5 was pinned with `uv tool install kaggle==2.2.5`, because the 2.2.4 outdated-version warning broke the identity-free listing.

Not tracked, re-derivable: the P0 caches (`work/screen01_pool_prescreen/`) and STLs. Their SHA-256 are in `pool_prescreen_rev1/rows.jsonl`.

## Reproduce

The P0 record, `states.json` and the raws come from the commands in [`pool_prescreen_rev1/README.md`](pool_prescreen_rev1/README.md). The written-once steps are:

```
E=docs/evidence/screen01_2026_10_30; W=$E/wl
python scripts/screen01/analyze_screen01.py rs --g1 docs/harness/screen01_campaign.json $W/verify/table_g1k11.json $W/verify/table_g1k12.json \
  --kernel-root $W/kernel_output --workers 4 --out /tmp/rs.json
python scripts/screen01/analyze_screen01.py finalist --g1 docs/harness/screen01_campaign.json $W/verify/table_g1k11.json $W/verify/table_g1k12.json \
  --g2 docs/harness/screen01_g2_campaign.json $W/verify/table_g2.json --rs $E/rs.json --kernel-root $W/kernel_output --workers 4 --out /tmp/finalist.json
python scripts/screen01/analyze_screen01.py main --g1 docs/harness/screen01_campaign.json $W/verify/table_g1k11.json $W/verify/table_g1k12.json \
  --g2 docs/harness/screen01_g2_campaign.json $W/verify/table_g2.json \
  --f32 docs/harness/screen01_f_campaign.json $W/verify/table_f32a.json $W/verify/table_f32b.json \
  --f48 docs/harness/screen01_f48_campaign.json $W/verify/table_f48k13.json $W/verify/table_f48k14.json \
  --rs $E/rs.json --finalist $E/finalist.json --kernel-root $W/kernel_output --out /tmp/analysis.json
python -m pytest tests/screen01 -q
```

Each command refuses to run if any freeze record, bound source, campaign, table or environment pin differs from the frozen one. `--out` is opened exclusively, so the outputs need a fresh path.

`SHA256SUMS` is repo-root relative, lists every tracked file of this directory except itself, and passes `scripts/check_sha256sums_tracked.py`.
