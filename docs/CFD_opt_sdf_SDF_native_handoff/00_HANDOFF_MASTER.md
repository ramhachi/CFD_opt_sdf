# CFD_opt_sdf — SDF-native adjoint/topology-changing optimization handoff

## 1. Mission

Re-architect the existing `CFD_opt_sdf` repository so that the **canonical geometry design state is an SDF field**

\[
\phi(\mathbf{x})
\]

rather than OpenFOAM B-spline control points or a density field after Stage T.

The target research system is:

\[
\boxed{
\phi
\rightarrow
\text{immersed/Cartesian primal CFD}
\rightarrow
\text{reverse/discrete adjoint}
\rightarrow
\frac{\partial J}{\partial \phi}
\rightarrow
\text{SDF evolution + topology birth}
\rightarrow
\phi_{\rm new}
}
\]

followed by independent body-fitted OpenFOAM verification.

The optimizer must be able to change topology, including **intentional birth/nucleation of new solid components**, not merely deform, merge, or split existing level sets.

Execution targets are:

- Google Colab GPU;
- local RTX 4070 Ti;
- MacBook Air for CPU development/tests/small cases.

Do not assume a fixed Colab GPU type.

---

## 2. Repository starting point

Work from:

```text
branch: feat/p0-openfoam-closed-loop
HEAD: ebdd01f293636b2fc736885a1032d466e6632e9a
message: Register Stage S reduced-basis FD v2 contract and pass S0R/S1R
```

The current K=16 B-spline/reduced-basis Stage S path has already passed S0R/S1R.

**Do not continue to S2.**

Freeze this architecture as a `superseded_reference`, preserving all evidence and code for reproducibility.

Do not delete or rewrite P21/OpenFOAM evidence.

---

## 3. Preserve the good architecture already built

Retain the existing scientific-control philosophy:

- ProblemSpec owns requested physics/semantics.
- Problem compiler owns objective/constraint meaning and signs.
- CFD backends return primitive responses and gradients only.
- Every execution backend has an immutable identity/fingerprint.
- Parent and trial evaluations are distinct.
- Actual nonlinear primal reevaluation is required for acceptance.
- Failed trial means rollback; no linear-model-only acceptance.
- Gradient qualification is fail-closed.
- Manifest/evidence identity is append-only.
- Cross-fidelity claims are explicitly scoped.

The following existing work remains valuable:

- Stage T density/Brinkman topology exploration;
- v16 candidate lineage;
- SDF/extraction/geometry qualification;
- Stage V moving-ground/freestream profile;
- domain-convergence v2-v3 evidence;
- OpenFOAM independent verification;
- cross-fidelity ranking tools;
- gradient-check infrastructure.

---

## 4. New canonical design state

Create:

```text
src/cfd_sdf/design/sdf_state.py
```

with an immutable canonical state approximately:

```python
@dataclass(frozen=True)
class SDFDesignState:
    phi: NDArray
    origin_m: tuple[float, float, float]
    spacing_m: float
    shape: tuple[int, int, int]

    design_mask: NDArray
    fixed_solid_mask: NDArray
    forbidden_mask: NDArray
    root_mask: NDArray

    sign_convention: Literal["negative_inside"]
    narrow_band_width_m: float

    generation: int
    source_sha256: str | None
    state_sha256: str
```

Convention:

```text
phi < 0 : solid
phi = 0 : interface
phi > 0 : fluid
```

The canonical identity hash must include at least:

- `phi`;
- grid/origin/spacing/shape;
- all geometry masks;
- sign convention;
- topology policy;
- reinitialization policy/profile.

STL is no longer a design state. It becomes a visualization/OpenFOAM-handoff artifact.

Retain `DensityDesignState` for Stage T reproducibility; do not mutate history to pretend it was SDF-native.

---

## 5. Desired optimization problem

Define downforce-positive convention:

\[
C_{DF}>0,\qquad C_D>0.
\]

Canonical minimization objective:

\[
\boxed{f(\phi)=-\overline{C}_{DF}}
\]

where force responses may be time-averaged over a preregistered measurement window.

The user's requested lift/downforce-to-drag requirement should **not** be implemented as a direct quotient in the first production contract.

Use:

\[
\boxed{
g_R(\phi)
=
R_{\min}\overline{C}_D-\overline{C}_{DF}
\le 0
}
\]

which is equivalent to

\[
\overline{C}_{DF}/\overline{C}_D\ge R_{\min}
\]

