`../src/` is a registered directory pin; keep every file and byte unchanged.
Place GEN-01 additions (including later `Force00.jl`) here and load them from jobs with `Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))`.
Local campaign kernel `pins` must explicitly include each added module.
