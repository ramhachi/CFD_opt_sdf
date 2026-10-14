# OPT-01 v1.1 Stage B preregistration (#30, #25): STATUS READY (frozen by `prerun_freeze.json`), nothing submitted

Date: 2026-10-15. Plan: `docs/opt01_v1_plan_2026_10_15.md` (Amendment 1 E1-E8, Amendment 2 F1-F3; **the plan file is frozen: its hash is pinned by contract v1.1, so this stage amends nothing there; the stage-specific rules live in this note and `inventory.json`**).
Contract: `docs/evidence/opt01_v1_2026_10_15/opt01_v1_1_contract.json` (v1.1, sha256 `0f164a4e...0ba1`, pinned in `scripts/opt01b_states.py`). Evidence class: solver-free registration of Stage B; no CFD was run.
Authority is the interpretation recorded in the contract (user words of 2026-10-13, not a #30-specific grant).

## Question

For `flow_24` and `flow_32`: does a step from the OPT-01 v1 parent (generation 1, `state_sha256` `c9e12f62...`) along the Stage A robust solution satisfy the registered D3 acceptance rule? Seven states per grid (14 runs, two T4 kernels
`ramhachi888/cfd-opt-sdf-opt01b-{a,b}`, per-state timeout 900 s, aggregate cap 6300 s per kernel): the parent, the positive ladder 0.3125 / 0.625 / 0.9375 / 1.25 mm (proposal states) and the reverse diagnostics -0.625 / -1.25 mm (probe states, never accepted or selected).

## Direction and lineage

The direction is derived by the registrar (`build_opt01b_inputs.py`), not chosen: the robust cross-grid coefficient vector of the hash-pinned Stage A analysis (`opt01a_analysis.json`, sha256 `229efc7e...1d43`, verdict `LOCAL_FEASIBLE_CONE_FOUND`) through the production
`coefficient_direction` (max-norm 1; m = 1.479435829 equals the Stage A normalization to 1e-12), frozen as raw bytes (`inputs/robust_opt01a.dir_f4_fortran.raw`, sha256 `32bb85a0...4478`). Coefficients per unit step on (D0, D1, D2, P1): (+0.5707, -0.0415, +0.1780, -0.3127).
Lineage recorded in the inventory and the analysis: parent state hash, direction hash, contract v1.1 hash, Stage A analysis hash; a selected step becomes the next parent with generation + 1 (phi hashes unchanged, new `state_sha256` per step recorded as `if_selected_lineage`); rollback = keep the parent.

## Pre-CFD gates (computed once in the inventory on the exact bytes; none in the kernel)

Contract v1.1 gate scope (F1): the four positive steps and the parent are **proposal states**: the full GEOM-02 profile v2 bundle (13 gates incl. the crossing-slope `near_zero_gradient_band`, transition from the new parent, `allowed_events = ()`), P22-v2 `N_phi <= 8272` with a positive count-equal
margin, and the retained LOWDIM gates (smoothed volume band +-10% vs the v17 baseline, clearance >= 0.15 m). The reverse diagnostics are **probes**: crossing-slope report-only, the other twelve hard. A positive step failing a gate would **not** be dropped or shrunk: it is recorded gate-REJECTED and still runs in CFD for the record
(the analyzer evaluates it with a False geometry verdict, so it can never be accepted or selected; the verdict treats it as not eligible); a failing parent or probe would block the stage (`BLOCKED_PRE_CFD`, no freeze).

**Result: READY. The parent and all four positive steps pass 13/13 plus P22-v2 and the retained gates (no step is gate-rejected); both reverse diagnostics pass every hard gate.** `N_phi = 8272` in every state.

| state | geom02 v2 | crossing-slope failing nodes | count-equal margin (m) | smoothed volume vs v17 | vs parent |
|---|---|---|---|---|---|
| parent | 13/13 | 0 | 2.199e-3 | -1.58% | 0 |
| +0.3125 mm | 13/13 | 0 | 1.887e-3 | -2.06% | -0.49% |
| +0.625 mm | 13/13 | 0 | 1.574e-3 | -2.54% | -0.98% |
| +0.9375 mm | 13/13 | 0 | 1.262e-3 | -3.03% | -1.47% |
| +1.25 mm | 13/13 | 0 | 0.949e-3 | -3.50% | -1.96% |
| -0.625 mm (probe) | 12/13 (report-only) | 167 (167 on baseline plateau, 0 off) | 1.574e-3 | -0.60% | +0.99% |
| -1.25 mm (probe) | 12/13 (report-only) | 392 (392 on baseline plateau, 0 off) | 0.949e-3 | +0.39% | +2.00% |

Plateau attribution (baseline v17 genesis `|phi| < 1e-6`, 5,370 nodes): every crossing-slope failing node of the reverse diagnostics lies in that node set. This is a **node-set coincidence, reported for every crossing-slope failure, not a mechanism**.

## Rules (unchanged from LOWDIM-04B, imported not re-implemented)

Parent byte-identity: the fresh parent CSV of each grid must equal the retained OPT-01 Stage A `opt01a__parent` force CSV of that grid before any other state runs, else `OPT01_V1_INCOMPLETE`. Accept = strictly more than 3e-5 N downforce gain and a computed drag change <= 0 on **both** grids (`evaluate_candidate`, unchanged) plus the gates above;
selection = largest minimum-over-grids gain, exact ties to the smaller step; reverse diagnostics never eligible. Verdicts: `OPT01_V1_ACCEPT` / `OPT01_V1_REJECT` (no positive step both gate-eligible and accepted, integrity complete) / `OPT01_V1_INCOMPLETE` (any integrity failure; no analysis is written).
ACCEPT or REJECT closes #30 (plan E5); INCOMPLETE does not. Estimated runtime: flow_24 about 7 x 3 min, flow_32 about 7 x 7 min of solver time (Stage A: 182 s and 405 s per state) plus the Julia/CUDA setup; hard caps 6300 s per kernel, kernel timeout 10800 s; both kernels in parallel.

## Disclosure and claims

Non-blind: the author has seen the OPT-01 Stage A secants and their linear predictions at 1.25 mm (flow_24 downforce +1.20e-4 N, drag -2.97e-4 N; flow_32 downforce +6.00e-4 N, drag -1.65e-5 N), the LOWDIM-04A/04B results and the pre-CFD gate table above.
**No prediction of Stage B outcomes is registered**; the linear predictions are reported by the analyzer for hindcast only (also a diagonal-curvature estimate, descriptive).
Exit-rule amendment: plan Amendment 1 E3 (one further cycle to test the complete contract prospectively, not for gain). R2 caveat for the Stage A secants that define this direction: every basis direction had at least one probe with report-only crossing-slope failures (all on the baseline plateau), so the secants may include
sub-cell zero-set jumps; `LOCAL_FEASIBLE_CONE_FOUND` is not a smooth-response measurement.
May say: the pre-CFD gate result above; after the run, the registered verdict, with accepted = a **record-level status of this trial** (a subspace step along a fixed finite-difference direction over the frozen 4-direction basis). May not say: a gradient (no gradient is claimed; the secants are finite-step responses), a flag change (all qualification flags false, `selected_delta` null, reinitialization none),
physical or Stage V downforce, grid convergence, optimizer convergence, multi-step behaviour. The selected gain is biased upward (the maximum of a few noisy steps); the flow_24 floor of 3e-5 N is about 1 sigma and the flow_32 drag headroom is within that floor, so "computed" drag sign is not noise-resolved.
