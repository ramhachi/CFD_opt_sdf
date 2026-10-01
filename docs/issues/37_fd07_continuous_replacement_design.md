# FD-07 continuous sign-consistency replacement candidates

Status: **pre-registered diagnostic design; no candidate result is included in
this file**. Evidence scope is one WaterLily 1.8.0 / v17 / `flow_24` CPU
fixture plus solver-free analytic geometry tests. This is not a production
change, an FD qualification, or a claim about physical accuracy.

## Pinned semantics

The source is the locally installed WaterLily 1.8.0 `src/Body.jl`, SHA-256
`aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee` (the
same bytes as upstream tag [`v1.8.0`](https://github.com/WaterLily-jl/WaterLily.jl/blob/v1.8.0/src/Body.jl)).
Its `AbstractBody` contract describes `d` as signed distance and `measure!`
fills center SDF `σ`, zeroth moment `μ₀`, first moment `μ₁` multiplied by the
face normal, and body velocity `V`. In the registered convention, negative
distance is solid and positive distance is fluid.

In `measure!`, `d[I]` is the SDF at a cell center and `dᵢ` is the SDF sampled
at that cell's staggered face in axis `i`. Coordinates are in WaterLily solver
units: one flow-grid cell is one distance unit. A face is exactly half a cell
from the center along its staggered axis. For a signed-distance field obeying
the unit Lipschitz bound, center/face signs can disagree only when the face is
within that half-cell distance of the zero set. WaterLily therefore preserves
the measured face sign when `|dᵢ| ≤ 0.5`, where a true crossing is possible,
and sets the sign to the center's when `|dᵢ| > 0.5`, where that sign pairing is
geometrically inconsistent for an exact SDF.

Upstream history provides the rationale explicitly: commit
[`3273a26`](https://github.com/WaterLily-jl/WaterLily.jl/commit/3273a26160708010320a974a678da442ea4650c0)
states that the SDF sign is global, lets `measure_sdf!` specialize the center
field, fills the face data near the BDIM transition, preserves possible
sign-flips inside the half-cell distance, and imposes center consistency
outside it. The current upstream body tests exercise the moment formulas,
body measurements, and body set operations, but do not have a dedicated test
for this sign-consistency branch or its thin-body invariants. The history and
tests do not establish that this correction is universally accurate.

The corrected face distance feeds WaterLily's convolution moments
`μ₀(dᵢ,ϵ)` and `μ₁(dᵢ,ϵ)nᵢ`; the kernel width is `ϵ=1` solver cell in this
fixture. Since the correction changes only sign and retains `|dᵢ|`,
WaterLily's `μ₁` is unchanged: its pinned kernel expression is even in `dᵢ`
(`d sin(πd)` and the remaining terms are even). `μ₀` is not even, so its
solid/fluid fraction changes with the corrected sign. The sampled face normal,
body velocity, center SDF `σ`, and geometry are not directly changed.

The moving ground is included as the existing exact planar half-space with
registered `+x` wall velocity. It is still combined with the candidate body
by the same set-union and passed through the same measurement path. Each
candidate will also be measured against the ground alone; any change there is
a rejection. No candidate changes the normal floor, coordinate maps,
canonical `phi`, or source STL.

For a truly thin body, signs can legitimately change between a center and its
face within the half-cell band. Candidate C leaves every `|dᵢ|≤0.5` sample
unchanged. A and B use a symmetric threshold blend and can modify a narrow
legal band below `0.5`; that is an explicit semantic risk, recorded per-face
and tested by the aligned-plane and one-cell/two-cell plate fixtures. A or B
must be rejected if they change those legal crossings. These fixtures test the
discrete geometry contract only; they do not establish conservation or flow
accuracy.

## Fixed parameters and candidate equations

All distances below are in flow-cell units, `ϵ=1`, and `δ` is fixed before the
new coefficient or force matrices are run. The prior registered diagnostic's
largest Float32-stored nodal perturbation at `1e-7 m` was
`4.76837158203125e-7 m`. With `flow_24` spacing `Δx=1/30 m`, this is
`δφ = 1.430511474609375e-5` solver units. Set
`δ = 8 δφ = 1.1444091796875e-4` solver units
(`3.814697265625e-6 m`). The factor eight keeps that largest recorded
perturbation within one eighth of a transition width, while the physical
width remains about `2.29e-4` of the geometric half-cell threshold. It is a
registered diagnostic scale, not a fitted physical length.

Define `S(q)=0` for `q≤0`, `S(q)=3q²−2q³` for `0<q<1`, and `S(q)=1` for
`q≥1`. Define a compact C1 center-sign surrogate

`sδ(c) = 2 S((c+δ)/(2δ)) − 1`.

It equals the exact center sign outside `|c|<δ`, crosses zero continuously at
`c=0`, and has zero slope at the two transition endpoints.

The controls are the pinned `UPSTREAM` expression and `NO_SIGN_CORRECTION`
(raw `dᵢ`). Neither is a replacement candidate. The three candidates are:

1. **A — smooth the half-cell threshold only.** Let
`wA = S((|dᵢ|−(0.5−δ))/(2δ))` and
   `dA = (1−wA)dᵢ + wA copysign(|dᵢ|, d[I])`.
   This follows the suggested symmetric threshold blend. The center sign is
   still hard, so A is expected to retain a center-sign discontinuity; its
   purpose is to measure whether threshold-only smoothing can suffice.
2. **B — continuous center-sign weighting.** Use the same `wA` and set
   `dB = (1−wA)dᵢ + wA |dᵢ| sδ(d[I])`.
   This makes the center-sign transition C1 but changes both moments through
   the resulting face distance, providing a direct-distance comparator.
3. **C — one-sided moment-level regularization.** Let
   `wC = S((|dᵢ|−0.5)/δ)`,
   `rC = S(−sign(dᵢ)d[I]/δ)`, and `αC=wC rC`. For `|dᵢ|>0.5`,
   `rC` smoothly activates only when center and face signs disagree; it is
   zero on the sign-consistent side and at a zero center. Set
   `mC = μ₀(dᵢ,1) + αC[μ₀(copysign(|dᵢ|,d[I]),1)−μ₀(dᵢ,1)]`.
   Store `μ₀=mC` and keep `μ₁=μ₁(dᵢ,1)nᵢ` exactly. This is a convex blend
   between raw and upstream corrected moments, preserves raw samples for
   `|dᵢ|≤0.5`, and recovers the upstream `μ₀` when `|dᵢ|≥0.5+δ` and
   `|d[I]|≥δ` on the disagreement side. It leaves normals, velocities, `σ`,
   and `μ₁` intact. Since the activation is flat at zero, the `sign(dᵢ)`
   factor is multiplied by zero in a neighborhood of `dᵢ=0` and introduces no
   face-sign jump in the interface band.

Candidate A is an intentional threshold-only ablation and remains discontinuous
when the center sign changes. B and C are designed to be C1 in the registered
sign/threshold region. WaterLily's existing `μ₀` truncation near the deep-solid
support boundary is retained unchanged, so no claim of global C1 behavior is
made across that separate kernel guard. No candidate adds a reinitialization,
smoothing, or normal modification.

## Frozen comparison and stop criteria

Stage 1 uses only the registered baseline `phi` and paired seed 1/11/2026
perturbations at `±1e-8 m` and `±1e-7 m`. It runs `measure!` and records
coefficient fields and identities without calling `sim_step!`. Compare
`UPSTREAM`, `NO_SIGN_CORRECTION`, A, B, and C for sign-disagreement counts,
`μ₀/μ₁` changes and `1e-3` counts, odd/even coefficient responses, the
10×-amplitude response ratio, non-finite values, body/ground localization,
active coefficient support, and array/input hashes.

Stage 2 uses analytic plane, sphere, one-cell plate, two-cell plate, exact
sample-plane, offset sample-plane, and deliberately sign-disagreeing center /
face fixtures. It compares sign counts, legal half-cell crossings, moments
under center-sign and face-threshold translations, reflection symmetry, and
plate occupancy. A candidate that changes a legal `|dᵢ|≤0.5` crossing,
erases a one-cell plate, changes ground-only initialization, produces
non-finite values, or retains an O(1) perturbation jump is rejected before any
flow step. Changes outside its registered transition band are also recorded
against the exact analytic SDF baseline.

Stage 3 runs only a survivor (at most two) on the same registered 26-run
short CPU fixture: baseline plus three paired seeds at both amplitudes,
original v17/design origin, `flow_24`, Float32, `normal_floor=0.25`, unchanged
pressure settings and moving ground, `tU/L≥3`, exact `[2,3]` window, and
`1/900 N` force conversion. `NO_SIGN_CORRECTION` remains a lower-bound
diagnostic. Compare total, pressure, viscous, odd/even, baseline shifts,
response magnitudes, 10× response ratios, and coefficient jumps. No formal
FD threshold is introduced.

Select a single most promising diagnostic candidate only if the evidence
jointly supports continuity in the tested perturbation band, exact analytic
thin-body behavior, unchanged moving-ground behavior, localized baseline
semantic change, and substantially reduced solved-flow irregularity. If no
candidate satisfies those qualitative requirements, report no selected
candidate. In either case stop before production adoption, formal FD,
W3/W4 requalification, Kaggle, v18, gradient, or optimizer work.