when \(\overline{C}_D>0\), while avoiding division singularities and unstable denominator sensitivities.

Also define a volume constraint:

\[
g_V=
V(\phi)/V_{\max}-1
\le0.
\]

Initial differentiable optimization constraints:

- downforce objective;
- drag-efficiency constraint;
- volume.

Initial hard fail-closed trial gates:

- finite responses;
- `CD > CD_floor`;
- `CDF > CDF_floor`;
- design-domain containment;
- forbidden-region exclusion;
- root-connectivity policy;
- clearance;
- minimum feature;
- SDF/reinitialization validity;
- CFD convergence;
- force stationarity;
- runtime/manifest identity.

Do not force every geometry rule into a differentiable constraint in the first implementation.

---

## 6. Solver architecture

Introduce solver-independent interfaces:

```text
src/cfd_sdf/oracles/base.py
src/cfd_sdf/gradients/base.py
```

Core conceptual interfaces:

```python
class ResponseOracle(Protocol):
    def evaluate(
        self,
        state: SDFDesignState,
        request: ResponseRequest,
    ) -> PrimalEvaluation: ...

class GradientEngine(Protocol):
    def gradient(
        self,
        state: SDFDesignState,
        primal: PrimalEvaluation,
        responses: tuple[str, ...],
    ) -> GradientEvaluation: ...
```

A solver must not own canonical optimization semantics.

Backends produce primitive responses such as:

```text
drag
downforce
volume-related primitive if applicable
```

The Python problem compiler forms:

```text
f
g_i <= 0
df/dphi
dg_i/dphi
```

---

## 7. WaterLily: adopted role

WaterLily is the **first primal PoC** because its architecture aligns strongly with the research:

- Cartesian incompressible CFD;
- BDIM immersed body;
- geometry naturally described by SDF;
- 2D/3D;
- CUDA-capable GPU execution;
- differentiability work already exists.

However:

\[
\boxed{
\text{WaterLily primal candidate}
\neq
\text{qualified production reverse-adjoint backend}
}
\]

### Critical current fact

As of 2026-09-26, WaterLily PR #285
`Reverse AD via Enzyme extension`
is still open.

Exact experimental head observed:

```text
feed49f480b52047b4e9b8bfacdf3e4f8201106b
```

The PR demonstrates CPU reverse mode through full `sim_step!` with a custom implicit reverse rule for the Poisson solve.

It also reports:

- default Poisson tolerance around `1e-4` produced roughly 10% disagreement versus ForwardDiff in its example;
- tightening the Poisson solve to `1e-10` reduced disagreement to approximately `2.4e-5`;
- GPU reverse remains blocked by missing Enzyme/CUDA derivative support around a CUDA host-to-device copy path (`cuMemcpyHtoDAsync_v2`).

Therefore split WaterLily work into:

```text
stable/pinned WaterLily -> production primal experiments and FD
PR #285 exact commit    -> experimental CPU reverse-AD PoC
CUDA reverse            -> explicit separate Go/No-Go research gate
```

Never silently make PR #285 the production primal dependency.

---

## 8. WaterLily SDF bridge

Do not represent an evolving topology as an ever-growing Boolean expression tree of analytic bodies.

Create a grid-backed SDF body:

```text
phi[i,j,k]
    ↓
trilinear interpolation
    ↓
sdf(x)
    ↓
WaterLily body interface
```

The authoritative state remains a dense/grid SDF.

Recommended Julia package:

```text
julia/CFDSDFWaterLily/
├── Project.toml
├── Manifest.toml
└── src/
    ├── CFDSDFWaterLily.jl
    ├── GridSDFBody.jl
    ├── Simulation.jl
    ├── Forces.jl
    ├── ADExperiments.jl
    └── Bridge.jl
```

Use total aerodynamic force, including pressure and viscous contributions, unless a preregistered experiment explicitly studies components separately.

---

## 9. WaterLily is not the high-Re truth solver

Do not turn uniform-grid WaterLily into a claim of inexpensive high-Re FSAE truth.

The WaterLily literature itself shows that uniform Cartesian resolution becomes expensive for boundary layers at increasing Reynolds number.

Therefore use WaterLily for:

- SDF-native topology exploration;
- low/moderate-fidelity optimization;
- GPU throughput;
- gradient/adjoint research.

Retain OpenFOAM Stage V for independent sharp-interface verification.

Future high-Re production verification/adjoint work may use:

- OpenFOAM;
- DAFoam;
- another qualified body-fitted stack.

