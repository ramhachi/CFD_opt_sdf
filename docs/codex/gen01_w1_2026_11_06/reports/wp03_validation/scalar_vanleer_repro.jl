# Demonstrate a scalar branch/tie case only; no Simulation or flow steps.
using WaterLily, SHA
const FD = WaterLily.ForwardDiff
println("RUNTIME\t",VERSION,"\t",pkgversion(WaterLily),"\t",pkgversion(FD))
flow_path = joinpath(dirname(pathof(WaterLily)), "Flow.jl")
dual_path = joinpath(dirname(pathof(FD)), "dual.jl")
for (name,path,needle) in (("WaterLily.Flow",flow_path,"vanLeer(u,c,d)"),("ForwardDiff.dual_comparator",dual_path,"Base.:(<=),"))
    lines = readlines(path)
    line = findfirst(s -> occursin(needle,s),lines)
    line === nothing && error("source needle not found")
    println("SOURCE\t",name,"\t",path,"\t",bytes2hex(sha256(read(path))),"\t",line)
end
for T in (Float32,Float64)
    DT = FD.Dual{Nothing,T,1}
    dual(v,p) = DT(T(v),FD.Partials((T(p),)))
    u,c,d = dual(1,1),dual(1,2),dual(1,3)
    result = WaterLily.vanLeer(u,c,d)
    predicate = c <= min(u,d) || c >= max(u,d)
    v,p = Float64(FD.value(result)),Float64(FD.partials(result,1))
    println("SCALAR\t",T,"\t",WaterLily.vanLeer(T(1),T(1),T(1)),"\t",v,"\t",p,"\t",isfinite(v),"\t",isfinite(p),"\t",predicate,"\t",FD.value(d-u),"\t",FD.partials(d-u,1))
end
