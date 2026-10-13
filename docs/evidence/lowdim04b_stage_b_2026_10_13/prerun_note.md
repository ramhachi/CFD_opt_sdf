# LOWDIM-04 Stage B preregistration (#51): an actual-primal ladder along the Stage A solution

Date: 2026-10-13 Asia/Tokyo. Issue: [#51](https://github.com/ramhachi/CFD_opt_sdf/issues/51). Plan: `docs/lowdim04_plan_2026_10_13.md` (Cycle 2). Integration parent: `69d8851…` (the Stage A record).
Evidence class: bounded two-grid actual-primal capability at the accepted LOWDIM-03 parent. This stage stops after recording and ends the LOWDIM-04 track (exit rule below).

## Authority, disclosure, reviewers

The user's words (session, 2026-10-13), recorded on #51: 「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」 This registration reads them as authorizing Stage B under this preregistration and Kaggle submissions of the
frozen kernels; the words themselves say only that human decisions are permitted and no longer needed. It waives no freeze, hash, review or fail-closed rule. All reviews are Claude subagents, not human reviewers.
Stage A's verdict (LOCAL_FEASIBLE_CONE_FOUND) is **not** the authority for this stage: it is a statement about a linear model and its own report says it is not a go-ahead.

**Non-blind, with a known marginal outcome.** The author has seen the Stage A result, its descriptive and unregistered diagonal-curvature estimate, the LOWDIM-03 ladder and every earlier result. That estimate puts the flow_24 actual downforce
gain of the Stage A solution at about +3e-5 N (0.25 of the step), +5e-5 N (0.5), +4e-5 N (0.75) and +2e-5 N (full step), against the 3e-5 N floor: whether any step passes on flow_24 is a toss-up, and the sign and size of those figures are not established (differences of terms of about 1e-4 N).
flow_32 downforce is estimated at about +1.2e-4, +2.4e-4, +3.5e-4 and +4.5e-4 N. The flow_32 **drag** estimates (about -6e-6, -2e-5, -4e-5, -6e-5 N, linear parts -4e-6 to -1.6e-5 N) are at or below the 3e-5 N jitter floor at the small steps, so the flow_32 drag sign is close
to a coin flip there and a NO_ACCEPT can come from drag jitter rather than from downforce. Both ACCEPT and NO_ACCEPT are informative; neither is read as more than the bounded statement below. Reviewers receive frozen sources and paths, never excerpts of the new run.

## Question and scope

On each of `flow_24` and `flow_32`: the accepted LOWDIM-03 parent, then the positive steps `s = 0.3125, 0.625, 0.9375, 1.25 mm` (0.25, 0.5, 0.75, 1.0 of the Stage A normalized step; `max |d phi| = s`) along the Stage A **L1-robust cross-grid solution**, and the reverse
diagnostics at `-0.625` and `-1.25 mm`: seven states per grid, 14 runs, two Kaggle T4 kernels. One fixed direction, no re-solve, no repeats (the solver reruns byte-identically), no reinitialization, no new basis directions, no curvature model.
The ladder extends the plan's sketch (four positive steps and two reverse diagnostics instead of three and one). The direction is derived by the registrar from the hash-pinned Stage A analysis (sha256 `414d0867…119d`, robust coefficient vector, unit l2; the production `coefficient_direction`, max-norm 1, whose `m` equals Stage A's normalization to 1e-12) and frozen as raw bytes.

## Frozen identity and parent gate

As in Stage A: `inventory.json` (derived by `scripts/build_lowdim04b_inputs.py`, `--check` re-derives) fixes four named hashes per state (`phi_fortran_order_sha256` for the runner and device round trip, `phi_c_order_sha256`, `state_sha256`, `npz_sha256`), the realized float32
`maximum_pointwise_change_m`, and the parent byte-identity reference. The fresh parent run on each grid must be byte-identical to the retained LOWDIM-03 `prop__s1.25mm` force CSV (the Stage A parent runs already matched it on both grids) before any other state runs; a mismatch is
`LOWDIM04B_INCOMPLETE` with no analysis, repair or resubmission.

## Pre-CFD checks (done in the inventory, on the exact bytes)

The five existing LOWDIM geometry gates for every state (base: the canonical v17 baseline) and the hard count `N_phi = 8272` (production evaluator), with the max-norm invariance margin (parent minimum `|centre|` 2.407 mm, minimum fluid centre 3.228 mm; the largest step
moves 1.25 mm; count-equal margin 1.156 mm after the Float32 rounding allowance). The ladder lowers the continuum zero-set volume by 0.5% to 2.0% of the parent (reverse diagnostics raise it by 1.2% and 2.5%). **Frozen sentence:** volume feasibility here means the lattice count
N <= 8272, exactly satisfied by construction; it constrains no physical or sub-voxel volume.