---

## 10. Reverse-AD memory architecture

Do not implement naive timestep tape storage.

For 3D Float32 CFD, the primal field storage already scales with cell count; reverse-mode history scales with both cell count and time horizon.

Even storing only velocity + pressure histories makes long unsteady reverse-mode quickly exceed commodity GPU memory.

Therefore production reverse architecture must explicitly choose among:

- short finite horizons;
- checkpoint/recompute;
- custom reverse rules;
- discrete-adjoint state reconstruction;
- bounded time windows.

Treat reverse-memory policy as part of the gradient backend contract, not an implementation detail.

Record:

- peak device memory;
- number of saved states;
- recomputation count;
- time horizon;
- Poisson tolerance;
- precision.

---

## 11. Gradient qualification

FD remains the permanent independent gradient oracle.

### Stage G1 — analytic/low-dimensional parameter

Use a circle/ellipse or similarly simple SDF:

\[
\phi(\mathbf{x};\theta)
\]

and compare parameter derivative from ForwardDiff/AD with centered FD.

### Stage G2 — SDF directional derivatives

For a direction \(d\),

\[
D_{\mathrm{FD}}(\epsilon)
=
\frac{
J(\phi+\epsilon d)-J(\phi-\epsilon d)
}{
2\epsilon
}
\]

compare with

\[
D_{\mathrm{grad}}
=
\nabla_\phi J\cdot d.
\]

Preregister directions:

- simple smooth direction;
- low-frequency field direction;
- at least three deterministic random holdouts;
- projected gradient direction.

Use an epsilon ladder scaled to grid spacing, not arbitrary physical numbers reused across grids.

Qualification requirements:

- same derivative sign;
- epsilon plateau;
- response above registered numerical noise;
- finite gradient;
- <=5% relative mismatch for non-near-zero directions;
- absolute-error rule for near-zero directions.

Separate:

```text
parameter_gradient_qualified
sdf_field_gradient_qualified
```

A low-dimensional pass never promotes the full SDF gradient.

---

## 12. GPU reverse decision tree

Order:

```text
WaterLily GPU primal
        ↓
SDF centered-FD qualification
        ↓
WaterLily CPU reverse-AD correctness
        ↓
bounded CUDA reverse spike
        ↓
production gradient decision
```

For the CUDA spike:

- allocate GPU arrays before entering the differentiated region;
- eliminate avoidable host/device transfers inside the differentiated function;
- keep runtime initialization outside Enzyme tracing;
- test the exact current PR failure path;
- preregister a bounded engineering effort.

If CUDA reverse remains blocked, do **not** promote K=16 FD to a production optimizer.

Instead compare:

- custom WaterLily discrete adjoint;
- TCLB;
- OpenLB;
- potentially DAFoam for gradient reference/body-fitted route.

WaterLily may remain the primal/FD oracle even if its reverse backend is rejected.

---

## 13. Topology change

Keep topology evolution and topology birth conceptually separate.

### Existing level-set/SDF evolution

A Hamilton-Jacobi-type evolution

\[
\partial_t\phi+V_n|\nabla\phi|=0
\]

can deform, merge, and split existing interfaces.

It does not by itself provide arbitrary nucleation away from existing interfaces.

### Explicit topology birth

Create:

```text
src/cfd_sdf/design/topology_birth.py
```

with a solver-independent operator concept:

```python
class TopologyBirthOperator(Protocol):
    def propose(
        self,
        state: SDFDesignState,
        primal: PrimalEvaluation,
        gradient: GradientEvaluation | None,
    ) -> list[BirthCandidate]: ...
```

First fixture:

- insert known spherical/ellipsoidal SDF seeds;
- combine using SDF union, e.g. `min(parent_phi, seed_phi)`;
- reinitialize;
- verify intentional component creation;
- distinguish intended topology birth from numerical islands.

Development sequence:

```text
Birth-0: geometry only, known seed
Birth-1: evaluate finite set of seed proposals by actual primal
Birth-2: reuse Stage T density information as temporary nucleation proposer
Birth-3: replace transition proposer with topological derivative /
         reaction-diffusion level-set mechanism
```

Stage T is not the final topology-birth algorithm; it is a transition/proposal mechanism.

Root connectivity and clearance must remain explicit policies.

---

## 14. One SDF optimization iteration

The production loop should have the following ownership:

