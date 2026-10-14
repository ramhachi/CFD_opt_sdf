# OPT-01 v1 Stage A preregistration draft (#30, #25): STATUS BLOCKED_PRE_CFD, not frozen, nothing submitted

Date: 2026-10-15. Plan: `docs/opt01_v1_plan_2026_10_15.md` (Amendment 1, E1-E8). Contract: `docs/evidence/opt01_v1_2026_10_15/opt01_v1_contract.json` (sha256 `f76a09c7...43e2`, pinned in `scripts/opt01a_states.py`).
Evidence class: solver-free registration of Stage A; no CFD was run. Authority is the interpretation recorded in the contract (user words of 2026-10-13, not a #30-specific grant).

## Question

For `flow_24` and `flow_32`: the new OPT-01 v1 parent plus the eight centered perturbations D0/D1/D2/P1 x -/+ 1.25 mm of that parent (nine states per grid, 18 runs, two T4 kernels `ramhachi888/cfd-opt-sdf-opt01a-{a,b}`, LOWDIM-04A
per-state timeout 900 s and aggregate cap 8100 s). Centered secants, the pinned LOWDIM cone solver, epsilon 0.012 N/m.

## New parent identity

The LOWDIM-04B selected state (LOWDIM-03 parent + 0.3125 mm x the robust Stage A direction, rebuilt with `construct_state` and hash-checked against the 04B inventory) re-created with generation 0 -> 1 (E4). Phi hashes are unchanged
(Fortran `2f23be78...`, C `ff4d3058...`); `state_sha256` changes `64e4efb1...` -> `c9e12f62...`. Children keep the new parent's generation (construct_state semantics). Mapping and NPZ: `inventory.json` `parent.lineage`.

## Pre-CFD gates (E4 order, computed once in the inventory on the exact bytes; none in the kernel)

Every state: GEOM-02 profile v2 (13 gates, transition from the new parent, `allowed_events=()`), P22-v2 `N_phi <= 8272` with a positive count-equal margin (parent 2.199e-3 m; every perturbation 0.949e-3 m), retained smoothed-volume band and clearance.
**Result: the parent passes 13/13 (also from the LOWDIM-03 parent, the E4 stop rule) and every state passes all gates except `near_zero_gradient_band`, which fails on six of the eight secant states**
(crossing-slope nodes below 0.5 / interior sign-change nodes): D0- 284/9299, D1- 40/8134, D1+ 153/8326, D2- 3/8045, D2+ 206/8416, P1+ 212/8408; D0+, P1- pass (0 failing). Failing nodes are near-tie `|phi|` below about 1.1e-3 m. The ±1.25 mm perturbation
creates near-tie sign-change nodes that the parent does not have. This is a **registered blocker before CFD** (E4: a gate failure is recorded, Stage A secant states are required, none is dropped or shrunk). No freeze, rendering or identity check follows.

## Rules that would have applied (unchanged from LOWDIM-04A, imported not re-implemented)

Parent byte-identity: the fresh parent CSV on each grid must equal the retained LOWDIM-04B `prop__s0.3125mm` CSV before any other state runs, else INCOMPLETE. Secants `[R(+s)-R(-s)]/(2s)`, s = 1.25 mm; resolved if |contrast| > 3e-5 N; `LOCAL_FEASIBLE_CONE_FOUND`
only if both the main and the L1-robust cross-grid problems pass (t* above 1e-8 and predicted 1.25 mm downforce at least 3e-5 N on both grids), else NOT_FOUND; any integrity failure gives `OPT01A_INCOMPLETE` with no analysis.
Exit-rule amendment: plan Amendment 1 E3 (one further cycle to test the complete contract prospectively, not for gain).

## Disclosure and claims

Non-blind: the author has seen the LOWDIM-04A and 04B results (secants at the LOWDIM-03 parent, the accepted 0.3125 mm step) and the phase 1 evaluation; **no prediction of the secants at the new parent is made.** May say: the pre-CFD gate result above.
May not say: any gradient (secants would be finite-step responses), a subspace step, a flag change (all false, `selected_delta` null, reinitialization none), that #30 is closed (E5: a blocked stage is neither ACCEPT nor REJECT).
Unblocking needs a new registered decision (for example a gate scope or basis/step change); it is not made here.
