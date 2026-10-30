# W1 GridSDFBody fixture suite (registered phase: docs/evidence/sdf_native_w1_adapter_criteria_2026_09.json, sha256 6da068fad8c79ba39197377157d4a5172dedf04511b2acbd8f69146aefea70ef; round 4 band bound 3.3e-3).
# Run: julia --project=julia/CFDSDFWaterLily test/test_grid_sdf_body.jl
# Prints one `RESULT <name> <verdict> <maxerr>` line per fixture; measured
# values are consumed by the evidence registration script outside this file.

include(joinpath(@__DIR__, "..", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily.GridSDFBody, Random, Printf

const REG = (
    sdf_abs_m = 3.3e-3,        # interface-band sdf value gate (round 4)
    sdf_band_m = 1e-3,         # registered probe band |phi_analytic| (m)
    radius_abs_m = 2e-3,       # zero-level radius bound (m)
    affine_abs_m = 2e-5,       # float64 affine reconstruction bound (m)
    roundtrip_abs_m = 1e-14,   # float64 world<->solver round-trip bound (m)
    sphere_margin_m = 0.10,    # sphere fixture's true zero-level margin
    run_margin_m = 0.15,       # registered minimum run-registered margin
    outside_value = 3.0,       # registered positive extension constant (m)
)

const origin = (-1.0, -0.8, -0.6)
const hgrid = (0.05, 0.05, 0.05)
const NX, NY, NZ = 61, 33, 25

function lattice()
    origin[1] .+ (0:NX-1) .* hgrid[1],
    origin[2] .+ (0:NY-1) .* hgrid[2],
    origin[3] .+ (0:NZ-1) .* hgrid[3]
end

"CENTER constant on every side to make a pass/fail pair visible."
function verdict(name, ok, value)
    @printf("RESULT %s %s %s\n", name, ok ? "PASS" : "FAIL", value)
    ok || global FAILED = true
end

FAILED = false

# ---------------------------------------------------------------- F1 roundtrip
let
    xs, ys, zs = lattice()
    phi = Float32.([1.0 for _ in xs, _ in ys, _ in zs] .+ 0.0)
    # registered gate-free raw pathway for pure-map probes
    g = GridSDF(phi, origin, hgrid, (NX, NY, NZ), REG.outside_value, 0.0)
    Random.seed!(2026)
    probes = [Tuple(collect(Float64, (-0.95+rand()*2.90,
        -0.80+rand()*1.60, -0.60+rand()*1.20))) for _ in 1:5000]
    errs = Float64[]
    for xw in probes
        s = world_to_solver(g, xw)
        back = solver_to_world(g, s)
        push!(errs, maximum(abs.(back .- xw)))
    end
    m = maximum(errs)
    verdict("world_solver_roundtrip", m <= REG.roundtrip_abs_m, @sprintf("%.3e", m))
end

# ------------------------------------------------------ F2 affine exactness
let
    xs, ys, zs = lattice()
    a = (2.0, -3.0, 0.5); b = 0.4
    phi = [a[1]*p + a[2]*q + a[3]*r + b for p in xs, q in ys, r in zs]
    # a whole-box affine zero plane crosses the design-box faces by
    # construction, so this pure-map probe uses the registered raw pathway
    g = GridSDF(phi, origin, hgrid, (NX, NY, NZ), REG.outside_value, 0.0)
    Random.seed!(2026)
    probes = [Tuple((xs[1]+rand()*(xs[end]-xs[1]),
        ys[1]+rand()*(ys[end]-ys[1]), zs[1]+rand()*(zs[end]-zs[1]))) for _ in 1:5000]
    errs = maximum(abs(sdf_at_world(g, xw) -
        (a[1]*xw[1] + a[2]*xw[2] + a[3]*xw[3] + b)) for xw in probes)
    verdict("affine_exactness", errs <= REG.affine_abs_m, @sprintf("%.3e", errs))
end

# ------------------------------------------------- F3 analytic sphere fidelity
let
    xs, ys, zs = lattice()
    c = (0.25, 0.0, 0.0); R = 0.5
    phi64 = [sqrt((p-c[1])^2 + (q-c[2])^2 + (r-c[3])^2) - R
             for p in xs, q in ys, r in zs]
    phi32 = Float32.(phi64)
    g64 = GridSDF(phi64; origin=origin, h=hgrid,
        outside_value=REG.outside_value, margin_m=REG.sphere_margin_m)
    g32 = GridSDF(phi32; origin=origin, h=hgrid,
        outside_value=REG.outside_value, margin_m=REG.sphere_margin_m)
    Random.seed!(42)
    N = 200000
    max64 = 0.0; max32 = 0.0
    for _ in 1:N
        xw = Tuple((xs[1]+rand()*(xs[end]-xs[1]),
            ys[1]+rand()*(ys[end]-ys[1]), zs[1]+rand()*(zs[end]-zs[1])))
        exact = sqrt((xw[1]-c[1])^2+(xw[2]-c[2])^2+(xw[3]-c[3])^2) - R
        max64 = max(max64, abs(sdf_at_world(g64, xw) - exact))
        max32 = max(max32, abs(sdf_at_world(g32, xw) - exact))
    end

    # explicit registered interface-band probes: points on and around the
    # sphere surface with |phi_analytic| <= sdf_band_m, so the gated band
    # measurement cannot be vacuous (uniform box sampling rarely lands in
    # the 2 mm band)
    max32_band = 0.0; nband = 0
    for _ in 1:5000
        theta = acos(1 - 2*rand()); azimuth = 2*pi*rand()
        direction = (sin(theta)*cos(azimuth), sin(theta)*sin(azimuth), cos(theta))
        u = (2*rand() - 1) * REG.sdf_band_m
        xw = (c[1] + (R + u)*direction[1],
              c[2] + (R + u)*direction[2],
              c[3] + (R + u)*direction[3])
        exact = sqrt((xw[1]-c[1])^2+(xw[2]-c[2])^2+(xw[3]-c[3])^2) - R
        @assert abs(exact) <= REG.sdf_band_m * (1 + 1e-9)
        max32_band = max(max32_band, abs(sdf_at_world(g32, xw) - exact))
        nband += 1
    end
    verdict("sphere_sdf_interface_band",
        nband == 5000 && max32_band <= REG.sdf_abs_m,
        @sprintf("n=%d max %.3e", nband, max32_band))
    verdict("sphere_sdf_interior_diagnostic", true,
        @sprintf("float64 %.3e float32 %.3e (recorded, not gated)", max64, max32))

    # zero-level radius along rays from the sphere center
    function zero_radius(g, y0, z0)
        f(t) = sdf_at_world(g, (t, y0, z0))
        tlo = c[1] - 1.0; thi = c[1] + 1.0
        for _ in 1:80
            mid = 0.5*(tlo+thi)
            if f(mid) < 0.0; tlo = mid; else; thi = mid; end
        end
        return thi - c[1]
    end
    for (name, g) in (("radius_float64", g64), ("radius_float32", g32))
        errs = Float64[]
        for j in 1:16
            ang = 2*pi*(j-1)/16 + 0.13
            y0 = 0.30*sin(ang); z0 = 0.38*cos(ang)
            rr = zero_radius(g, y0, z0)
            expected = sqrt(max(0.0, R^2 - y0^2 - z0^2))
            push!(errs, abs(rr - expected))
        end
        m = maximum(errs)
        verdict(name, m <= REG.radius_abs_m, @sprintf("%.3e", m))
    end
end

# --------------------------------------------------- F4 outside extension
let
    xs, ys, zs = lattice()
    phi = Float32.([1.0 for _ in xs, _ in ys, _ in zs])
    # pure-map outside-extension probe through the registered raw pathway
    g = GridSDF(phi, origin, hgrid, (NX, NY, NZ), REG.outside_value, 0.0)
    Random.seed!(7)
    probes = [ (2.0+rand()*3, rand()*4-2, rand()*4-2),
               (-1.0-rand()*3, rand()*4-2, rand()*4-2),
               (rand()*4-1, 0.8+rand()*3, rand()*4-2),
               (rand()*4-1, -0.8-rand()*3, rand()*4-2),
               (rand()*4-1, rand()*4-2, 0.6+rand()*3),
               (rand()*4-1, rand()*4-2, -0.6-rand()*3) ]
    allpos = all(sdf_at_world(g, Tuple(x)) > 0.0 for x in probes)
    allext = all(sdf_at_world(g, Tuple(x)) == Float64(REG.outside_value) for x in probes)
    verdict("outside_extension_positive_exactly", allpos && allext,
        @sprintf("n=%d", length(probes)))
end

# ------------------------------------------------- F5 margin gate pass/refuse
let
    xs, ys, zs = lattice()
    c = (0.25, 0.0, 0.0); R = 0.5
    phi = Float32.([sqrt((p-c[1])^2 + (q-c[2])^2 + (r-c[3])^2) - R
                    for p in xs, q in ys, r in zs])
    g = GridSDF(phi; origin=origin, h=hgrid,
        outside_value=REG.outside_value, margin_m=REG.sphere_margin_m)
    measured = zero_level_margin_m(phi, origin, hgrid)
    verdict("margin_gate_pass", measured >= REG.sphere_margin_m - 1e-6,
        @sprintf("%.9e", measured))
    refused = false; msg = ""
    try
        GridSDF(phi; origin=origin, h=hgrid,
            outside_value=REG.outside_value, margin_m=REG.run_margin_m)
    catch e
        refused = e isa GridSDFError
        msg = e.msg
    end
    verdict("margin_gate_fail_closed", refused,
        @sprintf("%.9e", measured))
end

# -------------------------------------------------------- F6 all-solid refuse
let
    xs, ys, zs = lattice()
    phi = (-1.0) .+ 0*Float32.([1.0 for _ in xs, _ in ys, _ in zs])
    refused = false
    try
        GridSDF(phi; origin=origin, h=hgrid,
            outside_value=REG.outside_value, margin_m=0.0)
    catch e
        refused = e isa GridSDFError
    end
    verdict("all_solid_refused", refused, "")
end

# ------------------------------------------------------- F7 real v16 genesis
let
    # real-data fixture: the registered v16 genesis state's margin is
    # pre-declared ~0.35 m >= 0.15 m; this controller-external measurement
    # runs through scripts/register_sdf_native_w1_grid_sdf_body_2026_09.py,
    # which exports the npz phi and calls this module's zero_level_margin_m
    # and the gate constructor on the real state.
    println("SKIPPED real_genesis_margin_diagnosis (executed by scripts/register_sdf_native_w1_grid_sdf_body_2026_09.py)")
end

exit(FAILED ? 1 : 0)
