# XV-01 (#65, M3b-2, L2) registration: independent body-fitted OpenFOAM verification of the frozen SCREEN-01 finalist against the v18 parent (Re 80)

Status: **`DRAFT_FOR_PLAN_REVIEW`** (revision 0, 2026-10-31). Not frozen; no OpenFOAM case of XV-01 is funded, queued or run, and no OpenFOAM force of the finalist exists. The study becomes `REGISTERED_FROZEN` at freeze 2 (§10), after the PROC-01 plan review (§12), the sources and their source review, and the smokes/probe. No flag changes: all qualification flags stay false, `shape_update_allowed=false`. Integration branch `codex/kaggle-batch-migration` (not main). Where this text and the future `scripts/xv01/analyze_xv01.py` disagree, this text governs and the disagreement is an analyzer defect. Decisions, alternatives and residual risks: `docs/evidence/xv01_2026_10_31/decision_memo.md`.

Inputs (registered records, read by content hash; binding from freeze 1):
- SCREEN-01 `SCREEN01_GAIN` (#64, `REGISTERED_FROZEN`; branch `exp/screen01-registration-2026-10-30`, PR #76): `docs/evidence/screen01_2026_10_30/xv_handoff.json` (SHA-256 `ac0909e2…`), `analysis.json` (`cbf0292b…`), registration revision 2 (`fa3e5f7e…`), `rs.json` (`66f7005d…`), `finalist.json` (`f7fd2456…`), freezes 1, 2, 2.1, 3. Finalist `v18__camber_m29.55_pitch_p0.155_reflex_p16.115` (spec pitch +0.155 deg, camber -29.55 mm, reflex +16.115 mm; u = (0.05, -1.5, 0.55)); state `da2d2121…`, NPZ `9e2f4bf7…`, phi Fortran `a7c1e3b9…`, direction raw `27d7b742…`, r = 8 STL `714f6b98…`. Parent `v18__parent`: state `e7376e35…`, NPZ `36967c90…`, phi Fortran `29d53b23…`. WaterLily confirmation (flow_32, phases 13-16, P = 4): downforce `Delta_bar = 1.0774190511977672e-2 N`, `SE_eff = 2.9231082773713274e-4 N`; drag `-1.9938669864582037e-3 N`, `SE_eff = 5.397769910001766e-4 N`; flow_48 (phases 13, 14) downforce `+1.0357e-2 N`, `R3_CONFIRMED`. §5.7 planning projection: `b_K` 1.03e-3 / 2.67e-3 N, expected OpenFOAM V1 gain 2.40 % central / 1.74 % pessimistic of `J_b,48`.
- FID-01 `FID01_GO` (#62; `docs/evidence/fid01_2026_10_21/analysis.json`, SHA-256 `b89203d0…`; registration revision 3 `4d692af6…`): the OpenFOAM procedure (§5: pipeline, levels V1/V2/V3, X3 shift generator, case validity), the G rules (§6.3), the NC and EX forms (§6.6), the §8 mapping to XV: OpenFOAM minimum gain `g_OF = 2 max(S_d, S_d,OF) = 0.012674959854238867` (`S_d = 0.003399676556346094`, `S_d,OF = 0.006337479927119433`); R3 not challenged, flow_48 measured, `EXPORT_INSENSITIVE` (W4, W6). Descriptive values used in §7 and §5.1: per-design OpenFOAM differences on V1/V2/V3, the V2 pooled pair SD (downforce `1.984576864434452e-4 N`, drag `1.3747177622390572e-4 N`, dof 12), the OpenFOAM parent downforce (V1 about 0.2017 N, V2 0.2062 N, V3 0.2124 N).
- M2 UNC-01 `M2_COMPLETE` (`docs/evidence/unc01_2026_10_20/analysis.json`, `ee71c6d6…`): the OpenFOAM NC reference `-6.614761397334482e-4 N`, SE `5.792182318004298e-5 N` (as FID §7.1 / §6.6).
- LOCAL-OF-01 (`docs/local_openfoam_env_gate_2026_10_20.md`): `LOCAL_ENV_PASS_BITWISE` for the U3/X3 pipeline; lock `infra/local_openfoam/local_openfoam_lock.json` (`c105b7df…`), image `sha256:e9ceb8a7…25eb` (amd64 under emulation on the Apple M4 host); `scripts/local_openfoam.py run`. The T2-0c mesh family (`LOCAL_ENV_FAIL`) is not used.
- Preparation: `docs/xv01_registration_requirements_2026_10_22.md` (`ffd8328a…`), `docs/fid01_to_screen_xv_handoff_2026_10_23.md`, `docs/screen_xv_preparation_2026_10_23.md` (option A′), issue #65.

## 1. Question, hypothesis and claim ceiling
**Question (L2, roadmap M3b-2; #65).** Does the WaterLily-selected SCREEN-01 finalist keep, in independent body-fitted CFD on three OpenFOAM meshes never used for selection, a paired downforce gain over the v18 parent of at least the FID-mapped OpenFOAM minimum, with drag not increased, with the FID fidelity rules (sign on every mesh, retention, mesh consistency) satisfied and with the gain insensitive to the STL extraction?

**Hypothesis.** The SCREEN gain is not an artefact of the WaterLily solver family, of its grids or of the selection among K_opt = 19 WaterLily candidates: it persists on OpenFOAM V1, V2 and V3 above `g_OF` with drag non-increase.

Claim ceiling: Re = 80 laminar steady OpenFOAM v2512 (local Docker, the U3/X3 pipeline, three snappy meshes, not grid-converged) for **one** WaterLily-selected finalist against **one** analytic parent (v18), uncertified geometry, the r = 8 STL (r = 4 as the extraction control), three-axis sub-cell STL shifts of 0.5-4 mm per axis from a fixed Halton panel (the bottom wall is fixed, so a shift also changes the ground distance by up to 4 mm), paired same-shift differences. An `XV01_PASS` is the L2 statement **for this finalist at Re 80**: its WaterLily improvement is confirmed by independent CFD on grids not used for optimization. It is not physical downforce, not grid independence or a GCI claim, not FSAE, not high Re, not a fidelity statement for the camber extension beyond this one design, and not a statement about the optimizer's general reliability (one draw). The finalist lies in the camber extension (u = -1.5, -29.55 mm) where FID-01 has no fidelity evidence, and its WaterLily drag neutrality relies on an OpenFOAM camber drag retention that FID-01 did not test (§7.3); both are what XV-01 measures, not assumptions it inherits.

Outcomes (§5.9): `XV01_PASS`, `XV01_FAIL` (a resolved failure; cause list), `XV01_UNRESOLVED` (run set completed; a rule not resolved, or case-level data insufficient), `XV01_INCOMPLETE` (registered run set not completed: a kernel lost after its rerun, or the budget stop), `XV01_INVALID` (a chain control fails: NC or determinism). Registered secondary labels (no effect on the outcome): `XV_OF_GAIN_CONFIRMED`, `GAIN_RESOLVED_ABOVE_FLOOR_{V1,V2,V3}`, the drag resolution labels per level, `XV_DRAG_MESH_DEPENDENT`, `G5B_NOT_TESTED`, `REF_CONSISTENT`, `OF_OPT_VS_MANUAL`, `OF_OPT_VS_RANDOM`, the retentions and ratios of §5.10.

## 2. Stages (PROC-01)
| Stage | Content | Status |
| --- | --- | --- |
| P0 | solver-free: handoff verification (§3.1), geometry re-evaluation of the finalist on XV's arm (§3.2), STL export and X1 of every XV state (§3.3), the pass-probability record (§7) | before freeze 1, no force |
| P1 | revision 0 → one three-angle plan review → revision 1 | revision 0 (this text) |
| P2 | sources (`scripts/xv01/*.py`: builder, analyzer, independent checker, freeze writer; `tests/xv01/`) → one source review → revision 2 and its work orders → implementation, `pytest -q tests/xv01/` → **freeze 1** (commit, push, #65 comment) | not started |
| S | smokes and probe under freeze 1 (§4.6): V1 smoke and the environment replay, V2 smoke, the V3 convergence probe of the finalist; statuses only (the replay excepted, §4.6) → the funding decision (§7.5) and the §4.4 budget record → **freeze 2** (`REGISTERED_FROZEN`) | engineering |
| R | every formal kernel (V1, V2, V3) pushed after freeze 2, regardless of any value | registered |
| A | one analysis (`analyze_xv01.py main`), written once on every branch, cross-checked against the independent checker before writing | registered |

Every written-once output is opened exclusively (`--out`), reads only outputs whose criteria SHA-256 freeze 2 lists (each exactly once; the first valid output of a kernel is authoritative), applies §5 mechanically, and is cross-checked against an independent second implementation of the decision tables (a discrepancy stops the write and is an analyzer defect to fix before writing). After a write the output stands; a later discrepancy is reported beside it in a dated note.

## 3. States, geometry and constraints on XV's own arm (nothing inherited as passed)
### 3.1 Handoff verification (P0, before freeze 1)
The builder re-reads `xv_handoff.json` and checks, by content hash against the files on disk and the SCREEN freezes: the outcome `SCREEN01_GAIN`; the finalist name, spec, u and `in_camber_extension = true`; the parent and finalist NPZ, phi (Fortran and C order), state and direction-raw SHA-256; the r = 8 STL SHA-256 of the admissibility row; the gate profile and topology-policy hashes; the SCREEN registration, analysis, `rs.json`, `finalist.json`, adoption-record SHA-256; the campaign, prerun-freeze and verify-table SHA-256. It records the FID label values that decide the conditional obligations of the requirements note §4: `R3_CHALLENGED = false` and flow_48 `measured` (the whole-pool flow_48 P >= 2 obligation is **not triggered**; SCREEN measured its finalist on flow_48 at P = 2 anyway); `EXPORT_INSENSITIVE` for W4 and W6 (the conditional export-resolution obligation is **not triggered**; XV runs its own EX check for the finalist regardless, §5.7, because #65 lists the STL extraction control in scope and the FID control does not extend to an unobserved shape). Any mismatch stops the registration (not frozen; a defect record).

### 3.2 Geometry constraints re-evaluated (P0)
The frozen SCREEN admissibility code (`screen01_pool.admissible_rows`, unchanged, fingerprint `f5a5a95a…`) is re-run on the finalist bytes reconstructed from the handoff (the state model `construct_state(parent, d / max|d|, 1000 max|d| mm, +1)` from the direction raw and step 24.65274930000305 mm): the 13 GEOM-02 v2 gates incl. R0 `min_feature_width` at the native placement, P22-v2 `N_phi <= 8272`, the 10 % smoothed-volume band vs the v17 baseline, clearance >= 0.15 m, the X1 practical gate in double and float32 at r = 8, the STL chain check `|V_STL / V_STL,parent - 1 - dV_SDF,smoothed / V| <= 0.01`. Every gate value, `N_phi`, the volumes, the STL SHA-256 and the chain value must equal the handoff's admissibility row; then G5a = PASS (§5.6) is established before any case. A difference stops the registration (a defect; not frozen). R0 is placement-dependent and is decided at the native placement only (SCREEN §3.6); it is not re-decided at the OpenFOAM shifts, which act on the STL, not on the WaterLily lattice. The OpenFOAM-side validity of every mesh is a case-level rule (§4.5).

### 3.3 States and STLs
| State | Role | STL (r) | Levels | Source of the bytes |
| --- | --- | --- | --- | --- |
| `v18__parent` | reference of every difference | 8, 4 | V1, V2, V3 (r = 8); V1 (r = 4) | v18 genesis; FID export (`of/export.json`) re-exported and hash-checked |
| finalist | decision state | 8, 4 | V1, V2, V3 (r = 8); V1 (r = 4) | handoff (§3.1); r = 4 newly exported (X1 double and float32 required; a failure stops the registration) |
| `v18__roll_p25` | NC (x-translation by one cell) | 8 | V1 | M2/FID bytes; FID export re-checked |
| `v18__camber_m19.7` (FID W4) | known-design reference (`REF_CONSISTENT`) | 8 | V1 | FID bytes and export re-checked |
| `v18__camber_m19.7_pitch_m0.38` (SCREEN M) | descriptive control | 8 | V1 | SCREEN P0 row (STL `2299e68c…`) re-exported |
| `v18__camber_m28.656_pitch_m0.68_reflex_p2.727` (SCREEN R-best) | descriptive control | 8 | V1 | SCREEN P0 row (STL `d1a0a9e3…`) re-exported |

Every STL is exported by `geom02_canonical.export_from_state` (profile `docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json`) through `unc01_u3_prepare.export` and must hash to its source record (re-export equality is the extraction check of the bytes; the EX rule of §5.7 is the extraction check of the force). The WaterLily side is SCREEN's: XV builds no WaterLily grid and runs no WaterLily case.

## 4. OpenFOAM design
### 4.1 Pipeline and environment (FID §5.1, unchanged)
The U3 pipeline: the XFID X3 formal runner byte for byte except the bound criteria SHA, the Round 5 case template (hash-identical minus the candidate STL, plus the level changes of §4.2), simpleFoam with residual control, last-25 % iteration window, forces from the registered patches. Executed locally with `scripts/local_openfoam.py run` (`--cpus 1 --memory 8g`) in the locked image; a kernel output is valid only if `local_run.json` records return code 0 and `dpkg_after_matches_lock: true`. Every XV case runs in this one environment; there is no cross-environment comparison.

### 4.2 Levels, shifts and run sets
| Level | Template change (FID §5.2) | Shifts (X3 Halton generator, exact mirror pairs) | States |
| --- | --- | --- | --- |
| V1 | none (blockMesh 25 x 13 x 9, snappy (2 3)); endTime 3000 | 16 pairs, Halton 81-96 ± (32 shifts) | parent, finalist (r = 8 and r = 4), NC, W4, M, R-best (8 STLs) |
| V2 | blockMesh 50 x 26 x 18; endTime 3000 | 4 pairs, Halton 81-84 ± (8 shifts) | parent, finalist |
| V3 | blockMesh 100 x 52 x 36; endTime 6000 (or 12000 under §4.6) | 4 pairs, Halton 81-84 ± (8 shifts) | parent, finalist |

Halton indices 1-80 are used or registered elsewhere (calibration 1-16, X3 17-32, U3 33-48, FID 49-64 with the registered but unused FID extension 65-72, FID smoke 80); XV uses 81-96 for the formal cases and 99 + for the smokes and the probe; a re-registration uses 101 and above. V2 and V3 use the first four V1 pairs, so every level shares the pairs 81-84 (grid contrasts on common pairs, §5.5). The shift vectors are identical for every state on a level; case order is shift-major.

### 4.3 Kernels and cost (local, one core per case)
Measured on this pipeline (FID-01 formal, 2026-10-21/22, about four concurrent containers): V1 median 74 s per case (58-551 s; 105.8 s per case of kernel wall), V2 median 1,713 s (1,299-1,777 s), V3 median 33,566 s = 9.3 h (30,339-37,535 s, 4,415-4,599 iterations of the 6,000 allowed); the V3 parent probe alone took 28,491 s = 7.9 h.

| Kernels | Level | Cases | Estimate (case wall) |
| --- | --- | --- | --- |
| `v1_1` … `v1_4` (four whole mirror pairs each: 81-84, 85-88, 89-92, 93-96; `v1_1` ends with the determinism repeat, §5.6) | V1 | 4 x 64 + 1 = 257 | 257 x 105.8 s = 7.6 CPU h (about 1.9 h per kernel) |
| `v2_81` … `v2_84` (one mirror pair each: parent and finalist at + and -) | V2 | 4 x 4 = 16 | 16 x 1,713 s = 7.6 CPU h (about 1.9 h per kernel) |
| `v3_81p`, `v3_81m`, … `v3_84m` (one shift each: parent, then finalist) | V3 | 8 x 2 = 16 | 16 x 33,566 s = 149 CPU h (135-167; about 18.6 h per kernel) |

Formal estimate **164 CPU h** (150-182). The parent and the finalist of a pairing unit are in one kernel at V2/V3; at V1 every state of a mirror pair is in one kernel. A lost V3 kernel loses one shift and hence one V3 pair. Hang detectors (FID §5.3): stage timeouts V1 7,200 s, V2 43,200 s, V3 259,200 s (at least 7x the slowest measured need); a timeout is a kernel loss (§10). `stop_after_consecutive_failures` 10. Concurrency is an operating choice with no effect on any value (planned: four containers; with four, the eight V3 kernels take two waves, about 37 h, and the whole run set about 41-45 h of wall).

### 4.4 Budget
Cap **250 CPU h** of formal case wall (the summed stage wall of every formal case, kernel reruns included; smokes and the probe excluded, about 10.4 CPU h). Before every rerun and before the second V3 wave: `T = sum(case wall of finished formal kernels) + sum(estimates of every unfinished formal kernel, reruns included)`, written once as a budget record; if `T > 250 CPU h` the pushes stop and the decision goes to the user (not an automatic rule change); kernels never run are declared `--not-run KERNEL=BUDGET` citing the stop record and the outcome is `XV01_INCOMPLETE` (cause `BUDGET`). The cap admits one rerun of every V3 kernel of one wave (4 x 18.6 h) on top of the estimate. No new spending: local CPU only.

### 4.5 Case validity and matching (FID §5.4, unchanged)
A case is valid if every stage returns 0 (checkMesh exit 1 allowed only for the registered single concave-cell failure with fraction <= 0.08; the raw `Failed 1 mesh checks.` line is that allowed output, AGENTS.md) and simpleFoam reports `SIMPLE solution converged` before endTime. A case that ends at endTime without convergence, or whose mesh fails otherwise, is invalid: data loss for that state and shift, a result, never a rerun and never a FAIL. Matching per state and level: the mirror pairs where the state and the parent are valid at both members (whole-pair unit). A failed parent case removes that pair for every state of that level. **Minimum data** (finalist with the parent): V1 >= 12 valid pairs, V2 >= 3, V3 >= 3; the EX difference (§5.7) >= 12 pairs; NC >= 12 pairs. Below a minimum the rule that needs it is `UNRESOLVED_DATA`.

### 4.6 Smokes, environment replay and the V3 probe (after freeze 1, before freeze 2)
- **Environment replay** (V1): the parent at Halton 49 + (the FID formal case `V1_v18__parent_49p`, downforce 0.20139452023048948 N, drag 0.3444265555692308 N): the window means of both forces must equal the FID record within 1e-12 N, the iteration count and the cell count exactly. A difference stops the registration before freeze 2 (an environment defect; LOCAL-OF-01 found the pipeline bitwise deterministic). This parent force is already public; no finalist force is read.
- **V1 and V2 smokes**: the parent and the finalist at Halton 99 +; statuses only (stage return codes, cells, iterations, convergence, times; the force files are removed by the sanitiser before anyone reads them, as FID P0).
- **V3 probe**: the finalist at Halton 99 + with endTime 6000; status only. If it does not reach `SIMPLE solution converged` before 6000, endTime is raised to 12000 for **every** V3 case (parent and finalist alike; a template number, no force read) and the probe is repeated once; if it still does not converge, the registration stops (not frozen; a new plan). The probe's iteration count and wall update the §4.3 estimate in the budget record of freeze 2 (estimates, not rules).

### 4.7 Blinding
While the formal kernels run, only statuses, stage return codes, cell counts, iteration counts and times are read. Forces are read only by `analyze_xv01.py main`, after every formal kernel is verified valid or declared lost or not run. No value of any XV case changes a rule, a state, a shift, a mesh or the run set; the OpenFOAM meshes are judgment-only holdout data, never fed back into geometry, mesh or candidate selection.

## 5. Rules (computed by the frozen `scripts/xv01/analyze_xv01.py`, cross-checked by an independent checker)
Responses: downforce (objective) and drag (constraint), N, the window means of the runner. Differences are state minus parent at the same shift on the same level; the sign of the finalist's WaterLily difference is s = +1.

### 5.1 Estimators and the single-finalist uncertainty (requirements §2.1)
- **Unit.** For state x, level L and mirror pair j: `d_Lj = ((F_x,L,j+ - F_parent,L,j+) + (F_x,L,j- - F_parent,L,j-)) / 2`. The two mirror members are never counted as independent samples.
- **Level estimate.** `Delta_L = mean_j d_Lj` over the matched pairs J_L (n_L = |J_L|); `s_L` = the sample SD of the units (n_L - 1 dof).
- **Standard error.** `SE_V1 = s_V1 / sqrt(n_V1)` (FID §6.1, unchanged; dof 15 at 16 pairs). `SE_V2 = max(s_V2, f) / sqrt(n_V2)` and `SE_V3 = max(s_V3, f) / sqrt(n_V3)` with the floor `f` = the FID V2 pooled pair SD of the response (downforce `1.984576864434452e-4 N`, drag `1.3747177622390572e-4 N`; an OpenFOAM-internal within-design placement SD pooled over 12 designs, dof 12). `t_L = t_{0.95, n_L - 1}` (one-sided quantile; 1.753 at 16 pairs, 2.353 at 4 pairs).
- **Why this rule.** FID's V2 SE pooled the pair variance of about 12 designs and its V3 SE was the leave-one-out residual of the tier-A V3-on-V1 regression; neither exists for one finalist and neither is copied (the 1.45e-3 N regression residual mixes placement noise with design-to-design grid departure and is not a measurement SE). Each level therefore carries its own ensemble of 4 mirror pairs (option A′ of the preparation note: dof 3 on V2 and V3), and the floor prevents a spuriously small SE from a near-zero sample SD; SE = 0 is never inferred. The WaterLily `sigma_d` is never used on the OpenFOAM side.
- **Sampling meaning (stated, not assumed away).** The shifts are a fixed deterministic Halton panel of the X3 generator (per-axis magnitudes 0.5-4 mm, signs from separate Halton bases, exact mirror pairs), not an iid sample. `SE_L` is the empirical spread of the paired units over this panel, used as a placement-sensitivity scale with conventional t quantiles; no frequentist coverage is claimed. Because the bottom wall is fixed, the spread includes the ground-distance change of up to 4 mm; it is not pure mesh noise and not a physical attitude invariance. The force-window SD of a single case is an iterative-convergence diagnostic and is never used as a placement SE.

### 5.2 Gain floor (FID §8 mapping; requirements §2.4)
`x_OF,L = g_OF max(J_b,48, |F_bar_parent,L|)` with `g_OF = 0.012674959854238867` and `J_b,48 = 0.26577921974115387 N` (the SCREEN normalisation); `F_bar_parent,L` is the mean parent downforce over the level's valid XV cases. With the FID parent forces (0.20-0.21 N) the floor is `x_OF = 3.3687e-3 N` on every level. The normaliser is the larger of the two parent downforces (decision memo D3: it is the basis of the SCREEN §5.7 projection, the M2 `S_d` precedent `max(|J_b,48|, J_scale)`, and the stricter of the two readings by a factor 1.25-1.32; the OpenFOAM-normalised gain `Delta_L / |F_bar_parent,L|` is reported beside it). No other floor, no 0.68 %, no 2 %, no literal-E2 term is added.
- **GAIN_L** (L = V1, V2, V3): `PASS` if `Delta_L >= x_OF,L` and `Delta_L > 3 SE_L` (the FID tier form, as SCREEN G); `FAIL` if `Delta_L + t_L SE_L < x_OF,L` (bounded below the floor); else `UNRESOLVED_STAT`; missing level `UNRESOLVED_DATA`. Label `GAIN_RESOLVED_ABOVE_FLOOR_L` = `Delta_L - t_L SE_L >= x_OF,L`.

### 5.3 Drag non-increase (the SCREEN constraint, allowance 0; requirements §3b)
- **DRAG_L** (every level): with the drag unit estimate `D_L` and `SE_L`: `PASS` iff `D_L + t_L SE_L <= 0` (resolved non-increase); `FAIL` iff `D_L - t_L SE_L > 0` (resolved increase); else `UNRESOLVED_STAT` (labels `PASS_UNRESOLVED` for `D_L <= 0`, `VIOLATION_UNRESOLVED` for `D_L > 0`); missing `UNRESOLVED_DATA`. Every level must pass: a drag sign that depends on the mesh is not a confirmed constraint. Label `XV_DRAG_MESH_DEPENDENT` iff the three level labels are not all of one side of zero (point signs).
- The SCREEN drag decision (point sign on WaterLily, `PASS_RESOLVED` there) is not inherited; the WaterLily drag interval [-3.26e-3, -0.72e-3] N is reported beside the OpenFOAM values.

### 5.4 Fidelity rules inherited from FID §6.3 (applied to the finalist as a tier-A design)
- **G1 sign on every level**: `PASS` if `Delta_L > 0`; `FAIL` if `Delta_L < 0` and `|Delta_L| > 2 SE_L`; else `UNRESOLVED_STAT`; missing `UNRESOLVED_DATA`.
- **G2 above 3 sigma on V1**: `PASS` if `Delta_V1 > 3 SE_V1`, else `UNRESOLVED_STAT`.
- **G3 spread V1-V2**: `m = (Delta_V1 + Delta_V2) / 2`, `R = |Delta_V1 - Delta_V2|`, `sigma_R = sqrt(SE_V1^2 + SE_V2^2)`: `PASS` if `R <= 0.5 |m|`; `FAIL` if `R - 2 sigma_R > 0.5 |m|`; else `UNRESOLVED_STAT`.
- **G4 retention on V1**: `rho = Delta_V1 / Delta_32` with the SCREEN confirmation `Delta_32 = 1.0774190511977672e-2 N`, `SE_eff = 2.9231082773713274e-4 N`, `t = t_{0.95, min(P, n_V1) - 1}` = 2.353 (P = 4): `FAIL` if `Delta_V1 + t SE_V1 < 0.5 (Delta_32 - t SE_eff)` (= 5.043e-3 N at the registered values, minus `t SE_V1`) or `Delta_V1 - t SE_V1 > 2 (Delta_32 + t SE_eff)`; `PASS` if `0.5 <= rho <= 2.0` (`Delta_V1 >= 5.387e-3 N`); else `UNRESOLVED_STAT`. `rho_V2`, `rho_V3` reported.
- **G5 constraints**: (a) geometry — established at P0 (§3.2; PASS before any case, else no freeze); (b) drag fidelity — eligible only where `|Delta_drag,32| >= 2e-3 N` and `> 3 SE_eff`; the finalist's `|-1.994e-3| < 2e-3 N`, so G5b is `PASS` with the note "not tested" (label `G5B_NOT_TESTED`), which carries no constraint information: compliance is decided by §5.3 only (requirements §3.1).

### 5.5 V3 consistency for one finalist (adaptation of the FID G3-set; requirements §2.2)
FID's G3-set judged the slope of `Delta_V3` on `Delta_V1` through the origin across 8 tier-A designs against [0.6, 1.67] (the two-level G3 tolerance). For one finalist it is judged on the common pairs `J = J_V1 ∩ J_V3 ⊆ {81, …, 84}` (|J| >= 3, else `UNRESOLVED_DATA`) with the margin units `lo_j = d_V3,j - 0.6 d_V1,j` and `hi_j = 1.67 d_V1,j - d_V3,j`: `PASS` if `mean(lo) >= 0` and `mean(hi) >= 0` (the point ratio of the common-pair means lies in [0.6, 1.67]; the FID point-pass form); `FAIL` if `mean(lo) + t SE(lo) < 0` or `mean(hi) + t SE(hi) < 0` (resolved outside on either side), with `SE(·) = max(sd(·), f_DF) / sqrt(|J|)`, `t = t_{0.95, |J| - 1}`; else `UNRESOLVED_STAT`. Never a silent drop of V3: a missing V3 is `UNRESOLVED_DATA` and blocks `XV01_PASS`. The ratio `Delta_V3,J / Delta_V1,J`, `Delta_V3 / Delta_V2` and the finalist's `|Delta_V3 - Delta_V2| / |F_bar_parent,V3|` (to compare with `S_d,OF`) are reported. This is a new single-design adaptation, stricter than the set rule (one design is judged alone; FID's camber -19.7 had a V3/V1 ratio of 1.52 inside a set slope of 1.086); it is not called the FID rule.

### 5.6 Chain controls
- **NC** (FID §6.6, OpenFOAM form): `z = |Delta_roll,V1 - (-6.614761397334482e-4)| / sqrt(SE_roll,V1^2 + (5.792182318004298e-5)^2)`; `CONSISTENT` if `z <= 3.5`, else `NOT_CONSISTENT` → `XV01_INVALID`; fewer than 12 valid roll pairs → `MISSING` (no outcome of `XV01_PASS`; §5.9).
- **Determinism**: the last case of kernel `v1_1` is a repeat of the parent at 81 + (state `v18__parent__repeat`, the parent's bytes under its own name); both window means must equal the parent's at 81 + within 1e-12 N, else `NONDETERMINISM` → `XV01_INVALID`; a repeat that is invalid or missing leaves the check `NOT_JUDGED` (reported).
- The environment replay of §4.6 is a precondition of freeze 2, not an outcome rule.

### 5.7 STL extraction control EX (FID §6.6 form, for the finalist; outcome-relevant here)
Per V1 mirror pair `u_j = [pair mean of (F_r4(f) - F_r4(parent))] - [pair mean of (F_r8(f) - F_r8(parent))]`; `delta_EX = mean(u)`, `SE_EX` from the pairs; tolerance `0.1 |Delta_V1|` (r = 8). `EXPORT_INSENSITIVE` (→ PASS) if `|delta_EX| + 2 SE_EX <= tolerance`; `EXPORT_SENSITIVE` (→ FAIL, cause `EXPORT`) if `|delta_EX| - 2 SE_EX > tolerance`; else `EXPORT_UNRESOLVED` (→ `UNRESOLVED_STAT`). FID found `|delta_EX|` of 6e-6 N against tolerances of 8e-4 N for camber -19.7 and reflex -29.3; the rule is expected to pass and is included because the extraction control is part of #65's scope and FID's result does not cover an unobserved shape.

### 5.8 Descriptive controls (labels, no effect on the outcome)
- **`REF_CONSISTENT`** (W4 camber -19.7 on V1): `|Delta_V1,W4 - 7.957e-3| <= 3 sqrt(SE_V1,W4^2 + (3.2e-4)^2)` against FID's V1 value (Halton 49-64); a reproduction of a known design difference at new shifts; an inconsistency is reported, not a chain failure (the NC is the chain control).
- **`OF_OPT_VS_MANUAL` / `OF_OPT_VS_RANDOM`** (V1): per pair `e_j = d_f,j - d_c,j` for c = M, R-best; `OPT_BEATS_*` if `mean(e) - t SE(e) > 0`, `*_BEATS_OPT` if `mean(e) + t SE(e) < 0`, else `*_UNRESOLVED`; their V1 drag differences reported. One draw each; these controls also give two more camber-heavy OpenFOAM V1 retentions (M camber -19.7, R-best camber -28.656, both with SCREEN confirmation values).

### 5.9 Outcome (evaluation order)
1. **Parent minimum data** (V1 >= 12, V2 >= 3, V3 >= 3 valid pairs for the parent): else `XV01_INCOMPLETE` if a declared lost or not-run kernel caused it (cause `KERNEL_LOSS` / `BUDGET`), otherwise `XV01_UNRESOLVED` (cause `DATA_PARENT`).
2. **Chain controls**: NC `NOT_CONSISTENT` or `NONDETERMINISM` → `XV01_INVALID` (causes `NC`, `NONDETERMINISM`).
3. **Resolved failures**: any `FAIL` among GAIN_V1/V2/V3, DRAG_V1/V2/V3, G1_V1/V2/V3, G3, G4, V3 consistency, EX → `XV01_FAIL`; the cause list contains every applicable cause in this order: `GAIN_BELOW_FLOOR`, `DRAG_VIOLATION`, `WL_OF` (G1 on V1, G4), `OF_MESH` (G1 on V2/V3, G3, V3 consistency), `EXPORT`.
4. **Pass**: GAIN, DRAG and G1 on every level, G2, G3, G4, G5 (a, b as §5.4), V3 consistency and EX all `PASS`, NC `CONSISTENT` → **`XV01_PASS`**.
5. **Otherwise**: `XV01_INCOMPLETE` if any missing value traces to a declared lost or not-run kernel (cause `KERNEL_LOSS` / `BUDGET`); else `XV01_UNRESOLVED` with the cause list of every `UNRESOLVED_STAT` / `UNRESOLVED_DATA` rule and `NC_MISSING`.
Nothing in steps 1-5 is repaired from a value: no added shift, pair, level, state or extension round; no V3 removal; no rule variant per level or per pair.

`XV_OF_GAIN_CONFIRMED` (secondary) = GAIN and DRAG `PASS` on every level and NC `CONSISTENT`: it separates "the OpenFOAM improvement and constraint hold on every mesh" from the fidelity and consistency rules, so that a `XV01_FAIL` caused only by `WL_OF` / `OF_MESH` / `EXPORT` is legible. It changes no outcome.

### 5.10 Reported for the finalist (descriptive)
Every level estimate with SE, `s_L`, units, n_L and the matched pairs; the relative gains `Delta_L / J_b,48` and `Delta_L / |F_bar_parent,L|`; `rho_V1/V2/V3` for downforce and drag; `Delta_V2 / Delta_V1`, `Delta_V3 / Delta_V1` (all pairs and common pairs); the parent's absolute forces per level; the per-shift differences; the WaterLily-to-OpenFOAM component reading of §7.3 recomputed with the measured values (which component retained how much is not identifiable from one design; the reading is labelled as a model); the EX numbers; the controls of §5.8.

## 6. Coefficients
| Coefficient | Value | Source | Use |
| --- | --- | --- | --- |
| g_OF | 0.012674959854238867 | FID §8 (`2 max(S_d, S_d,OF)`) | §5.2 |
| J_b,48 | 0.26577921974115387 N | FID / M2 / SCREEN | §5.2 normaliser |
| x_OF (planning) | 3.3687e-3 N | g_OF J_b,48 (J_b,48 > every FID OpenFOAM parent downforce) | §5.2 |
| Delta_32, SE_eff (downforce) | 1.0774190511977672e-2, 2.9231082773713274e-4 N | SCREEN `xv_handoff.json` confirmation f32 | G4 |
| Delta_32 (drag), SE_eff | -1.9938669864582037e-3, 5.397769910001766e-4 N | same | G5b eligibility, report |
| floor f (downforce / drag) | 1.984576864434452e-4 / 1.3747177622390572e-4 N | FID V2 `sigma_pool_n` (dof 12) | SE_V2, SE_V3, V3 consistency |
| NC reference OF | -6.614761397334482e-4 N, SE 5.792182318004298e-5 | M2 U3 (FID §7.1) | §5.6 |
| V3 band | [0.6, 1.67] | FID §6.3 (two-level G3 tolerance) | §5.5 |
| G4 band | [0.5, 2.0] | FID §6.3 | §5.4 |
| EX tolerance | 0.1 \|Delta_V1\| | FID §6.6 | §5.7 |
| W4 reference | 7.957e-3 N (SE 3.2e-4) | FID V1 | `REF_CONSISTENT` |
| environment replay | 0.20139452023048948 / 0.3444265555692308 N | FID `V1_v18__parent_49p` | §4.6 |
The analyzer re-reads the SCREEN handoff, the FID and M2 analysis files by SHA-256 and refuses if any value differs.

## 7. Expected pass probability, stated before any case is funded (SCREEN §7)
Planning only; no outcome effect. Computed by `docs/evidence/xv01_2026_10_31/pass_probability.py` (seed 20261031, 20,000 replicates) from the visible SCREEN and FID records; output `pass_probability.json`.

### 7.1 What SCREEN §5.7 implies
§5.7 projects the OpenFOAM V1 gain as `0.655 (Delta_32 - b_K)` (central, `b_K = 1.03e-3 N`) and `0.57 (Delta_32 - b_K,upper)` (pessimistic, `b_K,upper = 2.67e-3 N`): 6.38e-3 N (2.40 % of J_b,48) and 4.62e-3 N (1.74 %). With a predictive SD of `sqrt(sigma_disc^2 + (retention SE_eff)^2 + SE_V1^2)` (6.4e-4 N central with `sigma_disc = 5.61e-4`; 1.48e-3 N pessimistic with the upper 1.45e-3) the probability that the **V1 gain clears `x_OF = 3.369e-3 N`** is **1.00 central and 0.80 pessimistic** (0.92 pessimistic under the OpenFOAM-parent normalisation). This is the probability of one rule (GAIN_V1); §5.7 does not project drag, V2, V3, retention or consistency.

### 7.2 The composed gate (component model)
The SCREEN response surface splits the finalist's WaterLily response at u = (0.05, -1.5, 0.55) into parts (N, downforce / drag): camber (linear + quadratic) +1.660e-2 / +3.009e-3; reflex -7.739e-3 / -6.024e-3; pitch +2.081e-3 / +1.521e-3; cross terms -8.39e-4 / -4.1e-5; rest (measured minus surface) +6.66e-4 / -4.58e-4. The WaterLily drag of -1.99e-3 N is a cancellation of +4.5e-3 N (camber, pitch) against -6.0e-3 N (reflex). Each part is carried to V1/V2/V3 with the OpenFOAM/WaterLily ratio vector of one FID design of its family (bootstrap: camber -11.3 or -19.7; pitch +0.7 or -0.7; reflex -29.3; the rest and cross terms with the tier-A through-origin slope per level), times log-normal noise (design spread 0.08; an extra common camber factor 0.10 for the extension), plus planning measurement noise (V1 2.5e-4 / 1.0e-4 N, V2 and V3 1.0e-4 / 0.7e-4 N); every rule of §5 is applied. Three variants: no selection shift; the WaterLily gain reduced by `b_K` (central); by `b_K,upper`.

| Variant | P(XV01_PASS) | P(XV01_FAIL) | P(UNRESOLVED) | P(`XV_OF_GAIN_CONFIRMED`) | median Delta V1 / V2 / V3 (N) | median drag V1 / V2 / V3 (N) |
| --- | --- | --- | --- | --- | --- | --- |
| no shift | 0.22 | 0.52 | 0.26 | 0.44 | 7.8e-3 / 5.9e-3 / 9.5e-3 | -1.10e-3 / -1.10e-3 / -1.3e-4 |
| `b_K` central | 0.17 | 0.59 | 0.24 | 0.40 | 7.2e-3 / 5.2e-3 / 8.7e-3 | same |
| `b_K` upper | 0.08 | 0.74 | 0.18 | 0.26 | 6.1e-3 / 4.2e-3 / 7.6e-3 | same |

Per rule (pass / fail, `b_K` central): GAIN V1 0.99 / 0.00, V2 0.94 / 0.04, V3 1.00 / 0.00; **DRAG V3 0.48 / 0.32**, DRAG V1 0.89 / 0.05, V2 0.95 / 0.02; **V3 consistency 0.64 / 0.22** (mostly the upper side, V3/V1 > 1.67); **G3 0.78 / 0.13**; G4 0.82 / 0.07.

### 7.3 Reading
- **The binding risk is the drag constraint on V3, not the gain floor.** On the FID descriptive values the OpenFOAM drag retention of negative camber is high on V3 (camber -11.3: V1 0.56, V2 0.53, V3 0.92; camber -19.7: 0.84, 0.67, 0.84; below the G5b tested size, so FID reported but never judged them), while reflex -29.3 retains 0.69 / 0.62 / 0.59 and pitch +0.7 0.84 / 0.73 / 0.65 of its WaterLily drag. The camber drag that the reflex trim cancels in WaterLily is therefore kept more on V3 than the reflex credit: the model puts the V3 drag difference at about -1e-4 N, a coin flip at the resolution of the OpenFOAM SE. This is the disclosure "drag neutrality relies on an untested OpenFOAM camber drag retention", quantified.
- **The second risk is mesh consistency**: camber -19.7 had the largest V3/V1 ratio of the FID tier A (1.52) and the lowest V2 retention (0.52); a camber-dominated finalist projects V3/V1 of about 1.2-1.8 and a V1-V2 spread near the G3 tolerance.
- **The gain itself is robust**: every GAIN_L passes with probability >= 0.94 except V2 under the upper bias (0.74). `XV_OF_GAIN_CONFIRMED` is limited by the V3 drag.
- **Stated pass probability.** Before funding, XV-01 states: the §5.7-implied probability for the gain floor is 1.00 central / 0.80 pessimistic; the projected probability of `XV01_PASS` under the registered composed gate is **about 0.2 (0.08-0.22 over the three variants)**, and `XV01_FAIL` (0.52-0.74) is more likely than `XV01_PASS`, mainly through `DRAG_VIOLATION` on V3 and `OF_MESH`. The model is a planning device (one surrogate decomposition with `RS_FIT_POOR`, bootstrap over two to three FID designs per family, independent planning noise); it is not a measurement and changes no rule.

### 7.4 What a non-PASS would still decide
A `XV01_FAIL (DRAG_VIOLATION)` measures, for the first time, the OpenFOAM drag retention of a camber-extension design whose WaterLily drag neutrality is a cancellation, which is the constraint-transfer question M4 (#66) needs answered; `OF_MESH` measures the V3 behaviour of the camber extension; `WL_OF` measures the selection attenuation. A PASS is the first L2 statement of the project. Every outcome is informative and the run set is the same for all of them.

### 7.5 Funding decision (recorded at freeze 2, not here)
The cost is about 164 CPU h of the local host (no spending, no Kaggle quota), about two days of wall at four containers. The registrant's proposal is to fund the full run set at freeze 2 on the stated probability, because the non-PASS outcomes answer the M4 constraint-transfer and extension-fidelity questions that no other registered study answers. The decision is recorded in `freeze2.json` with the pass-probability record's SHA-256; a decision not to fund closes XV-01 as `XV01_NOT_FUNDED` (no outcome; M4 decides with SCREEN's L1 result). Rejected: making the rules easier because the probability is low (§14).

## 8. Consequences
- `XV01_PASS`: the L2 statement for this finalist at Re 80 (§1 ceiling); recorded in STATE.md and phase_plan; M4 (#66) decides with it. Flags unchanged (`shape_update_allowed=false`).
- `XV01_FAIL` (any cause): recorded with the cause list and `XV_OF_GAIN_CONFIRMED`; #65 is closed with the result and M4 decides. No finalist retuning, no other SCREEN candidate verified in its place (the four proposals and R-best are not substitutes), no second SCREEN round, no rule change.
- `XV01_UNRESOLVED`, `XV01_INCOMPLETE`, `XV01_INVALID`: no extra shift, pair or level within this registration. **At most one re-registration in total for #65** (fresh Halton indices >= 101, no pooling with this study's cases, rules no weaker than these, the same finalist), after an explicit recorded decision; otherwise M4.
- Flags: unchanged in every case.

## 9. What was visible before this registration, and what was chosen with it
- All of SCREEN-01 (the finalist's WaterLily confirmation forces and labels, the controls, `rs.json`, the §5.7 projection) and all of FID-01 (every OpenFOAM value of the 17 FID states on V1, of 12 on V2 and of 9 on V3, incl. the parent's absolute forces, the descriptive camber drag values and the V2 pooled SD) and M2 (U3).
- **Chosen with these values visible:** the normaliser `max(J_b,48, |F_parent|)` (the stricter reading; FID parent forces visible); the SE floor (FID V2 pooled SD); 4 pairs on V2/V3 (the preparation note's A′); the drag rule on every level with resolution; the two-sided V3 consistency adaptation; the inclusion of EX, REF, M and R-best; the §7 model. None was chosen to raise the pass probability: §7 shows every choice that could be made looser (the OpenFOAM-parent normaliser, a point-sign drag rule, drag on V1 only, a one-sided V3 rule) would raise it, and none of them is taken.
- No OpenFOAM value of the finalist, M, R-best at any shift, of any state at Halton 81-99, or of any XV mesh exists.

## 10. Freeze, rerun, amendment and stopping rules (fail-closed)
- Order: §2. Freezes 1 and 2 and the written-once analysis are committed, pushed and commented on #65 before the runs they determine.
- **Kernel loss (FID §10 objective causes):** a kernel whose `local_run.json` has a non-zero return code or `dpkg_after_matches_lock` false, that is stopped by a host or Docker failure, or with a case whose stage hits the hang-detector timeout. **One identical rerun per kernel** (same criteria bytes, same image); the first valid output is authoritative; both are archived. A kernel lost again is declared `--lost KERNEL=ID` with its criteria SHA-256; its cases are data loss. A per-case mesh failure, non-convergence or unexpected value is a result (§4.5), never a reason to rerun. No third attempt; a timeout is never raised after freeze 2.
- **Engineering defect found by a smoke or the probe before freeze 2:** fixed and re-frozen (an amendment of freeze 1 with diff and reason); rules, states, shifts and bytes never change; the endTime change of §4.6 is the only registered template change.
- **Amendment after freeze 2 (`REGISTERED_AMENDED`):** only for a defect that prevents a pre-specified quantity, filed on #65 before the analysis reads any force, never touching a rule, a state or a shift; the original outcome (or `INCOMPLETE`) is kept beside it.
- **Analyzer-defect protocol:** freeze 1 contains synthetic-output tests of every §5.9 branch and the independent checker; the analysis is cross-checked before writing; after a write it stands.
- Stopping: one run set (§4.2), no stage repeated, no extension round, the §4.4 cap, a second loss of the same kernel is final.

## 11. Freeze content
**Freeze 1** (`freeze1.json`): source commit; SHA-256 of this registration, `decision_memo.md`, `plan_review/adoption.md`, the source-review adoption record, `scripts/xv01/*.py`, `tests/xv01/*.py`; the reused code (`fid01_build.py` level/shift/template functions, `prepare_kaggle_xfid_gridphase_x3.py`, `unc01_u3_prepare.py`, `geom02_canonical.py`, `local_openfoam.py`, the X3 formal runner and the Round 5 template, `screen01_pool.py` with its dependency fingerprint); the P0 records (§3.1 handoff verification, §3.2 geometry re-evaluation, §3.3 export with every STL SHA-256 and X1 record); the case lists and criteria of every formal kernel (`of_criteria_sha256`); `pass_probability.json`; the SCREEN, FID and M2 record SHA-256; the lock and image identity; python and numpy versions.
**Freeze 2** (`freeze2.json`): freeze 1's SHA-256; the sanitised smoke and probe records, the environment replay record, the V3 endTime decision (§4.6), the criteria of every formal kernel as they will run, the §4.4 budget record, the funding decision (§7.5).
The analyzer refuses to run without these records and accepts exactly the frozen criteria set (minus declared lost and not-run kernels). Nothing in §1-§9 changes at freeze 2.

## 12. Plan review record
(revision 1)

## 13. Source review record
(revision 2)

## 14. Deviations from FID-01, the requirements note, the preparation note and #65 (inventory)
| Source text | Here | Stricter / looser / not in source | Decided by |
| --- | --- | --- | --- |
| FID §6.1: V2 SE from the pair SD pooled over about 12 designs (2 pairs per design) | own 4 pairs (dof 3) with the FID pooled SD as a floor | not in source (single finalist); never smaller than the FID V2 SE at n = 4 | requirements §2.1, preparation A′ |
| FID §6.1: V3 SE = leave-one-out residual SD of the tier-A V3-on-V1 regression, one shift | own 4 pairs (8 shifts, dof 3) with the floor | not in source; the 1.45e-3 N residual is not copied | requirements §2.1, handoff note |
| FID §6.3 G3-set (slope across tier A in [0.6, 1.67]) | per-design margins on the common pairs, point-pass, resolved-fail on either side | stricter (one design alone); a new adaptation | requirements §2.2 |
| FID §6.8 registered extension | none | stricter (UNRESOLVED is terminal within XV) | registrant |
| FID §8: OF minimum gain `2 max(S_d, S_d,OF)`, normaliser unstated | `x_OF = g_OF max(J_b,48, |F_parent,L|)` | the stricter of the two readings | registrant |
| SCREEN D: point sign `Delta_drag <= 0`, allowance 0 | resolved non-increase on every OpenFOAM level | stricter (unresolved → not PASS; any resolved violation → FAIL) | requirements §3b, §4 |
| FID §6.6 EX consequence (only on SENSITIVE / UNRESOLVED) | EX on the finalist always, outcome-relevant | stricter | #65 scope |
| requirements §4 terminal labels | adds `XV01_INVALID` (chain control) | defined | registrant |
| FID §5.2 V1 shifts 49-64, V2 49-50, V3 49 + | V1 81-96, V2/V3 81-84 (both mirror members) | fresh shifts (holdout) | registrant |
| preparation note: options A (80 cases) / A′ (96) | A′ plus V1 controls (NC, W4, M, R-best, r = 4) and the V1 determinism repeat: 289 cases | A′ chosen before any run; A rejected (dof 1) | registrant |
