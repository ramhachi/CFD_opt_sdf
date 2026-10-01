# #44 static research: mass and force observables for Candidate C

Status: solver-free source and equation review only. This is not a Candidate C
qualification, a production-operator freeze, a registered criterion round, or a
finding that the operator fails conservation. No code, body, threshold, or
historical evidence was changed.

## Source identity and scope

The source audit used the installed WaterLily **1.8.0** package at
`/Users/sota/.julia/packages/WaterLily/yOkji`, bound by
`julia/CFDSDFWaterLily/Manifest.toml` (`git-tree-sha1 =
8e1d973f428df4bae450e1a45f19d0dba3ac6857`, Manifest.toml lines 320–324). The
package `Project.toml` records version 1.8.0. File SHA-256 values are:

| Source | Relevant lines | SHA-256 |
| --- | --- | --- |
| `/Users/sota/.julia/packages/WaterLily/yOkji/src/Body.jl` | 28–60 | `aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee` |
| `/Users/sota/.julia/packages/WaterLily/yOkji/src/Flow.jl` | 1–25, 176–231 | `6138c88f48b04db7ed6861f1f1bec9c450e04214160caef177d85bdad326b7f0` |
| `/Users/sota/.julia/packages/WaterLily/yOkji/src/Metrics.jl` | 91–137 | `58f9cbe34c4f5de05423d18143ee4a2fbb3f990f9b2be1911d478599d0362c00` |
| `/Users/sota/.julia/packages/WaterLily/yOkji/src/Poisson.jl` | 63–75 | `a77c631c88a7637fa5ffdd80d52610acad9aba7346904cb4a90df55c3d0077fb` |
| `/Users/sota/.julia/packages/WaterLily/yOkji/Project.toml` | version | `f64b63e93fa07ebef8a09212ca5424915185e7f8e61bb563e18d6e75729f7faa` |
| `julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl` | 68–108 | `2a4b056a1a4a23dc5699ad340faed8ad35bfab4c103302169a93150feedd04c6` |
| `julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl` | 28–41 | `6686585c205eb07508979b3fdba8bf7aab28c0b29a0d021606a2a1280d031ecf` |
| `julia/CFDSDFWaterLily/src/Forces.jl` | 1–43 | `0e5a6b9dae2a5a3044a9ed08162a42ceb9e5ea5fac41585e7a758184205adc8e` |

The repository-side source snapshot is integration commit `b086d1714ebe75132dcefbafed01b0f040cc7992`.

## What the discretization currently says

WaterLily 1.8.0 computes the cosine kernel and its moments in `Body.jl`:

\[
 K(s)=\tfrac12(1+\cos\pi s),\quad |s|\le1,\qquad
 \mu_0(d)=\int_{-1}^{d}K(s)\,ds
 =\tfrac12\left(1+d+\frac{\sin\pi d}{\pi}\right),
\]

with the implementation clamping/scaling by the kernel width \(\epsilon\).
The first moment is implemented separately in `kern₁`/`μ₁` (Body.jl:53–60).
The `measure!` fill (Body.jl:31–40) derives both from the same face distance
after upstream sign consistency and multiplies the first moment by the body
normal. The BDIM update uses both moments in distinct terms
(`Flow.jl:176–179`): \(\mu_1\) multiplies the derivative term and \(\mu_0\)
multiplies the local acceleration.

Candidate C replaces only the \(\mu_0\) handoff with its registered smooth
blend (`CandidateCWaterLilyBody.jl:68–76, 88–97`); its \(\mu_1\) still uses
the raw face distance. The wrapped normal-floor body evaluates
\(n=\nabla\phi/\max(\lVert\nabla\phi\rVert,0.25)\)
(`WaterLilyNormalFloorBody.jl:35–40`). Thus this vector is unit length only
when \(\lVert\nabla\phi\rVert\ge0.25\); below the floor it is deliberately
sub-unit. Do not silently substitute a normalized geometric normal when
describing or recording the solver's `μ₁` input.

