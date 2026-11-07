# Read-only reviewer probe: R_cv box dependence and time-level consistency on a solved 2D cylinder.
using WaterLily, Statistics
const REPO = "/Users/sota/projects/FomulaTMU/CFD2026_09-wp-02-force00"
include(joinpath(REPO, "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily, joinpath(REPO, "julia", "CFDSDFWaterLily", "gen01", "Force00.jl"))
const C = CFDSDFWaterLily
R = 8f0
center = WaterLily.SA[48.3f0, 48.7f0]
body = AutoBody((x,t)-> sqrt(sum(abs2, x .- center)) - R)
sim = Simulation((192, 96), (1f0, 0f0), 2R; ν=2R/100, body, T=Float32)
boxes = [(32:66, 32:66), (24:90, 20:78), (16:140, 12:86)]
foreach(b -> C.validate_force_box(sim, b), boxes)
for _ in 1:1500; sim_step!(sim); end
rows = []
for k in 1:800
    sim_step!(sim)
    r = [C.force_readouts(sim, b) for b in boxes]
    terms = C.control_volume_terms(sim, boxes[2])
    push!(rows, (cur=r[1].cur, nds=r[1].nds, cv=[x.cv for x in r], st=terms.storage, adv=terms.advection, pr=terms.pressure))
end
m(f) = mean(f(r) for r in rows)
println("mean cur  ", m(r->r.cur))
println("mean nds  ", m(r->r.nds))
for i in eachindex(boxes); println("mean cv box$i ", m(r->r.cv[i])); end
println("mean storage(box2) ", m(r->r.st), "  mean |storage| ", m(r->abs.(r.st)))
println("instant rms diff cv box1-box3 ", sqrt.(m(r->(r.cv[1]-r.cv[3]).^2)), "  rms cv box2 ", sqrt.(m(r->r.cv[2].^2)))
println("lift(y) std cur ", std([r.cur[2] for r in rows]), " cv2 ", std([r.cv[2][2] for r in rows]))
