"""Cellwise real-root enumeration for the immutable #45 Round 3 GridSDF.

This is a successor diagnostic. It does not import or alter any Round 3
evaluator or verifier. Polynomial coefficients are in the local cell
coordinate s in [0, 1]; root existence and root-position enclosure are kept
separate, and no residual cutoff discards a candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import itertools
import math

import numpy as np

EPS = np.finfo(np.float64).eps
_DEGREE_EPS = 32.0 * EPS
_EVAL_EPS = 64.0 * EPS
_POSITION_EPS = 16384.0 * EPS


@dataclass(frozen=True)
class Root:
    t_m: float
    bracket_m: tuple[float, float]
    kind: str
    cell: tuple[int, int, int]


@dataclass(frozen=True)
class RootSet:
    roots: tuple[Root, ...]
    status: str
    reasons: tuple[str, ...]
    zero_intervals: tuple[tuple[float, float], ...]


def position_tolerance(h: float, interval_length: float, *t_values: float) -> float:
    """Machine-scaled position tolerance; all length scales are in meters."""
    scale = max(
        float(h), abs(float(interval_length)), *(abs(float(t)) for t in t_values)
    )
    return _POSITION_EPS * scale


def _decimal_value(coeff: tuple[float, ...], x: Decimal) -> Decimal:
    value = Decimal(0)
    for a in reversed(coeff):
        value = value * x + Decimal.from_float(float(a))
    return value


def _degree(coeff: tuple[float, ...]) -> tuple[int, float, float]:
    """Return scale-aware effective degree, discarded bound, and scale."""
    scale = math.fsum(abs(float(v)) for v in coeff)
    tolerance = _DEGREE_EPS * scale
    degree = len(coeff) - 1
    while degree > 0 and abs(float(coeff[degree])) <= tolerance:
        degree -= 1
    discarded = math.fsum(abs(float(v)) for v in coeff[degree + 1 :])
    return degree, discarded, scale


def _quadratic_real_roots(a: Decimal, b: Decimal, c: Decimal) -> list[Decimal]:
    if a == 0:
        return [] if b == 0 else [-c / b]
    disc = b * b - Decimal(4) * a * c
    if disc < 0:
        return []
    root_disc = disc.sqrt()
    q = -(b + (root_disc if b >= 0 else -root_disc)) / Decimal(2)
    if q == 0:
        return [-b / (Decimal(2) * a)]
    roots = [q / a, c / q]
    return sorted(roots)


def _critical_points(coeff: tuple[float, ...], effective_degree: int) -> list[float]:
    """Derivative roots for the reduced polynomial and any discarded terms."""

    def derivative_roots(values: tuple[float, ...]) -> list[Decimal]:
        with localcontext() as ctx:
            ctx.prec = 100
            c = [Decimal.from_float(float(v)) for v in values]
            derivative = [Decimal(i) * c[i] for i in range(1, len(c))]
            while len(derivative) > 1 and derivative[-1] == 0:
                derivative.pop()
            if len(derivative) <= 1:
                return []
            if len(derivative) == 2:
                return [-derivative[0] / derivative[1]]
            return _quadratic_real_roots(derivative[2], derivative[1], derivative[0])

    reduced = tuple(coeff[: effective_degree + 1])
    roots = derivative_roots(reduced)
    if effective_degree < len(coeff) - 1:
        roots.extend(derivative_roots(coeff))
    result = []
    for root in sorted(float(x) for x in roots if Decimal(0) < x < Decimal(1)):
        if not result or root - result[-1] > _POSITION_EPS:
            result.append(root)
    return result


def _has_repeated_root(coeff: tuple[float, ...]) -> bool:
    degree = len(coeff) - 1
    c = [Fraction.from_float(float(v)) for v in coeff]
    while degree > 0 and c[degree] == 0:
        degree -= 1
    if degree == 2:
        a, b, d = c[2], c[1], c[0]
        return b * b - 4 * a * d == 0
    if degree == 3:
        a, b, d, e = c[3], c[2], c[1], c[0]
        return (
            18 * a * b * d * e
            - 4 * b**3 * e
            + b * b * d * d
            - 4 * a * d**3
            - 27 * a * a * e * e
            == 0
        )
    return False


def _sign(coeff: tuple[float, ...], s: float, uncertainty: float) -> int | None:
    with localcontext() as ctx:
        ctx.prec = 100
        x = Decimal.from_float(float(s))
        value = _decimal_value(coeff, x)
        error = Decimal.from_float(float(uncertainty))
        if value == 0 and error == 0:
            return 0
        if value > error:
            return 1
        if value < -error:
            return -1
        return None


def polynomial_roots(
    coefficients: tuple[float, ...] | list[float] | np.ndarray,
    *,
    ta: float,
    tb: float,
    h: float,
    coefficient_error: float = 0.0,
    cell: tuple[int, int, int] = (-1, -1, -1),
    exact_endpoint_roots: tuple[bool, bool] = (False, False),
) -> RootSet:
    """Enumerate every real zero of a cubic or lower polynomial on [ta,tb]."""
    coeff = tuple(float(v) for v in coefficients)
    if len(coeff) != 4 or not all(math.isfinite(v) for v in coeff):
        raise ValueError("coefficients must be four finite ascending powers")
    if not (math.isfinite(ta) and math.isfinite(tb) and ta < tb and h > 0):
        raise ValueError("expected a finite nonempty ray interval and positive h")
    if coefficient_error < 0 or not math.isfinite(coefficient_error):
        raise ValueError("coefficient_error must be finite and non-negative")

    effective_degree, discarded, scale = _degree(coeff)
    if scale == 0.0:
        return RootSet((), "ZERO_INTERVAL", (), ((ta, tb),))

    # The scale-relative degree reduction is explicit. The discarded uniform
    # envelope remains in every sign decision, while critical points are
    # computed from the full coefficients to preserve any near-linear roots.
    uncertainty = coefficient_error + discarded
    critical = _critical_points(coeff, effective_degree)
    length = tb - ta
    tol_t = position_tolerance(h, length, ta, tb)
    tol_s = min(1.0, tol_t / length)
    cuts = [0.0]
    for s in critical:
        if 0.0 < s < 1.0 and (not cuts or s > cuts[-1]):
            cuts.append(s)
    cuts.append(1.0)

    roots: list[Root] = []
    reasons: list[str] = []
    repeated = _has_repeated_root(coeff)
    critical_zero: set[float] = set()
    if repeated and critical:
        with localcontext() as ctx:
            ctx.prec = 100
            best_critical = min(
                critical,
                key=lambda s: abs(_decimal_value(coeff, Decimal.from_float(float(s)))),
            )
            best_value = abs(
                _decimal_value(coeff, Decimal.from_float(float(best_critical)))
            )
            tangent_envelope = Decimal.from_float(
                4096.0 * EPS * EPS * max(scale, np.finfo(float).tiny)
            )
        if best_value <= tangent_envelope:
            if uncertainty > 0.0:
                reasons.append("repeated_root_with_coefficient_uncertainty")
            else:
                critical_zero.add(best_critical)
                t = ta + best_critical * length
                bracket = position_tolerance(h, length, ta, tb)
                roots.append(
                    Root(
                        t,
                        (max(ta, t - bracket), min(tb, t + bracket)),
                        "tangent",
                        cell,
                    )
                )
        else:
            reasons.append("repeated_root_critical_point_not_located")
    for s in critical:
        if repeated and s in critical_zero:
            continue
        sign = _sign(coeff, s, uncertainty)
        if sign == 0:
            if coefficient_error > 0.0:
                reasons.append("critical_zero_with_coefficient_uncertainty")
            else:
                critical_zero.add(s)
                t = ta + s * length
                bracket = position_tolerance(h, length, ta, tb)
                roots.append(
                    Root(
                        t,
                        (max(ta, t - bracket), min(tb, t + bracket)),
                        "tangent",
                        cell,
                    )
                )
        elif sign is None:
            reasons.append("near_tangent_value_within_roundoff_envelope")

    def add_endpoint(s: float, exact: bool) -> bool:
        if exact:
            t = ta if s == 0.0 else tb
            roots.append(Root(t, (t, t), "endpoint", cell))
            return True
        sign = _sign(coeff, s, uncertainty)
        if sign == 0:
            t = ta if s == 0.0 else tb
            roots.append(Root(t, (t, t), "endpoint", cell))
            return True
        if sign is None:
            reasons.append("endpoint_value_within_roundoff_envelope")
            return False
        return False

    add_endpoint(0.0, exact_endpoint_roots[0])
    add_endpoint(1.0, exact_endpoint_roots[1])

    def refine(a: float, b: float, sa: int) -> Root:
        # The robust opposite endpoint signs certify existence. Stop on a
        # position enclosure, never on a residual threshold.
        while (b - a) * length > tol_t:
            m = a + (b - a) * 0.5
            sm = _sign(coeff, m, uncertainty)
            if sm is None:
                # Keep an existence bracket with robust opposite signs. If the
                # midpoint is inside the arithmetic uncertainty band, probe
                # both sides and retain only positions whose signs are still
                # outside that band. This never turns a residual estimate into
                # a positional certificate.
                probe_positions = ((a + m) * 0.5, (m + b) * 0.5)
                signed = [(s, _sign(coeff, s, uncertainty)) for s in probe_positions]
                lower_candidates = [a]
                upper_candidates = [b]
                lower_candidates.extend(s for s, sign in signed if sign == sa)
                upper_candidates.extend(s for s, sign in signed if sign == -sa)
                new_a, new_b = max(lower_candidates), min(upper_candidates)
                if new_a >= new_b or (new_a == a and new_b == b):
                    reasons.append("root_position_exceeds_roundoff_enclosure")
                    break
                a, b = new_a, new_b
                continue
            if sm == 0:
                a = b = m
                break
            if sm == sa:
                a, sa = m, sm
            else:
                b = m
        lo, hi = ta + a * length, ta + b * length
        mid = lo + (hi - lo) * 0.5
        return Root(mid, (lo, hi), "crossing", cell)

    for a, b in zip(cuts[:-1], cuts[1:], strict=True):
        exact_a = a == 0.0 and exact_endpoint_roots[0]
        exact_b = b == 1.0 and exact_endpoint_roots[1]
        sa = (
            0
            if exact_a or any(abs(a - s) <= tol_s for s in critical_zero)
            else _sign(coeff, a, uncertainty)
        )
        sb = (
            0
            if exact_b or any(abs(b - s) <= tol_s for s in critical_zero)
            else _sign(coeff, b, uncertainty)
        )
        if sa is None or sb is None:
            # A narrow interval whose critical value is indistinguishable from
            # zero cannot be assigned a root count by floating signs.
            if b - a > tol_s:
                reasons.append("monotonic_interval_endpoint_sign_unresolved")
            continue
        if sa == 0 or sb == 0 or sa == sb:
            continue
        roots.append(refine(a, b, sa))

    roots.sort(key=lambda root: root.t_m)
    unique: list[Root] = []
    for root in roots:
        tol = position_tolerance(h, length, root.t_m, *(root.bracket_m))
        if unique and abs(root.t_m - unique[-1].t_m) <= tol:
            previous = unique[-1]
            same_endpoint = (
                previous.kind == root.kind == "endpoint"
                and previous.bracket_m[0] == previous.bracket_m[1]
                and root.bracket_m[0] == root.bracket_m[1]
                and previous.bracket_m[0] == root.bracket_m[0]
            )
            if not same_endpoint:
                reasons.append("distinct_roots_not_separable_at_registered_precision")
                unique.append(root)
                continue
            # Shared cell endpoints and a repeated critical root are one zero.
            bracket = (
                min(previous.bracket_m[0], root.bracket_m[0]),
                max(previous.bracket_m[1], root.bracket_m[1]),
            )
            kind = "tangent" if "tangent" in (previous.kind, root.kind) else "endpoint"
            unique[-1] = Root(previous.t_m, bracket, kind, cell)
        else:
            unique.append(root)

    if uncertainty > 0.0 and effective_degree < 3 and discarded > 0.0:
        # The reduced model was used only with its omitted-term envelope. If
        # that envelope reaches a candidate root, retain the result as
        # unresolved instead of guessing its count or identity.
        if any(
            abs(float(_decimal_value(coeff, Decimal.from_float(r.t_m)))) <= uncertainty
            for r in unique
        ):
            reasons.append("reduced_degree_root_within_discarded_term_envelope")

    status = "UNRESOLVED" if reasons else "COMPLETE"
    return RootSet(tuple(unique), status, tuple(sorted(set(reasons))), ())


def _axis_cell(
    phi: np.ndarray, origin: np.ndarray, h: float, p: np.ndarray
) -> tuple[int, int, int]:
    return tuple(
        max(0, min(int(math.floor((float(p[a]) - origin[a]) / h)), phi.shape[a] - 2))
        for a in range(3)
    )


def _ray_coefficients(
    phi: np.ndarray,
    origin: np.ndarray,
    h: float,
    point: np.ndarray,
    direction: np.ndarray,
    ta: float,
    tb: float,
    cell: tuple[int, int, int],
) -> tuple[tuple[float, float, float, float], float]:
    p0 = point + ta * direction
    delta = (tb - ta) * direction
    q0 = (p0 - (origin + h * np.asarray(cell))) / h
    dq = delta / h
    f = np.asarray(
        phi[
            cell[0] : cell[0] + 2,
            cell[1] : cell[1] + 2,
            cell[2] : cell[2] + 2,
        ],
        dtype=np.float64,
    )
    f000 = f[0, 0, 0]
    c = (
        f000,
        f[1, 0, 0] - f000,
        f[0, 1, 0] - f000,
        f[0, 0, 1] - f000,
        f[1, 1, 0] - f[1, 0, 0] - f[0, 1, 0] + f000,
        f[1, 0, 1] - f[1, 0, 0] - f[0, 0, 1] + f000,
        f[0, 1, 1] - f[0, 1, 0] - f[0, 0, 1] + f000,
        f[1, 1, 1]
        - f[1, 1, 0]
        - f[1, 0, 1]
        - f[0, 1, 1]
        + f[1, 0, 0]
        + f[0, 1, 0]
        + f[0, 0, 1]
        - f000,
    )
    x = (float(q0[0]), float(dq[0]))
    y = (float(q0[1]), float(dq[1]))
    z = (float(q0[2]), float(dq[2]))

    def mul(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
        out = [0.0] * min(4, len(a) + len(b) - 1)
        for i, av in enumerate(a):
            for j, bv in enumerate(b):
                if i + j < 4:
                    out[i + j] += av * bv
        return tuple(out)

    xy, xz, yz = mul(x, y), mul(x, z), mul(y, z)
    xyz = mul(xy, z)
    terms = [
        (c[0],),
        (c[1] * x[0], c[1] * x[1]),
        (c[2] * y[0], c[2] * y[1]),
        (c[3] * z[0], c[3] * z[1]),
        tuple(c[4] * v for v in xy),
        tuple(c[5] * v for v in xz),
        tuple(c[6] * v for v in yz),
        tuple(c[7] * v for v in xyz),
    ]
    coefficients = tuple(
        math.fsum(term[i] for term in terms if i < len(term)) for i in range(4)
    )
    term_scale = math.fsum(abs(v) for term in terms for v in term)
    error = _EVAL_EPS * term_scale
    return coefficients, error


def _field_value_error(
    phi: np.ndarray, origin: np.ndarray, h: float, point: np.ndarray
) -> tuple[float, float]:
    cell = _axis_cell(phi, origin, h, point)
    q = (point - (origin + h * np.asarray(cell))) / h
    terms = []
    for bits in itertools.product((0, 1), repeat=3):
        weight = 1.0
        for axis, bit in enumerate(bits):
            weight *= q[axis] if bit else 1.0 - q[axis]
        value = float(phi[tuple(cell[a] + bits[a] for a in range(3))]) * weight
        terms.append(value)
    magnitude = math.fsum(abs(value) for value in terms)
    return math.fsum(terms), _EVAL_EPS * magnitude


def _structural_zero(
    phi: np.ndarray, origin: np.ndarray, h: float, point: np.ndarray
) -> bool:
    value, error = _field_value_error(phi, origin, h, point)
    return value == 0.0 and error == 0.0


def enumerate_ray_roots(
    phi: np.ndarray,
    origin: np.ndarray | tuple[float, float, float],
    h: float,
    point: np.ndarray | tuple[float, float, float],
    direction: np.ndarray | tuple[float, float, float],
    span: float,
) -> RootSet:
    """Enumerate the complete cellwise cubic zero set on a bounded ray."""
    field = np.asarray(phi)
    origin = np.asarray(origin, dtype=np.float64)
    point = np.asarray(point, dtype=np.float64)
    direction = np.asarray(direction, dtype=np.float64)
    if field.ndim != 3 or not np.isfinite(field).all():
        raise ValueError("phi must be a finite 3D array")
    if origin.shape != (3,) or point.shape != (3,) or direction.shape != (3,):
        raise ValueError("origin, point, and direction must be 3-vectors")
    norm = float(np.linalg.norm(direction))
    if not math.isfinite(norm) or norm == 0.0 or not math.isfinite(span) or span <= 0:
        raise ValueError("direction and span must be finite and nonzero")
    direction = direction / norm
    hi = origin + h * (np.asarray(field.shape) - 1)
    breaks = [-float(span), float(span)]
    for axis in range(3):
        if direction[axis] == 0.0:
            continue
        planes = origin[axis] + h * np.arange(field.shape[axis], dtype=np.float64)
        ts = (planes - point[axis]) / direction[axis]
        breaks.extend(ts[(ts > -span) & (ts < span)].tolist())
    breaks.sort()
    merged = [breaks[0]]
    for value in breaks[1:]:
        if value > merged[-1]:
            merged.append(value)
    roots: list[Root] = []
    zeros: list[tuple[float, float]] = []
    reasons: list[str] = []
    for ta, tb in zip(merged[:-1], merged[1:], strict=True):
        mid = ta + (tb - ta) * 0.5
        p_mid = point + mid * direction
        if np.any(p_mid < origin) or np.any(p_mid > hi):
            continue
        cell = _axis_cell(field, origin, h, p_mid)
        coeff, error = _ray_coefficients(
            field, origin, h, point, direction, ta, tb, cell
        )
        exact_endpoints = (
            _structural_zero(field, origin, h, point + ta * direction),
            _structural_zero(field, origin, h, point + tb * direction),
        )
        result = polynomial_roots(
            coeff,
            ta=ta,
            tb=tb,
            h=h,
            coefficient_error=error,
            cell=cell,
            exact_endpoint_roots=exact_endpoints,
        )
        roots.extend(result.roots)
        zeros.extend(result.zero_intervals)
        reasons.extend(result.reasons)

    roots.sort(key=lambda root: root.t_m)
    unique: list[Root] = []
    for root in roots:
        tol = position_tolerance(h, 2 * span, root.t_m, *root.bracket_m)
        if unique and abs(root.t_m - unique[-1].t_m) <= tol:
            prior = unique[-1]
            same_endpoint = (
                prior.kind == root.kind == "endpoint"
                and prior.bracket_m[0] == prior.bracket_m[1]
                and root.bracket_m[0] == root.bracket_m[1]
                and prior.bracket_m[0] == root.bracket_m[0]
            )
            if not same_endpoint:
                reasons.append("distinct_roots_not_separable_at_registered_precision")
                unique.append(root)
                continue
            kind = "tangent" if "tangent" in (prior.kind, root.kind) else "endpoint"
            unique[-1] = Root(
                prior.t_m,
                (
                    min(prior.bracket_m[0], root.bracket_m[0]),
                    max(prior.bracket_m[1], root.bracket_m[1]),
                ),
                kind,
                prior.cell,
            )
        else:
            unique.append(root)
    guard = math.sqrt(EPS) * max(float(h), float(span))
    classified: list[Root] = []
    for root in unique:
        if root.kind != "endpoint":
            classified.append(root)
            continue
        before = point + (root.t_m - guard) * direction
        after = point + (root.t_m + guard) * direction
        if (
            np.any(before < origin)
            or np.any(before > hi)
            or np.any(after < origin)
            or np.any(after > hi)
        ):
            reasons.append("boundary_root_sidedness_unavailable")
            classified.append(root)
            continue
        vb, eb = _field_value_error(field, origin, h, before)
        va, ea = _field_value_error(field, origin, h, after)
        sb = 1 if vb > eb else -1 if vb < -eb else 0
        sa = 1 if va > ea else -1 if va < -ea else 0
        if sb == 0 or sa == 0:
            reasons.append("boundary_root_sidedness_unresolved")
            classified.append(root)
        else:
            kind = "crossing" if sb != sa else "tangent"
            classified.append(Root(root.t_m, root.bracket_m, kind, root.cell))
    status = "UNRESOLVED" if reasons else "COMPLETE"
    return RootSet(tuple(classified), status, tuple(sorted(set(reasons))), tuple(zeros))


def nearest_root(result: RootSet, h: float, span: float) -> tuple[Root | None, str]:
    """Select only after enumeration; never fall back past an ambiguity."""
    if result.status != "COMPLETE":
        return None, "UNRESOLVED_ROOT_SET"
    if result.zero_intervals:
        return None, "AMBIGUOUS_ZERO_INTERVAL"
    if not result.roots:
        return None, "NO_ADMISSIBLE_ROOT"
    ordered = sorted(result.roots, key=lambda root: abs(root.t_m))
    tol = position_tolerance(h, 2 * span, ordered[0].t_m)
    if len(ordered) > 1 and abs(abs(ordered[1].t_m) - abs(ordered[0].t_m)) <= tol:
        return None, "AMBIGUOUS_EQUIDISTANT_ROOTS"
    if ordered[0].kind == "tangent":
        return None, "AMBIGUOUS_TANGENCY"
    return ordered[0], "UNIQUE_NEAREST_ROOT"


def _self_check() -> None:
    result = polynomial_roots((0.09375, -0.6875, 1.5, -1.0), ta=0.0, tb=1.0, h=0.025)
    expected = (0.25, 0.5, 0.75)
    assert result.status == "COMPLETE"
    assert len(result.roots) == 3
    assert np.allclose(
        sorted(r.t_m for r in result.roots),
        expected,
        atol=position_tolerance(0.025, 1.0),
        rtol=0,
    )


if __name__ == "__main__":
    _self_check()
    print("XFID45_ROOT_CERTIFIER_SELF_CHECK_OK")
