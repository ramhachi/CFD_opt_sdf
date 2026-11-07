"""Free, fail-closed GEOM-S1 scene checks, before any CFD evaluation.

This is solver-free software evidence. Defaults ``t_min=g_min=4h`` are
development defaults, not RES-00 registered limits. R3 is the opening-defect
definition in ``docs/width_rule_decision_2026_10_20.md``; reusing its definition
does not adopt that historical proposal or change the existing v2 gates.

Topology uses finite-body node occupancy (negative phi), excluding infinite
ground: 8/26 neighbours for solid, 4/6 for void. ``required_components`` counts
the entire finite union, including fixed parts. Individual bodies must also
be represented and connected. Geometry labels and element identities remain
distinct from this sampled union component count.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import itertools
import math
from numbers import Real
from typing import Any

import numpy as np
from scipy import ndimage

from cfd_sdf.design.geometry_gates import LENGTH_TOLERANCE_M, _gate
from cfd_sdf.design.sdf_state import SDFDesignState
from .primitives import BoxBody, EndplatePlate, MeshBody, PlateElement, _validate_id
from .scene import MergedElement, SceneSamplingLimit

_DEFAULT_SOURCE = "development_default_4h_not_RES00_registered"
_MAX_REFINED_NODES = 8_000_000


@dataclass(frozen=True)
class SceneGatePolicy:
    """Explicit admission inputs; absent required inputs block acceptance.

    ``envelope`` is a mapping or object with ``lower``, ``upper`` and nonempty
    ``rule_source``. It is supplied by the caller/ProblemSpec, never inferred
    from a v2 CFD domain. Coordinates are x,z or x,y,z in metres. ``domain``
    separately declares a finite clearance box. ``clearance_m`` applies to
    ground and to that box; at least one target must exist. Envelope, clearance,
    forbidden masks and roots apply only to movable components, not fixed
    context. ``joints`` lists (plate/merged wing ID, endplate ID): all such pairs
    present in the scene require a declaration and sampled contact. A valid
    declaration exempts that pair
    from the inter-body gap check, not any other pair.

    Root/forbidden masks use the sampled state's shape. A named root with
    ``None`` or a required-but-missing forbidden mask is unmeasured. Every
    connected movable solid must have a root owner when roots are declared.
    Arbitrary STL thickness cannot be inferred from its AABB: an externally
    established lower width may be supplied in ``minimum_widths_m`` with
    ``width_source`` provenance; otherwise its thickness is unmeasured.
    """

    minimum_thickness_m: float | None = None
    minimum_gap_m: float | None = None
    required_components: int | None = None
    envelope: Any = None
    clearance_m: float | None = None
    domain: Any = None
    joints: tuple[tuple[str, str], ...] = ()
    root_masks: Mapping[str, np.ndarray | None] = field(default_factory=dict)
    forbidden_mask: np.ndarray | None = None
    require_forbidden_mask: bool = False
    minimum_widths_m: Mapping[str, float] = field(default_factory=dict)
    width_source: str | None = None

    def __post_init__(self):
        for name in ("minimum_thickness_m", "minimum_gap_m", "clearance_m"):
            value = getattr(self, name)
            if value is not None:
                _nonnegative(value, name)
        if self.required_components is not None and (
            type(self.required_components) is not int or self.required_components < 1
        ):
            raise ValueError("required_components must be a positive integer or None")
        if not isinstance(self.root_masks, Mapping) or not isinstance(self.minimum_widths_m, Mapping):
            raise ValueError("root_masks and minimum_widths_m must be mappings")
        for name in self.root_masks:
            _validate_id(name)
        for name, width in self.minimum_widths_m.items():
            _validate_id(name)
            if _nonnegative(width, "declared width") == 0:
                raise ValueError("declared widths must have positive values")
        if self.minimum_widths_m and (not isinstance(self.width_source, str) or not self.width_source.strip()):
            raise ValueError("declared widths require width_source provenance")
        if type(self.require_forbidden_mask) is not bool:
            raise ValueError("require_forbidden_mask must be boolean")
        pairs = tuple(tuple(pair) for pair in self.joints)
        if any(len(pair) != 2 for pair in pairs):
            raise ValueError("joints must be element/endplate ID pairs")
        for pair in pairs:
            for name in pair:
                _validate_id(name)
        if len(set(pairs)) != len(pairs):
            raise ValueError("duplicate joint declaration")
        object.__setattr__(self, "joints", pairs)


def _nonnegative(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def _value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, Mapping) else getattr(obj, key, default)


def _box(box, dimension, *, provenance=False):
    if box is None:
        return None
    if isinstance(box, Mapping) and set(box) - {"lower", "upper", "rule_source"}:
        raise ValueError("unknown box fields")
    lower, upper = _value(box, "lower"), _value(box, "upper")
    if lower is None or upper is None:
        return None
    if np.iscomplexobj(lower) or np.iscomplexobj(upper):
        raise ValueError("box coordinates cannot be complex")
    lower, upper = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
    if dimension == 2 and lower.shape == upper.shape == (3,):
        lower, upper = lower[[0, 2]], upper[[0, 2]]
    if lower.shape != (dimension,) or upper.shape != (dimension,) or not np.isfinite([lower, upper]).all() or np.any(upper <= lower):
        raise ValueError("box must declare finite ordered lower/upper coordinates")
    if provenance and (not isinstance(_value(box, "rule_source"), str) or not _value(box, "rule_source").strip()):
        return None
    return lower, upper


def _opening_defect(body, step, radius):
    if not body.any():
        return None
    eroded = ndimage.distance_transform_edt(body, sampling=step) > radius
    if not eroded.any():
        return math.inf
    opened = ndimage.distance_transform_edt(~eroded, sampling=step) <= radius
    removed = body & ~opened
    return float(ndimage.distance_transform_edt(~opened, sampling=step)[removed].max()) if removed.any() else 0.0


def _defect_status(value, h, *, void=False):
    if value is None:
        return "pass" if void else "unmeasured"
    if value <= h + LENGTH_TOLERANCE_M:
        return "pass"
    return "unmeasured" if value <= 1.25 * h + LENGTH_TOLERANCE_M else "fail"


def opening_defect_gate(phi: np.ndarray, h: float) -> dict:
    """R3 on node-aligned h/4 trilinear (bilinear in 2D) negative occupancy.

    Crop: solid-node AABB + three original cells, clipped to input bounds.
    Erosion is strictly EDT > .75h, opening EDT <= .75h. Defect <= h passes,
    <=1.25h is unmeasured, larger fails; empty solid is unmeasured, absent
    void passes. The 3D calculation is numerically identical to the research
    script's ``r3``; no script is imported by production code. A resource cap
    returns unmeasured rather than silently reducing refinement.
    """
    h = _nonnegative(h, "h")
    if np.iscomplexobj(phi):
        raise ValueError("R3 phi cannot be complex")
    phi = np.asarray(phi, dtype=float)
    if h == 0 or phi.ndim not in (2, 3) or min(phi.shape) < 1 or not np.isfinite(phi).all():
        raise ValueError("R3 requires finite 2D/3D phi and positive h")
    thresholds = {"rule": "R3_trilinear_opening_defect", "refinement": 4, "radius_m": 0.75 * h,
                  "crop_padding_cells": 3, "pass_defect_m": h, "unmeasured_defect_m": 1.25 * h,
                  "erosion": "strict_EDT_greater_than_radius"}
    solid = phi < 0
    if not solid.any():
        return _gate(unmeasured=["empty_solid"], measured={"solid_defect_m": None, "void_defect_m": None,
                     "solid_status": "unmeasured", "void_status": "pass"}, thresholds=thresholds)
    idx = np.argwhere(solid)
    crop = tuple(slice(max(int(a) - 3, 0), min(int(b) + 4, n)) for a, b, n in zip(idx.min(0), idx.max(0), phi.shape))
    phi = phi[crop]
    refined_shape = tuple((n - 1) * 4 + 1 for n in phi.shape)
    node_count = math.prod(refined_shape)
    if node_count > _MAX_REFINED_NODES:
        return _gate(unmeasured=["R3_refinement_resource_limit"], measured={"refined_shape": list(refined_shape),
                     "node_count": node_count, "max_nodes": _MAX_REFINED_NODES}, thresholds=thresholds)
    coordinates = np.meshgrid(*[np.arange(n, dtype=float) / 4 for n in refined_shape], indexing="ij")
    body = ndimage.map_coordinates(phi, coordinates, order=1) < 0
    defects = [_opening_defect(mask, h / 4, 0.75 * h) for mask in (body, ~body)]
    statuses = [_defect_status(defects[0], h), _defect_status(defects[1], h, void=True)]
    boundary = any(np.any(np.take(solid, edge, axis=axis))
                   for axis in range(phi.ndim) for edge in (0, -1))
    # solid is still the uncropped input: clipping can hide a cavity or a fin.
    unresolved = [f"{name}_opening_defect_unresolved" for name, status in zip(("solid", "void"), statuses) if status == "unmeasured"]
    if boundary:
        unresolved.append("finite_solid_touches_array_boundary")
    return _gate(
        fail=[f"{name}_opening_defect" for name, status in zip(("solid", "void"), statuses) if status == "fail"],
        unmeasured=unresolved,
        measured={"solid_defect_m": defects[0], "void_defect_m": defects[1], "solid_status": statuses[0], "void_status": statuses[1],
                  "refined_shape": list(refined_shape)}, thresholds=thresholds,
    )


def _normal_width(body, dimension, policy):
    if isinstance(body, PlateElement):
        # f'(u) on sc=2u/chord in [-1,1], zero beyond the clamped caps.
        candidates = [-1., 1.]
        if body.reflex:
            stationary = -body.camber / (3 * body.reflex)
            if -1 < stationary < 1:
                candidates.append(stationary)
        slope = max(abs((4 * body.camber * s + 2 * body.reflex * (3*s*s - 0.6)) / body.chord) for s in candidates)
        width = body.thickness / math.sqrt(1 + slope*slope)
        if dimension == 3:
            width = min(width, body.span)
        return width, "conservative_sheet_separation_from_max_camber_reflex_slope"
    if isinstance(body, EndplatePlate):
        return min(body.height, body.chord, *([body.thickness] if dimension == 3 else [])), "rectangular_plate_minimum_dimension"
    if isinstance(body, BoxBody):
        radii = np.asarray(body.radii) if dimension == 3 else np.asarray(body.radii)[[0, 2]]
        return 2 * float(radii.min()), "conservative_superellipsoid_insphere_diameter"
    if hasattr(body, "parts"):
        widths = [_normal_width(part, dimension, policy)[0] for part in body.parts]
        return min(widths), "minimum_child_width_of_explicit_aggregate"
    if isinstance(body, MeshBody) and body.id in policy.minimum_widths_m:
        return float(policy.minimum_widths_m[body.id]), f"external_declared_lower_bound:{policy.width_source}"
    return None, "no_qualified_width_lower_bound"


def _parameter_floor(plate, minimum, policy):
    # The section width is t/sqrt(1+max(f')**2), linear in the thickness
    # parameter. Span is an independent constraint that changing t cannot fix.
    width, _ = _normal_width(plate, 2, policy)
    return minimum * (plate.thickness / width)


def thickness_parameter_floors(scene, *, h, dimension=3, policy: SceneGatePolicy):
    """Per-ID plate thickness-parameter floors, shared with knock-out history.

    The floor is derived from the gate's conservative normal section width,
    not from the raw t parameter alone. Merged children retain their own IDs
    and floors. In 3D a too-short fixed span remains a separate gate failure;
    increasing thickness cannot remedy it. 4h is a development default only.
    """
    h = _nonnegative(h, "h")
    if h == 0 or type(dimension) is not int or dimension not in (2, 3) or not isinstance(policy, SceneGatePolicy):
        raise ValueError("positive h, dimension 2/3 and SceneGatePolicy are required")
    minimum = 4*h if policy.minimum_thickness_m is None else policy.minimum_thickness_m
    return {part.id: _parameter_floor(part, minimum, policy)
            for body in scene.components
            for part in (body.parts if isinstance(body, MergedElement) else (body,))
            if isinstance(part, PlateElement)}


def _thickness_gate(bodies, dimension, h, policy):
    minimum = 4*h if policy.minimum_thickness_m is None else policy.minimum_thickness_m
    fail, unmeasured, components = [], [], {}
    for body in bodies:
        width, method = _normal_width(body, dimension, policy)
        components[body.id] = {"lower_bound_m": width, "method": method}
        if isinstance(body, PlateElement):
            components[body.id]["parameter_floor_m"] = _parameter_floor(body, minimum, policy)
        elif isinstance(body, MergedElement):
            components[body.id]["parameter_floors_m"] = {
                part.id: _parameter_floor(part, minimum, policy) for part in body.parts}
        if width is None:
            unmeasured.append(f"component_width_unmeasured|{body.id}")
        elif width < minimum - LENGTH_TOLERANCE_M:
            fail.append(f"minimum_thickness_violation|{body.id}")
    return _gate(fail=fail, unmeasured=unmeasured, measured={"components": components,
                 "scope": "conservative interior sheet/insphere bound plus independent sampled R3; not every boundary chord"},
                 thresholds={"minimum_thickness_m": minimum, "source": _DEFAULT_SOURCE if policy.minimum_thickness_m is None else "caller_supplied"})


def _topology_gates(fields, dimension, policy):
    union = np.minimum.reduce(fields)
    solid = union < 0
    solid_structure = ndimage.generate_binary_structure(dimension, dimension)
    labels, count = ndimage.label(solid, solid_structure)
    fail, unmeasured = [], []
    if not solid.any():
        fail.append("empty_finite_solid")
    clipped = any(np.any(np.take(solid, edge, axis=axis)) for axis in range(dimension) for edge in (0, -1))
    if clipped:
        unmeasured.append("finite_solid_touches_array_boundary")
    if policy.required_components is None:
        unmeasured.append("required_components_missing")
    elif count != policy.required_components:
        fail.append("solid_component_count_mismatch")
    connectivity = _gate(fail=fail, unmeasured=unmeasured, measured={"solid_components": int(count)},
                         thresholds={"required_components": policy.required_components, "solid_connectivity": 8 if dimension == 2 else 26,
                                     "scope": "finite_union_excluding_ground_node_phi_negative"})
    filled = ndimage.binary_fill_holes(solid, structure=ndimage.generate_binary_structure(dimension, 1))
    cavities = filled & ~solid
    cavity_count = ndimage.label(cavities, ndimage.generate_binary_structure(dimension, 1))[1]
    cavity_gate = _gate(fail=["closed_void_cavity"] if cavities.any() else (),
                        unmeasured=["finite_solid_touches_array_boundary"] if clipped else (),
                        measured={"enclosed_void_nodes": int(cavities.sum()), "enclosed_void_components": int(cavity_count)},
                        thresholds={"void_connectivity": 4 if dimension == 2 else 6})
    return connectivity, cavity_gate, labels


def _masks_gate(solid, labels, state, policy, dimension):
    fail, unmeasured, roots = [], [], {}
    def checked(mask, name):
        if mask is None:
            unmeasured.append(f"mask_missing|{name}")
            return None
        if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != state.shape:
            unmeasured.append(f"mask_shape_or_dtype_invalid|{name}")
            return None
        return mask[:, 0, :] if dimension == 2 else mask
    if policy.forbidden_mask is not None or policy.require_forbidden_mask:
        forbidden = checked(policy.forbidden_mask, "forbidden")
        if forbidden is not None and np.any(forbidden & solid):
            fail.append("material_in_forbidden_mask")
    owner_union = np.zeros(solid.shape, dtype=bool)
    for name, mask in policy.root_masks.items():
        root = checked(mask, f"root|{name}")
        if root is None:
            continue
        roots[name] = int(root.sum())
        if not root.any():
            fail.append(f"required_root_mask_empty|{name}")
        if np.any(root & ~solid):
            fail.append(f"required_root_not_material|{name}")
        owner_union |= root
    if policy.root_masks and not unmeasured:
        for label in range(1, int(labels.max()) + 1):
            if not np.any((labels == label) & owner_union):
                fail.append(f"solid_component_unrooted|{label}")
    return _gate(fail=fail, unmeasured=unmeasured, measured={"root_node_counts": roots, "scope": "movable_components_only"})


def _pair_gate(scene, fields, h, dimension, policy):
    minimum = 4*h if policy.minimum_gap_m is None else policy.minimum_gap_m
    # Covers the documented plate tip mesh (including its edge strip). This is
    # sampled software geometry, not a certified continuous mesh clearance.
    guard = (1 + math.sqrt(2) if dimension == 3 else 1) * h / 4
    bodies = {b.id: b for b in scene.bodies}
    movable = {b.id for b in scene.components}
    endplates = {b.id for b in scene.bodies if isinstance(b, EndplatePlate)}
    elements = {b.id for b in scene.components if isinstance(b, (PlateElement, MergedElement))}
    declared = set(policy.joints)
    required = set(itertools.product(elements, endplates))
    joint_fail = [f"joint_declaration_missing|{a}|{b}" for a, b in sorted(required - declared)]
    contacts, gaps, gap_fail, gap_unmeasured = {}, {}, [], []
    valid = set()
    surfaces = {}
    def distance(a, b):
        for body in (a, b):
            if body.id not in surfaces:
                points = np.asarray(body.boundary_points(h / 4, dimension), dtype=float)
                if points.ndim != 2 or points.shape[1] != dimension or not len(points) or not np.isfinite(points).all():
                    raise ValueError(f"invalid boundary samples for {body.id}")
                surfaces[body.id] = points
        values = np.r_[b.phi(surfaces[a.id]), a.phi(surfaces[b.id])]
        if not np.isfinite(values).all():
            raise ValueError("nonfinite inter-body field")
        return float(values.min())
    for a, b in sorted(declared):
        if a not in elements or b not in endplates:
            joint_fail.append(f"joint_ids_or_types_invalid|{a}|{b}")
            continue
        d = distance(bodies[a], bodies[b])
        overlap = np.any((fields[a] < 0) & (fields[b] < 0))
        contact = d <= LENGTH_TOLERANCE_M or overlap
        contacts[f"{a}|{b}"] = {"minimum_sampled_field_m": d, "node_overlap": bool(overlap)}
        if contact:
            valid.add(frozenset((a, b)))
        else:
            joint_fail.append(f"joint_contact_missing|{a}|{b}")
    for a, b in itertools.combinations(scene.bodies, 2):
        if not ({a.id, b.id} & movable) or frozenset((a.id, b.id)) in valid:
            continue
        alo, ahi = a.bbox(dimension)
        blo, bhi = b.bbox(dimension)
        lower = float(np.linalg.norm(np.maximum(np.maximum(np.asarray(alo) - bhi, np.asarray(blo) - ahi), 0)))
        key = f"{a.id}|{b.id}"
        if lower >= minimum - LENGTH_TOLERANCE_M and lower > 0:
            gaps[key] = {"bbox_lower_bound_m": lower, "method": "conservative_AABB_separation"}
            continue
        d = distance(a, b)
        def distance_error(body):
            if isinstance(body, PlateElement):
                return .02 * body.thickness if body.camber or body.reflex else 0.
            if hasattr(body, "parts"):
                return max(distance_error(p) for p in body.parts)
            return 0.
        extra = distance_error(a) + distance_error(b)
        pair_guard = guard + extra
        gaps[key] = {"minimum_sampled_field_m": d, "guard_m": pair_guard, "bbox_lower_bound_m": lower,
                     "method": "boundary_field_samples_with_guard"}
        if d < -LENGTH_TOLERANCE_M or np.any((fields[a.id] < 0) & (fields[b.id] < 0)):
            gap_fail.append(f"component_overlap|{a.id}|{b.id}")
        elif any(isinstance(body, BoxBody) and not (body.exponent == 2 and len(set(body.radii)) == 1) for body in (a, b)):
            # A normalized implicit BoxBody field need not overestimate the
            # distance. Its sign proves overlap, but d < g_min proves no gap
            # violation; neither field values nor angular coverage qualify it.
            gap_unmeasured.append(f"gap_field_or_surface_coverage_unqualified|{a.id}|{b.id}")
        elif d < minimum - LENGTH_TOLERANCE_M:
            # A minimum over boundary samples is an upper bound on the true
            # gap: d < g_min already proves a violation. The sampling guard
            # applies only above the threshold, where admission is uncertain.
            gap_fail.append(f"minimum_gap_violation|{a.id}|{b.id}")
        elif d < minimum + pair_guard - LENGTH_TOLERANCE_M:
            gap_unmeasured.append(f"gap_within_sampling_guard|{a.id}|{b.id}")
    gap = _gate(fail=gap_fail, unmeasured=gap_unmeasured, measured={"pairs": gaps, "scope": "sampled software geometry; no continuum/BDIM qualification"},
                thresholds={"minimum_gap_m": minimum, "sampling_guard_m": guard,
                            "source": _DEFAULT_SOURCE if policy.minimum_gap_m is None else "caller_supplied"})
    joints = _gate(fail=joint_fail, measured={"contacts": contacts}, thresholds={"required_pairs": [list(p) for p in sorted(required)],
                    "contact": "negative boundary sample, exact zero, or solid node overlap; no positive-gap tolerance"})
    return gap, joints


def _bounds_gates(scene, dimension, policy):
    boxes = [body.bbox(dimension) for body in scene.components]
    lower, upper = np.min([b[0] for b in boxes], axis=0), np.max([b[1] for b in boxes], axis=0)
    box = _box(policy.envelope, dimension, provenance=True)
    if box is None:
        envelope = _gate(unmeasured=["rules_envelope_or_provenance_missing"])
    else:
        outside = np.any(lower < box[0] - LENGTH_TOLERANCE_M) or np.any(upper > box[1] + LENGTH_TOLERANCE_M)
        envelope = _gate(fail=["outside_rules_envelope"] if outside else (),
                         measured={"body_lower_m": lower.tolist(), "body_upper_m": upper.tolist()},
                         thresholds={"lower_m": box[0].tolist(), "upper_m": box[1].tolist(), "rule_source": _value(policy.envelope, "rule_source"),
                                     "scope": "movable_components_conservative_primitive_bounding_boxes"})
    measurements = {}
    if scene.ground is not None:
        measurements["ground_m"] = float(lower[-1] - scene.ground)
    domain = _box(policy.domain, dimension)
    if domain is not None:
        measurements["domain_m"] = float(min(np.min(lower - domain[0]), np.min(domain[1] - upper)))
    unmeasured = []
    if policy.clearance_m is None:
        unmeasured.append("clearance_threshold_missing")
    if not measurements:
        unmeasured.append("clearance_target_missing")
    if policy.domain is not None and domain is None:
        unmeasured.append("domain_bounds_missing")
    fail = [f"minimum_clearance_violation|{name}" for name, v in measurements.items()
            if policy.clearance_m is not None and v < policy.clearance_m - LENGTH_TOLERANCE_M]
    clearance = _gate(fail=fail, unmeasured=unmeasured, measured=measurements,
                      thresholds={"minimum_clearance_m": policy.clearance_m, "scope": "movable_components_to_ground/declared_domain; independent_of_rules_envelope"})
    return envelope, clearance


def _report(scene, gates, h, dimension, state=None):
    rejections = [{"gate": name, "reason": reason, "status": status}
                  for name, gate in gates.items() for status, key in (("fail", "fail_reasons"), ("unmeasured", "unmeasured_reasons"))
                  for reason in gate[key]]
    return {"passed": all(g["status"] == "pass" for g in gates.values()), "gates": gates, "rejection_reasons": rejections,
            "cfd_evaluations": 0, "budget_charged": 0, "scene_sha256": scene.scene_sha256,
            "state_sha256": None if state is None else state.state_sha256, "dimension": dimension, "h_m": h,
            "distance_contract_exemptions": [body.id for body in scene.bodies if isinstance(body, MergedElement)],
            "evidence_class": "solver_free_scene_software_unqualified"}


def evaluate_scene_gates(scene, *, h, dimension=3, policy: SceneGatePolicy, phase=(0, 0, 0), state: SDFDesignState | None = None) -> dict:
    """Inspect all scene checks and enumerate every rejection; charge zero CFD.

    Optional state must belong to this scene and grid; passing another field
    under the scene's hash is rejected. 2D state storage is (nx,1,nz), never a
    fictitious volume. Missing policy measurements block overall admission.
    Exceeding the 2,000,000-node design sampling cap is recorded unmeasured;
    malformed inputs still raise. Explicit MergedElement IDs are listed as
    band-distance-contract exemptions, not qualified BDIM geometry.
    """
    h = _nonnegative(h, "h")
    if h == 0 or type(dimension) is not int or dimension not in (2, 3) or not isinstance(policy, SceneGatePolicy):
        raise ValueError("positive h, dimension 2/3 and SceneGatePolicy are required")
    if np.iscomplexobj(phase):
        raise ValueError("phase cannot be complex")
    phase = np.asarray(phase, dtype=float)
    if phase.shape != (3,) or not np.isfinite(phase).all() or np.any((phase < 0) | (phase >= 1)) or (dimension == 2 and phase[1] != 0):
        raise ValueError("phase must contain x,y,z fractions in [0,1); y=0 in 2D")
    if not scene.bodies:
        return _report(scene, {"connectivity": _gate(fail=["empty_finite_scene"])}, h, dimension)
    if not scene.components:
        return _report(scene, {"connectivity": _gate(fail=["no_movable_components"])}, h, dimension)
    if state is None:
        try:
            state = scene.sample(h, dimension=dimension, phase=phase)
        except SceneSamplingLimit as limit:
            sampling = _gate(unmeasured=["scene_sampling_resource_limit"], measured={
                "shape": list(limit.shape), "node_count": limit.node_count, "max_nodes": limit.max_nodes})
            return _report(scene, {"sampling": sampling}, h, dimension)
    if not isinstance(state, SDFDesignState) or state.source_sha256 != scene.scene_sha256 or state.spacing_m != h:
        raise ValueError("state does not belong to scene/grid")
    if state.recompute_sha256() != state.state_sha256:
        raise ValueError("state content no longer matches its hash")
    if (dimension == 2 and state.shape[1] != 1) or (dimension == 3 and min(state.shape) < 2):
        raise ValueError("state dimension does not match requested dimension")
    points = scene.grid_points(state)
    if dimension == 2:
        points = points[..., [0, 2]]
    expected = scene.phi(points)
    if not np.array_equal(state.phi, expected.astype(np.float32)):
        raise ValueError("state field does not match scene")
    fields = {body.id: body.phi(points) for body in scene.bodies}
    if dimension == 2:
        fields = {name: phi[:, 0, :] for name, phi in fields.items()}
    if not all(np.isfinite(phi).all() for phi in fields.values()):
        raise ValueError("scene body field must be finite")
    finite_phi = np.minimum.reduce(list(fields.values()))
    connectivity, cavities, _ = _topology_gates(list(fields.values()), dimension, policy)
    for body in scene.bodies:
        count = ndimage.label(fields[body.id] < 0, ndimage.generate_binary_structure(dimension, dimension))[1]
        if count != 1:
            connectivity["fail_reasons"].append(f"component_absent_or_disconnected|{body.id}")
            connectivity["status"] = "fail"
    movable_solid = np.minimum.reduce([fields[body.id] for body in scene.components]) < 0
    movable_labels = ndimage.label(movable_solid, ndimage.generate_binary_structure(dimension, dimension))[0]
    gap, joints = _pair_gate(scene, fields, h, dimension, policy)
    envelope, clearance = _bounds_gates(scene, dimension, policy)
    gates = {"thickness": _thickness_gate(scene.bodies, dimension, h, policy), "gap": gap,
             "opening_defect": opening_defect_gate(finite_phi, h), "connectivity": connectivity,
             "closed_cavities": cavities, "endplate_joints": joints, "envelope": envelope, "clearance": clearance,
             "masks_roots": _masks_gate(movable_solid, movable_labels, state, policy, dimension)}
    return _report(scene, gates, h, dimension, state)
