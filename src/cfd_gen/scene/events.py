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

from .primitives import PlateElement, _number
from .scene import MergedElement, Scene, _positive


def _finite(value,name):
    return _number(value,name)


def _unique_scenes(scenes):
    seen, result = set(), []
    for scene in scenes:
        digest = scene.scene_sha256
        if digest not in seen:
            result.append(scene)
            seen.add(digest)
    return result


def downstream_seed_positions(scene,downstream,below):
    """Cartesian offsets from each exposed plate trailing-tip centre.

    Offsets are world x downstream and world -z below (metres), both strictly
    positive. This is a finite grid proposer, not a flow-informed seed rule.
    """
    dx = [_positive(x,"downstream offset") for x in downstream]
    dz = [_positive(z,"below offset") for z in below]
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
            points.update((x+d,z-e) for d,e in itertools.product(dx,dz))
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
        xy.append(tuple(_finite(v,"seed position") for v in position))
    proposals = []
    parts = [p for b in scene.bodies for p in ((b,)+b.parts if isinstance(b,MergedElement) else (b,))]
    occupied = {p.id for p in parts}
    # Parameter IDs collapse duplicates. A merged child can retain an old ID
    # after being translated: a parent-bound suffix permits reseeding that site.
    for e,(x,z) in itertools.product(entries,xy):
        params = {k:_finite(v,k) for k,v in e.items()}
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
    """One proposal per removable component; fixed/ground are never removed."""
    return [replace(scene,components=scene.components[:i]+scene.components[i+1:]) for i in range(len(scene.components))]


def _anchor(p):
    # At u=0, v=-f(0)=camber/3, the strict interior centre-line point.
    return np.array([p.x-p.camber/3*math.sin(p.angle),p.y,p.z+p.camber/3*math.cos(p.angle)])


def merge_candidates(scene,*,max_gap=None):
    """Near PlateElement pairs, translated to share an interior anchor.

    Nearness is the distance between conservative bounding boxes; this may
    over-propose, so it is never an admission decision. Default radius is the
    mean pair thickness. One explicit MergedElement replaces two top-level
    elements, retains their IDs, and permits their internal union overlap.
    """
    if max_gap is not None:
        max_gap = _positive(max_gap,"max_gap",zero=True)
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
        shift = _anchor(a)-_anchor(b)
        moved = replace(b,x=b.x+shift[0],y=b.y+shift[1],z=b.z+shift[2])
        merged = MergedElement(f"merge:{a.id}:{b.id}",(a,moved))
        components = tuple(merged if k==i else p for k,p in enumerate(scene.components) if k!=j)
        proposals.append(replace(scene,components=components))
    return _unique_scenes(proposals)


def thickness_knockout_ids(history,minimum_thickness,*,tolerance=1e-12):
    """IDs at their lower bound at the last two consecutive checkpoints.

    History entries contain exactly ``checkpoint`` (nonnegative integer) and
    ``thickness`` (ID -> metres). A gap, new/disappeared ID or only one record
    does not satisfy two consecutive checkpoints. Malformed histories raise.
    """
    limit = _positive(minimum_thickness,"minimum_thickness")
    tolerance = _positive(tolerance,"tolerance",zero=True)
    rows = []
    for row in history:
        if not isinstance(row,Mapping) or set(row)!={"checkpoint","thickness"} or type(row["checkpoint"]) is not int or row["checkpoint"]<0:
            raise ValueError("invalid checkpoint history")
        if rows and row["checkpoint"]<=rows[-1][0]:
            raise ValueError("checkpoints must increase")
        if not isinstance(row["thickness"],Mapping):
            raise ValueError("thickness history must map IDs to metres")
        values = {}
        for key,val in row["thickness"].items():
            if not isinstance(key,str) or not key.strip():
                raise ValueError("invalid thickness-history ID")
            values[key] = _positive(val,"historical thickness")
            if values[key]<limit-tolerance:
                raise ValueError("historical thickness below lower bound")
        rows.append((row["checkpoint"],values))
    if len(rows)<2 or rows[-1][0]!=rows[-2][0]+1:
        return ()
    a,b = rows[-2][1],rows[-1][1]
    return tuple(sorted(k for k in a.keys() & b.keys() if abs(a[k]-limit)<=tolerance and abs(b[k]-limit)<=tolerance))


def element_count_designs(scene,n_max,*,gap):
    """N=1..n_max finite split warm starts; no inner optimization.

    Start from one PlateElement. Split the longest chord in two, retain all
    shape/thickness/span settings, and separate the child centre lines by the
    caller's explicit chord-direction gap. Registered gates judge each design.
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
        chord = p.chord/2
        # Round-cap extents are chord + t. This makes the nominal axial gap exact.
        offset = (chord+p.thickness+gap)/2
        children = tuple(replace(p,id=f"{p.id}:split{n}:{k}",chord=chord,
            camber=p.camber/2,reflex=p.reflex/2,
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
