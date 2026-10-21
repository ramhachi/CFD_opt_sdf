# FID-01 (#62, M3a) registration: fidelity go/no-go of the central hypothesis on fixed v18 designs, without an optimizer

Status: **PLAN, revision 1 (2026-10-21), for the PROC-01 plan review (three independent angles: numerical, controls, strategy).** Freeze 1 (plan, sources, designs, OpenFOAM inputs) follows the plan review and one source review; the study is `REGISTERED_FROZEN` from freeze 2 (§10), before the first formal WaterLily kernel or OpenFOAM case. No flag changes: all qualification flags stay false, `shape_update_allowed=false`. Integration branch `codex/kaggle-batch-migration` (not main). Where this text and `scripts/fid01/analyze_fid01.py` disagree, this text governs and the disagreement is an analyzer defect.

Inputs (registered or `EXPLORATORY_COMMITTED`, binding from freeze 1):
- M2 UNC-01 `M2_COMPLETE` (`docs/evidence/unc01_2026_10_20/analysis.json`, SHA-256 `ee71c6d6…`): the coefficients of §7.
- v18 parent `docs/evidence/v18_genesis_2026_10_19/` (state `e7376e35…`, phi Fortran `29d53b23…`), generator `scripts/v18_plate.py` (`4641c2f4…`, not edited); MODE-01 v18 basis (`docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json`) and its gate stack (`scripts/mode01_v18_prescreen.py`).
- WIDTH-RULE decision proposal D-1 (`docs/width_rule_decision_2026_10_20.md`): this registration adopts it (§3.3).
- Harness v1.1 with JOB-02 per-run placement (`docs/harness/README.md`); LOCAL-OF-01 `LOCAL_ENV_PASS_BITWISE` for the U/X3 OpenFOAM pipeline (`docs/local_openfoam_env_gate_2026_10_20.md`, lock `infra/local_openfoam/local_openfoam_lock.json` `c105b7df…`).

