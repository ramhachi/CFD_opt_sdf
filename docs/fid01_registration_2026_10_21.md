# FID-01 (#62, M3a) registration: fidelity go/no-go of the central hypothesis on fixed v18 designs, without an optimizer

Status: **PLAN, revision 3 (2026-10-21): revision 1 (`0ac6107f`) after the PROC-01 plan review (three independent adversarial reviews: numerical 16, controls 14, strategy 14 findings; every finding and its decision in §12a), with the source-review changes (§13).** Freeze 1 (plan, sources, designs, OpenFOAM V1 inputs) follows. The study is `REGISTERED_FROZEN` from freeze 2 (§11), before the first formal WaterLily kernel or OpenFOAM case. No flag changes: all qualification flags stay false, `shape_update_allowed=false`. Integration branch `codex/kaggle-batch-migration` (not main). Where this text and `scripts/fid01/analyze_fid01.py` disagree, this text governs and the disagreement is an analyzer defect.

Inputs (registered or `EXPLORATORY_COMMITTED`, binding from freeze 1):
- M2 UNC-01 `M2_COMPLETE` (`docs/evidence/unc01_2026_10_20/analysis.json`, SHA-256 `ee71c6d6…`): the coefficients of §7 (re-read and checked by the analyzer).
- v18 parent `docs/evidence/v18_genesis_2026_10_19/` (state `e7376e35…`, phi Fortran `29d53b23…`), generator `scripts/v18_plate.py` (`4641c2f4…`, not edited); MODE-01 v18 basis and its gate stack (`scripts/mode01_v18_prescreen.py`).
- WIDTH-RULE decision proposal D-1 (`docs/width_rule_decision_2026_10_20.md`), adopted here (§3.3).
- Harness v1.1 with JOB-02 per-run placement; LOCAL-OF-01 `LOCAL_ENV_PASS_BITWISE` for the U/X3 OpenFOAM pipeline (lock `infra/local_openfoam/local_openfoam_lock.json` `c105b7df…`).

