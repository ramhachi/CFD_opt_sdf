# OPT-01 v1.1 Stage A preregistration (#30, #25): STATUS READY (frozen by `prerun_freeze.json`), nothing submitted

Date: 2026-10-15. Plan: `docs/opt01_v1_plan_2026_10_15.md` (Amendment 1 E1-E8, Amendment 2 F1-F3). Contract: `docs/evidence/opt01_v1_2026_10_15/opt01_v1_1_contract.json` (v1.1, sha256 `0f164a4e...0ba1`,
pinned in `scripts/opt01a_states.py`; predecessor v1 `f76a09c7...43e2` stays as history). Evidence class: solver-free registration of Stage A; no CFD was run. Authority is the interpretation recorded in the contract
(user words of 2026-10-13, not a #30-specific grant).

**Supersession.** This note and `inventory.json` replace the earlier `BLOCKED_PRE_CFD` draft of commit `576441c` (inventory sha256 `52f4b1d6...53cd`, in git history, recorded in `inventory.json` `supersedes`).
The only change in the inputs is the gate scope F1 of contract v1.1; the nine states, the parent and every threshold are byte-identical.

## Question

For `flow_24` and `flow_32`: the new OPT-01 v1 parent plus the eight centered perturbations D0/D1/D2/P1 x -/+ 1.25 mm of that parent (nine states per grid, 18 runs, two T4 kernels `ramhachi888/cfd-opt-sdf-opt01a-{a,b}`, LOWDIM-04A
per-state timeout 900 s and aggregate cap 8100 s per kernel). Centered secants, the pinned LOWDIM cone solver, epsilon 0.012 N/m.

## New parent identity

The LOWDIM-04B selected state (LOWDIM-03 parent + 0.3125 mm x the robust Stage A direction, rebuilt with `construct_state` and hash-checked against the 04B inventory) re-created with generation 0 -> 1 (E4). Phi hashes are unchanged
(Fortran `2f23be78...`, C `ff4d3058...`); `state_sha256` changes `64e4efb1...` -> `c9e12f62...`. Children keep the new parent's generation (construct_state semantics). Mapping and NPZ: `inventory.json` `parent.lineage`.

## Gate scope (F1) and pre-CFD result (computed once in the inventory on the exact bytes; none in the kernel)

Probe states (the eight +-1.25 mm perturbations): twelve GEOM-02 profile v2 gates, P22-v2 `N_phi <= 8272` with a positive count-equal margin, the retained smoothed-volume band and clearance, and `allowed_events = ()` are hard;
`near_zero_gradient_band` (crossing-slope rule) is **report-only**. The parent is a proposal state: all 13 gates hard. A Stage B ladder step would also keep the full bundle (a failure is a REJECT of that step).
**Result: the parent passes 13/13 (also from the LOWDIM-03 parent, the E4 stop rule) and all eight probes pass every hard gate**; the count-equal margin is 2.199e-3 m at the parent and 0.949e-3 m at every probe.

Report-only `near_zero_gradient_band` (failing crossing-slope nodes below 0.5 / interior sign-change nodes) with attribution to the baseline tie plateau (v17 genesis `|phi| < 1e-6`, 5,370 nodes):

| probe | failing | on baseline plateau | off plateau |
|---|---|---|---|
| D0- | 284 / 9,299 | 284 | 0 |
| D0+ | 0 / 8,038 | - | - |
| D1- | 40 / 8,134 | 40 | 0 |
| D1+ | 153 / 8,326 | 153 | 0 |
| D2- | 3 / 8,045 | 3 | 0 |
| D2+ | 206 / 8,416 | 206 | 0 |
| P1- | 0 / 8,038 | - | - |
| P1+ | 212 / 8,408 | 212 | 0 |

Every failing node is a baseline tie-plateau node (the planner's check, here recomputed and cross-checked against the gate's counts). Interpretation: inside a plateau the perturbation alone decides the sign, so the zero set there is set by tiny
differences of the direction: a v17 representation ill-conditioning, not a gate defect. The representation fix (a re-genesis on a lattice offset) is follow-up work, not done here (F3).

## Rules that apply (unchanged from LOWDIM-04A, imported not re-implemented)

Parent byte-identity: the fresh parent CSV on each grid must equal the retained LOWDIM-04B `prop__s0.3125mm` CSV before any other state runs, else INCOMPLETE. Secants `[R(+s)-R(-s)]/(2s)`, s = 1.25 mm; resolved if |contrast| > 3e-5 N; `LOCAL_FEASIBLE_CONE_FOUND`
only if both the main and the L1-robust cross-grid problems pass (t* above 1e-8 and predicted 1.25 mm downforce at least 3e-5 N on both grids), else NOT_FOUND; any integrity failure gives `OPT01A_INCOMPLETE` with no analysis.
Exit-rule amendment: plan Amendment 1 E3 (one further cycle to test the complete contract prospectively, not for gain). Estimated runtime: up to 8100 s per kernel (nine states x 900 s cap), both kernels in parallel; kernel timeout 10800 s.

## Disclosure and claims

Non-blind, twice: (1) the author has seen the LOWDIM-04A and 04B results (secants at the LOWDIM-03 parent, the accepted 0.3125 mm step) and the phase 1 evaluation; **no prediction of the secants at the new parent is made.**
(2) The gate scope F1 and contract v1.1 were registered **after** the probe near-zero result of commit `576441c` was seen (plan Amendment 2: made after seeing the block); the profile and every threshold are unchanged, only the scope of one gate for probes.
May say: the pre-CFD gate result above; the probes pass every hard gate and all failures of the report-only gate lie on the baseline tie plateau.
May not say: any gradient (secants would be finite-step responses), a subspace step, a flag change (all false, `selected_delta` null, reinitialization none), that #30 is closed (a stage result is neither ACCEPT nor REJECT of a trial; E5),
that the report-only failures are benign for the physics (only that they are plateau-attributed), grid-independent or Stage V downforce.
