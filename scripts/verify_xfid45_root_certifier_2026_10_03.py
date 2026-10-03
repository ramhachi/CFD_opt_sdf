"""Independent exact-Sturm verifier for #45 cellwise trilinear ray roots.

This file intentionally imports no primary certifier or Round 3 helper. It
reconstructs each local cubic from four independent field evaluations, counts
its distinct real roots with an exact-rational Sturm chain, and isolates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math

import numpy as np

_EPS = np.finfo(np.float64).eps


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


def _tol(h: float, length: float, a: float, b: float) -> float:
    return (
        16384.0 * _EPS * max(float(h), abs(float(length)), abs(float(a)), abs(float(b)))
    )


def _trim(p: list[Fraction]) -> list[Fraction]:
    while len(p) > 1 and p[-1] == 0:
        p.pop()
    return p


def _eval(p: list[Fraction], x: Fraction) -> Fraction:
    out = Fraction(0)
    for c in reversed(p):
        out = out * x + c
    return out


def _derivative(p: list[Fraction]) -> list[Fraction]:
    return _trim([Fraction(i) * p[i] for i in range(1, len(p))] or [Fraction(0)])


def _remainder(a: list[Fraction], b: list[Fraction]) -> list[Fraction]:
    r = a.copy()
    while len(r) >= len(b) and any(r):
        shift = len(r) - len(b)
        factor = r[-1] / b[-1]
        for i, c in enumerate(b):
            r[shift + i] -= factor * c
        _trim(r)
    return r


def _sturm(p: list[Fraction]) -> list[list[Fraction]]:
    p = _trim(p.copy())
    if len(p) <= 1:
        return [p]
    seq = [p, _derivative(p)]
    while len(seq[-1]) > 1 or seq[-1][0] != 0:
        rem = _remainder(seq[-2], seq[-1])
        if len(rem) == 1 and rem[0] == 0:
            break
        seq.append([-x for x in rem])
    return seq


def _sign_near(p: list[Fraction], x: Fraction, side: int) -> int:
    q = p
    order = 0
    while True:
        value = _eval(q, x)
        if value:
            sign = 1 if value > 0 else -1
            return sign if side > 0 or order % 2 == 0 else -sign
        if len(q) <= 1:
            return 0
        q = _derivative(q)
        order += 1


def _variations(seq: list[list[Fraction]], x: Fraction, side: int) -> int:
    signs = [_sign_near(p, x, side) for p in seq]
    signs = [s for s in signs if s]
    return sum(a != b for a, b in zip(signs[:-1], signs[1:], strict=True))


def _count_open(seq: list[list[Fraction]], a: Fraction, b: Fraction) -> int:
    return _variations(seq, a, +1) - _variations(seq, b, -1)


def _multiplicity(p: list[Fraction], x: Fraction) -> int:
    q = p
    count = 0
    while _eval(q, x) == 0 and len(q) > 1:
        count += 1
        q = _derivative(q)
    return count + int(_eval(q, x) == 0)


def polynomial_roots(
    coefficients: tuple[float, ...] | list[float] | np.ndarray,
    *,
    ta: float,
    tb: float,
    h: float,
    cell: tuple[int, int, int] = (-1, -1, -1),
) -> RootSet:
    if len(coefficients) != 4 or not all(math.isfinite(float(x)) for x in coefficients):
        raise ValueError("coefficients must be four finite ascending powers")
    if not (math.isfinite(ta) and math.isfinite(tb) and ta < tb and h > 0):
        raise ValueError("expected a finite nonempty ray interval and positive h")
    p = _trim([Fraction.from_float(float(x)) for x in coefficients])
    if all(x == 0 for x in p):
        return RootSet((), "ZERO_INTERVAL", (), ((ta, tb),))
    seq = _sturm(p)
    length = tb - ta
    tol_s = min(1.0, _tol(h, length, ta, tb) / length)
    lo, hi = Fraction(0), Fraction(1)
    roots_s: list[tuple[Fraction, Fraction, Fraction, str]] = []
    if _eval(p, lo) == 0:
        m = _multiplicity(p, lo)
        roots_s.append((lo, lo, lo, "tangent" if m > 1 else "endpoint"))
    if _eval(p, hi) == 0:
        m = _multiplicity(p, hi)
        roots_s.append((hi, hi, hi, "tangent" if m > 1 else "endpoint"))

    unresolved: list[str] = []

    def isolate(a: Fraction, b: Fraction, count: int) -> None:
        if count <= 0:
            return
        width = float(b - a)
        if count == 1 and width <= tol_s:
            left = _sign_near(p, a, +1)
            right = _sign_near(p, b, -1)
            kind = "crossing" if left != right else "tangent"
            roots_s.append((a, b, (a + b) / 2, kind))
            return
        if width <= tol_s and count > 1:
            unresolved.append("distinct_roots_not_separable_at_registered_precision")
            return
        mid = (a + b) / 2
        if _eval(p, mid) == 0:
            m = _multiplicity(p, mid)
            roots_s.append((mid, mid, mid, "tangent" if m > 1 else "crossing"))
            isolate(a, mid, _count_open(seq, a, mid))
            isolate(mid, b, _count_open(seq, mid, b))
            return
        isolate(a, mid, _count_open(seq, a, mid))
        isolate(mid, b, _count_open(seq, mid, b))

    isolate(lo, hi, _count_open(seq, lo, hi))
    roots: list[Root] = []
    for a, b, x, kind in roots_s:
        left = ta if a == 0 else tb if a == 1 else ta + float(a) * length
        right = ta if b == 0 else tb if b == 1 else ta + float(b) * length
        value = ta if x == 0 else tb if x == 1 else ta + float(x) * length
        roots.append(Root(value, (left, right), kind, cell))
    roots.sort(key=lambda root: root.t_m)
    for first, second in zip(roots[:-1], roots[1:], strict=True):
        if abs(second.t_m - first.t_m) <= _tol(h, length, first.t_m, second.t_m):
            unresolved.append("distinct_roots_not_separable_at_registered_precision")
    return RootSet(
        tuple(roots), "UNRESOLVED" if unresolved else "COMPLETE", tuple(unresolved), ()
    )


def _cell(
    phi: np.ndarray, origin: np.ndarray, h: float, p: np.ndarray
) -> tuple[int, int, int]:
    out = []
    for axis in range(3):
        i = math.floor((float(p[axis]) - origin[axis]) / h)
        out.append(max(0, min(int(i), phi.shape[axis] - 2)))
    return tuple(out)


def _value(phi: np.ndarray, origin: np.ndarray, h: float, p: np.ndarray) -> float:
    return _value_error(phi, origin, h, p)[0]


def _value_error(
    phi: np.ndarray, origin: np.ndarray, h: float, p: np.ndarray
) -> tuple[float, float]:
    cell = _cell(phi, origin, h, p)
    q = (p - origin - h * np.asarray(cell, dtype=np.float64)) / h
    vals = []
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                weight = q[0] if i else 1.0 - q[0]
                weight *= q[1] if j else 1.0 - q[1]
                weight *= q[2] if k else 1.0 - q[2]
                vals.append(float(phi[cell[0] + i, cell[1] + j, cell[2] + k]) * weight)
    total = math.fsum(vals)
    magnitude = math.fsum(abs(value) for value in vals)
    return total, 64.0 * _EPS * magnitude


def _sampled_coefficients(
    phi: np.ndarray,
    origin: np.ndarray,
    h: float,
    point: np.ndarray,
    direction: np.ndarray,
    ta: float,
    tb: float,
) -> tuple[float, float, float, float]:
    fractions = (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)
    vals = [
        _value(phi, origin, h, point + (ta + s * (tb - ta)) * direction)
        for s in fractions
    ]
    d1 = [vals[i + 1] - vals[i] for i in range(3)]
    d2 = [d1[i + 1] - d1[i] for i in range(2)]
    d3 = d2[1] - d2[0]
    return (
        vals[0],
        3.0 * d1[0] - 1.5 * d2[0] + d3,
        4.5 * d2[0] - 4.5 * d3,
        4.5 * d3,
    )


def enumerate_ray_roots(
    phi: np.ndarray,
    origin: np.ndarray | tuple[float, float, float],
    h: float,
    point: np.ndarray | tuple[float, float, float],
    direction: np.ndarray | tuple[float, float, float],
    span: float,
) -> RootSet:
    field = np.asarray(phi)
    origin = np.asarray(origin, dtype=np.float64)
    point = np.asarray(point, dtype=np.float64)
    direction = np.asarray(direction, dtype=np.float64)
    norm = float(np.linalg.norm(direction))
    if field.ndim != 3 or not np.isfinite(field).all() or norm == 0 or span <= 0:
        raise ValueError("invalid field or ray")
    direction = direction / norm
    hi = origin + h * (np.asarray(field.shape) - 1)
    cuts = [-float(span), float(span)]
    for axis, size in enumerate(field.shape):
        if direction[axis] != 0.0:
            values = origin[axis] + h * np.arange(size, dtype=np.float64)
            cuts.extend(((values - point[axis]) / direction[axis]).tolist())
    cuts = sorted(x for x in cuts if -span <= x <= span)
    breaks = [cuts[0]]
    for x in cuts[1:]:
        if x > breaks[-1]:
            breaks.append(x)
    roots: list[Root] = []
    zero_intervals: list[tuple[float, float]] = []
    reasons: list[str] = []
    for ta, tb in zip(breaks[:-1], breaks[1:], strict=True):
        mid = (ta + tb) * 0.5
        p_mid = point + mid * direction
        if np.any(p_mid < origin) or np.any(p_mid > hi):
            continue
        cell = _cell(field, origin, h, p_mid)
        coeff = _sampled_coefficients(field, origin, h, point, direction, ta, tb)
        result = polynomial_roots(coeff, ta=ta, tb=tb, h=h, cell=cell)
        roots.extend(result.roots)
        zero_intervals.extend(result.zero_intervals)
        reasons.extend(result.reasons)
    roots.sort(key=lambda root: root.t_m)
    unique: list[Root] = []
    for root in roots:
        tolerance = _tol(h, 2 * span, root.t_m, root.bracket_m[1])
        if unique and abs(root.t_m - unique[-1].t_m) <= tolerance:
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
    guard = math.sqrt(_EPS) * max(float(h), float(span))
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
        vb, eb = _value_error(field, origin, h, before)
        va, ea = _value_error(field, origin, h, after)
        sb = 1 if vb > eb else -1 if vb < -eb else 0
        sa = 1 if va > ea else -1 if va < -ea else 0
        if sb == 0 or sa == 0:
            reasons.append("boundary_root_sidedness_unresolved")
            classified.append(root)
        else:
            kind = "crossing" if sb != sa else "tangent"
            classified.append(Root(root.t_m, root.bracket_m, kind, root.cell))
    return RootSet(
        tuple(classified),
        "UNRESOLVED" if reasons else "COMPLETE",
        tuple(sorted(set(reasons))),
        tuple(zero_intervals),
    )


def nearest_root(result: RootSet, h: float, span: float) -> tuple[Root | None, str]:
    if result.status != "COMPLETE":
        return None, "UNRESOLVED_ROOT_SET"
    if result.zero_intervals:
        return None, "AMBIGUOUS_ZERO_INTERVAL"
    if not result.roots:
        return None, "NO_ADMISSIBLE_ROOT"
    ordered = sorted(result.roots, key=lambda root: abs(root.t_m))
    tol = _tol(h, 2 * span, ordered[0].t_m, ordered[0].bracket_m[1])
    if len(ordered) > 1 and abs(abs(ordered[0].t_m) - abs(ordered[1].t_m)) <= tol:
        return None, "AMBIGUOUS_EQUIDISTANT_ROOTS"
    if ordered[0].kind == "tangent":
        return None, "AMBIGUOUS_TANGENCY"
    return ordered[0], "UNIQUE_NEAREST_ROOT"


def _self_check() -> None:
    result = polynomial_roots((0.0, -0.125, 1.0, -1.0), ta=0.0, tb=1.0, h=0.025)
    expected = (0.0, (1.0 - math.sqrt(0.5)) / 2.0, (1.0 + math.sqrt(0.5)) / 2.0)
    assert result.status == "COMPLETE" and len(result.roots) == 3
    assert np.allclose(
        sorted(r.t_m for r in result.roots),
        expected,
        atol=_tol(0.025, 1.0, 0.0, 1.0),
        rtol=0,
    )


if __name__ == "__main__":
    _self_check()
    print("XFID45_STURM_VERIFIER_SELF_CHECK_OK")
