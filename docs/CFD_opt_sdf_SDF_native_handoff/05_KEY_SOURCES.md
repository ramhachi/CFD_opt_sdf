# Key external sources / revisions

These are the critical sources to re-check before implementation decisions that depend on upstream state.

## WaterLily

Repository:
https://github.com/WaterLily-jl/WaterLily.jl

Reverse AD PR:
https://github.com/WaterLily-jl/WaterLily.jl/pull/285

PR title:
`Reverse AD via Enzyme extension`

Observed experimental PR head during 2026-09-26 planning:
`feed49f480b52047b4e9b8bfacdf3e4f8201106b`

Important: this is an experimental revision, not the production primal dependency.

WaterLily paper / differentiable backend-agnostic solver:
https://arxiv.org/abs/2407.16032

## Project repository

https://github.com/ramhachi/CFD_opt_sdf

Architecture-fork base branch:
`feat/p0-openfoam-closed-loop`

Verified base commit for this bundle:
`ebdd01f293636b2fc736885a1032d466e6632e9a`

## Upstream alternatives to investigate if WaterLily GPU reverse is rejected

DAFoam:
https://dafoam.github.io/

OpenLB:
https://www.openlb.net/

TCLB:
https://github.com/CFD-GO/TCLB

waLBerla:
https://walberla.net/

lbmpy:
https://pycodegen.pages.i10git.cs.fau.de/lbmpy/

Re-check exact current versions, licenses, GPU support and adjoint capabilities before locking a replacement backend.