**Static mathematical inference:** the continuous BDIM derivation obtains its
moments as one convolution of the fluid/body equations with a shared signed
distance and interface normal. Candidate C's locally blended \(\mu_0\), raw
distance \(\mu_1\), and regularized normal are not, in general, the pair of
moments of one common unmodified distance/kernel argument in cells affected by
the blend/floor. This is a localized departure from the literal moment
construction. It does **not** establish a mass leak, a failed projection, or a
force-closure error. The physical effect, if any, requires registered
observations.

The normal floor itself is a bounded regularization of the sampled SDF
gradient, not an algebraic conservation or projection identity. Where the
gradient magnitude is below 0.25 it reduces the magnitude of the vector passed
to BDIM's first moment while preserving its direction; any effect on boundary
kinematics must be observed separately from the Candidate C `μ₀` blend.
WaterLily's force metric also obtains `n` by calling `measure(body,...)`
(`Metrics.jl:91–107, 125–129`), so its immersed-surface stress quadrature sees
the wrapped normal-floor vector too. If that vector is sub-unit, the metric
weights the corresponding stress contribution by that smaller magnitude.
This is another normal-floor operator effect to measure against a geometric-unit-
normal surface reference; it is not evidence by itself that the integrated
force is wrong or outside an acceptance limit, and no numerical bound for its
effect has been registered.

The separate pressure projection is built from \(\mu_0\): Simulation creates
the Poisson operator with `flow.μ₀` (WaterLily.jl:93–105), and the pressure
correction multiplies the discrete pressure gradient by `a.μ₀` (Flow.jl:223–231).
At the operator level this is the compatible pair

\[
 u^{n+1}=u^*-M_{\mu_0}G_hp,\qquad
 A_{\mu_0}p=D_hu^*,\qquad
 D_hu^{n+1}=D_hu^*-A_{\mu_0}p=r_p,
\]

