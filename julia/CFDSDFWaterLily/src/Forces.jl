"""
Forces — canonical force response for the SDF-native WaterLily line.

WaterLily's `pressure_force`, `viscous_force` and `total_force` return the
surface-integral reaction with the outward body normal, i.e. the force of
the body on the fluid.  The physical force on the body is the negative of
those arrays.  The canonical response for this repository is the Cartesian
body-force vector in the registered solver units:

    F_body = (Fx, Fy, Fz) = -total_force(sim)
           = -(pressure_force(sim) + viscous_force(sim))

`drag`, `lift` and `downforce` are not fixed component numbers here; they are
projections onto registered ProblemSpec / physical-profile directions
(append-only clarification `sdf_native_w2_semantic_clarification_2026_09`).
The W2a sphere fixture interprets +x as drag because its registered
freestream is +x.  The force sign is exercised by a registered gate on that
fixture (drag must be positive along the freestream).
"""

using WaterLily

"""
    force_on_body(sim) -> Vector{Float64}

Total hydrodynamic force on the immersed body in registered solver units
(negative of `WaterLily.total_force`).
"""
force_on_body(sim) = -(WaterLily.total_force(sim))

"""
    pressure_force_on_body(sim) -> Vector{Float64}

Pressure contribution to the force on the body.
"""
pressure_force_on_body(sim) = -(WaterLily.pressure_force(sim))

"""
    viscous_force_on_body(sim) -> Vector{Float64}

Viscous contribution to the force on the body.
"""
viscous_force_on_body(sim) = -(WaterLily.viscous_force(sim))
