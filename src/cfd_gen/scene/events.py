"""Finite deterministic geometry proposals, without evaluation or selection.

Discrete component identity is separate from sampled solid connectivity. A
merge deliberately overlaps two translated plates in one explicit aggregate.
All proposals must pass scene/policy gates before any CFD; generating them
does not qualify Birth-1, consume an evaluation, or change an optimizer.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import itertools
import json
import math
from collections.abc import Mapping

import numpy as np
from scipy.optimize import minimize
from scipy.spatial import cKDTree

from .primitives import PlateElement, _number, _validate_id
from .scene import MergedElement, Scene, _positive


def _unique_scenes(scenes):
    seen, result = set(), []
    for scene in scenes:
        digest = scene.scene_sha256
        if digest not in seen:
            result.append(scene)
            seen.add(digest)
    return result


def downstream_seed_positions(scene,downstream,vertical_offsets,*,allowed_quadrants=("above","below")):
    """Cartesian offsets from each exposed plate trailing-tip centre.

    World x offsets are strictly positive. World z offsets are signed metres:
    positive is above, negative is below, and zero is invalid. The nonempty
    policy lists allowed ``above``/``below`` quadrants (both by default);
    offsets in undeclared quadrants are omitted. This finite grid proposal
    uses neither local plate normals nor flow information.
    """
    try:
        allowed = set(allowed_quadrants)
    except TypeError as exc:
        raise ValueError("allowed_quadrants must contain above and/or below") from exc
    if isinstance(allowed_quadrants,str) or not allowed or not allowed<={"above","below"}:
        raise ValueError("allowed_quadrants must contain above and/or below")
    try:
        dx = [_positive(x,"downstream offset") for x in downstream]
        dz = [_number(z,"vertical offset") for z in vertical_offsets]
    except TypeError as exc:
        raise ValueError("offset grids must be finite nonempty sequences") from exc
    if not dx or not dz or any(z==0 for z in dz):
        raise ValueError("offset grids must be nonempty with nonzero vertical offsets")
    dz = [z for z in dz if ("above" if z>0 else "below") in allowed]
    points = set()
    for body in scene.components:
        parts = body.parts if isinstance(body,MergedElement) else (body,)
        for p in parts:
            if not isinstance(p,PlateElement):
                continue
            u = .5*(p.chord+p.thickness)
            f = (2./3)*p.camber+.4*p.reflex
            x = p.x+u*math.cos(p.angle)+f*math.sin(p.angle)
            z = p.z+u*math.sin(p.angle)-f*math.cos(p.angle)
            points.update((x+d,z+e) for d,e in itertools.product(dx,dz))
    return sorted(points)


def seed_candidates(scene,library,positions,*,span=None):
    """Product of parameter-library entries and (x,z) positions as Scenes.

    ``library`` is a mapping of discrete values (required chord, thickness,
    camber; optional angle/reflex) or an iterable of such scalar dictionaries.
    All other geometry and fixed context is retained. Duplicate geometric
    proposals collapse deterministically, including repeated library entries.
    A shared existing plate span is inherited; otherwise span is explicit.
    """
    required = {"chord","thickness","camber"}
    optional = {"angle","reflex"}
    if isinstance(library,Mapping):
        if not required<=set(library) or set(library)-(required|optional):
            raise ValueError("library needs chord, thickness, camber and known optional parameters")
        keys = sorted(library)
        try:
            entries = [dict(zip(keys,values)) for values in itertools.product(*(library[k] for k in keys))]
        except TypeError as e:
            raise ValueError("library values must be finite discrete sequences") from e
    else:
        entries = list(library)
    if not entries:
        raise ValueError("library must not be empty")
    for e in entries:
        if not isinstance(e,Mapping) or not required<=set(e) or set(e)-(required|optional):
            raise ValueError("invalid library entry")
    plates = [p for b in scene.components for p in (b.parts if isinstance(b,MergedElement) else (b,)) if isinstance(p,PlateElement)]
    if span is None:
        spans = {p.span for p in plates}
        if len(spans)!=1:
            raise ValueError("span must be explicit without a unique existing plate span")
        span = spans.pop()
    span = _positive(span,"span")
    centres_y = {p.y for p in plates}
    if len(centres_y)>1:
        raise ValueError("seed positions require a shared fixed span centre y")
    y = centres_y.pop() if centres_y else 0.
    positions = list(positions)
    xy = []
    for position in positions:
        if len(position)!=2:
            raise ValueError("seed positions must be (x,z)")
        xy.append(tuple(_number(v,"seed position") for v in position))
    proposals = []
    parts = [p for b in scene.bodies for p in ((b,)+b.parts if isinstance(b,MergedElement) else (b,))]
    occupied = {p.id for p in parts}
    # Parameter IDs collapse duplicates. A merged child can retain an old ID
    # after being translated: a parent-bound suffix permits reseeding that site.
    for e,(x,z) in itertools.product(entries,xy):
        params = {k:_number(v,k) for k,v in e.items()}
        params = {"angle":0.,"reflex":0.,**params,"span":span,"y":y,"x":x,"z":z}
        identity = hashlib.sha256(json.dumps(params,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()[:16]
        if any(isinstance(p,PlateElement) and p.to_dict()["parameters"]==params for p in parts):
            continue
        seed_id = f"seed:{identity}"
        if seed_id in occupied:
            seed_id += f":{scene.scene_sha256[:12]}"
            suffix = 0
            while seed_id in occupied:
                suffix += 1
                seed_id = f"seed:{identity}:{scene.scene_sha256[:12]}:{suffix}"
        seed = PlateElement(id=seed_id,**params)
        proposals.append(replace(scene,components=scene.components+(seed,)))
    return _unique_scenes(proposals)


def knockout_candidates(scene):
    """Remove one plate/merged wing element, retaining all context and bodies."""
    return [replace(scene,components=scene.components[:i]+scene.components[i+1:])
        for i,body in enumerate(scene.components) if isinstance(body,(PlateElement,MergedElement))]


def _nearest_boundary_pair(a,b):
    """Numerical nearest zero-surface pair, or None for an existing contact.

    The distance between extrusions factors into x-z closed-section distance
    and exact y-interval distance. Deterministic section boundary samples seed
    eight bounded SLSQP minimizations subject to phi_a<=0 and phi_b<=0; this
    also handles overlapping sections when only the span intervals separate
    the bodies. Scaling keeps the tolerance relative to the geometry. Local
    refinements are not a certified global distance for deformed plates.
    """
    spacing = min(a.thickness,b.thickness)/4
    pa,pb = a.boundary_points(spacing,2),b.boundary_points(spacing,2)
    scale = max(a.chord,b.chord,a.span,b.span,a.thickness,b.thickness)
    tolerance = 1e-9*scale
    distances,indices = cKDTree(pa).query(pb)
    origin = np.array([a.x,a.z])
    lower = np.r_[a.bbox(2)[0],b.bbox(2)[0]]-np.tile(origin,2)
    upper = np.r_[a.bbox(2)[1],b.bbox(2)[1]]-np.tile(origin,2)
    bounds = list(zip(lower/scale,upper/scale))
    alo,ahi = a.y-a.span/2,a.y+a.span/2
    blo,bhi = b.y-b.span/2,b.y+b.span/2
    if max(alo,blo)<=min(ahi,bhi):
        ya = yb = (max(alo,blo)+min(ahi,bhi))/2
    else:
        ya,yb = (ahi,blo) if ahi<blo else (alo,bhi)

    def interiors(q):
        return -np.array([a.phi(origin+scale*q[:2]),b.phi(origin+scale*q[2:])])/scale

    best = None
    # ponytail: eight local starts suffice for proposals; a certified global
    # closest-pair solver is needed before using this as an admission oracle.
    for index in np.argsort(distances,kind="stable")[:8]:
        initial = (np.r_[pa[indices[index]],pb[index]]-np.tile(origin,2))/scale
        # Tight refinement resolves near-contact directions. A second solve
        # at normal precision can terminate when roundoff stalls the first.
        for ftol in (1e-20,1e-14):
            result = minimize(lambda q: np.dot(q[:2]-q[2:],q[:2]-q[2:]),initial,
                jac=lambda q: 2*np.r_[q[:2]-q[2:],q[2:]-q[:2]],
                bounds=bounds,constraints={"type":"ineq","fun":interiors},method="SLSQP",
                options={"ftol":ftol,"maxiter":100})
            if result.success:
                break
            initial = result.x
        if result.success and np.isfinite(result.x).all() and np.min(interiors(result.x))>=-1e-9:
            a_xz,b_xz = origin+scale*result.x[:2],origin+scale*result.x[2:]
            qa,qb = np.array([a_xz[0],ya,a_xz[1]]),np.array([b_xz[0],yb,b_xz[1]])
            distance = float(np.linalg.norm(qa-qb))
            if distance<=tolerance:
                return None
            if max(abs(a.phi(qa)),abs(b.phi(qb)))>tolerance:
                continue
            if best is None or distance<best[0]:
                best = (distance,qa,qb)
    if best is None:
        raise ValueError("nearest-boundary refinement did not converge")
    return None if best[0]<=tolerance else best


def merge_candidates(scene,*,max_gap=None,overlap=None):
    """Join separated plate neighbours by a minimal boundary-direction move.

    Move b towards a along their numerically closest boundary-point direction
    by gap + ``overlap`` metres. Default overlap is one quarter of the pair's
    smaller thickness; default max_gap is their mean thickness. Existing
    contacts/overlaps are not proposed. A stays unchanged and child IDs retain
    provenance. The nearest-pair refinement and union field are proposal-only:
    all scene gates remain mandatory, and the merged overlap is exempt from
    the individual-primitive distance contract, never BDIM qualified.
    """
    if max_gap is not None:
        max_gap = _positive(max_gap,"max_gap",zero=True)
    if overlap is not None:
        overlap = _positive(overlap,"overlap")
    proposals = []
    for i,j in itertools.combinations(range(len(scene.components)),2):
        a,b = scene.components[i],scene.components[j]
        if not isinstance(a,PlateElement) or not isinstance(b,PlateElement):
            continue
        alo,ahi = a.bbox(3)
        blo,bhi = b.bbox(3)
        gap = float(np.linalg.norm(np.maximum(np.maximum(np.asarray(alo)-bhi,np.asarray(blo)-ahi),0.)))
        radius = (a.thickness+b.thickness)/2 if max_gap is None else max_gap
        if gap>radius+1e-12:
            continue
        closest = _nearest_boundary_pair(a,b)
        if closest is None:
            continue
        gap,pa,pb = closest
        if gap>radius+1e-12:
            continue
        delta = min(a.thickness,b.thickness)/4 if overlap is None else overlap
        shift = (pa-pb)*(1+delta/gap)
        moved = replace(b,x=b.x+shift[0],y=b.y+shift[1],z=b.z+shift[2])
        merged = MergedElement(f"merge:{a.id}:{b.id}",(a,moved))
        components = tuple(merged if k==i else p for k,p in enumerate(scene.components) if k!=j)
        proposals.append(replace(scene,components=components))
    return _unique_scenes(proposals)


def thickness_knockout_ids(history,minimum_thickness=None,*,tolerance=1e-12):
    """IDs at their lower bound at the last two consecutive checkpoints.

    Entries contain ``checkpoint`` (nonnegative integer), ``thickness`` (plate
    parameter ID -> metres), and optionally ``parameter_floors``. Snapshot the
    latter from gates.thickness_parameter_floors at that checkpoint; it must
    exactly cover the row's thickness IDs. Snapshots handle changing shapes
    and IDs, and take precedence over the legacy ``minimum_thickness`` scalar
    or per-ID mapping. Legacy fallback floors must stay fixed throughout the
    supplied history and cover every row using them. With no fallback every
    row needs its own snapshot. These caller-supplied numbers are validated,
    but cannot authenticate historical geometry without that scene evidence.

    A gap, new/disappeared ID or one record does not satisfy two checkpoints.
    Unknown IDs and below-floor history raise. Returned IDs include retained
    merged child IDs; they are parameter IDs, not automatic top-level targets
    for knockout_candidates.
    """
    if isinstance(minimum_thickness,Mapping):
        if not minimum_thickness:
            raise ValueError("minimum_thickness floors must not be empty")
        floors = {_validate_id(key):_positive(value,"minimum_thickness") for key,value in minimum_thickness.items()}
        limit = None
    else:
        limit = None if minimum_thickness is None else _positive(minimum_thickness,"minimum_thickness")
        floors = None
    tolerance = _positive(tolerance,"tolerance",zero=True)
    rows = []
    for row in history:
        if not isinstance(row,Mapping) or not {"checkpoint","thickness"}<=set(row) or set(row)-{"checkpoint","thickness","parameter_floors"} or type(row["checkpoint"]) is not int or row["checkpoint"]<0:
            raise ValueError("invalid checkpoint history")
        if rows and row["checkpoint"]<=rows[-1][0]:
            raise ValueError("checkpoints must increase")
        if not isinstance(row["thickness"],Mapping):
            raise ValueError("thickness history must map IDs to metres")
        values = {_validate_id(key):_positive(val,"historical thickness") for key,val in row["thickness"].items()}
        if "parameter_floors" in row:
            snapshot = row["parameter_floors"]
            if not isinstance(snapshot,Mapping) or set(snapshot)!=set(values):
                raise ValueError("parameter_floors must exactly cover checkpoint thickness IDs")
            row_floors = {_validate_id(key):_positive(val,"parameter floor") for key,val in snapshot.items()}
        elif floors is not None:
            if values.keys()-floors.keys():
                raise ValueError("historical thickness ID must be known in parameter floors")
            row_floors = {key:floors[key] for key in values}
        elif limit is not None:
            row_floors = {key:limit for key in values}
        else:
            raise ValueError("parameter_floors snapshot required without frozen fallback floors")
        for key,value in values.items():
            if value<row_floors[key]-tolerance:
                raise ValueError("historical thickness below lower bound")
        rows.append((row["checkpoint"],values,row_floors))
    if len(rows)<2 or rows[-1][0]!=rows[-2][0]+1:
        return ()
    (_,a,af),(_,b,bf) = rows[-2:]
    return tuple(sorted(k for k in a.keys() & b.keys()
        if abs(a[k]-af[k])<=tolerance and abs(b[k]-bf[k])<=tolerance))


def element_count_designs(scene,n_max,*,gap):
    """N=1..n_max finite split warm starts; no inner optimization.

    Split the longest straight chord L with child chord (L-t-gap)/2, retaining
    the parent's axial footprint L+t and the explicit round-tip gap. Thickness,
    angle and span are retained; camber/reflex scale with child chord to retain
    their dimensionless amplitudes and slope bounds. Impossible positive-child
    requests raise. Registered gates still judge each generated design.
    """
    if type(n_max) is not int or n_max<1:
        raise ValueError("n_max must be a positive integer")
    gap = _positive(gap,"gap",zero=True)
    if len(scene.components)!=1 or not isinstance(scene.components[0],PlateElement):
        raise ValueError("outer count loop needs one initial plate")
    designs = [scene]
    for n in range(2,n_max+1):
        current = designs[-1]
        index = max(range(len(current.components)),key=lambda i:current.components[i].chord)
        p = current.components[index]
        chord = (p.chord-p.thickness-gap)/2
        if chord<=0:
            raise ValueError("split needs a positive child straight chord")
        # 2*(chord+t)+gap == L+t: both external axial endpoints stay fixed.
        offset = (chord+p.thickness+gap)/2
        children = tuple(replace(p,id=f"{p.id}:split{n}:{k}",chord=chord,
            camber=p.camber*chord/p.chord,reflex=p.reflex*chord/p.chord,
            x=p.x+sign*offset*math.cos(p.angle),z=p.z+sign*offset*math.sin(p.angle)) for k,sign in enumerate((-1,1)))
        designs.append(replace(current,components=current.components[:index]+children+current.components[index+1:]))
    return designs


def classify_change(parent,proposed):
    """Software identity classification only; not actual Birth-1 response."""
    if parent.fixed!=proposed.fixed or parent.ground!=proposed.ground:
        raise ValueError("an element event cannot change fixed context or ground")
    before,after = {p.id:p for p in parent.components},{p.id:p for p in proposed.components}
    removed,added = sorted(before.keys()-after.keys()),sorted(after.keys()-before.keys())
    delta = len(after)-len(before)
    same_retained = all(before[k].to_dict()==after[k].to_dict() for k in before.keys() & after.keys())
    kind = "unclassified"
    if delta==1 and len(added)==1 and not removed and same_retained:
        kind = "seed"
    elif delta==-1 and len(removed)==1 and not added and same_retained:
        kind = "knockout"
    elif delta==-1 and len(removed)==2 and len(added)==1 and same_retained:
        merged = after[added[0]]
        if isinstance(merged,MergedElement) and {p.id for p in merged.parts}==set(removed):
            kind = "merge"
    elif not added and not removed:
        kind = "identity" if same_retained else "parameter_change"
    return {"kind":kind,"element_count_delta":delta,"added_ids":added,"removed_ids":removed,
        "parent_scene_sha256":parent.scene_sha256,"proposed_scene_sha256":proposed.scene_sha256,
        "evidence_class":"Birth-1 software preparation","cfd_evaluations":0}
