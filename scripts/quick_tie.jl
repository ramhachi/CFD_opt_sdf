# GRAD-TA1: the tie-averaged QUICK limiter derivative, extracted verbatim in logic from scripts/waterlily_grad_g2_diag5_stages.jl:37-67
# (that file is frozen by the DIAG5 freeze and is not edited).  `Base.include(WaterLily, path)` it: it needs WaterLily's `quick` and `median` and ForwardDiff.
#
# VALUE: bit for bit the original `quick` (it is called).  PARTIALS: the mean of the partials of every candidate whose value lies within `τ` of the selected
# value (inner median first, then outer).  This is a surrogate / generalised derivative, NOT the derivative of the implemented map at ties.
# Differences from the DIAG5 copy: the silent fallback for mixed Float32/Dual arguments is an error, and only Dual width 1 is accepted (the partials are indexed
# with `partials(x, 1)` and rebuilt as a one-element `Partials`, so a wider Dual would silently lose the other partials).
struct QuickTie{T}
    τ::T
end
@inline _p1(x) = ForwardDiff.partials(x, 1)

function (q::QuickTie)(u::D, c::D, d::D) where {D<:ForwardDiff.Dual{<:Any,<:Any,1}}
    m = quick(u, c, d)                                          # the original: the VALUE (and the selected branch's partials) are exactly the original ones
    vu, vc, vd = ForwardDiff.value(u), ForwardDiff.value(c), ForwardDiff.value(d)
    pu, pc, pd = _p1(u), _p1(c), _p1(d)
    vC, pC = 10vc - 9vu, 10pc - 9pu                            # inner candidates: 10c-9u, c, d
    mi = median(vC, vc, vd)
    n = 0; s = zero(pu)
    abs(vC - mi) <= q.τ && (n += 1; s += pC)
    abs(vc - mi) <= q.τ && (n += 1; s += pc)
    abs(vd - mi) <= q.τ && (n += 1; s += pd)
    pin = s / n                                                 # n >= 1: the selected inner value is one of the three
    vA, pA = (5vc + 2vd - vu) / 6, (5pc + 2pd - pu) / 6         # outer candidates: (5c+2d-u)/6, c, inner
    mo = median(vA, vc, mi)
    n = 0; s = zero(pu)
    abs(vA - mo) <= q.τ && (n += 1; s += pA)
    abs(vc - mo) <= q.τ && (n += 1; s += pc)
    abs(mi - mo) <= q.τ && (n += 1; s += pin)
    return typeof(m)(ForwardDiff.value(m), ForwardDiff.Partials((s / n,)))
end
(q::QuickTie)(u::T, c::T, d::T) where {T<:AbstractFloat} = quick(u, c, d)   # value-only arguments (no derivative involved): the original limiter
(q::QuickTie)(u, c, d) = error("QuickTie: arguments must be three Dual numbers of one type with width 1, or three plain floats of one type")
