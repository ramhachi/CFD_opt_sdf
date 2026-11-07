# TOPO-2D scene job. CPU default never imports CUDA; the opt-in CUDA path is
# unexecuted here and requires an externally frozen qualified backend/UUID.
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Topo2D.jl"))
CFDSDFWaterLily.Topo2D.main()
