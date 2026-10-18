# STATE — current position in one page (overwrite at each milestone; the history is in `docs/phase_plan.md`)

Updated: 2026-10-19 (M1 done: JOB-02 gate passed). Integration branch: `codex/kaggle-batch-migration`. Roadmap authority: `docs/phase_plan.md` (latest entry: "2026-10-16 roadmap re-baseline").
Re-plan document: `docs/roadmap_review_2026_10_16.md`.

## Goal
SDF-native shape/topology optimizer whose improvements are confirmed by independent body-fitted CFD on grids not used in optimization; final use FSAE aero (target physics Re 1e5-6e6, turbulent, ground effect). No deadline (user, 2026-10-16).

## Where we are
- Physics so far: Re = 80 reduced laminar only (WaterLily Candidate C on Kaggle T4; OpenFOAM Stage V on Kaggle CPU).
- No optimized shape has had its improvement confirmed by independent CFD. Accepted gains so far: 0.01-0.2 % downforce.
- Diagnosis: the response DIFFERENCE (slope) varies 50-100 % with flow grid and grid placement; flow_24 is the outlier, flow_32 and flow_48 agree; wide-support smooth modes (uniform offset D0) agree WaterLily vs OpenFOAM within 2 %.
- Gradient backends (forward/reverse AD) BLOCKED, cause unidentified; research only (#23).
- M2 (UNC-01) is blocked on the parent/mode-basis decision from MODE-01.
- All qualification flags false; `shape_update_allowed=false`.

## Principles (R1-R6)
R1 decide on paired differences with measured sigma_d and the E2 rule I_f > 2 max(S_b, S_c); R2 wide-support smooth (rigid/analytic) modes; R3 optimize on flow_32, confirm on flow_48, flow_24 demoted; R4 common random placement phases per generation, finalists on the full phase set; R5 screening + small response surface (no gradient, no CMA-ES/BO); R6 common campaign harness first.

## Process (PROC-01, approved 2026-10-16)
- `EXPLORATORY_COMMITTED`: committed script + output hashes + short note; never feeds flags, thresholds or claims; listed in `docs/exploratory_index.md`.
- `REGISTERED_FROZEN` / `REGISTERED_AMENDED`: pre-registration, freeze, independent review (1 plan review with 3 angles + 1 source review max), fail-closed. Required for M2, M3a, M3b and any claim.

## Milestones (order)
| ID | Issue | Status |
| --- | --- | --- |
| M0 re-baseline | #41, #18 closed; #24, #25, #39 closed | done 2026-10-16 |
| T2-0 FSAE RANS feasibility (parallel) | #57 | T2-0a done (exploratory): 2D ground-effect wing, SA Cl within ~5 % of experiment, peak h/c matches; T2-0b next |
| M1 common harness + per-state placement job | #58 closed, #59 closed | done 2026-10-19: harness v1.1 merged; JOB-02 per-run (x, y) placement in one kernel (optional run `name`, z fixed per kernel) passed its byte-identity gate on Kaggle T4 (`JOB02_GATE_PASS`, 4/4 force CSVs: native and GRID-02-shifted parents, flow_24 and flow_32; `docs/evidence/job02_gate_2026_10_19/`). The gate was run ahead of UNC-01 instead of inside its smoke because its references are the existing parents and do not depend on B1; the UNC-01 smoke only has to check its new parent |
| M1' wide-support volume-neutral modes (solver-free) | #60 | prescreen done (exploratory): the OPT-01 v1 parent admits no wide-support mode (lattice-plane ties, pinned end layers, 2-3 cell slab); parent choice awaits the user (v18 analytic plate recommended) |
| M2 paired-difference uncertainty sigma_d | #61 | after M1, M1' |
| M3a fidelity go/no-go (no optimizer) | #62 | after M2 |
| M3b screening + response surface + independent verification | SCREEN-01, XV-01 | only if M3a GO |
| M4 evaluator / product-scope decision | — | after M3, T2-0 |
| M5 topology, multi-step loop, CLI | #32, #33, #40 | after M4 |
NO-GO branch (pre-committed): smooth-advection-scheme WaterLily test first, then move to the T2-0 evaluator.

## Compute backend (user, 2026-10-16)
Kaggle T4 (GPU) and Kaggle CPU (OpenFOAM) stay the backends for now. The user knows GPU rental APIs could cut cost and wants to decide a switch only when it becomes necessary, not a full switch now. Triggers to raise the decision: weekly GPU need above the Kaggle quota (~30 h), queue/round-trip latency dominating a milestone, or a run class Kaggle cannot hold (e.g. 3D high-Re WaterLily, > 12 h sessions). The harness keeps the runner portable (working root via CAMPAIGN_WORK_ROOT); submission stays the only Kaggle-specific step.

## Standing facts to remember
- OpenFOAM is kept (2026-10-16 reversal of the 10-02 removal direction); working Kaggle CPU recipes: `infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/`.
- Kaggle: 2 concurrent GPU sessions, ~30 GPU h/week; per-state T4 solver time flow_24 ~175 s, flow_32 ~400 s, flow_48 ~2,200 s.
- Full pytest in a fresh worktree has 50 pre-existing failures (missing ignored `work/` fixtures); compare failure-ID sets, not counts.
