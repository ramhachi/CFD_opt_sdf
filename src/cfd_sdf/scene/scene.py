"""Analytic-body union, canonical Julia interchange, and design sampling.

``min(phi_c)`` has the correct negative-inside union sign. In overlapping
interiors it need not be the true distance to the union boundary. Separate
design elements may not overlap; declared endplate joints and explicit
MergedElements are checked separately by the scene gate. The design lattice
is a diagnostic/export artifact, never the WaterLily flow domain.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json

import numpy as np

from ..design.sdf_state import SDFDesignState
from .primitives import BoxBody, EndplatePlate, MeshBody, PlateElement, _points, _number, _dimension

FIELD_CONTRACT = "geom_s1_amendment1_v1"
_TYPES = {"plate": PlateElement, "endplate": EndplatePlate, "box": BoxBody, "mesh": MeshBody}


def _positive(value, name, *, zero=False):
    value = _number(value,name)
    if value < 0 or (value==0 and not zero):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}")
    return float(value)


@dataclass(frozen=True)
class MergedElement:
    """One explicit element made from overlapping PlateElements.

    Child IDs retain the merge's material provenance. This is a union proposal,
    not a fitted replacement or a topology/primal qualification.
    """

    id: str
    parts: tuple[PlateElement,...]

    def __post_init__(self):
        if not isinstance(self.id,str) or not self.id.strip():
            raise ValueError("merged id must be a nonempty string")
        object.__setattr__(self,"parts",tuple(self.parts))
        if len(self.parts)<2 or not all(isinstance(p,PlateElement) for p in self.parts):
            raise ValueError("a merged element needs at least two plates")
        ids = [self.id]+[p.id for p in self.parts]
        if len(set(ids))!=len(ids):
            raise ValueError("duplicate merged/child id")

    def phi(self,points):
        return np.minimum.reduce([part.phi(points) for part in self.parts])

    def bbox(self,dimension=3):
        boxes = [part.bbox(dimension) for part in self.parts]
        return np.min([b[0] for b in boxes],axis=0), np.max([b[1] for b in boxes],axis=0)

    def boundary_points(self,spacing,dimension=3):
        p = np.concatenate([part.boundary_points(spacing,dimension) for part in self.parts])
        # Remove internal child surfaces; union's exposed boundary only.
        tolerance = 64*np.finfo(float).eps*max(1.,float(np.max(np.abs(p))))
        return p[self.phi(p)>=-tolerance]

    def to_dict(self):
        return {"kind":"merged","id":self.id,"parameters":{"parts":[part.to_dict() for part in self.parts]}}


def _body_from_dict(value):
    if not isinstance(value,dict) or set(value)!={"kind","id","parameters"} or not isinstance(value["parameters"],dict):
        raise ValueError("body must contain exactly kind, id, parameters")
    kind, params = value["kind"],value["parameters"]
    if kind=="merged":
        if set(params)!={"parts"} or not isinstance(params["parts"],list):
            raise ValueError("merged parameters must contain parts")
        return MergedElement(value["id"],tuple(_body_from_dict(p) for p in params["parts"]))
    if not isinstance(kind,str) or kind not in _TYPES:
        raise ValueError(f"unknown primitive kind {kind!r}")
    cls = _TYPES[kind]
    allowed = {f.name for f in fields(cls) if f.init and f.name!="id"}
    if set(params)!=allowed:
        raise ValueError(f"{kind} parameters must contain exactly {sorted(allowed)}")
    return cls(id=value["id"],**params)


def _unique_object(pairs):
    out = {}
    for k,v in pairs:
        if k in out:
            raise ValueError(f"duplicate JSON key {k!r}")
        out[k] = v
    return out


@dataclass(frozen=True)
class Scene:
    """Ordered movable components, immutable context bodies, optional ground z.

    Ties in labels go to the first body; ground, if present, is the last label.
    IDs, list order, field version and source STL hashes are in the canonical
    SHA256. File paths are portable scene inputs; mesh bytes are also bound.
    """

    components: tuple
    fixed: tuple = ()
    ground: float | None = None

    def __post_init__(self):
        object.__setattr__(self,"components",tuple(self.components))
        object.__setattr__(self,"fixed",tuple(self.fixed))
        ids = []
        for body in self.bodies:
            if not isinstance(body,tuple(_TYPES.values())+(MergedElement,)):
                raise ValueError("unknown scene body type")
            ids.append(body.id)
            if isinstance(body,MergedElement):
                ids.extend(p.id for p in body.parts)
        if len(set(ids))!=len(ids):
            raise ValueError("scene body and child ids must be unique")
        if self.ground is not None:
            if isinstance(self.ground,(bool,np.bool_)) or not np.isscalar(self.ground) or not np.isfinite(self.ground):
                raise ValueError("ground must be a finite z coordinate or None")
            object.__setattr__(self,"ground",float(self.ground))

    @property
    def bodies(self):
        return self.components+self.fixed

    def _fields(self,points):
        p = _points(points)
        values = [body.phi(p) for body in self.bodies]
        if self.ground is not None:
            values.append(p[...,-1]-self.ground)
        return p,values

    def phi(self,points):
        """Negative-inside min union; an empty scene has phi=+infinity."""
        p,values = self._fields(points)
        return np.minimum.reduce(values) if values else np.full(p.shape[:-1],np.inf)

    def labels(self,points):
        p,values = self._fields(points)
        return np.argmin(values,axis=0) if values else np.full(p.shape[:-1],-1,dtype=np.int32)

    def bbox(self,dimension=3):
        _dimension(dimension)
        if not self.bodies:
            raise ValueError("empty/ground-only scene has no finite bounding box")
        boxes = [body.bbox(dimension) for body in self.bodies]
        return np.min([b[0] for b in boxes],axis=0),np.max([b[1] for b in boxes],axis=0)

    def to_dict(self):
        return {"schema_version":1,"kind":"sdf_scene","field_contract":FIELD_CONTRACT,
            "units":{"length":"m","angle":"rad"},
            "components":[body.to_dict() for body in self.components],
            "fixed":[body.to_dict() for body in self.fixed],
            "ground":None if self.ground is None else {"z":self.ground}}

    def to_json(self):
        """Canonical compact UTF-8 JSON for the future Julia body builder."""
        return json.dumps(self.to_dict(),sort_keys=True,separators=(",",":"),allow_nan=False)

    @property
    def scene_sha256(self):
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls,value):
        data = json.loads(value,object_pairs_hook=_unique_object)
        keys = {"schema_version","kind","field_contract","units","components","fixed","ground"}
        if not isinstance(data,dict) or set(data)!=keys or type(data["schema_version"]) is not int or data["schema_version"]!=1:
            raise ValueError("invalid scene schema")
        if data["kind"]!="sdf_scene" or data["field_contract"]!=FIELD_CONTRACT or data["units"]!={"length":"m","angle":"rad"}:
            raise ValueError("unknown scene kind, field contract or units")
        if not all(isinstance(data[k],list) for k in ("components","fixed")):
            raise ValueError("scene components/fixed must be lists")
        ground = data["ground"]
        if ground is not None and (not isinstance(ground,dict) or set(ground)!={"z"}):
            raise ValueError("ground must be null or contain z")
        return cls(tuple(_body_from_dict(b) for b in data["components"]),
            tuple(_body_from_dict(b) for b in data["fixed"]),None if ground is None else ground["z"])

    @staticmethod
    def grid_points(state):
        return np.stack(np.meshgrid(*[o+np.arange(n)*state.spacing_m for o,n in zip(state.origin_m,state.shape)],indexing="ij"),axis=-1)

    def label_grid(self,state):
        p = self.grid_points(state)
        return self.labels(p[..., [0,2]] if state.shape[1]==1 else p)

    def sample(self,h,*,dimension=3,padding_cells=3,phase=(0.,0.,0.),bounds=None,max_nodes=2_000_000):
        """Sample a finite bbox on a uniform h lattice into SDFDesignState.

        ``phase`` is a fractional-cell lattice-origin shift in x,y,z, each in
        [0,1). 2D uses x,z and stores a singleton y=0, so it has no 3D cell
        volume. This phase is a design sampling diagnostic; Julia owns moving
        the physical scene AND ground together on a fixed flow grid.
        """
        h = _positive(h,"h")
        _dimension(dimension)
        if type(padding_cells) is not int or padding_cells<0:
            raise ValueError("dimension must be 2/3 and padding_cells a nonnegative integer")
        if type(max_nodes) is not int or max_nodes<=0:
            raise ValueError("max_nodes must be a positive integer")
        if np.iscomplexobj(phase) or (bounds is not None and np.iscomplexobj(bounds)):
            raise ValueError("phase/bounds must be real")
        phase = np.asarray(phase,dtype=float)
        if phase.shape!=(3,) or not np.isfinite(phase).all() or np.any((phase<0)|(phase>=1)) or (dimension==2 and phase[1]!=0):
            raise ValueError("phase must contain x,y,z fractions in [0,1); y=0 in 2D")
        lo,hi = self.bbox(dimension) if bounds is None else np.asarray(bounds,dtype=float)
        lo,hi = np.asarray(lo,dtype=float),np.asarray(hi,dtype=float)
        if lo.shape!=(dimension,) or hi.shape!=(dimension,) or not np.isfinite([lo,hi]).all() or np.any(hi<=lo):
            raise ValueError("bounds must be finite lower/upper coordinates")
        phase = phase if dimension==3 else phase[[0,2]]
        origin = (np.floor(lo/h)-padding_cells+phase)*h
        maximum = (np.ceil(hi/h)+padding_cells+phase)*h
        shape = np.rint((maximum-origin)/h).astype(np.int64)+1
        if np.prod(shape,dtype=object)>max_nodes:
            raise ValueError("sample would exceed max_nodes")
        axes = [o+np.arange(n)*h for o,n in zip(origin,shape)]
        p = np.stack(np.meshgrid(*axes,indexing="ij"),axis=-1)
        phi = self.phi(p)
        fixed = np.zeros(phi.shape,dtype=bool)
        for body in self.fixed:
            fixed |= body.phi(p)<0
        if self.ground is not None:
            fixed |= p[...,-1]<self.ground
        if dimension==2:
            phi,fixed = phi[:,None,:],fixed[:,None,:]
            origin = (origin[0],0.,origin[1])
        return SDFDesignState.create(phi=phi,origin_m=tuple(origin),spacing_m=h,
            design_mask=~fixed,fixed_solid_mask=fixed,narrow_band_width_m=2*h,
            source_sha256=self.scene_sha256,topology_policy_id="geom_s1_software_unqualified",
            reinitialization_policy_id="analytic_scene_no_reinitialization")

    @staticmethod
    def sampled_measure(state,*,dimension):
        """Node-occupancy diagnostic area/volume, never a continuum or P22 cap."""
        _dimension(dimension)
        if dimension==2 and state.shape[1]!=1:
            raise ValueError("2D measure requires a singleton y lattice")
        if dimension==3 and min(state.shape)<2:
            raise ValueError("singleton axes do not define a 3D volume")
        return {"measure":int(state.solid_mask.sum())*state.spacing_m**dimension,
            "unit":f"m^{dimension}","method":"node occupancy phi<0",
            "state_sha256":state.state_sha256}
