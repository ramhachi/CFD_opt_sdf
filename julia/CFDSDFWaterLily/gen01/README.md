# GEN-01 additions outside the registered `src/`

`../src/` is a registered directory pin (`campaign_build.BASE_PINS`; the DIAG5/GRID01/GRID02/LOWDIM/STEP01 freezes bind its hash): keep every file and byte unchanged.
GEN-01 modules (`Checkpoint.jl`, `Force00.jl`, `Topo2D.jl`, …) live here and are loaded explicitly from new entrypoints with
`Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "<Module>.jl"))`.
Campaign kernel `pins` must list each added module explicitly.
