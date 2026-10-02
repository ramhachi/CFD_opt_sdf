using DelimitedFiles, LinearAlgebra
include(joinpath(pwd(),"julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl")); using .CFDSDFWaterLily.GridSDFBody
include(joinpath(pwd(),"julia/CFDSDFWaterLily/src/SurfaceFluxQuadrature.jl")); using .SurfaceFluxQuadrature
input="work/issue44_round8_prep/sphere-input-v2"
phi=reshape(copy(reinterpret(Float32,read(joinpath(input,"canonical_phi_f32_fortran.bin")))),(61,33,25))
grid=GridSDF(phi;origin=(-1.,-.8,-.6),h=(.05,.05,.05),outside_value=3.,margin_m=.15)
v=readdlm(joinpath(input,"seed_vertices.csv"),',',Float64);f=readdlm(joinpath(input,"seed_faces.csv"),',',Int)
evaluator=x->sdf_value_gradient_at_world(grid,x)
projected=[first(SurfaceFluxQuadrature._project(Tuple(v[i,:]),evaluator;tol_m=1e-10,max_iterations=20)) for i in axes(v,1)]
output="work/issue44_round8_prep/parent_projection_audit_001"
writedlm(joinpath(output,"projected_vertices.csv"),reduce(vcat,permutedims.(collect.(projected))),',')
areas=[norm(cross(collect(projected[f[i,2]]).-collect(projected[f[i,1]]),collect(projected[f[i,3]]).-collect(projected[f[i,1]])))/2 for i in axes(f,1)]
writedlm(joinpath(output,"projected_areas.csv"),areas,',')
println("faces=",length(areas)," exact_zero_area=",findall(iszero,areas)," total_area=",sum(areas))
