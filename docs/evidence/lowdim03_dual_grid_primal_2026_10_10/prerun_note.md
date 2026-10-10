# LOWDIM-03: 二解像度 actual-primal direction / step 検証

Date: 2026-10-10. Evidence class: fixed-basis bounded two-grid capability.
User approved the full plan, including 14 runs, strict computed drag nonincrease,
new immutable registration, one submission per kernel and result recording.
This is not a trust-region/filter optimizer, gradient qualification, grid
convergence, physical downforce/drag guarantee, or OPT-01 (#30).

## Inputs and known information

Start from integration `29fd60dd7b985e79b907700ab5600376b10ce230`. The sole baseline
is the canonical v17 state used by GRID-01, not the LOWDIM-01 accepted state.
Read the saved GRID-01 `grid01_analysis.json` with SHA-256
`ec00ed9afe4f44926dd40ff1e87f303dd9baf89195b19cb550103606beedb69c`;
do not rerun GRID-01 analysis or solve another proposal problem.
The basis order is D0_interface_offset, D1_filtered_seed11,
D2_filtered_seed2026, P1_upstream_lobe. Use the full-precision robust coefficients
in that JSON and the existing coefficient_direction normalization. The spatial
normalizer is `m=1.6562277258951545`; the Float32 Fortran-order direction SHA-256
is `c0f69676929c3eb17b1b623c599bfd97ea286d09810c63848e0d7499437e0bf5`.
The step in mm is max-norm SDF update amplitude, not calibrated interface motion.
Record the realized Float32 maximum change and all state/NPZ/phi identities.
STEP-01, LOWDIM-01, LOWDIM-02A and GRID-01 outcomes are known before this trial.
The six-state geometry preflight was observed before freezing. This is not blind
validation or a comparison establishing the robust proposal's superiority.

## Frozen 14-run design

Seven unique geometries are generated once: baseline, +0.625/+1.25/+2.5 mm,
then -0.625/-1.25/-2.5 mm. The same phi bytes are used on both grids.
Kernel a runs flow_24; kernel b runs flow_32. Each executes its fresh baseline
first and must match the grid-specific historical force CSV byte-for-byte before
running any perturbation. Historical baselines are identity references only.
Keep existing Julia primal jobs/operator, Candidate C, Re80, Float32 T4,
canonical design h=0.025 m and the [80,120] tU/L trapezoidal force window.
The flow grid's force scale is grid-specific; do not pass flow_24 scale to flow_32.

Each kernel selects physical GPU index0, observes a singleton CUDA UUID under
CUDA_DEVICE_ORDER=PCI_BUS_ID / CUDA_VISIBLE_DEVICES=0, and uses Julia threads1.
All visible nvidia-smi devices must be Tesla T4; extra visible T4 devices are
recorded but unused. The JSON3-free amended GRID-01 CUDA probe is retained.
Budget per kernel: instantiate2400s, GPUprobe300s, each state900s,
aggregate solver6300s, reserve300s, Kaggle timeout10800s. No new dataset is needed.
Provider identities are checked using complete authenticated owned listings and
positive existing-resource access controls, including title/slug collisions.

## Geometry and actual response decision

Before submission all six perturbations must pass the existing LOWDIM five gates:
clearance >=0.15m; exact masks/outside-support preservation; face-connected solid
cell components equal baseline1; absolute relative smoothed-volume change <=10%;
narrow-band median ||grad phi|-1| <=0.10. If any of the six fails before submission the trial is not frozen; no candidate is dropped and the
direction/ladder is not changed. Sharp volume, Eikonal p95/max and node6 components remain
recorded-only. These five gates do not close GEOM-01's full geometry contract.
Positive states can have two node6 components; the prior read-only node26 check
showed one component and no registered #31 topology event. No threshold changes.

Only positive candidates may be selected. At a common step s require on each grid:
actual host-recomputed Δdownforce >3e-5N and Δdrag <=0N, plus all five geometry gates.
Do not inherit LOWDIM-01's +3e-5 drag allowance or LOWDIM-02A's reverse-loss gate.
Choose maximum min(ΔL24,ΔL32); exact score ties choose the smaller step.
Reverse states are paired diagnostics and never selected. An intact trial with no
feasible common step is LOWDIM03_NO_ACCEPT, not an integrity failure or proof of
basis insufficiency. Accepted trial is LOWDIM03_ACCEPT; invalid trial is
LOWDIM03_INCOMPLETE, with analysis --write forbidden.

Record signed drag margins and |Δdrag|<=3e-5N as a small-margin diagnostic. The
nominal floor is not a measured statistical noise bound, especially on flow_32.
A sign pass establishes a computed sign only in this frozen measurement. GRID-01 predicts the flow_32 drag change at 1.25 mm as about -8.9e-6 N (raw) and about 0 N (L1 upper bound), both inside the nominal 3e-5 N floor, so the flow_32 drag sign is not expected to be noise-resolved before the run; a NO_ACCEPT caused only by a flow_32 drag change within +/-3e-5 N is not evidence about physical drag, and an ACCEPT is not evidence of physical drag non-increase.
The L1 sensitivity model likewise is not an empirical uncertainty guarantee.

## Model diagnostics, integrity and stop

For each grid/step, with s in metres, raw predictions are
pL=(s/m)gL^T c and pD=(s/m)gD^T c. Record rho=actualΔL/pL and
eD=actualΔD-pD; robust lower lift/upper drag predictions are separate references.
Nonpositive/nonfinite pL has null rho plus explicit diagnostic reason.
Rho is not an acceptance or radius-update rule. Report all three paired odd/even
responses O=(Rplus-Rminus)/2, E=(Rplus+Rminus-2Rbase)/2 for lift and drag.
Do not uniquely attribute mismatch to curvature, nonadditivity or numerical effects.

A solver divergence, non-finite field/force or timeout in ANY of the 14 runs (including a reverse diagnostic or the 2.5 mm candidate) makes the trial LOWDIM03_INCOMPLETE (no analysis --write, no repair, no resubmission); it is accepted as registered that this conflates a possible physical divergence with an infrastructure failure.

Bind reviewed source, registration, input, helper and test closure by hashes.
Both kernels require COMPLETE, DONE without ERROR, exact seven-state order,
all required files, safe-path manifest SHA verification, independent GPU probe,
state/runtime/source/job summary agreement, finite exact-window force identities,
host force recomputation and fresh-baseline byte/force agreement.
Download outputs, run analyzer --check before exactly one --write. Integrity-valid
NO_ACCEPT is recorded; ERROR/CANCEL/integrity failure is preserved in
failed_attemptN/ with no analysis --write, repair or resubmission.
After result recording commit/push intended files and --no-ff merge integration.
#26 stays open. Keep all qualification flags false and shape_update_allowed=false,
delta unset, FD-08/GRAD-03 verdicts unchanged. Stop before secant rebuild, a second
iteration, basis expansion, reinitialization, #49 Stage B and #30 supersession.
The uncommitted GEOM-01 worktree remains separate.
