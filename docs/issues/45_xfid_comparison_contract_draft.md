# XFID-01 comparison contract draft (preparation only)

Status: **draft; not an immutable criteria round, not registered, and not
runnable**. The Kaggle CPU v16 replay is only the environment prerequisite.
The composite Candidate C implementation identity is now frozen by #44 as
`docs/evidence/candidate_c_composite_operator_identity_v1_2026_10.json`
(SHA-256
`516cfb26b9cc11f920918f08224ec2cfa5ed89d1e7372fa8d8dd7d4807bd5efc`). This
freezes software identity only; physical operator qualification remains
pending. The formal comparison also remains blocked on independently supported
resolution floors and shared perturbed-geometry lineage.

This draft records the comparison semantics and missing bindings without
choosing epsilon values, directions, response floors, or shapes. Those choices
must be frozen together in a new immutable registration before any comparison
measurement. Historical environment replay ceilings and FD-06 upstream noise
are not Candidate C response floors.

## Required paired cases and force response

Use the adopted canonical v17 state and frozen composite C software identity.
The physical profile/Reynolds number, canonical baseline and perturbations,
coordinate frame, response axes and sign definitions must match. WaterLily-C
uses the registered `flow_24` grid/domain and v17 physical-time force window
`[80,120] tU/L`, exact endpoint interpolation, and trapezoidal means. OpenFOAM
Stage V uses a body-fitted mesh from the same exported geometry and its
registered steady `simpleFoam` force-history rule: the last 25% of samples,
with at least 20 rows, plus registered stationarity checks. These are
solver-specific averaging/stationarity contracts; they are not an identical
physical-time window or evidence of time-history equivalence.

Each deformed state must be created once from a fixed canonical direction and
epsilon, then bound to the same exported zero-level surface artifact used by
Stage V. WaterLily-C consumes the matching perturbed canonical `GridSDF` through
the frozen composite body; OpenFOAM consumes the same geometry as the exported
STL. Native upstream WaterLily or a different shape extraction path cannot
serve as the comparison arm.

For each solver and each registered perturbation, retain the baseline force
`R0` and the two force responses `R(+eps)` / `R(-eps)`. Every response must be a
physical force in N, with identical coordinate frame, force projection, sign
convention, averaging window, and force components documented and hash-bound.
Do not compare coefficients as the primary XFID response. Preserve the solver's
raw force components and the projected force used for the verdict.

Compute per solver:

```text
delta_R_plus  = R(+eps) - R0       [N]
delta_R_minus = R(-eps) - R0       [N]
S             = (R(+eps) - R(-eps)) / 2   [N]
centered_secant = S / eps          [N / direction-unit]
```

The baseline cancels from `S`; do not add baseline uncertainty to the centered
contrast as though it were an independent measurement. A reported uncertainty
bound for `S` must be supported by the calibration design: use a measured bound
for the paired contrast, or propagate measured `+eps`/`-eps` bounds with their
covariance/dependence documented. Assume independence only if it is separately
checked and registered. The centered-secant bound is the registered `S` bound
divided by `eps`; it does not have the units or floor of a force response.

## Independent resolution and rank rules

Calibrate each solver's resolution independently in N using that solver's
exact same backend, force-extraction, averaging, and stationarity contracts as
its formal cases. WaterLily calibration and formal runs bind `flow_24` and the
registered physical-time window; OpenFOAM calibration and formal runs bind the
registered `simpleFoam` iteration-tail rule. These are within-solver bindings,
not a shared cross-solver time window. Freeze a supported absolute resolution
floor for `delta_R_plus`, `delta_R_minus`, and `S`; the `S` floor may be derived
from the registered paired-noise model above. Candidate
rank contrasts (`R_i-R_j`, N) also need an independently justified floor for
each solver. Calibration runs are not formal XFID cases. The v16 environment
reproduction gate ceilings are comparisons against historical references and
must not be substituted for any of these response floors.

A contrast resolves only when its absolute value is strictly greater than
that solver's corresponding floor. Equality to a floor is UNRESOLVED. Compare
the sign of each resolved `delta_R_plus`, `delta_R_minus`, and `S` separately.
For each required candidate pair, both solvers must resolve the rank contrast
before the pair's order can vote. An unresolved response or pair cannot count
as agreement.

The registered aggregate uses three values:

- **AGREE**: every required representative direction and candidate-pair order
  resolves in both solvers and the signs and orderings agree.
- **DISAGREE**: at least one required representative response contrast or
  candidate-pair order is resolved in both solvers and disagrees. An unresolved
  sibling contrast does not erase a resolved disagreement. This is the only
  outcome that stops Track C computation.
- **UNRESOLVED**: neither of the above applies, including any required
  comparison whose response floor is not cleared. This leaves the branch
  undecided and never counts as a pass.

Unresolved comparisons never count as agreement or disagreement. A resolved
disagreement is retained even when another required comparison is unresolved;
absent a resolved disagreement, any unresolved required comparison makes the
aggregate UNRESOLVED.

## Fields required before immutable registration

The registrar must bind all of the following before the first XFID measurement:

1. Composite Candidate C implementation/body type, moment-blend identity,
   `normal_floor=0.25`, parent commit, source hash, and qualification status
   from #44's frozen identity record (SHA-256
   `516cfb26b9cc11f920918f08224ec2cfa5ed89d1e7372fa8d8dd7d4807bd5efc`). This
   identity freeze does not qualify the operator physically.
2. Canonical v17 state, direction vectors, epsilon values, perturbed `phi`
   hashes, geometry exporter/version/settings, and exact shared baseline/plus/
   minus STL hashes and lineage.
3. Exact OpenCFD v2512 package family/versions/hashes, OS, `foamVersion`, Stage V
   mesh and solver inputs, and exact independent verifier identity. The passed
   v16 environment replay only satisfies the environment prerequisite; each
   formal case still records its runtime identity.
4. WaterLily-C backend/runtime identity, `flow_24` domain/grid, physical-time
   window, endpoint averaging and stationarity gate; Stage V body-fitted grid,
   iteration-tail averaging and stationarity gate; their common physical
   profile/Reynolds number and force projection/sign mapping.
5. Disjoint calibration and formal comparison case IDs, calibration repetitions
   and raw histories, per-solver floors for the three force contrasts and
   candidate-pair ranking contrasts, the supported uncertainty propagation
   model, and the exact resolution inclusivity rule.
6. Representative directions and required candidate pairs, objective
   orientation for sorting, tie handling, the three-valued aggregation rule,
   fail-closed behavior, output schema, and source-bound verifier hashes.

The composite source identity is frozen, but #44 physical qualification and
independent resolution calibration remain pending. Until all listed fields are
backed by evidence and immutably registered, there is no formal criteria file
and no permitted XFID shape or solver run.
The exact Kaggle CPU `/4` v16 environment gate is PASS, but it establishes no
cross-fidelity response, ranking, operator equivalence, or production
qualification. All qualification flags remain false.

The small arithmetic implementation in `src/cfd_sdf/xfid_response.py` covers
only finite N-based delta/centered-contrast calculations and strict three-value
resolution comparison. It does not implement rank aggregation, choose floors,
or authorize a formal verdict. Its preparation-only validation and exact
failure-ID record are preserved under
`docs/evidence/xfid_comparison_contract_preparation_2026_10_02/`.
