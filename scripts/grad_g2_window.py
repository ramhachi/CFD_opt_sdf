"""Host-side, independent reconstruction of the G2 full-window tangent from saved force/tangent histories.

Mirrors the registered FD-08 window semantics (``fd08_v2_campaign_io.clipped_window`` / ``time_weighted_mean``): linear
interpolation at the exact window endpoints, interior samples strictly inside, trapezoid time weights, mean = integral
/ duration. A history row carries a value and a tangent (d/dalpha, alpha = phi-perturbation amplitude in metres) for the
sample time and for every force series, so the mean's tangent follows by forward-mode arithmetic.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

SERIES = ("fx", "fy", "fz", "pfx", "pfy", "pfz", "vfx", "vfy", "vfz")
HEADER = ("step", "t_u_l", "t_u_l_tan", *(c for s in SERIES for c in (s, s + "_tan")))
FORCE_SCALE_N_PER_SOLVER = 1.0 / 900.0  # rho U^2 dx^2, flow_24 (formal criteria measurement block)


@dataclass(frozen=True)
class Dual:
    v: float
    d: float = 0.0

    def __add__(self, o):
        o = _d(o); return Dual(self.v + o.v, self.d + o.d)

    __radd__ = __add__

    def __sub__(self, o):
        o = _d(o); return Dual(self.v - o.v, self.d - o.d)

    def __rsub__(self, o):
        return _d(o) - self

    def __mul__(self, o):
        o = _d(o); return Dual(self.v * o.v, self.d * o.v + self.v * o.d)

    __rmul__ = __mul__

    def __truediv__(self, o):
        o = _d(o); return Dual(self.v / o.v, (self.d * o.v - self.v * o.d) / (o.v * o.v))


def _d(x):
    return x if isinstance(x, Dual) else Dual(float(x), 0.0)


def read_history(path: Path) -> list[dict[str, float]]:
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != HEADER:
            raise ValueError(f"history schema mismatch: {path}")
        rows = [{k: float(r[k]) for k in HEADER} for r in reader]
    if len(rows) < 4 or any(not math.isfinite(x) for r in rows for x in r.values()):
        raise ValueError(f"history empty or non-finite: {path}")
    if any(b["step"] <= a["step"] or b["t_u_l"] <= a["t_u_l"] for a, b in zip(rows, rows[1:])):
        raise ValueError(f"history step/time not strictly increasing: {path}")
    return rows


def window_mean(rows, series, start, end, *, time_tangent=True):
    """(value, tangent) of the time-weighted window mean of ``series`` ('fx', or '-fz' for downforce)."""
    sign = -1.0 if series.startswith("-") else 1.0
    name = series.lstrip("-")

    def t_of(r):
        return Dual(r["t_u_l"], r["t_u_l_tan"] if time_tangent else 0.0)

    def f_of(r):
        return Dual(sign * r[name], sign * r[name + "_tan"])

    def last_le(t):
        hits = [r for r in rows if r["t_u_l"] <= t]
        return hits[-1] if hits else None

    def first_ge(t):
        for r in rows:
            if r["t_u_l"] >= t:
                return r
        return None

    def at(t):
        left, right = last_le(t), first_ge(t)
        if left is None or right is None:
            raise ValueError("history does not bracket the window")
        if left["t_u_l"] == right["t_u_l"]:
            return t_of(left), f_of(left)
        tl, tr = t_of(left), t_of(right)
        alpha = (Dual(t) - tl) / (tr - tl)
        fl, fr = f_of(left), f_of(right)
        return Dual(t), fl + alpha * (fr - fl)

    points = [at(start), *[(t_of(r), f_of(r)) for r in rows if start < r["t_u_l"] < end], at(end)]
    num, den = Dual(0.0), Dual(0.0)
    for (t0, f0), (t1, f1) in zip(points, points[1:]):
        dt = t1 - t0
        num = num + 0.5 * (f0 + f1) * dt
        den = den + dt
    mean = num / den
    return mean.v, mean.d