```text
load parent
  ↓
primal response
  ↓
qualified gradient backend
  ↓
problem compiler:
  f, g, df/dphi, dg/dphi
  ↓
regularization / design-mask projection
  ↓
constrained trust-region proposal
  ↓
optional topology operator
  ↓
SDF reinitialization
  ↓
hard geometry preflight
  ↓
trial primal
  ↓
actual nonlinear objective/constraints
  ↓
accept or rollback
  ↓
checkpoint
```

Never accept from an adjoint prediction alone.

Initially use a simple controlled optimizer:

```text
projected gradient
+ augmented Lagrangian
+ trust region / move limit
```

Do not introduce MMA/GCMMA until the SDF gradient and one-step loop are qualified.

---

## 15. Cross-fidelity criterion

Do not require WaterLily and OpenFOAM absolute force values to immediately match within 5%.

Their discretizations and boundary treatments differ.

Instead preregister cross-fidelity evidence on a candidate set:

- sign of improvement;
- pairwise ranking;
- Spearman correlation;
- Kendall correlation;
- resolution/min-feature validity regime.

The important early scientific question is:

\[
\boxed{
\text{Does an improvement found by the SDF inner solver survive independent
body-fitted CFD verification?}
}
\]

Reuse the repository's existing cross-fidelity ranking infrastructure.

---

## 16. Colab-first runtime

Notebooks must remain thin bootstrap/orchestration wrappers.

Recommended:

```text
colab/
├── 00_runtime_probe.ipynb
├── 10_waterlily_primal.ipynb
├── 20_sdf_fd.ipynb
├── 30_reverse_cpu.ipynb
├── 40_reverse_cuda_spike.ipynb
├── 50_sdf_step.ipynb
└── 60_topology_birth.ipynb
```

Core code remains in `src/`, `julia/`, and `scripts/`.

Each runtime must produce a fingerprint containing at least:

```text
platform
GPU name
VRAM
CUDA driver/runtime
Julia version
WaterLily version/commit
Enzyme version
repo commit
precision
grid
Re
Poisson tolerance
measurement horizon/window
```

A changed Colab GPU is a different execution backend identity.

Checkpoint durable state after accepted iterations and after expensive qualification jobs.

Do not assume Docker exists on managed Colab.

---

## 17. Hardware roles

### Colab GPU

Use for:

- WaterLily CUDA primal;
- FD perturbation farms;
- grid studies;
- candidate evaluation;
- GPU reverse only after it is demonstrated.

### RTX 4070 Ti

Use as the primary reproducible local CUDA development worker:

- VRAM profiling;
- repeatability;
- longer runs;
- CUDA reverse experiments;
- bounded optimization campaigns.

### MacBook Air

Use for:

- Python unit tests;
- ProblemSpec/compiler;
- SDF geometry operations;
- manifests/checkpoints;
- plotting;
- small WaterLily CPU cases;
- CPU reverse-AD correctness experiments where practical.

Do not make Apple/Metal support a blocking production requirement.

---

## 18. Package/file migration

### Retain as core

```text
problem_spec.py
problem_spec_compiler.py
canonical_objective.py
extraction_qualification.py
independent_verification.py
cross_fidelity_ranking.py
stage_v_physical_profile.py
evidence/manifest machinery
```

### Retain for reproduction / transition

```text
design_transform.py
stage_t_loop.py
openfoam_oracle.py
projected_restoration.py
robust_fields.py
```

### Freeze as superseded Stage-S reference

```text
stage_s_reduced_basis.py
stage_s_surface_fd.py
stage_s_adjoint_case.py
stage_s_adjoint_qualification.py
stage_s_geometry_jacobian.py
stage_s_perturbation.py
```

### Add

```text
src/cfd_sdf/design/sdf_state.py
src/cfd_sdf/design/sdf_ops.py
src/cfd_sdf/design/reinitialization.py
src/cfd_sdf/design/topology_birth.py
src/cfd_sdf/design/geometry_policy.py

src/cfd_sdf/oracles/base.py
src/cfd_sdf/oracles/waterlily.py
src/cfd_sdf/oracles/openfoam_verifier.py

src/cfd_sdf/gradients/base.py
src/cfd_sdf/gradients/fd_directional.py
src/cfd_sdf/gradients/waterlily_reverse.py

src/cfd_sdf/optimization/sdf_step.py
src/cfd_sdf/optimization/trust_region.py

src/cfd_sdf/qualification/gradient_qualification.py

src/cfd_sdf/runtime/fingerprint.py
src/cfd_sdf/runtime/checkpoint.py

julia/CFDSDFWaterLily/...
colab/...
```