## 1. Question, hypothesis and claim ceiling
**Central hypothesis** (`docs/architecture_effectiveness_2026_09.md` §9, E2; roadmap M3a): a shape change that the cheap solver (WaterLily, flow_32, placement-phase mean) shows as a difference large enough to be acted on, persists in independent body-fitted CFD (OpenFOAM on three meshes): same sign on every mesh, a magnitude retained to at least one half, robust across meshes, constraints confirmed. It has never been tested on any shape other than the M2 arms. M3a tests it on **fixed, pre-registered designs without an optimizer**; M3b (SCREEN-01 #64, XV-01 #65) starts only on `FID01_GO`.

Outcome (§6.7): `FID01_GO`, `FID01_NO_GO`, `FID01_INCONCLUSIVE_DESIGN_SET`, `FID01_INVALID` (a control or minimum-data failure). Secondary registered labels (no effect on the outcome): narrow-support stratum (`NARROW_*`), flow_48 confirmation (`R3_*`), extraction control (`EXPORT_*`), the verdict at the literal E2 threshold, the improvement-only subset.

Claim ceiling: Re = 80 reduced-laminar WaterLily (Kaggle T4) against laminar steady OpenFOAM v2512 (local Docker, three snappy meshes that are not grid-converged) for the registered designs of one analytic parent at one amplitude each, uncertified geometry, in-plane placement phases (z not sampled). It is a statement about **differences**, not absolute forces; about **pre-registered** designs, not about a design an optimizer selects (an optimizer's argmax is biased toward designs where WaterLily over-predicts; XV-01 verifies selected candidates); not physical downforce, not FSAE, not high Re.

## 2. Stages (PROC-01)
| Stage | Content | Status |
| --- | --- | --- |
| P0 | design prescreen (geometry only, `scripts/fid01/fid01_designs.py prescreen`), STL export gate, OpenFOAM V2/V3 timing probe on the parent (statuses, cells, times only; §9) | done before this text (solver-free / no force read) |
| P1 | this plan → three-angle plan review → rev. 2 | |
| P2 | sources (`scripts/fid01/`, `tests/fid01/`) → one source review → **freeze 1** (commit, push, #62 comment) | |
| S | WaterLily harness smoke (flow_32 parent, phase 7) and `verify --smoke`; OpenFOAM development smoke on V1 and V2 (the parent and the first design at Halton 80 +, a shift outside every registered set; statuses only, sanitised archive); on V3 the P0 timing probe of the parent is the smoke (its convergence status decides the §5.3 contingency); harness prerun freeze → **freeze 2** | engineering under freeze 1 |
| F | all WaterLily kernels pushed and all OpenFOAM runs started, unconditionally (§4.4, §5.5) | `REGISTERED_FROZEN` |
| A | one analysis (`analyze_fid01.py main`), written once; if and only if §6.8 requires it, the registered extension runs and `analyze_fid01.py extension` is written once | `REGISTERED_FROZEN` |

## 3. Designs and controls
### 3.1 Construction
Every design is a dict `{mode: amplitude}` built by `scripts/fid01/fid01_designs.py` on the v18 parent:
- **Analytic modes** heave, pitch, camber, reflex, twist, sweep (units and signs of `v18_plate.UNITS`) are applied **jointly** to the plate parameters: heave moves zc, pitch alpha, camber/reflex the section terms, twist/sweep the spanwise callables, and `v18_plate.plate_phi` is evaluated once. A combination is therefore again an exact plate SDF (no linear superposition of phi differences); a single mode reproduces `v18_plate.mode_phi` bit for bit (test).
- **Narrow-support modes**: the one-sided Gaussian normal offsets of `mode01_modes` applied to the v18 parent: `bump_lower` (ground-facing surface, sigma 0.125 m), `bump_upper` (upward-facing, 0.125 m), `bump_small` (ground-facing, 0.05 m); + = outward. They are asymmetric on purpose: the symmetric support probes of M2 (s050) moved downforce by 5.6e-6 N, too little to test anything.
- Only active nodes change; the evaluated bytes are the harness state model `construct_state(parent, d / max|d|, 1000 max|d| mm, +1)` (`v18_plate.harness_state`), i.e. what the WaterLily runner regenerates and what the STL is exported from.

### 3.2 Slots and the admissibility rule (fixed before any solver run)
Each slot lists candidates in a fixed order; **the design of a slot is its first candidate whose harness bytes pass the MODE-01 v18 gate stack** (13 GEOM-02 v2 gates including the registered R0 `min_feature_width`, P22-v2, the 10 % smoothed-volume band, clearance; unmeasured counts as fail) **and whose STL passes the X1 practical export gate** (double and float32). A slot with no admissible candidate is empty. The rule reads geometry only.

| Slot | Stratum / family | Candidates (in order) | Expected sign of the downforce change (planning only) |
| --- | --- | --- | --- |
| W1 | wide / rigid | heave -31.1, -13.7 mm (toward the ground) | + |
| W2 | wide / rigid | heave +31.1, +13.7 mm | - |
| W3 | wide / rigid | pitch -0.7 deg | - |
| W4 | wide / section | camber -19.7, -11.3 mm | + |
| W5 | wide / section | camber +19.7, +11.3 mm | - |
| W6 | wide / section | reflex -29.3, -19.7 mm | + |
| W7 | wide / span | twist +2.3, +1.1 deg | + |
| W8 | wide / span | twist -1.1 deg | - |
| C1 | wide / combination (section x section) | camber {-19.7, -11.3} x reflex {-29.3, -19.7, -11.3} | + |
| C2 | wide / combination (rigid x rigid) | heave {-31.1, -13.7} x pitch {+1.3, +0.7} | + |
| C3 | wide / combination (rigid x section x span) | heave {-31.1, -13.7} x camber {-19.7, -11.3} x twist {+2.3, +1.1} | + |
| C4 | wide / combination (rigid x section x span) | pitch {-1.3, -0.7} x reflex {+29.3, +19.7, +11.3}, sweep +11.3 | - |
| C5 | wide / combination (section x span) | camber {+19.7, +11.3} x (twist -1.1 with / without sweep -11.3) | - |
| N1 | narrow / local | bump_lower +20, +15, +10 mm | ? |
| N2 | narrow / local | bump_lower -20, -15, -10 mm | ? |
| N3 | narrow / local | bump_upper +20, +15, +10 mm | ? |
| N4 | narrow / local | bump_small +20, +15, +10 mm | ? |

Products are expanded with the first factor slowest. Amplitudes are MODE-01 ladder values (incommensurate with h; pitch 3.1 deg is excluded because it is an M2 arm and dominates every combination). Families: rigid {heave, pitch}, section {camber, reflex}, span {twist, sweep}, combination (two or three families jointly), local (narrow support). **Excluded on purpose:** the M2 states with an OpenFOAM value (pitch ±3.1, pitch +1.3, reflex +29.3, D0 +3, s050 -5) — their fidelity is already known; sweep alone (its U1 single-phase difference was about 1e-4 N, far below the minimum gain, §9); dihedral and twist_anti (no gate-clean point).
Support (MODE-01 definition: share of active interface-band nodes whose |dphi| exceeds 10 % of the band maximum) is recorded per design; the stratum is fixed by the slot (wide slots have support >= 0.5 by MODE-01; the bumps are expected near 0.02-0.1), and the measured support is printed.
The prescreen result (`docs/evidence/fid01_2026_10_21/designs.json`) is the design list; it is part of freeze 1 and is reproduced at freeze 1 by `fid01_build.py states` (refuses on any byte difference).

### 3.3 Width rule (UNC-01 TODO 0; WIDTH-RULE D-1 adopted)
Admissibility uses the registered R0 `min_feature_width` unchanged. With fixed designs the R0 artefact only narrows the admissible set (which candidate of a slot is used), it does not steer a search. R3 (the opening defect of the trilinear body, `width_rule_study.r3`) is recorded per design as a descriptive column. M3b's width rule is not decided here (WIDTH-RULE D-2/D-3).

### 3.4 Controls
- **Negative control NC (x-translation, `v18__roll_p25`)**: the parent translated by exactly one flow_32 cell and one SDF lattice cell (the M2 state, same bytes). It is not null: M2 measured -1.648e-3 N (SE 8.5e-5, P = 6) on flow_32 and -6.61e-4 N (SE 5.8e-5, 16 pairs) on OpenFOAM V1. It is run on flow_32 (all phases) and on V1 (all pairs) and judged **against those measured values** (§6.6), not against zero. It checks the whole measurement chain (state construction, pairing, placement, export, meshing) on new phases and shifts.
- **Extraction control EX (STL export)**: the parent, the W4 design and the N1 design (fixed now: the slot designs) are also exported with marching-cubes refinement r = 16 instead of the registered r = 8 (`geom02_canonical.export_from_state` with the profile's `export.refinement` replaced; X1 gate applied) and run on V3 at the V3 shifts (§5.2). The paired change of the difference, `Delta_r16 - Delta_r8`, measures how much the OpenFOAM difference depends on the export resolution (the WaterLily body samples the SDF directly). V3 is used because its surface cells (6.25-12.5 mm) are the only ones fine enough to see a 3 mm vs 1.5 mm triangulation.

## 4. WaterLily design
### 4.1 States and phases
- flow_32 (decision grid): parent, every design, NC: 1 + n_D + 1 states (n_D = number of non-empty slots) at phases **k = 7, 8, 9, 10** (the R2 sequence of M2, `f_k = frac(k (0.7548776662, 0.5698402910))`, disjoint from M2's k = 1..6 and U1's k = 0). All states share the phases (R4). P = 4.
- flow_48 (confirmation, R3): parent and every wide design (W and C slots) at phase **k = 7** (P = 1). Narrow designs and NC are not run on flow_48.
- Placement as M2: phase k moves `W4_CANONICAL_ORIGIN_M` by (f_kx, f_ky, 0) h_g; z never moves.
### 4.2 Kernels (`docs/harness/fid01_campaign.json`, `scripts/fid01/fid01_build.py campaign`)
| Kernel | Grid | Phases | Runs (n_D = 17) | per-state / aggregate cap / kernel timeout (s) | Estimate (s) |
| --- | --- | --- | --- | --- | --- |
| f32a | flow_32 | 7, 8 | 38 | 900 / 20000 / 23000 | 16,030 |
| f32b | flow_32 | 9, 10 | 38 | 900 / 20000 / 23000 | 16,030 |
| f48a | flow_48 | 7 | parent + first 6 wide | 6000 / 20000 / 23000 | 16,640 |
| f48b | flow_48 | 7 | parent + remaining wide | 6000 / 20000 / 23000 | 16,640 |
Every pair (design and parent at the same phase) is inside one kernel; phase-major order, parent first. Estimates: recorded maxima flow_32 415 s, flow_48 2,340 s per state plus 260 s setup per kernel; total about 18.4 GPU h (n_D = 17, 13 wide). The f48 kernels each carry their own parent at k = 7.
### 4.3 Budget, quota, queue
Cap **22 GPU h** of formal session time (Kaggle session wall from each kernel log). Push order f32a, f32b, f48a, f48b (two concurrent sessions). The cap governs only flow_48: before pushing f48a and f48b, `T = sum(session wall of finished kernels) + sum(estimate + 260 s of pushed unfinished kernels) + estimates of the f48 kernels`; if `T > 79,200 s` the f48 kernels are not pushed and flow_48 is `NOT_MEASURED` (recorded with its inputs). If the weekly quota stops a push: pause, resume in order, no rule change. **Backend trigger** (STATE.md): if any kernel waits more than 24 h in the queue, or the quota blocks the remaining kernels for more than 7 days, stop pushing and report the trigger; finished kernels stay valid, missing ones follow §10.
### 4.4 Blinding
While kernels run, only statuses, session times and `verify` pass/fail are read (`verify` tables are written to files, stdout discarded). No force of a design is read before the analysis (§10).

## 5. OpenFOAM design
### 5.1 Pipeline and environment
The U3 pipeline: the XFID X3 formal runner byte for byte except the bound criteria SHA (it discovers `x3_criteria.json`), the Round 5 case template (hash-identical minus the candidate STL), STL export `geom02_canonical.export_from_state` (r = 8, prescreen profile `docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json`) with the X1 practical gate on the double mesh and the float32 STL, simpleFoam with residual control, last-25 % iteration window, 0.32 N per coefficient. Executed locally with `scripts/local_openfoam.py run` in the locked image (`sha256:e9ceb8a7…25eb`); a run is valid only if `local_run.json` records return code 0 and `dpkg_after_matches_lock: true` (else `INFRA_LOSS`, §10).
### 5.2 Mesh levels and shifts
| Level | Template change (everything else hash-identical) | Cells (parent) | Shifts per state | Halton indices |
| --- | --- | --- | --- | --- |
| V1 | none (the U3/X3 mesh: blockMesh 25 x 13 x 9, snappy surface level (2 3)) | about 40k | 32 (16 mirror pairs) | 49-64 |
| V2 | blockMesh 50 x 26 x 18 | 212,822 (probe) | 4 (2 mirror pairs) | 49, 50 |
| V3 | blockMesh 100 x 52 x 36; controlDict endTime 6000 | 1,461,141 (probe) | 1 (the + member of pair 49) | 49 + |
V2/V3 halve and quarter the background cell (snappy levels are relative, so surface cells halve and quarter too), the convention of the Stage V V1/V2/V3 family (background = 4 voxels). Shifts: the X3 generator (Halton bases (2, 3, 5) magnitudes 0.5-4 mm, bases (7, 11, 13) signs, exact mirror pairs) at indices disjoint from X2/X3 (1-32) and U3 (33-48); identical for every state on a level; shift-major case order (every state of a shift before the next). NC runs on V1 only (its references are WaterLily and V1); EX STLs run on V3 at the V3 shift. "One phase" on V3 is the roadmap's "V2/V3 one phase"; V2 gets two mirror pairs because the V3 standard error is borrowed from V2 (§6.1) and needs a pooled estimate with enough degrees of freedom.
**Scope of the local environment gate.** LOCAL-OF-01 qualified the software (image, lock, runner, wrapper) on the V1 template: Kaggle and local force histories are byte-identical. V2/V3 change two input numbers of the template (block counts, endTime), not software; no Kaggle comparison exists or is needed for them, because every M3a OpenFOAM case runs locally in the same image (all comparisons are within one environment). This is stated as a limit, not a gate result.
### 5.3 Cost and execution
Probe (§9, parent, one shift, the shared host under load average 70-150): V2 snappy 137 s, 212,822 cells, concave cells 4.0 % (allowed), simpleFoam about 1.1 s per iteration (p residual 1.8e-4 at iteration 800, decaying about 0.62x per 100 iterations); V3 snappy 431 s, 1,461,141 cells, concave 2.0 %, simpleFoam about 10-12 s per iteration, peak container memory about 1.5 GiB. Estimates (local, single core per case): V1 640 cases x about 150 s = 27 CPU h; V2 76 cases x about 30 min = 38 CPU h; V3 21 cases x 6-10 h = 125-210 CPU h; in total 190-275 CPU h, i.e. 2-3 days of wall time at four concurrent containers. Kernels (each a criteria file and a dataset, all with the same runner bytes, run with `--cpus 1`, `--memory 8g`): V1 four kernels of four whole mirror pairs (49-52, 53-56, 57-60, 61-64); V2 one kernel per shift (4); V3 one kernel per shift with its states split into groups of at most six cases (4 kernels); at most four containers at a time, V3 kernels first. Stage timeouts: V1 1800 s, V2 3600 s, V3 43,200 s per stage. The parent's V3 convergence in the probe is recorded at freeze 2 (it was still running when this revision was written). **Pre-registered contingency (status only):** if the V3 probe of the parent does not reach `SIMPLE solution converged` before endTime 6000, V3 is removed before freeze 2 (freeze 1 amendment) and G1/G3 use V1 and V2; the record carries `V3_NOT_CONVERGED`.
### 5.4 Case validity
A case is valid if every stage returns 0 (checkMesh exit 1 allowed only for the registered single concave-cell failure with fraction <= 0.08) and simpleFoam reports `SIMPLE solution converged` (residual control met; a run that only reaches endTime is invalid). Matching is per design: on V1 a design uses the mirror pairs where it and the parent are valid at both members (M2's whole-pair unit); on V2/V3 the shifts where both are valid. A failed parent case therefore removes that shift (V1: that pair) for every design; a failed design case only for that design. Minimum data (parent): V1 >= 12 valid pairs, V2 >= 2 valid shifts, V3 its one shift; below it the outcome is `FID01_INVALID` (§6.7). A design below the same minimum on a level has no value there (UNRESOLVED, §6.3).
### 5.5 Blinding and order
All OpenFOAM kernels start after freeze 2 regardless of any WaterLily result. While they run only statuses, stage return codes, cell counts and times are read. Force fields are read only by the analysis.

## 6. Rules (computed by the frozen `scripts/fid01/analyze_fid01.py`)
Response: downforce (decision); drag is the constraint response (G5b) and is reported throughout. Differences are design minus parent at the same phase (WaterLily) or the same shift (OpenFOAM).
### 6.1 Estimators
- **WaterLily flow_32** (P = 4): `Delta_bar`, `sigma_d` (P - 1 dof), the M2 estimator (`analyze_unc01.stats`). For the 3-sigma test the standard error has an M2 floor: `SE_eff = max(sigma_d, 2.09e-4 N) / sqrt(P)` (2.09e-4 N = the M2 flow_32 sigma_d of the roll, the paired-difference floor when the discretisation is identical, and the smallest wide-arm sigma_d).
- **flow_48** (P = 1): `Delta_48`, no SE.
- **OpenFOAM V1**: the M2 U3 estimator: the unit is the mirror-pair mean of matched-shift differences; `Delta_bar_V1`, `SE_V1` (pairs - 1 dof), `sigma_d,shifts`.
- **OpenFOAM V2, V3**: `Delta_bar_g` = mean over the design's matched valid shifts (design and parent valid at the same shift); `SE_g = sigma_pool,V2 / sqrt(n_g)`, where `sigma_pool,V2` is the pooled SD of the V2 per-shift differences around each design's V2 mean, pooled over every design (dof = sum of (n_shifts - 1), about 51), and n_g the design's number of valid shifts on level g. V3 has one shift and no own noise estimate; it borrows the V2 value as a proxy (the placement noise comes from snapping the STL to the background cells and is expected to shrink with the cell size, so the V2 value should over-state the V3 noise). Shifts are treated as independent (the mirror structure is ignored). Disclosed: the pooled SD assumes similar placement noise across designs; M2's V1 single-shift SDs ranged 4e-4 to 1.6e-3 N across states.
### 6.2 Minimum gain and the decision set D
- `Delta_min = 2 S_d |J_b,48| = 0.0067994 x 0.265779 N = 1.807e-3 N` (M2 paired E2, §7.2).
- A **wide** design (W, C slots) is in **D** iff `|Delta_bar_WL,32| >= Delta_min` and `|Delta_bar_WL,32| > 3 SE_eff`. Both signs count (a resolved loss that persists is the same fidelity evidence as a gain; the improvement-only subset D+ is reported, §6.9).
- D is computed from WaterLily only; no OpenFOAM value enters it.
- **Valid decision set**: |D| >= 8, D contains designs of >= 3 of the 4 wide families (rigid, section, span, combination), and >= 3 designs of D have `Delta_bar > 0`. Otherwise `FID01_INCONCLUSIVE_DESIGN_SET`.
### 6.3 The five G rules for a design i in D (s_i = sign of `Delta_bar_WL,32`)
Each rule returns PASS, FAIL (a resolved failure) or UNRESOLVED.
- **G1 sign on every OpenFOAM level** g in {V1, V2, V3}: PASS if `sign(Delta_bar_g) = s_i`; FAIL if the sign differs and `|Delta_bar_g| > 2 SE_g`; else UNRESOLVED. G1 = FAIL if any level fails, else UNRESOLVED if any is unresolved, else PASS. A level without data is UNRESOLVED.
- **G2 above 3 sigma**: the WaterLily part holds by the definition of D; the OpenFOAM part on the powered level V1: PASS if `s_i Delta_bar_V1 > 3 SE_V1`, else FAIL (V1 has 16 pairs, SE about 1-2.4e-4 N in M2; a decision-size difference that does not clear 3 SE there has not persisted).
- **G3 spread across levels**: x_g = `Delta_bar_g` on V1, V2, V3; m = median, R = max - min. PASS if `R <= 0.5 |m|`; FAIL if `R - 2 sqrt(SE_max^2 + SE_min^2) > 0.5 |m|` (SE of the levels attaining the max and min); else UNRESOLVED. Any level missing: UNRESOLVED.
- **G4 retention** `rho = Delta_bar_V1 / Delta_bar_WL,32` with the M2 interval on |rho| (`exp(log|rho| +- t' sqrt((SE_V1/Delta_V1)^2 + (SE_eff/Delta_WL)^2))`, t' at min(P, pairs) - 1 dof): PASS if `0.5 <= rho <= 2.0`; FAIL if `rho <= 0` or the interval lies entirely below 0.5 or entirely above 2.0; else UNRESOLVED. The upper bound 2.0 is added to #62's "at least 0.5" (the E1 band 0.5-2.0 of the same document): a retention above 2 means WaterLily's difference does not predict the magnitude, which also misranks designs. rho on V2, V3 and on the level median are reported.
- **G5 constraints confirmed on OpenFOAM**: (a) geometry: the design's exported STL passes the X1 practical gate (watertight, manifold, positive volume, clearance, orientation; double and float32) and its STL volume relative to the parent STL is within the registered 10 % band (`|V_STL(i) / V_STL(parent) - 1| <= 0.10`) — both fixed at freeze 1; (b) drag, the constraint response M3b will carry: FAIL if the drag difference is resolved above 3 SE on both WaterLily flow_32 (SE_eff with the M2 drag floor 1.36e-4 N, the roll's drag sigma_d) and V1 with opposite signs; else PASS. G5 = FAIL if (a) or (b) fails.
A design PASSes if all five PASS; FAILs if any FAILs; else it is UNRESOLVED.
### 6.4 Narrow stratum (registered secondary label)
Narrow designs (N slots) meeting the D criteria are judged with the same G rules: `NARROW_UNTESTABLE` (none eligible), `NARROW_FAIL` (any FAIL), `NARROW_PASS` (all PASS), else `NARROW_UNRESOLVED`. No effect on the outcome; it informs R2 (local modes stay out of M3b in any case; `NARROW_FAIL` with `FID01_GO` is the expected pattern under R2).
### 6.5 flow_48 confirmation (R3, registered secondary label)
For each design in D: `R3_CONFIRMED` if `sign(Delta_48) = s_i`; `R3_CONTRADICTED` if the sign differs and `|Delta_48| > 2 max(sigma_d,32, 2.09e-4)` (the design's own flow_32 sigma_d as the single-phase noise proxy; M2: flow_48 sigma_d 4.97e-4 vs flow_32 5.46e-4 for pitch +3.1); else `R3_UNRESOLVED`. Ratio `Delta_48 / Delta_bar_32` and the per-design paired E2 term `|Delta_48 - Delta_bar_32| / |J_b,48|` are descriptive. Consequence: any `R3_CONTRADICTED` in D makes the record carry `R3_CHALLENGED`, and M3b must confirm every candidate on flow_48 with P >= 2.
### 6.6 Controls
- **NC**: `NC_WL_CONSISTENT` if `|Delta_bar_roll,32 - (-1.648e-3)| <= 3 sqrt(SE_32^2 + (8.53e-5)^2)` (SE_32 = the roll's own SE, no floor); `NC_OF_CONSISTENT` if `|Delta_bar_roll,V1 - (-6.61e-4)| <= 3 sqrt(SE_V1^2 + (5.79e-5)^2)`. Both are required; either inconsistency makes the outcome `FID01_INVALID` (the chain does not reproduce a measured difference on new phases/shifts; the cause is investigated before any further registered run). A 3-sigma consistency rule has a false-alarm rate of about 0.3 % per test under correct operation.
- **EX** (W4 and N1 on V3, each against the parent at the same export resolution): `delta_EX(i) = (F_r16(i) - F_r16(parent)) - (F_r8(i) - F_r8(parent))` at the V3 shift. `EXPORT_INSENSITIVE` if `|delta_EX| <= 0.1 |Delta_V3,r8(i)|` or `|delta_EX| <= 2 sqrt(2) sigma_pool,V2`; else `EXPORT_SENSITIVE`. The parent's absolute change `F_r16 - F_r8` is reported. Consequence: none on the outcome; `EXPORT_SENSITIVE` for W4 obliges XV-01 to register an export-resolution check (or r = 16).
### 6.7 Outcome (evaluation order)
1. Minimum data: flow_32 with P >= 3 phases for every state; the parent at its OpenFOAM minimum on every level (§5.4). Otherwise `FID01_INVALID` (minimum data).
2. NC inconsistent: `FID01_INVALID`.
3. Decision set not valid (§6.2): `FID01_INCONCLUSIVE_DESIGN_SET`.
4. Any design in D FAILs: `FID01_NO_GO`.
5. Every design in D PASSes: `FID01_GO`.
6. Otherwise (no FAIL, some UNRESOLVED): `EXTENSION_REQUIRED` → §6.8.
### 6.8 Registered extension (at most once; part of this registration, not an amendment)
For every UNRESOLVED design in D, the parent and that design are run on the level(s) responsible (for G1 the unresolved levels, for G3 the levels attaining the maximum and the minimum or the missing ones, for G2/G4 V1): V1 Halton pairs 65-72, V2 pairs 51-52, V3 the shifts 49 -, 50 +, 50 - (three more). Then `analyze_fid01.py extension` recomputes those designs once with all shifts (pooled SDs recomputed with the added shifts) and the outcome is re-evaluated by §6.7 with **every remaining UNRESOLVED counted as FAIL**. No other design and no rule changes. The main analysis output stays as written.
### 6.9 Reported for every design (descriptive)
All estimators on every grid and level; support, maximum change, smoothed and STL volume change; R0 and R3 status; rho per level; the improvement-only subset D+ and its verdict; the outcome recomputed at the **literal** E2 threshold (`Delta_min,lit = 0.020180 x 0.265779 = 5.363e-3 N`, same validity rule); the sub-threshold wide designs (resolved but below Delta_min) with their G values; the correlation of WaterLily and OpenFOAM differences over all designs.

## 7. Coefficients fixed from M2 (and the E2 choice)
### 7.1 Table
| Coefficient | Value | Source (`docs/evidence/unc01_2026_10_20/analysis.json`) | Use |
| --- | --- | --- | --- |
| S_d (downforce, common phases) | 0.0034 (SE 0.0015) | `Q4_E2.downforce.common_phases.S_d` | Delta_min (§7.2) |
| J_b,48 | 0.265779 N | `...denominator_n` | Delta_min |
| S_b, S_c | 0.0067, 0.0101 | same block | literal threshold (descriptive) |
| sigma_d floor (downforce) | 2.09e-4 N | `grids.flow_32.differences.v18__roll_p25.downforce.sigma_d_n` | SE_eff, R3 noise proxy |
| sigma_d floor (drag) | 1.36e-4 N | same, drag | G5b |
| NC reference WL | -1.648e-3 N, SE 8.53e-5 | roll flow_32 downforce | §6.6 |
| NC reference OF | -6.61e-4 N, SE 5.79e-5 | `u3.differences.v18__roll_p25.downforce` | §6.6 |
| flow_32 / flow_48 ratio | 0.980 [0.962, 0.999] | `Q3` | context for R3 (no rule) |
| OF retention (wide arms) | 0.63-0.71 | `u3` | context for G4 (no rule) |
### 7.2 E2: the paired form (2 S_d) is adopted; the literal form is reported
E2 (`architecture_effectiveness_2026_09.md` §9) asks the normalised improvement to exceed twice the grid sensitivity: `I_f > 2 max(S_b, S_c)`, where S_b, S_c are the medium-to-fine shifts of each shape's **absolute** objective. Decision for M3a (and, if GO, for SCREEN-01 and XV-01): **the minimum gain is `2 S_d` with S_d the grid sensitivity of the paired difference itself**, i.e. 0.68 % of |J_b,48| (Delta_min = 1.807e-3 N). Reasons:
1. R1 (approved 2026-10-16) makes paired same-phase differences the decision quantity. The quantity whose grid error E2 guards is then the difference, and its medium-to-fine change is exactly S_d. S_b and S_c measure absolute shifts that are common to both shapes and cancel in the pair (M2: common phases remove 71-89 % of the parent's placement spread; S_d < min(S_b, S_c)).
2. The mapping SCREEN-01 asks to fix ("which component of sigma_d maps to S_b and S_c"): in the paired form both are replaced by S_d (one term), measured with the same J, grids (flow_48 = f, flow_32 = m), common phases and J_scale as M2.
3. Conservative where it matters: S_d was measured on the largest lever (pitch +3.1 deg), where the 2 % multiplicative grid difference dominates (|Delta_48 - Delta_32| = 9.0e-4 N); for smaller responses the multiplicative part is proportionally smaller, so 2 S_d over-states their grid error.
4. The literal threshold (2.0 %, 5.363e-3 N) would leave only pitch-, camber- and reflex-sized changes testable and would turn M3b into a screen of large rigid levers, which is not the hypothesis.
Against it, stated: S_d has SE 0.0015 (its 90 % upper bound is about 0.0069, i.e. 1.4 %), it rests on one state and four common phases, and |.| of a noisy difference is biased upward by about 0.8 SE. Therefore the outcome at the literal threshold is computed and printed beside the registered one (§6.9), and Delta_min is fixed now from M2 (not re-estimated from M3a data).

## 8. Consequences
- `FID01_GO`: M3b may be registered (SCREEN-01 #64 first). This registration fixes for it: the paired E2 minimum gain 2 S_d (§7.2), the G rules and coefficients of §6.3 for XV-01, the OpenFOAM procedure of §5 (levels, shifts, validity), the R3 and EX consequences (§6.5, §6.6).
- `FID01_NO_GO`: the pre-committed branch: a smooth-advection-scheme WaterLily test first (one cheap registered test; its issue is opened with the NO-GO record, budget and stopping rule fixed there), then the T2-0 evaluator via M4 (#66). #64 and #65 are closed as not planned. No AD diagnosis round.
- `FID01_INCONCLUSIVE_DESIGN_SET`: no M3b. A new registration with designs chosen to meet §6.2 is required; nothing else changes.
- `FID01_INVALID`: no M3b; the failing control or data loss is diagnosed and recorded; a new registration follows.

## 9. What was visible before this registration
- All of M2 (registered) and its U1 exploratory single-phase flow_32 values (camber ±19.7: -1.04e-2 / +1.31e-2 N; reflex ±29.3; twist ±1.1: +1.6e-3 / -1.2e-3 N; sweep ±11.3: about 1e-4 N; pitch ±3.1). They were used to (i) drop sweep as a single design, (ii) expect camber, reflex, twist sizes. W4, W5 and W8 are U1 states (their native-phase WaterLily values are known; M3a uses new phases). No OpenFOAM value of any M3a design exists.
- The design prescreen and STL export of every candidate (geometry only).
- The OpenFOAM V2/V3 timing probe of the parent at one shift (Halton 49 +): statuses, stage times, cell counts, iteration counts and convergence only; the force fields were not read (the probe output is outside the repository; its `result.json` SHA-256 is recorded in the freeze).
Nothing in §1-§8 was chosen after a force of an M3a design was seen; no M3a force exists.

## 10. Freeze, re-run, amendment and stopping rules (fail-closed)
- Order: §2. Freeze 1 and freeze 2 are committed, pushed and commented on #62 before the corresponding runs.
- `INFRA_LOSS` (a WaterLily kernel or an OpenFOAM kernel that ends without output for an infrastructure reason: install, GPU identity, Kaggle error, session kill, Docker failure, host crash, `dpkg_after_matches_lock` false): one identical rerun per kernel; the first valid output is authoritative; both are archived. A per-case solver or mesh failure, a timeout or an unexpected value is a result (§5.4), never a reason to rerun.
- Engineering defect found by a smoke before freeze 2: fixed and re-frozen (freeze 1 amendment with diff and reason); rules never change.
- Amendment after freeze 2 (`REGISTERED_AMENDED`): only for a defect that prevents a pre-specified quantity, filed on #62 before any verdict-relevant output is read, never touching a rule; the original outcome (or `INCOMPLETE`) is kept beside it.
- The analysis is written once (`analyze_fid01.py main --out` opens the file exclusively); it cross-checks every kernel file it reads against the verified tables and criteria; `analysis.md` is its human summary, written once. Later readings are dated separate notes.
- Session budget: WaterLily 1 smoke + 4 formal (+ one INFRA_LOSS rerun each); OpenFOAM 1 development smoke + the formal kernels (+ one INFRA_LOSS rerun each) + the §6.8 extension kernels if triggered.

## 11. Freeze content
**Freeze 1** (`docs/evidence/fid01_2026_10_21/freeze1.json`): source commit; SHA-256 of this registration; `scripts/fid01/*.py`, `tests/fid01/*.py`; reused code (`v18_plate.py`, `mode01_v18_prescreen.py`, `mode01_prescreen.py`, `mode01_modes.py`, `step01_states.py`, `geom02_canonical.py`, `build_xfid45_stage_v_input_2026_10_04.py`, `prepare_kaggle_xfid_gridphase_x3.py`, `unc01_u3_prepare.py`, `analyze_unc01.py`, `width_rule_study.py`, `local_openfoam.py`, the harness tool hashes); inputs (`designs.json`, `states.json`, every direction raw, `export.json`, every STL, the OpenFOAM criteria, datasets' file hashes, runners); the M2 analysis SHA and the coefficient values of §7.1 as read from it; python, numpy, scipy, scikit-image versions; the probe record.
**Freeze 2** (`freeze2.json`): the harness campaign and its prerun freeze (smoke table SHA), the OpenFOAM development smoke record (sanitised), the budget-rule inputs known at that time. Nothing in §1-§8 changes at freeze 2.

## 12. Outputs and documentation
`docs/evidence/fid01_2026_10_21/`: `designs.json`, `states.json`, `inputs/`, `export.json`, `freeze1.json`, `freeze2.json`, `wl/` (smoke, kernel outputs, per-kernel verify tables, budget decision), `of/` (criteria, smoke, outputs as tar archives with manifests, local run records), `analysis.json` (+ `analysis_extension.json` if §6.8), `analysis.md`, `README.md`, `SHA256SUMS` (split per directory if it exceeds about 5,000 entries; passes `scripts/check_sha256sums_tracked.py`; `*.log` tracked). Also `docs/STATE.md` (M3a row, "Updated"), a `docs/phase_plan.md` entry, `docs/exploratory_index.md` (the probe), comments on #62 at freeze 1, freeze 2 and the result.

## 12a. Plan review record
(to be filled after the review)

## 13. Source review record
(to be filled after the source review)
