# Porous directional force objective

`porousDirectionalForce` integrates the reaction of the linear Brinkman
momentum sink over selected cell zones:

```text
C_dir = 2 / (Aref UInf^2) * integral(betaMax beta U.direction dV)
```

For a positive streamwise velocity, `direction (1 0 0)` gives positive drag.
For a coordinate system with positive Z upward, `direction (0 0 -1)` gives
positive downforce. The integral covers all cells by default. Set `zones` only
when the design domain is represented by one or more complete cell zones.

This first implementation intentionally matches OpenFOAM's linear
`topOSource` interpolation. Nonlinear porosity interpolation requires the
objective and its direct derivative to use the same interpolation function.

Example objective entry:

```text
downforce
{
    weight      -1;
    type        porousDirectionalForce;
    direction   (0 0 -1);
    Aref        1;
    UInf        1;
}
```

Build with the OpenCFD OpenFOAM v2512 image:

```powershell
docker run --rm `
  --entrypoint bash `
  -v "${PWD}:/work" `
  -w /work/openfoam_extensions/porousDirectionalForce `
  opencfd/openfoam-default:2512 `
  -lc "source /usr/lib/openfoam/openfoam2512/etc/bashrc && export FOAM_USER_LIBBIN=/work/openfoam_extensions/porousDirectionalForce/lib && wmake libso"
```

## Staged raw-alpha response-gradient export

`stagedRawAlphaGradientExporter` is the solver-side boundary for the
localized G2 response-gradient artifact.  Its contract is deliberately
response-specific and must declare `flowCaseId`, `responseId`,
`namedAdjointId`, `gradientVariable staged_raw_alpha`, the exact derivative
meaning `dJ=sum_i g_alpha[i]*d(alpha_i)`, and the complete internal chain
`alpha->alphaTilda->beta->response`.  It also requires a raw-coefficient
formula/units, Newton conversion factor/formula/units, source path and
SHA-256, and records the solver final time when an audited export becomes
available.

The current v2512 extension does **not** provide a public, audited solver API
that returns this complete staged-raw-alpha derivative.  The function object
therefore validates the explicit contract and then fails closed without
writing an artifact.  This is intentional: `dJ/dbeta`, or an existing
sensitivity field chosen by name, cannot be relabelled as `dJ/d(raw alpha)`.
It also rejects parallel execution; the first qualification contract is
strictly serial and does not accept an implicit processor ordering.

Do not add this function object to a production run until the missing solver
API is implemented and audited.  The required future artifact is one per
named response and must contain a finite native-float64 vector in canonical
serial cell order (or a strictly defined native scalar-field equivalent), the
above provenance, final time, source path/hash, and the declared unit
conversion.  No G2 qualification is implied by this extension scaffold.
