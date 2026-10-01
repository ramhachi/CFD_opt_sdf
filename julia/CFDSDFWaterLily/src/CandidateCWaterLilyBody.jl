"""
CandidateCWaterLilyBody — Candidate C moment blend for a composed body.

Wrap a `NormalFloorWaterLilyBody` (or a union containing it) and apply the
registered one-sided C1 blend to `μ₀` at WaterLily's face-to-moment handoff.
The wrapped body's `measure` supplies the SDF, normal, and velocity; `μ₁` is
computed from the raw face distance and is left unchanged.  This file is
loaded explicitly by Candidate C jobs so historical bodies and their source
hashes remain untouched.
"""

using WaterLily

struct CandidateCWaterLilyBody{B,T<:Real} <: WaterLily.AbstractBody
    inner::B
    normal_floor::T
    transition_width::T
    function CandidateCWaterLilyBody{B,T}(inner::B, normal_floor::T,
                                          transition_width::T) where {B,T<:Real}
        normal_floor == T(0.25) ||
            throw(ArgumentError("Candidate C fixes normal_floor=0.25"))
        transition_width == T(1.1444091796875e-4) ||
            throw(ArgumentError("Candidate C fixes the FD-07 transition width"))
        _contains_required_normal_floor(inner) ||
            throw(ArgumentError("Candidate C requires a NormalFloorWaterLilyBody at normal_floor=0.25"))
        return new{B,T}(inner, normal_floor, transition_width)
    end
end

_contains_required_normal_floor(body::NormalFloorWaterLilyBody) =
    body.normal_floor == oftype(body.normal_floor, 0.25)
function _contains_required_normal_floor(body::WaterLily.SetBody)
    return _contains_required_normal_floor(body.a) || _contains_required_normal_floor(body.b)
end
_contains_required_normal_floor(::WaterLily.AbstractBody) = false

function _candidate_c_body(inner, normal_floor, transition_width; check_inner=true)
    isfinite(transition_width) && transition_width > 0 ||
        throw(ArgumentError("transition_width must be finite and positive"))
    (!check_inner || _contains_required_normal_floor(inner)) ||
        throw(ArgumentError("Candidate C requires an inner body with normal_floor=0.25"))
    T = promote_type(typeof(normal_floor), typeof(transition_width))
    return CandidateCWaterLilyBody{typeof(inner),T}(inner, T(normal_floor), T(transition_width))
end

CandidateCWaterLilyBody(inner; normal_floor=0.25f0,
                        transition_width=Float32(1.1444091796875e-4)) =
    _candidate_c_body(inner, normal_floor, transition_width)

function CandidateCWaterLilyBody(candidate, other::WaterLily.AbstractBody;
                                 normal_floor=0.25f0,
                                 transition_width=Float32(1.1444091796875e-4))
    hasproperty(candidate, :normal_floor) && getproperty(candidate, :normal_floor) == normal_floor ||
        throw(ArgumentError("Candidate C requires an inner body with normal_floor=0.25"))
    return _candidate_c_body(candidate + other, normal_floor, transition_width;
        check_inner=false)
end

WaterLily.measure(body::CandidateCWaterLilyBody, x::AbstractVector, t;
                  fastd²=eltype(x)(Inf)) =
    WaterLily.measure(body.inner, x, t; fastd²)

@inline function candidate_c_smoothstep(q)
    t = clamp(q, zero(q), one(q))
    return t * t * (3 - 2t)
end

@inline function candidate_c_mu0(face, center, delta, ϵ)
    raw = WaterLily.μ₀(face, ϵ)
    weight = candidate_c_smoothstep((abs(face) - oftype(face, 0.5)) / delta)
    iszero(weight) && return raw
    mismatch = candidate_c_smoothstep((-sign(face) * center) / delta)
    alpha = weight * mismatch
    iszero(alpha) && return raw
    corrected = WaterLily.μ₀(copysign(abs(face), center), ϵ)
    return muladd(alpha, corrected - raw, raw)
end

# WaterLily has no public hook between `measure` and the BDIM moments.  This
# small override preserves its 1.8.0 fill/BC sequence and changes only μ₀.
function WaterLily.measure!(a::WaterLily.AbstractFlow{N,T},
                            body::CandidateCWaterLilyBody; t=zero(T), ϵ=1) where {N,T}
    a.V .= zero(T)
    a.μ₀ .= one(T)
    a.μ₁ .= zero(T)
    d² = T(2 + ϵ)^2
    WaterLily.measure_sdf!(a.σ, body, t; fastd²=d²)
    @fastmath @inline function fill_candidate_c!(μ₀, μ₁, V, d, I)
        if d[I]^2 < d²
            for i ∈ 1:N
                dᵢ, nᵢ, Vᵢ = WaterLily.measure(body, WaterLily.loc(i, I, T), t; fastd²=d²)
                μ₀[I, i] = candidate_c_mu0(dᵢ, d[I], body.transition_width, ϵ)
                V[I, i] = Vᵢ[i]
                m₁ = WaterLily.μ₁(dᵢ, ϵ)
                for j ∈ 1:N
                    μ₁[I, i, j] = m₁ * nᵢ[j]
                end
            end
        elseif d[I] < zero(T)
            for i ∈ 1:N
                μ₀[I, i] = zero(T)
            end
        end
    end
    WaterLily.@loop fill_candidate_c!(a.μ₀, a.μ₁, a.V, a.σ, I) over I ∈ WaterLily.inside(a.p)
    WaterLily.BC!(a.μ₀, zeros(WaterLily.SVector{N,T}), false, a.perdir)
    WaterLily.BC!(a.V, zeros(WaterLily.SVector{N,T}), a.exitBC, a.perdir)
    return nothing
end
