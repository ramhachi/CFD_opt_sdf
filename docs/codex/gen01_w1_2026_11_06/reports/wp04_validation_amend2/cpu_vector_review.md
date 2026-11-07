# CPU Vector storage review

Evidence class: CPU_IMPLEMENTATION_CAPABILITY_ONLY. No GPU, mesh, or production
campaign was executed by this review.

The CPU storage change uses `Vector{NTuple{2,Float32}}` in `Topo2D.setup` so that
the number of polygon vertices is absent from the CPU body type. CUDA retains
Tuple storage and its existing isbits guard. The distance-to-segment loop,
winding sign, AutoBody differentiation, scene coordinates, force arithmetic,
window contract, and checkpoint checks are unchanged. Stage completion prints
were added to locate later-stage startup costs without removing any checks.

Reviewed module `julia/CFDSDFWaterLily/gen01/Topo2D.jl` SHA-256:
`67b07f46abca5b889ecc37994dbb477c2d4f300a9528e430d2aaf72197169c42`.
Selftest `scripts/topo2d_selftest.jl` SHA-256:
`13ddd8630436ce477f2ab93a0046df52f427094e9c8e481dce25ff1139e9dfdc`.

## Primitive check and reproducible invocation

Executed from the repository root with Julia 1.12.6 and the locked CPU project.
The successful command is shown with the Julia code line-broken for readability:

```sh
julia --startup-file=no --project=julia/CFDSDFWaterLily -e '
using Test, WaterLily
include("julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl")
Base.include(CFDSDFWaterLily, "julia/CFDSDFWaterLily/gen01/Topo2D.jl")
T = CFDSDFWaterLily.Topo2D
vertices = NTuple{2,Float32}[(0,0),(2,0),(2,2),(0,2),(0,0)]
vector = T.PolygonSDF(vertices)
inline = T.PolygonSDF(Tuple(vertices))
@testset "Float32 Vector and Tuple analytic polygon SDF" begin
    for (x,d,n) in (
        (WaterLily.SVector(3f0,.7f0), 1f0, WaterLily.SVector(1f0,0f0)),
        (WaterLily.SVector(.25f0,.8f0), -.25f0, WaterLily.SVector(-1f0,0f0)),
        (WaterLily.SVector(3f0,3f0), sqrt(2f0),
         WaterLily.SVector(inv(sqrt(2f0)),inv(sqrt(2f0))))
    )
        @test vector(x,0f0) === inline(x,0f0)
        @test isapprox(vector(x,0f0),d;rtol=1f-6,atol=1f-6)
        v = WaterLily.measure(AutoBody(vector),x,0f0)
        t = WaterLily.measure(AutoBody(inline),x,0f0)
        @test v == t
        @test isapprox(v[1],d;rtol=1f-6,atol=1f-6)
        @test isapprox(v[2],n;rtol=1f-6,atol=1f-6)
    end
    @test !isbitstype(typeof(AutoBody(vector)))
    @test isbitstype(typeof(AutoBody(inline)))
    @test !any(id.name=="CUDA" for id in keys(Base.loaded_modules))
end'
```

Observed output, exit 0:

```text
Test Summary:                                 | Pass  Total  Time
Float32 Vector and Tuple analytic polygon SDF |   18     18  0.5s
```

These are 15 distance/AD-normal checks at three probes plus the three storage
and CUDA-module checks. They instantiate neither `Simulation` nor a CFD step.
An earlier ad hoc command failed before the checks because `SVector` was not
qualified; the successful command above uses `WaterLily.SVector`.

## Review conclusion

The primitive check supports equivalence of the Vector and Tuple arithmetic for
the stated Float32 probes. The separately captured integrated CPU comparison in
`cpu_vertex_equivalence.json` is stronger evidence for the actual dense scenes:
all four force CSV files have identical old/new SHA-256, identical headers and
shapes, and zero maximum finite numerical difference. The parent recorded the
complete 56-check Vector selftest at 113.19236087799072 seconds versus
1805.9648878574371 seconds for the retained Tuple run. These are observed local
runs, not a statistically qualified performance benchmark.

This supports retaining native Vector storage for CPU execution while preserving
the original geometric and numerical contracts. CUDA compilation, execution,
performance, and the Tuple-backed GPU path remain unverified. No new tests were
run when this review note was saved, and no source was changed for this note.
