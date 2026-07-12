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
