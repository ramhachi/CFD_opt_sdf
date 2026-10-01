# WaterLily 1.8.0 sign-consistency semantics

Pinned source: `WaterLily/src/Body.jl`, version 1.8.0, SHA-256
`aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee`.
The registered line is `dᵢ = abs(dᵢ) ≤ 0.5 ? dᵢ : copysign(dᵢ,d[I])` in
`measure!`.

`d[I]` is the cell-center signed distance; `dᵢ` is the signed distance sampled
at a staggered face. In this project, negative values denote solid and
positive values denote fluid, so the center sign selects the inside/outside
side used for the face sample. For face samples farther than half a solver
cell from the interface, the routine makes the face-distance sign agree with
the center sign. It leaves face samples within the half-cell band unchanged. With the
registered `flow_24` spacing of `1/30 m`, the branch boundary corresponds to
`1/60 m` (about 16.7 mm), in solver-cell units; it is not the design-grid
spacing `h=0.025 m`.

The corrected `dᵢ` feeds WaterLily's zeroth kernel moment `μ₀(dᵢ,ϵ)` and first
moment `μ₁(dᵢ,ϵ)nᵢ`; `μ₀`, `μ₁`, body velocity `V`, and center signed-distance
field `σ` are the arrays written by `measure!`. The correction does not alter
the sampled normal or body velocity directly. In this fixture, the observed
A/B initialized-array change is in `μ₀`; `μ₁`, `V`, and `σ` match exactly.

This is part of the discrete immersed-boundary inside/outside treatment, not a
generic noise filter. Removing it can change how sub-cell or thin features are
represented when face and center samples disagree in sign. This one fixture
does not establish which treatment is generally more accurate, nor does it
qualify thin-body behavior, conservation, long-horizon flow, or the physical
baseline. The diagnostic therefore reproduces the pinned branch and disables
only that operation in a private copy; it does not conclude that upstream is
wrong or authorize removing the correction in production.
