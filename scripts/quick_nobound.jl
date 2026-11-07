# WaterLily issue #358: remove QUICK's inner 10c-9u bound, retain the outer limiter.
# Base.include(WaterLily, path) so `median` is WaterLily's pinned implementation.
# The same expression is used for Float32, Float64 and ForwardDiff.Dual.
@inline quick_nobound(u, c, d) = median((5c + 2d - u) / 6, c, d)
