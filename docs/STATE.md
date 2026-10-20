# STATE — current position in one page (overwrite at each milestone; the history is in `docs/phase_plan.md`)

Updated: 2026-10-19 (incl. the T2-0b row and M1 done: JOB-02 gate passed); 2026-10-21 compute backend: LOCAL-OF-01 (OpenFOAM local for the U3 pipeline, T2-0c stays on Kaggle CPU). Integration branch: `codex/kaggle-batch-migration`. Roadmap authority: `docs/phase_plan.md` (latest entry: "2026-10-16 roadmap re-baseline").
Re-plan document: `docs/roadmap_review_2026_10_16.md`.

## Goal
SDF-native shape/topology optimizer whose improvements are confirmed by independent body-fitted CFD on grids not used in optimization; final use FSAE aero (target physics Re 1e5-6e6, turbulent, ground effect). No deadline (user, 2026-10-16).

## Where we are
- Physics so far: Re = 80 reduced laminar only (WaterLily Candidate C on Kaggle T4; OpenFOAM Stage V on Kaggle CPU).
- No optimized shape has had its improvement confirmed by independent CFD. Accepted gains so far: 0.01-0.2 % downforce.
- Diagnosis: the response DIFFERENCE (slope) varies 50-100 % with flow grid and grid placement; flow_24 is the outlier, flow_32 and flow_48 agree; wide-support smooth modes (uniform offset D0) agree WaterLily vs OpenFOAM within 2 %.
- Gradient backends (forward/reverse AD) BLOCKED, cause unidentified; research only (#23).
- M2 (UNC-01): parent = v18 analytic plate (B1, user 2026-10-19), basis proposed (MODE-01 v18); draft pre-registration written, freeze waits for JOB-02 (#59).
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
| T2-0 FSAE RANS feasibility (parallel) | #57 | T2-0a done (exploratory). T2-0b done 2026-10-19 (REGISTERED_FROZEN): **T20B_NO_GO** for the 2D-section SA wall-function evaluator: G2 fails (Cl peak at h/c 0.179 not 0.134; mean error 4.24 % but 5.45 % with the 0.15 deg incidence ambiguity), G3b fails (h/c 0.09 incidence derivative med30 0.055 vs fine30 0.082 per deg), G6 fails (+-0.25 deg not resolved above remeshing noise at h/c 0.134); G2d, G3a, G3c, G4, G5 pass; LM_DATA_AGREES (limit cycle, ~3.5 h/case); ADJ_FAILED; DAFoam not attempted. High-Re evaluator adoption (#66 item 1) is NO-GO on this basis; next per the registered table: wall-resolved/LM study or another validation case, and a fixed-topology (morphing) mesh study. Record: `docs/evidence/t20b_registered_2026_10_19/` |
| M1 common harness + per-state placement job | #58 closed, #59 closed | done 2026-10-19: harness v1.1 merged; JOB-02 per-run (x, y) placement in one kernel (optional run `name`, z fixed per kernel) passed its byte-identity gate on Kaggle T4 (`JOB02_GATE_PASS`, 4/4 force CSVs: native and GRID-02-shifted parents, flow_24 and flow_32; `docs/evidence/job02_gate_2026_10_19/`). The gate was run ahead of UNC-01 instead of inside its smoke because its references are the existing parents and do not depend on B1; the UNC-01 smoke only has to check its new (v18) parent |
| M1' wide-support volume-neutral modes (solver-free) | #60 | done (exploratory) 2026-10-19: B1 = v18 analytic plate (user); v18 parent passes all gates; MODE-01 v18 `V18_BASIS_READY` (heave, pitch, camber, reflex, twist, sweep + surge control), binding only in the M2 registration; min_feature_width is the binding gate on the smooth plate (40-50 % of sub-cell placements fail) |
| M2 paired-difference uncertainty sigma_d | #61 | pre-registration draft `docs/unc01_preregistration_draft_2026_10_19.md` (not frozen); JOB-02 (#59) is done (2026-10-19), so the freeze now waits only for the draft's own TODOs |
| M3a fidelity go/no-go (no optimizer) | #62 | after M2. Width rule for smooth bodies (UNC-01 TODO 0): exploratory WIDTH-RULE 2026-10-20, `NO_CANDIDATE_MEETS_K1_K6`; proposal `docs/width_rule_decision_2026_10_20.md`: M3a keeps the registered `min_feature_width` (R0-clean designs, R3 descriptive) |
| M3b screening + response surface + independent verification | SCREEN-01, XV-01 | only if M3a GO. R0 rejects 190/200 optimiser-like v18 combinations for a one-cell occupancy artefact; proposal: R3 (opening defect of the trilinear body) + frozen-node margin + fixed-topology gates, validated in a registered run on disjoint data before any optimiser run |
| M4 evaluator / product-scope decision | — | after M3, T2-0 |
| M5 topology, multi-step loop, CLI | #32, #33, #40 | after M4 |
NO-GO branch (pre-committed): smooth-advection-scheme WaterLily test first, then move to the T2-0 evaluator.

## Compute backend (user, 2026-10-16)
Kaggle T4 (GPU) and Kaggle CPU (OpenFOAM) stay the backends for now. The user knows GPU rental APIs could cut cost and wants to decide a switch only when it becomes necessary, not a full switch now. Triggers to raise the decision: weekly GPU need above the Kaggle quota (~30 h), queue/round-trip latency dominating a milestone, or a run class Kaggle cannot hold (e.g. 3D high-Re WaterLily, > 12 h sessions). The harness keeps the runner portable (working root via CAMPAIGN_WORK_ROOT); submission stays the only Kaggle-specific step.
OpenFOAM runs locally in Docker (user, 2026-10-20, verbatim: 「そうだね、タスクが重そうなのでopen formはローカルにしようか」), gated by LOCAL-OF-01 (`docs/local_openfoam_env_gate_2026_10_20.md`): image `sha256:e9ceb8a7…25eb` (linux/amd64 noble under Rosetta, OpenFOAM 2512.0-2 from the registered noble lock), lock `infra/local_openfoam/local_openfoam_lock.json`, wrapper `scripts/local_openfoam.py run` (usage `infra/local_openfoam/README.md`). Round 1 (2026-10-21): the U3 / XFID X3 pipeline passes bit for bit (`LOCAL_ENV_PASS_BITWISE`: X3 and v18 force histories byte-identical to Kaggle) -> UNC-01 U3 runs locally; the T2-0c pipeline fails (`LOCAL_ENV_FAIL`: OpenFOAM is deterministic locally, but gmsh meshes of rotated or displaced geometries differ from Kaggle's in 86 of 262 geometries, Cl moves by the remeshing sigma) -> T2-0c stays on Kaggle CPU. WaterLily stays on Kaggle T4.

## Standing facts to remember
- OpenFOAM is kept (2026-10-16 reversal of the 10-02 removal direction); working Kaggle CPU recipes: `infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/`; the same runners run locally under LOCAL-OF-01 (X3/U3 family only).
- The T2-0 gmsh generator is not run-to-run deterministic at the mesh-file level (numbering variants; 7 of 41 geometries differ between two Kaggle sessions) and its meshes of rotated or displaced geometries depend on the platform's floating point (LOCAL-OF-01).
- Kaggle: 2 concurrent GPU sessions, ~30 GPU h/week; per-state T4 solver time flow_24 ~175 s, flow_32 ~400 s, flow_48 ~2,200 s.
- Full pytest in a fresh worktree (no `work/`): 0 failed, 2873 passed, 73 skipped; with `work/` symlinked to the main checkout: 0 failed, 2920 passed, 26 skipped. The 39 formerly failing tests skip via `tests/conftest.py::requires_work` (reason names the missing gitignored path) or, for one sha256-pinned test file, by node id in conftest; one more skips when `case_metadata.json` bakes in another checkout's absolute path. 74 Kaggle kernel `*.log` files were recovered with matching sha256 and are tracked (`.gitignore` negation `!docs/evidence/**/kernel_output/**/*.log`); 22 manifest logs of failed-attempt/forward-bridge kernels are not recoverable and no test uses them. Several `SHA256SUMS` still list untracked/missing logs (`kaggle_kernel.log`, `push1.log`, validation pytest logs), so `scripts/check_sha256sums_tracked.py` fails on those evidence directories (pre-existing, not addressed here).
