# GRAD-00 Amendment 1: avoid vanLeer's zero primal denominator for Dual endpoints.
# Base.include(WaterLily, path) to use the pinned vanLeer and ForwardDiff bindings.
@inline vanLeer_safe(u,c,d) = ForwardDiff.value(d) == ForwardDiff.value(u) ? c : vanLeer(u,c,d)