---

## 19. Mergeable implementation sequence

### PR-01 — Freeze legacy Stage S and introduce contracts

No solver runs.

Add:

- `SDFDesignState`;
- oracle/gradient protocols;
- runtime fingerprint;
- efficiency-constraint semantics;
- architecture docs;
- legacy Stage-S supersession marker.

Gate:

- all old tests pass;
- new contract tests pass;
- no evidence modified;
- P21 hashes unchanged.

### PR-02 — SDF geometry kernel

Implement/test:

- interpolation;
- SDF Boolean ops;
- normals;
- volume;
- reinitialization;
- masks.

### PR-03 — WaterLily stable primal bridge

Start with 2D, then small 3D.

No AD claims.

### PR-04 — Force contract

Fix:

- force directions/signs;
- total force;
- `CD`, `CDF`;
- normalization;
- burn-in/measurement window.

### PR-05 — v16 WaterLily baseline

Load the repository's v16-derived SDF into WaterLily.

Compare against the existing OpenFOAM reference at the level appropriate for a new solver.

### PR-06 — SDF directional FD

Introduce deterministic SDF-direction perturbations and epsilon/noise qualification.

### PR-07 — CPU reverse AD experiment

Pin WaterLily PR #285 exact commit in a separate experimental environment.

Reproduce tolerance dependence before trusting it.

### PR-08 — bounded CUDA reverse spike

Explicit Go/No-Go. Do not allow indefinite Enzyme/CUDA debugging.

### PR-09 — choose production gradient backend

Decision among:

- qualified WaterLily GPU reverse;
- custom WaterLily adjoint;
- TCLB;
- OpenLB;
- other researched alternative.

No optimization campaign before this decision.

### PR-10 — one topology-fixed SDF update

One accepted/rejected step only.

### PR-11 — topology-birth geometry fixture

No uncontrolled CFD/gradient interaction yet.

### PR-12 — one topology-changing trial

Use actual primal acceptance.

### PR-13 — bounded closed loop

At most a small preregistered number of accepted iterations, e.g. 5.

### PR-14 — OpenFOAM independent verification

Verify baseline/intermediate/final candidates and cross-fidelity ranking.

---

## 20. Tests to create

At minimum:

```text
tests/test_sdf_design_state.py
tests/test_sdf_reinitialization.py
tests/test_sdf_boolean_ops.py
tests/test_topology_birth.py
tests/test_efficiency_constraint.py
tests/test_runtime_fingerprint.py
tests/test_checkpoint_resume.py
tests/test_waterlily_contract.py
tests/test_directional_gradient.py
tests/test_openfoam_stage_v_regression.py
tests/test_cross_fidelity_identity.py
```

Key requirements:

- SDF state roundtrip/hash is deterministic;
- zero level-set drift from reinitialization is bounded;
- birth fixture creates exactly the intended topology;
- efficiency constraint sign and gradient assembly are correct;
- resume rejects backend/solver/grid/hash mismatch;
- OpenFOAM Stage V regression evidence remains untouched.

---

## 21. Explicitly do not do these yet

Do not:

- run K=16 B-spline S2;
- call WaterLily GPU reverse production-ready;
- use only pressure force as the canonical car-aero response without justification;
- start full high-Re/FSAE optimization;
- start giant 3D reverse AD before coarse gradient qualification;
- implement naive full timestep reverse tape;
- debug topology birth and reverse AD simultaneously;
- change solver + BC + objective + geometry representation simultaneously;
- reuse B-spline FD qualification as SDF-gradient qualification;
- delete/rewrite P21 or Stage-S failure evidence;
- make FD the production high-dimensional gradient backend;
- introduce MMA/GCMMA before the one-step SDF loop is qualified.

---

## 22. Exact next commit

Starting from `ebdd01f`, the next commit should be:

```text
Architect SDF-native optimization core and freeze legacy Stage S
```

It must contain **no expensive CFD run**.

Acceptance criteria:

```text
all existing tests pass
new SDF contract tests pass

legacy Stage S is explicitly superseded but remains reproducible
S2 is not launched

P21 evidence unchanged
S0R/S1R evidence unchanged

shape_update_allowed = false
sdf_gradient_qualified = false
waterlily_reverse_cpu_qualified = false
waterlily_reverse_cuda_qualified = false
topology_birth_qualified = false
```

After that commit, implement the stable WaterLily primal bridge. Do not start reverse AD work before the primal/force/SDF contract is independently correct.