## Rule, selection, terminals

- **Accept** (LOWDIM-03's rule, `evaluate_candidate` reused unchanged): strictly more than `3e-5 N` downforce gain **and** a computed drag change `<= 0` on **both** grids, plus the five geometry gates. The drag sign is computed, not noise-resolved
  (flow_32 drag changes within `3e-5 N` are flagged "small", not resolved); the floor is nominal, about 1 sigma of the retained flow_32 response jitter, not a 3 sigma rule.
- **Selection:** among accepted positive steps, the largest minimum (over the two grids) actual downforce gain; exact ties use the smaller step. Reverse diagnostics are never eligible.
- **Terminals:** `LOWDIM04B_ACCEPT`, `LOWDIM04B_NO_ACCEPT`, `LOWDIM04B_INCOMPLETE` (any integrity failure, one grid incomplete, a non-finite run, a failed parent gate or a hash mismatch; nothing partial is written). **No analysis-amendment path is registered:** an analyzer,
  contract or test defect found after the run makes the stage INCOMPLETE and any correction is a new preregistered stage.
- **Reported for every outcome (descriptive, never used in the verdict):** the actual changes of all states on both grids; the odd and even parts of the +-0.625 and +-1.25 mm pairs; a hindcast of every positive step against Stage A's linear prediction and against its diagonal-curvature estimate
  (formula: linear term + sum over the four basis directions of `(w_i f / 1.25 mm)^2 * even_i`, `w` the Stage A robust basis coefficients in metres, `f = s / 1.25 mm`, `even_i` the Stage A even parts; not a registered model); volumes and counts per state.

## Claims

May say, for this parent, this fixed direction, two grids, Re 80 and this ladder only: the measured actual changes; which steps met the rule; the selected step if any; the hindcast comparison. An ACCEPT is a bounded actual-primal capability result: it is not physical
downforce or drag, not grid convergence, not a gradient, optimizer or second-iteration qualification, not #26 or #30, and not a go-ahead for further steps; a NO_ACCEPT is likewise bounded. The flow_32 drag sign is not noise-resolved. The rule has no multiplicity control (four correlated positive steps and a max-min selection on a floor of about 1 sigma): an ACCEPT means only that the computed rule passed, and the selected gain is biased upward
and is not an estimate of the true gain. All qualification flags false,
`selected_delta=null`, `shape_update_allowed=false`, reinitialization none.

## Exit rule

After this stage the outcome is recorded and #51 is closed. No third LOWDIM cycle starts on gain headroom alone: the attainable gain is below the Stage V resolution, and the leverage is in basis size and the open gates (#26, #28, #25/#29).

## Runtime and process

Kernels `ramhachi888/cfd-opt-sdf-lowdim04b-a` (flow_24, about 176 s per state) and `-b` (flow_32, about 410 to 440 s per state); per-state timeout 900 s, aggregate solver cap 6300 s (seven states, as LOWDIM-03), kernel timeout 10800 s, one T4, one Julia thread. New code only under `scripts/` and `tests/`;
the freeze binds every imported project file by hash (found by importing) and the source commit by its git tree id, the rendered workers by re-rendering, the fixed budgets, the pins, the exact flag set, the identity-free proof and the parent commit; the source commit is pushed (the runner fetches it).
Evidence logs are trackable through the `.gitignore` negation, and `scripts/check_sha256sums_tracked.py` is run on every evidence `SHA256SUMS`. Pre-freeze (no GPU): tests of the contract and the unchanged accept rule, the inventory (re-derivation, identity table, proposal binding), the runner's state generation and plan checks, `check_kernel` replayed over the real retained
LOWDIM-03 kernel files with regenerated identity fields and negatives (one real force CSV is copied into all seven states, so the replay does not exercise distinct per-state forces; synthetic ladders cover the verdict), and the strict registration validation with mutation tests. Then an independent adversarial review of the final bytes, an authenticated Kaggle identity check, the freeze, submission, `--check` then exactly one `--write`, an independent post-run review,
validation against the 48 known failures, record, stop.

## Known limitations

Reviewers are subagents. The registration is non-blind. The nominal floors are not a flow_32 noise measurement. The lemma and radii cover the Float32 phi artifact only. The even parts are negative everywhere and their cause is untested (physical curvature, a baseline near an extremum, or loss of the signed-distance property); it matters before any multi-step loop.
`build_lowdim04b_inputs.py --check` is machine-bound for `npz_sha256` and float volumes; the frozen `inventory.json` is the authority.