## 1. Question, hypothesis and claim ceiling
**Central hypothesis** (`docs/architecture_effectiveness_2026_09.md` §9, E2; roadmap M3a): a shape change that WaterLily (flow_32, placement-phase mean) shows as a difference large enough to act on persists in independent body-fitted CFD (OpenFOAM, three meshes): the same sign on every mesh, at least half of the magnitude and at most twice it, robust across meshes, constraints confirmed. M3a tests it on **fixed, pre-registered designs without an optimizer**; M3b (SCREEN-01 #64, XV-01 #65) starts only on `FID01_GO`.

Outcomes (§6.7): `FID01_GO`; `FID01_NO_GO` with a cause (`WL_OF` or `OF_MESH`); `FID01_INCONCLUSIVE_DESIGN_SET`; `FID01_INCONCLUSIVE_PRECISION`; `FID01_INCOMPLETE`; `FID01_INVALID`. Registered secondary labels (no effect on the outcome): tier B (`TIER_B_*`, it sets the M3b minimum gain), support (`SUPPORT_*`), flow_48 confirmation (`R3_*`), extraction control (`EXPORT_*`), heave sub-label, aggregate slope and rank concordance.

Claim ceiling: Re = 80 reduced-laminar WaterLily (Kaggle T4) against laminar steady OpenFOAM v2512 (local Docker, three snappy meshes, not grid-converged), for the registered designs of one analytic parent at one amplitude each (two for camber and heave), uncertified geometry, in-plane placement phases (z, the ride height, is not sampled; heave designs move the body against the z lattice, §6.9). A statement about **differences** of pre-registered designs. It is not a statement about a design an optimizer selects: an argmax over WaterLily favours designs WaterLily over-predicts; XV-01 verifies selected candidates. Not physical downforce, not FSAE, not high Re.

## 2. Stages (PROC-01)
| Stage | Content | Status |
| --- | --- | --- |
| P0 | design prescreen (geometry, `fid01_designs.py prescreen`) and X1 STL export selection (`select`); OpenFOAM V2/V3 timing probe of the parent (statuses, cells, times; §9); operating characteristics of the rules (`fid01_oc.py`, §6.10) | before freeze 1, no force of an M3a design |
| P1 | plan rev. 1 → three-angle plan review → this rev. 2 | done |
| P2 | sources → one source review → **freeze 1** (commit, push, #62 comment) | |
| S1 | WaterLily harness smoke of the flow_32 campaign (parent, phase 7) and `verify --smoke`; OpenFOAM development smoke on V1 and V2 (the parent, the first design and on V1 the parent's r = 4 STL, at Halton 80 +, a shift outside every registered set; archived only through the registered sanitiser `unc01_u3_prepare.strip_smoke`, statuses only); the V3 probe is the V3 smoke and decides the §5.3 contingency; harness prerun freeze → **freeze 2** | engineering under freeze 1 |
| F1 | the four flow_32 kernels pushed and the V1 kernels (designs, NC, EX) started, unconditionally | `REGISTERED_FROZEN` |
| D | `analyze_fid01.py dset`, written once, from the verified flow_32 tables only: tiers and the run sets of V2, V3 and flow_48 (§6.2) | registered step |
| S2 | the flow_48 campaign (`fid01_f48`) built from d_set, its harness smoke and prerun freeze; V2/V3 inputs → **freeze 3** | engineering |
| F2 | the flow_48 kernel pushed (budget rule §4.3) and the V2/V3 kernels started, unconditionally | `REGISTERED_FROZEN` |
| A | one analysis (`analyze_fid01.py main`), written once; only if it returns `EXTENSION_REQUIRED`, the §6.8 extension runs and `analyze_fid01.py extension` is written once | `REGISTERED_FROZEN` |

The staging (strategy S5, controls C10) keeps the OpenFOAM cost of designs that cannot enter a decision off the critical path. d_set reads WaterLily only and its rules are fixed here, so it cannot steer an OpenFOAM value; the analyst sees the WaterLily differences before the V2/V3 runs, which is disclosed.

## 3. Designs and controls
### 3.1 Construction
Every design is a dict `{mode: amplitude}` built by `scripts/fid01/fid01_designs.py` on the v18 parent:
- **Analytic modes** heave, pitch, camber, reflex, twist, sweep (units and signs of `v18_plate.UNITS`) are applied **jointly** to the plate parameters and `v18_plate.plate_phi` is evaluated once, so a combination is again an exact plate SDF (no linear superposition of phi differences); a single mode reproduces `v18_plate.mode_phi` bit for bit (test).
- **Support designs**: one-sided Gaussian normal offsets of `mode01_modes` on the v18 parent: `bump_lower` (ground-facing surface, sigma 0.125 m) and `bump_upper` (upward-facing, 0.125 m) are narrow; `bump_lower_s300` (ground-facing, 0.3 m) is mid support. They are asymmetric on purpose (M2's symmetric s050 moved downforce by 5.6e-6 N).
- Only active nodes change; the evaluated bytes are the harness state model `construct_state(parent, d / max|d|, 1000 max|d| mm, +1)`, i.e. what the WaterLily runner regenerates and what the STL is exported from.

### 3.2 Slots and the admissibility rule (geometry only, fixed before any solver run)
**The design of a slot is its first candidate (in the listed order) whose harness bytes pass the MODE-01 v18 gate stack** (13 GEOM-02 v2 gates including the registered R0 `min_feature_width`, P22-v2, the 10 % smoothed-volume band, clearance; unmeasured counts as fail) **and whose r = 8 STL passes the X1 practical export gate** (double and float32). A slot without an admissible candidate is empty. `fid01_build.py states` refuses unless at least 12 slots are filled from at least 4 families.

| Slot | Stratum / family | Candidates (in order) | Note |
| --- | --- | --- | --- |
| W1 | wide / rigid | heave -31.1 mm (toward the ground) | |
| W1b | wide / rigid | heave -13.7 mm | second amplitude of W1 |
| W2 | wide / rigid | heave +31.1, +13.7 mm | |
| W3 | wide / rigid | pitch -0.7 deg | |
| W8 | wide / rigid | pitch +0.7 deg | sign pair of W3 (replaces rev. 1's twist -1.1, known below Delta_min from U1, §9) |
| W4 | wide / section | camber -19.7 mm | |
| W4b | wide / section | camber -11.3 mm | second amplitude of W4 |
| W5 | wide / section | camber +19.7, +11.3 mm | |
| W6 | wide / section | reflex -29.3, -19.7 mm | |
| W7 | wide / span | twist +2.3, +1.1 deg | |
| C1 | wide / combination (section x section) | camber {-19.7, -11.3} x reflex {-29.3, -19.7, -11.3} | |
| C2 | wide / combination (rigid x rigid) | heave {-31.1, -13.7} x pitch {+1.3, +0.7} | |
| C3 | wide / combination (rigid x section x span) | heave {-31.1, -13.7} x camber {-19.7, -11.3} x twist {+2.3, +1.1}; then (heave -13.7, reflex -19.7, twist +2.3), (heave -13.7, reflex -11.3, sweep +11.3) | fallbacks added in rev. 3 |
| C4 | wide / combination (rigid x section x span) | pitch {-1.3, -0.7} x reflex {+29.3, +19.7, +11.3}, sweep +11.3 | |
| C5 | wide / combination (section x span) | camber {+19.7, +11.3} x (twist -1.1 with / without sweep -11.3); then (reflex +19.7, twist -1.1), (camber +11.3, sweep -11.3) | fallbacks added in rev. 3 |
| N1 | narrow / local | bump_lower +20, +15, +10, then -15, -10 mm | inward fallbacks added in rev. 3 |
| N2 | narrow / local | bump_upper +20, +15, +10, then -15, -10 mm | inward fallbacks added in rev. 3 |
| N3 | narrow / local | bump_small (ground-facing, sigma 0.05 m) +20, +15, +10 mm | restored in rev. 3 (the narrowest support) |
| M1 | mid / local | bump_lower_s300 +15, +10 mm | |

Products are expanded with the first factor slowest. Amplitudes are MODE-01 ladder values (incommensurate with h). The candidate order puts the larger amplitude first: this deliberately favours designs large enough to enter the decision tier (disclosed as a design choice, controls C3). **Excluded:** the M2 states with an OpenFOAM value (pitch ±3.1, pitch +1.3, reflex +29.3, D0 +3, s050 -5): their fidelity is known; sweep and twist -1.1 alone (U1 single-phase differences about 1e-4 N and -1.2e-3 N, below Delta_min); dihedral and twist_anti (no gate-clean point). Families: rigid {heave, pitch}, section {camber, reflex}, span {twist, sweep}, combination (two or three families jointly), local (support designs). Support (MODE-01 definition) is recorded per design; the stratum is fixed by the slot (C4's support, 0.49, is just below MODE-01's single-mode wide threshold 0.5; it is a combination of wide modes and stays wide, disclosed). The selection result is `docs/evidence/fid01_2026_10_21/designs.json`; `states` re-derives it byte for byte at freeze 1.

### 3.3 Width rule (UNC-01 TODO 0; WIDTH-RULE D-1 adopted)
Admissibility uses the registered R0 at the native placement, unchanged (as M2). With fixed designs the R0 artefact only selects which candidate of a slot is used; it does not steer a search. R3 (opening defect of the trilinear body) is a descriptive column. R0 is placement-dependent (WIDTH-RULE): a design's R0 status at the WaterLily phases and OpenFOAM shifts is not evaluated (disclosed). M3b's width rule is not decided here.

### 3.4 Controls
- **Negative control NC (x-translation `v18__roll_p25`)**: the parent translated by exactly one flow_32 cell and one lattice cell (the M2 state, same bytes). It is not null: M2 measured -1.648e-3 N (SE 8.53e-5, P = 6) on flow_32 and -6.61e-4 N (SE 5.79e-5, 16 pairs) on OpenFOAM V1. Run on flow_32 (all phases) and V1 (all pairs) and judged **against those values** (§6.6). It replicates a measured difference on new phases and shifts, i.e. it checks the measurement chain (state construction, pairing, placement, export, meshing), not a design-specific fault.
- **Chain check (part of G5a)**: for every judged design, the STL volume change against the parent STL must agree with the SDF smoothed-volume change within 1 percentage point; it fails when the exported surface does not represent the SDF the WaterLily body samples.
- **Extraction control EX (STL export)**: the parent, W4 and W6 (the slot designs) are also exported with marching-cubes refinement r = 4 instead of the registered r = 8 (X1 gate applied; the frozen extractor supports r in {1, 2, 4, 8}, so the control halves the export resolution rather than doubling it, a pre-freeze engineering change) and run on V1 at every V1 shift (the level where G2/G4 decide). `delta_EX = (F_r4(i) - F_r4(parent)) - (F_r8(i) - F_r8(parent))` by mirror pairs, three labels (§6.6). A difference insensitive to halving the export resolution is taken as insensitive to the export at r = 8 (a convergence assumption, stated).

## 4. WaterLily design
### 4.1 States and phases
- flow_32 (decision grid): parent, every design and NC, at phases **k = 7, 8, 9, 10** (the R2 sequence of M2, `f_k = frac(k (0.7548776662, 0.5698402910))`, disjoint from M2's k = 1..6 and U1's k = 0). All states share the phases (R4). P = 4.
- flow_48 (confirmation, R3): the d_set run set (§6.2: parent, every tier-B design, the tier-A design with the largest positive and the one with the largest negative flow_32 difference) at phase **k = 7**, one kernel, second harness campaign `fid01_f48` (its own smoke and prerun freeze, freeze 3). A sign flip between flow_32 and flow_48 is implausible for large differences (M2: ratio 0.98 [0.96, 1.00]); the informative designs are the small ones (strategy S8).
- Placement as M2: phase k moves `W4_CANONICAL_ORIGIN_M` by (f_kx, f_ky, 0) h_g; z never moves.

### 4.2 Kernels
| Campaign / kernel | Grid | Phases | Runs (n states) | per-state / aggregate cap / kernel timeout (s) | Estimate (s) |
| --- | --- | --- | --- | --- | --- |
| fid01 / f32k7, f32k8, f32k9, f32k10 | flow_32 | one each | n = 18 (parent, 16 designs, NC) | 900 / 13000 / 16000 | 415 n + 260 = 7,730 |
| fid01_f48 / f48 | flow_48 | 7 | the run set (about 4-6) | 6000 / max(1.3 x 2340 n, 6000) / cap + 3300 | 2340 n + 260 |

One phase per flow_32 kernel (controls C8): a kernel lost for a non-infrastructure reason costs one phase, and P >= 3 survives. Every pair (design and parent at the same phase) is inside one kernel; parent first. Total estimate about 9 GPU h (flow_32) + about 3-4 GPU h (flow_48) + two smokes.

### 4.3 Budget, quota, queue
Cap **18 GPU h** of formal session time (Kaggle session wall from each kernel log). It governs only flow_48: before pushing f48, `T = sum(session wall of the four f32 kernels) + estimate(f48)`; if `T > 64,800 s`, flow_48 is `NOT_MEASURED` (recorded with its inputs), with the §6.5 consequence. If the weekly quota stops a push: pause, resume in order, no rule change. **Backend trigger** (STATE.md): if a kernel waits more than 24 h in the queue, or the quota blocks the remaining kernels for more than 7 days, stop pushing and report the trigger; finished kernels stay valid.

### 4.4 Blinding
While kernels run only statuses, session times and `verify` pass/fail are read (`verify` tables to files, stdout discarded). Design forces are read first by the d_set step, after all four flow_32 kernels are verified or declared lost.

## 5. OpenFOAM design
### 5.1 Pipeline and environment
The U3 pipeline: the XFID X3 formal runner byte for byte except the bound criteria SHA (it discovers `x3_criteria.json`), the Round 5 case template (hash-identical minus the candidate STL, plus the level changes of §5.2), STL export `geom02_canonical.export_from_state` (r = 8, prescreen profile `docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json`) with the X1 practical gate, simpleFoam with residual control, last-25 % iteration window, 0.32 N per coefficient. Executed locally with `scripts/local_openfoam.py run` (`--cpus 1 --memory 8g`) in the locked image (`sha256:e9ceb8a7…25eb`); a kernel output is valid only if `local_run.json` records return code 0 and `dpkg_after_matches_lock: true`.

### 5.2 Mesh levels, shifts, run sets
| Level | Template change (everything else hash-identical) | Cells (parent probe) | States | Shifts | Halton tags |
| --- | --- | --- | --- | --- | --- |
| V1 | none (the U3/X3 mesh: blockMesh 25 x 13 x 9, snappy surface level (2 3)) | about 40k | parent, every design, NC, EX r = 4 (parent, W4, W6) | 32 (16 mirror pairs) | 49-64 ± |
| V2 | blockMesh 50 x 26 x 18 | 212,822 | d_set V2 set: parent, tier A, tier B, eligible support | 4 (2 mirror pairs) | 49 ±, 50 ± |
| V3 | blockMesh 100 x 52 x 36; controlDict endTime 6000 | 1,461,141 | d_set V3 set: parent, tier A | 1 | 49 + |

V2/V3 halve and quarter the background cell (snappy levels are relative, so surface cells halve and quarter too), the convention of the Stage V V1/V2/V3 family (background = 4 voxels). Shifts: the X3 generator (Halton bases (2, 3, 5) magnitudes 0.5-4 mm, bases (7, 11, 13) signs, exact mirror pairs) at indices disjoint from X2/X3 (1-32) and U3 (33-48); identical for every state on a level; shift-major case order. Registered extension shifts (§6.8): V1 65-72 ±, V2 51-52 ±, V3 49 -. Smoke shift: 80 +.

**Scope of the local environment gate.** LOCAL-OF-01 qualified the software (image, lock, runner, wrapper) on the V1 template: Kaggle and local force histories are byte-identical and runs are deterministic. V2/V3 change two input numbers of the template, not software; every M3a OpenFOAM case runs in the same local image, so all comparisons are within one environment. No Kaggle comparison exists for V2/V3 (a limit, not a gate result). Run-to-run determinism on V2/V3 is checked after the analysis by comparing the formal parent cases at V2/V3 49 + with the P0 probe outputs by force-history hash (descriptive; controls C7).

### 5.3 Cost and execution
Probe (§9, parent, one shift, host load average 70-230): V2 snappy 74 s, 212,822 cells, concave 4.0 % (allowed), converged in 1,562 iterations, 31 min per case; V3 snappy 431 s, 1,461,141 cells, concave 2.0 %, about 8-10 s per iteration, about 1.5 GiB. Estimates (local, one core per case): V1 21 STLs (18 states and 3 EX) x 32 = 672 cases x 3-5 min = 35-59 CPU h; V2 about 15 x 4 = 60 cases x 0.5-1 h = 30-60 CPU h; V3 about 10 cases x 7-12 h = 70-120 CPU h; about 4 containers at a time (an operating choice with no effect on any value; OpenFOAM is serial and deterministic). Kernels: V1 four kernels of four whole mirror pairs (49-52, 53-56, 57-60, 61-64; every state of a pair in one kernel); V2 one kernel per shift; V3 one kernel per group of at most six cases (the parent is in the first group: if that kernel is lost twice, V3 is lost, disclosed). Stage timeouts are hang detectors only: V1 7,200 s, V2 43,200 s, V3 259,200 s per stage (at least 8x the measured need); a stage timeout is `INFRA_LOSS` (§10). `stop_after_consecutive_failures` 10.

**Pre-registered contingency (status only):** if the V3 probe of the parent does not reach `SIMPLE solution converged` before endTime 6000, V3 is removed at freeze 2 (`of_levels` without V3), G1 uses V1 and V2, the G3-set rule is not applied, and the record carries `V3_NOT_CONVERGED`.

### 5.4 Case validity and matching
A case is valid if every stage returns 0 (checkMesh exit 1 allowed only for the registered single concave-cell failure with fraction <= 0.08) and simpleFoam reports `SIMPLE solution converged`. A case that ends at endTime without convergence is invalid (data loss for that design, never a FAIL). Matching is per design: on V1 and V2 a design uses the mirror pairs where it and the parent are valid at both members (M2's whole-pair unit); on V3 the shifts where both are valid. A failed parent case removes that shift (V1/V2: that pair) for every design. Minimum data (parent): V1 >= 12 valid pairs, V2 >= 1 valid pair, V3 its shift; below it `FID01_INVALID`. A design below the same minimum on a level has no value there (`UNRESOLVED_DATA`).

### 5.5 Blinding and order
V1 starts at freeze 2, V2/V3 at freeze 3, regardless of any OpenFOAM value. While they run only statuses, stage return codes, cell counts and times are read. Force fields are read only by the analysis (`analyze_fid01.py main`), which accepts exactly the OpenFOAM outputs whose criteria SHA-256 are listed in freeze 2 and freeze 3 (each exactly once; the first valid output of a kernel is authoritative).

## 6. Rules (computed by the frozen `scripts/fid01/analyze_fid01.py`)
Response: downforce (decision); drag is the constraint response (G5b). Differences are design minus parent at the same phase (WaterLily) or the same shift (OpenFOAM).

### 6.1 Estimators
- **WaterLily flow_32**: per design the phases common with the parent (at least 3, else WaterLily data loss); `Delta_bar`, `sigma_d` (P - 1 dof) as M2 (`analyze_unc01.stats`); `SE_eff = max(sigma_d, floor) / sqrt(P)` with the M2 floors 2.09e-4 N (downforce) and 1.36e-4 N (drag), the flow_32 sigma_d of the roll.
- **flow_48** (one phase): `Delta_48(k7)`, compared with the same-phase `Delta_32(k7)` (numerical N10).
- **OpenFOAM V1**: the M2 U3 estimator: the unit is the mirror-pair mean of matched-shift differences; `Delta_bar_V1`, `SE_V1` from the design's own pair means (pairs - 1 dof).
- **OpenFOAM V2**: pair means; `SE_V2 = sigma_pair / sqrt(n_pairs)`, `sigma_pair` pooled over every design's pair means on V2 (dof = sum(n_pairs - 1), about 15) (numerical N4).
- **OpenFOAM V3** (one shift): `Delta_V3` = the matched difference at 49 +; after the §6.8 extension, the mean over the design's matched shifts (49 + and 49 -) for the extended designs. Its standard error comes from the tier-A regression of `Delta_V3` on `Delta_V1` through the origin (G3-set): for design i the **leave-one-out** residual SD of that fit (dof n - 2), divided by sqrt(n_shifts). It contains placement noise and design-to-design spread, so it over-states pure noise; a design's own departure cannot inflate its own SE.

### 6.2 Tiers, d_set and run sets (WaterLily only)
- `Delta_min = 2 S_d |J_b,48| = 1.807e-3 N` (paired E2) and `Delta_lit = 2 max(S_b, S_c) |J_b,48| = 5.363e-3 N` (literal E2), both fixed from M2 (§7).
- **Tier A** (decides the outcome): wide designs (W, C slots) with `|Delta_bar_32| >= Delta_lit` and `|Delta_bar_32| > 3 SE_eff`. **Tier B** (validates the M3b range, §8): wide designs with `Delta_min <= |Delta_bar_32| < Delta_lit` and `> 3 SE_eff`. **Eligible support designs**: N/M slots with `|Delta_bar_32| >= Delta_min` and `> 3 SE_eff`. Both signs count (a resolved loss that persists is the same fidelity evidence as a gain; the improvement-only subset is reported).
- **Valid decision set**: tier A has at least 6 designs from at least 3 of the 4 wide families (rigid, section, span, combination) with at least 2 positive. Basis: if every one of 6 designs passes, a per-design failure rate of 39 % or more is excluded at 95 % (0.61^6 = 0.05); it is the smallest set that says something about "improvements persist" and is reachable with the registered slots. Otherwise `FID01_INCONCLUSIVE_DESIGN_SET`.
- Run sets (written by d_set): V2 = parent + tier A + tier B + eligible support; V3 = parent + tier A; flow_48 = parent + tier B + the largest positive and the largest negative tier-A design.

### 6.3 The rules for a judged design i (tier A, tier B, eligible support; s_i = sign of `Delta_bar_32`)
Each rule returns PASS, FAIL (a **resolved** failure), `UNRESOLVED_STAT` (not resolved by the noise) or `UNRESOLVED_DATA` (a value is missing). Levels: tier A V1, V2, V3; tier B and support V1, V2.
- **G1 sign on every level**: PASS if `sign(Delta_g) = s_i`; FAIL if the sign differs and `|Delta_g| > 2 SE_g`; else `UNRESOLVED_STAT`; a missing level `UNRESOLVED_DATA`.
- **G2 above 3 sigma on V1**: PASS if `s_i Delta_bar_V1 > 3 SE_V1`; otherwise `UNRESOLVED_STAT` (a small OpenFOAM difference fails through G4 when that is resolved). The WaterLily half of "3 sigma" is the tier definition.
- **G3 spread V1-V2 (per design)**: `m = (Delta_V1 + Delta_V2) / 2`, `R = |Delta_V1 - Delta_V2|`, `sigma_R = sqrt(SE_V1^2 + SE_V2^2)`: PASS if `R <= 0.5 |m|`; FAIL if `R - 2 sigma_R > 0.5 |m|`; else `UNRESOLVED_STAT`.
- **G3-set V3 (tier A, one rule for the set)**: slope b of `Delta_V3` on `Delta_V1` through the origin with its 90 % interval (t, n - 1 dof): PASS if `0.6 <= b <= 1.67` (the G3 tolerance for two levels: `|a - c| <= 0.5 (a + c) / 2` iff `c / a` in [0.6, 1.67]); FAIL if the interval lies outside; else `UNRESOLVED_STAT` (numerical N3).
- **G4 retention on V1** `rho = Delta_bar_V1 / Delta_bar_32`, t = t_0.95 at min(P, pairs) - 1 dof: FAIL if `s_i Delta_V1 + t SE_V1 < 0.5 (|Delta_32| - t SE_eff)` (OpenFOAM's upper bound below half of WaterLily's lower bound; this includes a resolved opposite sign) or `s_i Delta_V1 - t SE_V1 > 2 (|Delta_32| + t SE_eff)`; PASS if `0.5 <= rho <= 2.0`; else `UNRESOLVED_STAT`. The upper bound 2 is the E1 band of the same document (a deviation from #62, §14). rho on V2, V3 and the M2 interval on |rho| are reported.
- **G5 constraints confirmed on OpenFOAM**: (a) geometry: X1 practical gate (double and float32), STL volume within the registered 10 % band of the parent STL, and the chain check `|dV_STL / V - dV_SDF,smoothed / V| <= 0.01` — FAIL if any fails; (b) drag, the constraint response M3b will carry, tested where `|Delta drag_32| >= 2e-3 N` (about twice the roll's drag difference) and `> 3 SE_eff`: the same rule as G4 on drag (V1 drag vs flow_32 drag, band [0.5, 2]); below that size PASS with the note "not tested" (numerical N13, controls C4).

A design's status: FAIL if any rule FAILs; else `UNRESOLVED_DATA` if any is; else `UNRESOLVED_STAT` if any is; else PASS.

### 6.4 Tier B and support labels (registered secondary)
`TIER_B_EMPTY / TIER_B_FAIL / TIER_B_PASS / TIER_B_UNRESOLVED` and `SUPPORT_UNTESTABLE / SUPPORT_FAIL / SUPPORT_PASS / SUPPORT_UNRESOLVED` from the statuses of their designs. Tier B sets the M3b minimum gain (§8); support informs R2 (local modes stay out of M3b in any case).

### 6.5 flow_48 confirmation (R3)
For each design of the flow_48 run set: `R3_CONFIRMED` if `Delta_48(k7)` and `Delta_32(k7)` have the same sign; `R3_CONTRADICTED` if not and `|Delta_48(k7)| > 2 sqrt(2) x 2.09e-4 N`; else `R3_UNRESOLVED`; the ratio and `|Delta_48(k7) - Delta_32(k7)|` are reported, with `R3_E2_EXCEEDED` if that exceeds Delta_min for any design. Consequence: `R3_CHALLENGED` (any contradiction) or flow_48 `NOT_MEASURED` obliges M3b to confirm every candidate on flow_48 with P >= 2. No effect on the outcome.

### 6.6 Controls
- **NC**: WaterLily: `z = |Delta_bar_roll,32 - (-1.648e-3)| / sqrt(SE^2 + (8.53e-5)^2)` with `SE = max(sigma_d, 3e-4) / sqrt(P)`; OpenFOAM V1: the same with the roll's V1 SE and 5.79e-5, only with at least 12 valid pairs (else `MISSING`). CONSISTENT if `z <= 3.5`. Both CONSISTENT are required; otherwise `FID01_INVALID` (numerical N9, controls C5).
- **EX** (W4, W6 on V1): per mirror pair `u = mean over the pair of (F_r4(i) - F_r4(parent)) - (F_r8(i) - F_r8(parent))`; `delta_EX = mean(u)`, SE from the pairs; tolerance `0.1 |Delta_bar_V1,r8(i)|`. `EXPORT_SENSITIVE` if `|delta_EX| - 2 SE > tolerance`; `EXPORT_INSENSITIVE` if `|delta_EX| + 2 SE <= tolerance`; else `EXPORT_UNRESOLVED`; the minimum detectable effect 2 SE and the parent's absolute change are printed. Consequence: `EXPORT_SENSITIVE` or `EXPORT_UNRESOLVED` obliges XV-01 to register an export-resolution check; no effect on the outcome.

### 6.7 Outcome (evaluation order)
1. Minimum data (the parent's OpenFOAM minimum on every level of `of_levels`): else `FID01_INVALID`.
2. NC not CONSISTENT on both: `FID01_INVALID`.
3. Decision set not valid (§6.2): `FID01_INCONCLUSIVE_DESIGN_SET`.
4. Any tier-A design FAILs, or G3-set FAILs: `FID01_NO_GO`, cause `WL_OF` if some tier-A design fails G1 on V1, G4 or G5, else `OF_MESH` (G1 on V2/V3, G3, G3-set).
5. Every tier-A design and G3-set PASS: `FID01_GO`.
6. Otherwise, if some tier-A design is `UNRESOLVED_STAT`: `EXTENSION_REQUIRED` (§6.8).
7. Otherwise: `FID01_INCONCLUSIVE_PRECISION` if anything statistical stays unresolved (a tier-A design or G3-set), else `FID01_INCOMPLETE` (data missing only).

### 6.8 Registered extension (at most once; part of this registration)
For every tier-A design that is `UNRESOLVED_STAT`, the parent and that design run on the levels involved (G1: the unresolved levels; G3: V1 and V2; G2, G4, G5: V1) at the registered extension shifts (V1 pairs 65-72, V2 pairs 51-52, V3 shift 49 -). Before it runs, `fid01_build.py of-prepare --extension analysis.json` builds the kernels from the main analysis' plan and `fid01_freeze.py freeze4` records them (with the main analysis' SHA-256). `analyze_fid01.py extension` recomputes those designs once with every shift (the pooled V2 SD, the G3-set label and the V3 leave-one-out SDs recomputed) and re-evaluates §6.7 steps 4-7; tier-B and support labels stay those of the main analysis. A design still unresolved stays unresolved (`FID01_INCONCLUSIVE_PRECISION`), never a FAIL (numerical N1, N5; controls C1; strategy S1). Cost bound: at most 6 designs on V3 (the largest |Delta_32| first).

### 6.9 Reported for every design (descriptive)
All estimators on every grid and level; support, maximum change, volumes, R0/R3; rho per level; the improvement-only subset of tier A with its statuses; the heave sub-label (designs containing heave, which move against the z lattice that is never phased; strategy S12); sub-threshold wide designs; the aggregate slope of `Delta_V1` on `Delta_32` through the origin and Kendall's tau over all judged designs and over the positive tier-A designs (strategy S4); the OpenFOAM-side paired grid term `S_d,OF = median over tier A of |Delta_V3 - Delta_V2| / |F_parent,V3|` (strategy S7).

### 6.10 Operating characteristics (computed before freeze 1 with these rules; `scripts/fid01/fid01_oc.py`, `oc.json`)
Synthetic studies through `evaluate` and `extension_eval`: a planning mix of 12 wide differences (9 tier A, 3 tier B), the M2 WaterLily noise model (sigma_d = 9.7e-5 (|Delta|/1e-3)^0.48 N), OpenFOAM noise of one matched-shift difference sigma0 = 4e-4, 7e-4 or 1.2e-3 N on V1 (M2's single-shift range) and 0.7 or 1.0 x sigma0 on V2/V3, split equally between the parent's case (shared by every design at that shift) and the design's case, mirror correlation 0 or -0.5 on every level (crossed with the V2/V3 factor), the roll with the same noise, extension shifts only for the plan's designs; true retention 0.67/0.75/0.80 or 0.67 on every level, and a design-to-design spread of the true retention tau of 0, 0.08 or 0.15 (200 replicates each).

Result (`oc.json`, final outcome after the extension where it was triggered; ranges over the noise settings of each row):

| True retention (V1/V2/V3) | spread tau | GO | NO-GO | inconclusive / incomplete / invalid | extension triggered |
| --- | --- | --- | --- | --- | --- |
| 0.67/0.75/0.80 or 0.67 everywhere | 0 | 99-100 % | 0 % | 0-1 % | 0-2.5 % |
| same | 0.08 | 82-90 % | 2-9 % | 4.5-13 % | 6.5-19 % |
| same | 0.15 | 23-36.5 % | 40.5-62.5 % | 8.5-27.5 % | 9.5-36.5 % |
| 0.45 everywhere | 0.08 | 0 % | 98.5-100 % | 0-1.5 % | 0-1.5 % |
| 0.30 everywhere | 0.08 | 0 % | 98.5-100 % | 0-1.5 % | 0 % |
| V1 0.67, V2 0.60, V3 0.35 (mesh-dependent) | 0.08 | 0-10 % | 29-82 % | 18-61 % | 2-25.5 % |

A negative-control false alarm (`FID01_INVALID`) occurred in at most 0.5 % of the runs of any setting. Reading: with a common true retention the rules do not produce a NO-GO from noise (the review's false-NO-GO concern, N1); a true retention of 0.45 never gives a GO (target <= 5 %). With a design-to-design spread tau, some designs truly have a retention below 0.5 (tau 0.08: 1.7 % per design, about 14 % that at least one of 9 does; tau 0.15: 13 % per design, about 71 %), and the per-design conjunction then reports NO-GO; that is the registered meaning of "every decision design retains at least one half", not a false alarm. A mesh-dependent OpenFOAM difference is mostly detected (`OF_MESH`) or left inconclusive, rarely passed.

## 7. Coefficients fixed from M2 and the E2 decision
### 7.1 Table
| Coefficient | Value | Source (`docs/evidence/unc01_2026_10_20/analysis.json`) | Use |
| --- | --- | --- | --- |
| S_d (downforce, common phases) | 0.0034 (SE 0.0015) | `Q4_E2.downforce.common_phases.S_d` | Delta_min, tier B, M3b floor |
| S_b, S_c | 0.0067, 0.0101 | same block | Delta_lit, tier A |
| J_b,48 | 0.265779 N | `...denominator_n` | both thresholds |
| sigma_d floor (downforce / drag) | 2.09e-4 / 1.36e-4 N | `grids.flow_32.differences.v18__roll_p25` | SE_eff |
| NC reference WL | -1.648e-3 N, SE 8.53e-5 | roll flow_32 downforce | §6.6 |
| NC reference OF | -6.61e-4 N, SE 5.79e-5 | `u3.differences.v18__roll_p25.downforce` | §6.6 |
| flow_32 / flow_48 ratio | 0.980 [0.962, 0.999] | `Q3` | context for R3 (no rule) |
| OF retention (wide arms) | 0.63-0.71 | `u3` | context for G4 (no rule) |

### 7.2 E2: the literal form decides; the paired form is measured, not assumed
The approved re-baseline (`phase_plan.md`, 2026-10-16) sets the minimum gain "with the E2 rule I_f > 2 max(S_b, S_c) at M3a registration". Revision 1 replaced it by the paired form 2 S_d after M2 was visible, a loosening by a factor 3 (controls C2). Revision 2: **tier A, which decides GO/NO-GO, uses the literal threshold** (2.0 % of |J_b,48|, 5.363e-3 N). The paired form (0.68 %, 1.807e-3 N) is the tier-B floor: whether differences between the two thresholds persist is **measured** (tier B) and turned into the M3b minimum gain by a fixed rule (§8). Why the paired form is the right floor to test: R1 makes paired same-phase differences the decision quantity; S_b and S_c measure absolute shifts common to both shapes (M2: common phases remove 71-89 % of the parent's placement spread); the grid sensitivity of a paired difference is S_d. Stated against it: S_d rests on one state (pitch +3.1) and four common phases (90 % interval about [0.0009, 0.0059]); the roll, a pure translation of 1.65e-3 N, had OpenFOAM retention 0.40 [0.33, 0.49] (numerical N2, strategy S2), so differences near Delta_min may not persist; that is what tier B measures.

## 8. Consequences
- `FID01_GO`: M3b may be registered (SCREEN-01 #64 first). This registration fixes for it:
  - the **minimum gain** `g_min = max(2 S_d, x* / |J_b,48|)`, where `x*` is the smallest `|Delta_32|` of a PASSing tier-A or tier-B design that is larger than every non-PASSing tier-B design (if tier B is empty or fails throughout, x* is the smallest PASSing tier-A difference, i.e. g_min >= 2.0 %);
  - for XV-01 (OpenFOAM side): the G rules and coefficients of §6.3, the OpenFOAM procedure of §5 (levels, shifts, validity), and an OpenFOAM minimum gain `2 max(S_d, S_d,OF)`;
  - the R3 and EX consequences (§6.5, §6.6).
- `FID01_NO_GO`, cause `WL_OF`: the pre-committed branch: one cheap registered smooth-advection-scheme WaterLily test first (its issue is opened with the NO-GO record, budget and stopping rule fixed there), then the T2-0 evaluator via M4 (#66). #64 and #65 closed as not planned. No AD diagnosis round.
- `FID01_NO_GO`, cause `OF_MESH`: WaterLily and OpenFOAM agreed on V1 but the OpenFOAM difference is mesh-dependent. No M3b; M4 decides between an OpenFOAM mesh-convergence study of differences and the NO-GO branch; the smooth-scheme WaterLily test is not triggered by this cause alone (strategy S10).
- `FID01_INCONCLUSIVE_*`, `FID01_INCOMPLETE`, `FID01_INVALID`: no M3b. At most one re-registration of M3a addressing the recorded cause; after that an explicit recorded decision (user or the 2026-10-13 delegation) is required before anything else (strategy S10).

## 9. What was visible before this registration
- All of M2 (registered) and its U1 exploratory single-phase flow_32 values: camber ±19.7 (-1.04e-2 / +1.31e-2 N), reflex ±29.3 (∓1.4-1.6e-2 N), twist ±1.1 (+1.6e-3 / -1.2e-3 N), sweep ±11.3 (about 1e-4 N), pitch ±3.1. Used to drop sweep and twist -1.1 as singles (below Delta_min) and to expect sizes. **W4 (camber -19.7), W5 (camber +19.7, first candidate) and W6 (reflex -29.3, first candidate) are U1 states: their native-phase WaterLily differences are known and place them in tier A in expectation** (controls C3); M3a uses new phases. No OpenFOAM value of any M3a design exists.
- The design prescreen and STL exports (geometry only). The first prescreen run evaluated every revision-1 candidate (`prescreen_run1_designs.json`): every single-mode candidate passed; of the combinations only C1 (camber -11.3, reflex -11.3), C2 (heave -31.1, pitch +0.7; also heave -13.7, pitch +1.3) and C4 (three variants) had a gate-clean candidate, C3 and C5 none (all `min_feature_width`, some also the export gates); every outward one-sided bump failed and the inward bump_lower -15/-10 and bump_small +20/+15/+10 passed. Revision 3 therefore appended fallback candidates to C3, C5, N1, N2 and restored N3, in a declared order and on geometry alone (the rule controls C3 asked for); no slot was removed.
- The OpenFOAM timing probe of the parent on V2 and V3 at 49 + (statuses, stage times, cell counts, iterations, convergence; force fields removed by the registered sanitiser before anything was read; `p0_probe/`).
- The operating-characteristics simulation (synthetic data only).

Nothing in §1-§8 was chosen after a force of an M3a design was seen; no M3a force exists.

## 10. Freeze, re-run, amendment and stopping rules (fail-closed)
- Order: §2. Freezes 1, 2 and 3 are committed, pushed and commented on #62 before the corresponding runs.
- `INFRA_LOSS` (objective): a WaterLily kernel that ends with `ERROR` before its last run, or with no output, for an infrastructure cause (install, GPU identity, Kaggle error, session kill); an OpenFOAM kernel whose `local_run.json` has a non-zero return code or `dpkg_after_matches_lock` false, that is stopped by a host or Docker failure, or with a case whose stage hits the hang-detector timeout (counted `TIMED_OUT`, never a value). One identical rerun per kernel; the first valid output is authoritative; both are archived. A kernel lost again after its rerun is declared to the analysis (`--lost` with its criteria SHA-256, recorded in the output); its cases are data loss. A per-case mesh failure, non-convergence, a design's WaterLily divergence or an unexpected value is a result (data loss or a number), never a reason to rerun.
- Engineering defect found by a smoke before freeze 2/3: fixed and re-frozen (amendment of freeze 1 with diff and reason); rules never change.
- Amendment after freeze 2 (`REGISTERED_AMENDED`): only for a defect that prevents a pre-specified quantity, filed on #62 before any verdict-relevant output is read, never touching a rule; the original outcome (or `INCOMPLETE`) is kept beside it.
- d_set and the analyses are written once (`--out` opened exclusively); the analyzer re-derives d_set from the tables, checks every WaterLily file against the verified tables, and accepts exactly the frozen OpenFOAM criteria set; `analysis.md` is its human summary, written once. Later readings are dated separate notes.
- Session budget: WaterLily 2 smokes + 5 formal kernels (+ one INFRA_LOSS rerun each); OpenFOAM 2 development smoke kernels + the formal kernels (+ one rerun each) + the §6.8 extension kernels if triggered.

## 11. Freeze content
**Freeze 1** (`freeze1.json`, written by `scripts/fid01/fid01_freeze.py`): source commit; SHA-256 of this registration; `scripts/fid01/*.py`, `tests/fid01/*.py`; reused code (`v18_plate.py`, `mode01_v18_prescreen.py`, `mode01_prescreen.py`, `mode01_modes.py`, `step01_states.py`, `geom02_canonical.py`, `build_xfid45_stage_v_input_2026_10_04.py`, `prepare_kaggle_xfid_gridphase_x3.py`, `unc01_u3_prepare.py`, `unc01_build.py`, `unc01_verify.py`, `analyze_unc01.py`, `width_rule_study.py`, `local_openfoam.py`, the harness tool hashes); inputs (`designs.json`, `states.json`, direction raws, `of/export.json`, every STL by hash, `oc.json`); the M2 analysis SHA; python, numpy, scipy, scikit-image versions; the P0 probe record.
**Freeze 2** (`freeze2.json`): the flow_32 campaign and its harness prerun freeze (smoke table SHA); the V1 criteria and kernels (`of_criteria_sha256`); the sanitised OpenFOAM smoke record; `of_levels` (the §5.3 contingency from the V3 probe's status).
**Freeze 3** (`freeze3.json`): `d_set.json`; the budget decision (§4.3); the flow_48 campaign and its prerun freeze; the V2/V3 criteria (`of_criteria_sha256`; without V3 under the §5.3 contingency).
**Freeze 4** (only with `EXTENSION_REQUIRED`): the main analysis' SHA-256 and the extension criteria.
The analyzer refuses to run without these records, checks the campaigns and d_set against them and accepts exactly the frozen OpenFOAM criteria (minus declared lost kernels). Nothing in §1-§8 changes at freeze 2, 3 or 4.

## 12. Outputs and documentation
`docs/evidence/fid01_2026_10_21/`: `designs.json`, `states.json`, `inputs/`, `oc.json`, `p0_probe/`, `freeze1.json`, `freeze2.json`, `freeze3.json`, `d_set.json`, `wl/` (smokes, kernel outputs, per-kernel verify tables, budget decision), `of/` (criteria, export, smoke, outputs with manifests, local run records), `analysis.json` (+ `analysis_extension.json` if §6.8), `analysis.md`, `README.md`, `SHA256SUMS` (split per directory above about 5,000 entries; passes `scripts/check_sha256sums_tracked.py`; `*.log` tracked with `git add -f` where the `.gitignore` negation does not apply). Also `docs/STATE.md`, a `docs/phase_plan.md` entry, `docs/exploratory_index.md` (P0 probe), comments on #62 at freeze 1, freeze 2, freeze 3 and the result.

## 12a. Plan review record
One plan review of revision 1 (commit `0ac6107f`, 2026-10-21), three independent adversarial sonnet subagents: numerical (16 findings, 2 blockers), controls (14, 2 blockers), strategy (14, 2 blockers). A = adopted, P = partly, R = rejected.

Numerical: N1 A (false NO-GO: FAIL only when resolved, data loss never FAIL, the extension remainder is `INCONCLUSIVE_PRECISION`, operating characteristics §6.10); N2 A (two tiers: tier A at the literal threshold decides, the band between Delta_min and Delta_lit is tier B; 5.363e-3 N chosen over the proposed 4e-3 N because it is the approved E2 value, see C2); N3 A (V3 judged by the set-level slope G3-set; per-design G3 on V1-V2); N4 A (V2 pair-mean unit with pooled pair SD; V3 SE from the leave-one-out residual of the tier-A fit instead of borrowing V2); N5 A (G2 never FAILs; extension cost cap §6.8; non-convergence is data loss); N6 A (one flow_48 kernel, no duplicated parent); N7 A (timeouts are hang detectors; text and code aligned); N8 A (`of_levels` frozen at freeze 2; the analyzer drops V3 and G3-set when removed); N9 A (NC SE floor 3e-4 N, z <= 3.5); N10 A (R3 on the same phase k7; `R3_E2_EXCEEDED`); N11 A (EX three labels with the minimum detectable effect); N12 A (bias statement corrected; S_d interval stated); N13 A (drag tested only from 2e-3 N); N14 A (consistent resolution rules for G1, G2, G4); N15 A (per-design common phases); N16 A (counts).

Controls: C1 A (timeouts are INFRA_LOSS; `UNRESOLVED_DATA` vs `UNRESOLVED_STAT`; `FID01_INCOMPLETE`); C2 A (the literal E2 decides tier A; the paired form only through tier B and the measured M3b rule; recorded in phase_plan and #62); C3 A (§9 lists the U1-known designs; larger-first order disclosed; `states` refuses fewer than 12 designs or 4 families); C4 A (deviation table §14; G5 defined as a real check: STL-SDF chain and drag fidelity); C5 P (floor, z 3.5, minimum 12 pairs and the STL-SDF chain check adopted; INVALID on an NC failure kept, see S13); C6 A (EX on V1 with 32 shifts and three labels; r = 4 against r = 8 because the extractor has no r = 16); C7 P (determinism of the V2/V3 parent cases checked against the probe after the analysis; the r = 4 STL is smoked on V1; a separate duplicate V2 run rejected as redundant with that check); C8 A (frozen criteria set; one flow_48 kernel; one phase per flow_32 kernel; objective INFRA_LOSS; `stop_after_consecutive_failures` 10); C9 A (`fid01_freeze.py`; an I/O test of the OpenFOAM reader on a result tree; the analyzer's hash in the freeze); C10 A (registered sanitiser for smokes, statuses only; staging from WaterLily only); C11 A (operating characteristics; rho <= 0 FAIL only when resolved); C12 A (V3 no longer borrows V2); C13 A (text-code consistency); C14 A (R0 placement dependence disclosed; `NOT_MEASURED` consequence; this record).

Strategy: S1 A (as N1/C1); S2 A (two tiers; M3b minimum gain from the measured tier-B result); S3 A (twist -1.1 replaced by pitch +0.7; second amplitudes for camber and heave); S4 P (aggregate slope and Kendall tau reported; the per-design conjunction stays decisive because it is stricter); S5 A (staged OpenFOAM and flow_48 after d_set); S6 P (V3 restricted to tier A at one shift with the set-level rule; extension capped; V3 stays in the outcome through G1 and G3-set rather than descriptive); S7 A (`S_d,OF` and the XV-01 OpenFOAM minimum gain); S8 A (flow_48 restricted to tier B and two tier-A controls); S9 A (narrow designs reduced to N1, N2; one mid-support slot M1; support designs on V1/V2 only); S10 A (cause-conditioned NO-GO; one re-registration cap); S11 A (EX moved to V1); S12 A (heave sub-label); S13 P (floor and z adopted; an NC failure still makes the study INVALID: if the chain does not reproduce a measured difference, a NO-GO from it is not trustworthy either); S14 P (upper bound 2 kept for tier A and drag, deviation recorded in §14; M2's large ratios were small or local responses, which tier A excludes).

## 13. Source review record
One source review (sonnet subagent, commit `dbcc11a2`, 2026-10-21) of `scripts/fid01/*.py` and `tests/fid01/test_fid01.py` against revision 2: 17 findings (3 blockers, 6 major). A = adopted, P = partly.
- SR1 A (blocker): smoke criteria carried `registered_before_run: false`, which the runner refuses; now true, smoke told apart by `evidence_class` and directory.
- SR2 A (blocker): the analysis now refuses without freeze 2/3, checks both campaigns, d_set and its tables against them, and reads `of_levels` from freeze 2.
- SR3 A (blocker): with V3 removed (§5.3) the V3 kernels are neither built nor frozen.
- SR4 A: a kernel lost after its rerun is declared with `--lost`; timed-out cases are counted `TIMED_OUT`, never values.
- SR5 A: the extension has a builder option (`--extension`), a V3 cap of 6 designs and freeze 4; the extension analysis binds to it.
- SR6 A: G3-set is recomputed in the extension; Delta_V3 after the extension is defined (§6.1).
- SR7 A: a missing k7 run gives `R3_UNRESOLVED` / `NOT_MEASURED` instead of a crash.
- SR8 A: the budget rule derives the flow_48 estimate from d_set, needs exactly the four flow_32 kernels, and the flow_48 campaign is built only if it pushes.
- SR9 A: `--kernel-root` is required for every analysis command.
- SR10 A: the EX tolerance uses the design's V1 difference over all its valid pairs.
- SR11 A: stale X3 shift metadata removed from the criteria (shift tags per level).
- SR12 A: the §6.9 geometry columns are copied into the analysis; tier-B and support labels are main-analysis only (§6.8).
- SR13 A: the simulation shares the parent's noise across designs, extends only the plan's designs, scales the roll's noise and crosses the factors; `oc.json` regenerated with the final analyzer.
- SR14 A: prescreen and X1 rows carry a code fingerprint and are reused only under it (the first prescreen run predates the field; its dependency files are unchanged since `f634dcec`, checked by git).
- SR15 A: the V3 parent group disclosed; flow_48 kernels limited to one Kaggle session and to at least two states.
- SR16 A: tests added for the builder layout with planted designs (stages, contingency, extension, groups), the OpenFOAM reader (lost and timed-out kernels), R3 with missing rows, EX `SENSITIVE`, NC `MISSING`, G4 and G1-V3 extension paths; the M2 exclusion list in the test corrected.
- SR17 A: text made consistent (§6.1, §6.7 step 7, §6.10).

## 14. Deviations from #62 (inventory)
| #62 text | Here | Stricter / looser | Decided by |
| --- | --- | --- | --- |
| "differences above 3 sigma" | WaterLily: tier definition `> 3 SE_eff`; OpenFOAM: G2 on V1 (PASS above 3 SE, otherwise unresolved; failures through G4) | equal / looser for G2 alone | registrant, review N5/N14 |
| "retention at least 0.5" | 0.5 <= rho <= 2.0, resolution-aware | stricter (upper bound) | registrant, E1 band, review S14 |
| "sign agreement on all OpenFOAM grids" | G1 on every level with resolution; data loss is not a disagreement | equal | review C1/N1 |
| "grid spread at most 0.5 x median" | V1-V2 per design; V3 through the set-level slope band [0.6, 1.67] | equal in tolerance | review N3 |
| "constraints confirmed on OpenFOAM" | geometry (X1, volume band, STL-SDF chain) and drag fidelity from 2e-3 N | defined (was unspecified) | review C4 |
| "negative control, expected delta about 0" | judged against M2's measured non-null roll | corrected by M2 | M2 analysis |
| "V2/V3 one phase" | V2 two mirror pairs, V3 one shift, both for the d_set run sets only | V2 stricter, V3 equal | registrant, cost |
| minimum gain from E2 at registration | literal E2 decides (tier A); paired E2 tested as tier B | equal (literal) | review C2 |
| ">= 12 designs from >= 4 families, large and small support" | 20 slots, 5 families, wide/narrow/mid; at least 12 filled | equal | |
| OpenFOAM on Kaggle CPU (original pipeline) | local Docker (LOCAL-OF-01) | — | user, 2026-10-20 |
