"""Diagnostic-only scalar alternatives for WaterLily's face sign correction.

Nothing in this file is included by `CFDSDFWaterLily` or production runners.
Distances are in WaterLily solver-cell units and the BDIM width is one cell.
"""
module SDFNativeFD07ContinuousSignOperators

using WaterLily

export MODES, DEFAULT_DELTA, smoothstep01, smooth_sign, effective_distance,
    moment_values, activation_weight

const MODES = (:UPSTREAM, :NO_SIGN_CORRECTION, :A_THRESHOLD, :B_CENTER_SIGN,
               :C_MOMENT_BLEND)
const DEFAULT_DELTA = Float32(1.1444091796875e-4)

@inline function smoothstep01(q)
    t = clamp(q, zero(q), one(q))
    return t * t * (3 - 2t)
end

"Compact C1 approximation to sign(c), exactly ±1 outside |c|<delta."
@inline smooth_sign(c, delta=DEFAULT_DELTA) =
    2 * smoothstep01((c + delta) / (2delta)) - 1

@inline activation_weight(face, delta, ::Val{:A_THRESHOLD}) =
    smoothstep01((abs(face) - (0.5 - delta)) / (2delta))
@inline activation_weight(face, delta, ::Val{:B_CENTER_SIGN}) =
    activation_weight(face, delta, Val(:A_THRESHOLD))
@inline activation_weight(face, delta, ::Val{:C_MOMENT_BLEND}) =
    smoothstep01((abs(face) - 0.5) / delta)
@inline activation_weight(face, delta, ::Val) = one(face)

@inline effective_distance(face, center, ::Val{:UPSTREAM}, delta=DEFAULT_DELTA) =
    abs(face) <= 0.5 ? face : copysign(abs(face), center)
@inline effective_distance(face, center, ::Val{:NO_SIGN_CORRECTION}, delta=DEFAULT_DELTA) = face
@inline function effective_distance(face, center, ::Val{:A_THRESHOLD}, delta=DEFAULT_DELTA)
    w = activation_weight(face, delta, Val(:A_THRESHOLD))
    w == 0 && return face
    return muladd(w, copysign(abs(face), center) - face, face)
end
@inline function effective_distance(face, center, ::Val{:B_CENTER_SIGN}, delta=DEFAULT_DELTA)
    w = activation_weight(face, delta, Val(:B_CENTER_SIGN))
    w == 0 && return face
    corrected = abs(face) * smooth_sign(center, delta)
    return muladd(w, corrected - face, face)
end
@inline effective_distance(face, center, ::Val{:C_MOMENT_BLEND}, delta=DEFAULT_DELTA) = face

"Return `(mu0, mu1)` under the named diagnostic operator."
@inline function moment_values(face, center, mode::Val{M}, delta=DEFAULT_DELTA, ϵ=1) where M
    if M === :C_MOMENT_BLEND
        w = activation_weight(face, delta, mode)
        raw = WaterLily.μ₀(face, ϵ)
        w == 0 && return (raw, WaterLily.μ₁(face, ϵ))
        mismatch = smoothstep01((-sign(face) * center) / delta)
        alpha = w * mismatch
        alpha == 0 && return (raw, WaterLily.μ₁(face, ϵ))
        corrected = WaterLily.μ₀(copysign(abs(face), center), ϵ)
        return (muladd(alpha, corrected - raw, raw), WaterLily.μ₁(face, ϵ))
    end
    d = effective_distance(face, center, mode, delta)
    return (WaterLily.μ₀(d, ϵ), WaterLily.μ₁(d, ϵ))
end

end
