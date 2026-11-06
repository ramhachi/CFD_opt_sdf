# TOPO-2D scene job. CPU default never imports CUDA; the opt-in CUDA path is
# unexecuted here and requires an externally frozen qualified backend/UUID.
include(joinpath(@__DIR__, "..", "julia", "topo2d", "Topo2D.jl"))
Topo2D.main()
