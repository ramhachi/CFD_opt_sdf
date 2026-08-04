# Project-owned linear Brinkman `fvOption`

`cfdSdfLinearBrinkman` is the pinned OpenCFD OpenFOAM v2512 `simpleFoam`
extension used by the G4 B2.0 Cartesian porous-cylinder representation.  It
does not use `topOSource`, `topOVariablesBase`, adjoints, or a run-time coded
option.

## Fixed contract

The library is named `libcfdSdfLinearBrinkman.so` and its `fvOptions` type is
`cfdSdfLinearBrinkman`.  The option requires all of these entries:

```text
porousCylinderResistance
{
    type                cfdSdfLinearBrinkman;
    active              yes;
    selectionMode       all;
    U                   U;
    betaField           beta;
    betaMax             [0 0 -1 0 0 0 0] 1.5e5;
    resistanceField     brinkmanResistance;
}
```

Load the library from `system/controlDict`:

```text
libs ("libcfdSdfLinearBrinkman.so");
```

`betaField` is a required, explicitly read cell-centre, dimensionless
area/volume-fraction field with `0 = fluid` and `1 = solid`; the extension
registers it itself when `simpleFoam` has not already done so.  It rejects
values outside `[0, 1]`,
non-finite values, an absent field, a non-dimensional coefficient, a
non-positive coefficient, a different momentum field, and any selection mode
other than `all`.  `betaMax` is a kinematic coefficient in `1/s`; B2.0 pins
it to `1.5e5 1/s`.  The option contract cannot be changed after startup.

The source in the kinematic incompressible momentum equation is exactly

```text
Su(U) = -betaMax * beta * U
```

and is assembled implicitly.  It does not perform a nonlinear interpolation.

## Total porous resistance only

The auto-written `resistanceField` is the positive acceleration field

```text
brinkmanResistance = betaMax * beta * U  [m/s2]
```

For a fluid density `rho`, the later reporting layer must form only the total
resistance:

```text
Fporous,x = rho * integral(brinkmanResistance_x dV)
```

Do not label any part of this value as pressure drag or skin-friction drag,
and do not decompose it.  The sign is positive for a positive streamwise
velocity, consistent with the B2.0 positive-drag convention.

## Build (pinned v2512 image)

From the repository root in PowerShell:

```powershell
docker run --rm `
  --entrypoint bash `
  -v "${PWD}:/work" `
  -w /work/openfoam_extensions/cfdSdfLinearBrinkman `
  opencfd/openfoam-default:2512 `
  -lc "source /usr/lib/openfoam/openfoam2512/etc/bashrc && export FOAM_USER_LIBBIN=/work/openfoam_extensions/cfdSdfLinearBrinkman/lib && wmake libso"
```

The compiled library path and digest, the source-tree hash, the exact
`fvOptions` hash, the `beta` field hash, and the density used in the force
reduction are required run-manifest evidence.  A successful build alone does
not qualify the cylinder comparison.

## Runtime smoke

The repository also carries a small v2512-only run that builds the library,
loads it into the laminar `pitzDaily` `simpleFoam` tutorial for one iteration,
and checks that the auto-written resistance field exists:

```powershell
docker run --rm `
  --entrypoint bash `
  -v "${PWD}:/work" `
  -w /work/openfoam_extensions/cfdSdfLinearBrinkman `
  opencfd/openfoam-default:2512 `
  -lc "bash smoke_test.sh"
```

This only proves v2512 loading and the basic source/output path.  It is not a
channel or cylinder qualification result.