where \(A_{\mu_0}=D_hM_{\mu_0}G_h\) denotes the matrix actually assembled
for that coefficient field and \(r_p\) its solve residual (signs follow the
source's `div`, `∂`, `L` convention). Consequently changing \(\mu_0\) does not
by itself break this projection algebra if the same coefficient is used in
both the assembled operator and velocity correction. Incomplete linear solves
and the explicit boundary-condition re-enforcement can leave measured
divergence; this is why the actual post-projection residual must be recorded.
The \(\mu_1\) momentum term is not part of this projection identity.

The discrete `div` is a sum of neighboring face differences
(Flow.jl:1–18). Summing over the complete Cartesian index domain telescopes to
outer boundary fluxes (subject to the implemented ghost-cell and boundary
conventions). That global identity is a useful implementation control only:
it contains no explicit surface term for the embedded car and cannot certify
no-penetration or conservation on the geometric fluid region around an
immersed body.

## Force sign and proposed observables

WaterLily's force metric constructs `nds = n*K(d)` and sums pressure
`p*nds` plus viscous `-2νS*nds` (Metrics.jl:91–137). This is the reaction on
the fluid when `n` points outward from the body. The repository's
`force_on_body` explicitly negates `WaterLily.total_force` and its pressure /
viscous components (`Forces.jl:1–43`). Future evidence must separately retain
the WaterLily reaction (solver units), repository force-on-body vector (solver
units), registered projection (drag/downforce), and force converted with the
registered physical scale to **N**. A global sign flip must not be applied
twice.

For geometry observables, use the canonical GridSDF's trilinear zero surface
and its geometric unit normal \(n_b\), pointing out of the solid and into the
fluid. Do not use the floored solver normal as the geometric area normal. On a
fixed, closed surface \(S_b\), define

\[
 \Phi_b=\rho\int_{S_b}(u-V_b)\cdot n_b\,dA,
 \qquad
 \Phi_{b,abs}=\rho\int_{S_b}|(u-V_b)\cdot n_b|\,dA.
\]

Report signed flux, absolute flux, area-weighted RMS and maximum normal slip,
surface quadrature coverage, and locations where the geometric gradient is
zero/non-finite as separate quantities. The moving-ground check uses
\((u-V_g)\cdot n_g\) on its own fixed surface. For a horizontal ground moving
only tangentially in +x, the expected normal component is zero; tangential
velocity agreement is a separate condition.

For incompressible fluid in a time-dependent domain with the solid volumes
removed, Reynolds transport gives

\[
 \frac{d}{dt}\int_{\Omega_f(t)}\rho\,dV
 +\int_{S_{outer}}\rho u\cdot n_f\,dA
 +\int_{S_b}\rho(u-V_b)\cdot n_f\,dA
 +\int_{S_g}\rho(u-V_g)\cdot n_f\,dA=0,
\]

where each \(n_f\) is the outward normal of the **fluid region**. On the car
cutout, \(n_f=-n_b\); on a ground cutout it likewise points from fluid into
the solid. Include only the physical boundaries present in the selected
control region and use their actual velocities. This region balance is not
the same observable as the whole-grid telescoping identity.

For force closure on the stationary-car case, define a fluid-only control
volume enclosing the car: the solid body is excised, so its surface \(S_b\) is
an inner boundary. Let the artificial outer control surface be \(S_o\) with
outward normal \(n_o\), and the fluid-domain normal on the car cutout be
\(n_f=-n_b\). With
\(\sigma=-pI+2\mu S\), no body-force term, and consistent dimensional units,
the integral momentum equation is

\[
 F_{b\to f}
 =\frac{d}{dt}\int_{\Omega_{CV,f}}\rho u\,dV
 +\int_{S_o}\left[\rho u(u\cdot n_o)-\sigma n_o\right]dA.
\]

Here \(F_{b\to f}=\int_{S_b}\sigma n_f\,dA\) is body-on-fluid traction,
matching the sign of WaterLily's reaction integral and opposing the repo's
force-on-body helper. If the chosen fluid-only control volume also cuts the
moving-ground boundary, add that ground traction as its own inner-boundary
term; the simpler option is to position the control surface so it does not
intersect ground. Preserve storage, pressure, viscous, momentum-unsteady,
advective-flux, and traction terms independently before forming the closure
residual.

## Uncertainty and qualification limits

No acceptance limits are registered by this note. Before a physical
qualification, define and independently estimate these measurement-uncertainty
terms:

| Term | What it bounds | Independent estimate to register |
| --- | --- | --- |
| Surface geometry and area quadrature | Difference between the measured surface integral and the zero set of the canonical trilinear GridSDF. | Nested tessellation/quadrature refinement evaluated against the same trilinear field; retain geometry and quadrature changes separately. |
| Staggered-field interpolation | Error from reconstructing face velocities and cell pressure/stress at surface or control-surface points. | Compare the chosen reconstruction to a fixed higher-order/refined-grid evaluation; specify interpolation stencil and field locations. |
| Time/window | Error in momentum storage derivative and sampled force/flux integrals over the registered physical window. | Time-step refinement and exact endpoint/window integration; do not move endpoints after seeing results. |
| Control-surface integration | Advective and traction flux quadrature and sensitivity to the outer control-surface location. | Refine surface quadrature and compare predeclared nested surfaces in the same fluid region. |
| Discrete solve/projection | Pressure linear-solver residual and measured post-projection divergence. | Save the actual Poisson residual and divergence field/norms each sample; treat these as solver diagnostics, not physical closure allowance. |
| Representation and units | Float precision, world/GridSDF mapping, density and solver-to-world force conversion. | Bind exact source/runtime, grid/state and physical-profile identities; recompute conversions independently in N. |

Report these components separately with their method and independent control
evidence. Do not choose a cutoff from the Candidate C result, roll unrelated
errors into a single noise number, or infer a tolerance from the old upstream
FD noise.

The current GridSDF evaluator is explicitly trilinear in
`GridSDFBody.jl:161–202`, with its analytic gradient in lines 205–245. The
smallest future harness should reuse that canonical grid/evaluator and existing
surface/quadrature tools; if a triangulated surface is used, establish that it
approximates this same trilinear zero set and independently measure its
quadrature/refinement error. Avoid creating a second geometry convention.

The following remain unregistered physical gates: acceptable body-relative
normal flux, fluid-region mass-balance residual, post-projection divergence,
force-closure residual in N, prescribed surfaces/window, and how the independent
uncertainty terms combine with those physical residuals. The averaging window
and any numerical limits must be preregistered by the parent after the complete
Candidate C composite operator contract is frozen. Until then this is static
contract research, not an operator verdict.

Documentation validation: `git diff --check` passed. No runtime or solver
command was run for this source-only review.

Source inspection commands were `nl -ba <source> | sed -n '<registered line range>p'`
for the paths and line ranges above, and:

```text
sha256sum /Users/sota/.julia/packages/WaterLily/yOkji/src/{Body.jl,Flow.jl,Metrics.jl,Poisson.jl} /Users/sota/.julia/packages/WaterLily/yOkji/Project.toml julia/CFDSDFWaterLily/src/{CandidateCWaterLilyBody.jl,WaterLilyNormalFloorBody.jl,Forces.jl}
curl -L --fail --silent --show-error https://eprints.soton.ac.uk/349797/1/v20.pdf -o /tmp/weymouth_yue_2011_bdim.pdf
pdftotext -layout /tmp/weymouth_yue_2011_bdim.pdf /tmp/weymouth_yue_2011_bdim.txt
rg -n "no-slip|force|momentum equation|normal velocity|conservation|convol|kernel" /tmp/weymouth_yue_2011_bdim.txt
```

The PDF text check located the kernel convolution derivation in §2, the
no-slip momentum/projection equations in §3.1, and pressure-force integration
in §4.1; the article is Weymouth & Yue (2011), cited below.

## Primary references

- Weymouth & Yue, “Boundary data immersion method for Cartesian-grid
  simulations of fluid-body interaction problems,” *J. Comput. Phys.* 230
  (2011), 6233–6247, [doi:10.1016/j.jcp.2011.04.022](https://doi.org/10.1016/j.jcp.2011.04.022).
  Its author-hosted manuscript was checked locally; §§2–3 derive the single
  kernel-convolved meta-equation and no-slip projection, while §4.1 describes
  pressure-force integration. The downloaded PDF was
  `/tmp/weymouth_yue_2011_bdim.pdf` (SHA-256
  `5e46e0001410562112b6ce80a87a0f51686a888d2ed75a420ee762c54e59e46c`);
  text was extracted locally for equation/sign review. [Author-hosted manuscript](https://eprints.soton.ac.uk/349797/1/v20.pdf).
- Maertens & Weymouth, “Accurate Cartesian-grid simulations of near-body
  flows at intermediate Reynolds numbers,” *Comput. Methods Appl. Mech.
  Eng.* 283 (2015), 106–129,
  [doi:10.1016/j.cma.2014.09.007](https://doi.org/10.1016/j.cma.2014.09.007).
  This is the second-order BDIM reference named by WaterLily 1.8.0.
  [Southampton repository record](https://eprints.soton.ac.uk/369635/).
- Weymouth & Font, “WaterLily.jl: A differentiable and backend-agnostic Julia
  solver for incompressible viscous flow around dynamic bodies,” *Comput.
  Phys. Commun.* 315 (2025), 109748,
  [doi:10.1016/j.cpc.2025.109748](https://doi.org/10.1016/j.cpc.2025.109748).
- [WaterLily 1.8 stable documentation](https://waterlily-jl.github.io/WaterLily.jl/stable/),
  checked for its body/moment, projection, force-metric and solver contracts.
