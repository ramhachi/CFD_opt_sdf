"""Scene/serialization and common lattice contracts (solver-free)."""
from dataclasses import replace
import hashlib
import json

import numpy as np
import pytest
from scipy import ndimage

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.scene.primitives import PlateElement
from cfd_sdf.scene.scene import MergedElement, Scene


def plate(id="main", **kw):
    return PlateElement(id=id, x=0., z=0., chord=1., thickness=.2, span=.6, **kw)


def test_union_and_argmin_signs():
    a = plate()
    b = replace(a, id="flap", x=1.4, z=.4)
    scene = Scene((a, b), ground=-.8)
    p = np.array([[0., 0., 0.], [1.4, 0., .4], [0., 0., -1.], [0., 0., .5]])
    fields = np.stack([a.phi(p), b.phi(p), p[:, 2]+.8])
    np.testing.assert_array_equal(scene.phi(p), fields.min(axis=0))
    np.testing.assert_array_equal(scene.labels(p), fields.argmin(axis=0))
    assert (scene.phi(p)<0).tolist() == [True, True, True, False]


def test_state_roundtrip_labels_and_fixed_masks(tmp_path):
    a = plate()
    fixed = replace(a, id="fixed", x=1.5)
    scene = Scene((a,), (fixed,))
    s = scene.sample(.05, dimension=3)
    assert s.source_sha256 == scene.scene_sha256
    assert s.recompute_sha256() == s.state_sha256
    points = scene.grid_points(s)
    np.testing.assert_array_equal(s.phi, scene.phi(points).astype(np.float32))
    np.testing.assert_array_equal(s.fixed_solid_mask, fixed.phi(points)<0)
    assert not (s.design_mask & s.fixed_solid_mask).any()
    np.testing.assert_array_equal(scene.label_grid(s), scene.labels(points))
    path = s.save(tmp_path/"scene.npz")
    assert SDFDesignState.load(path) == s


def test_2d_singleton_y_has_area_not_a_fictitious_volume():
    scene = Scene((plate(),))
    s = scene.sample(.005, dimension=2, phase=(.5,0.,.5))
    assert s.shape[1] == 1
    assert s.origin_m[1] == 0
    assert scene.sampled_measure(s, dimension=2)["unit"] == "m^2"
    expected_area = 1.*.2+np.pi*.1**2
    assert scene.sampled_measure(s, dimension=2)["measure"] == pytest.approx(expected_area, rel=.01)
    with pytest.raises(ValueError, match="singleton"):
        scene.sampled_measure(s, dimension=3)


@pytest.mark.parametrize("dimension", [2,3])
def test_subcell_phases_preserve_resolved_solid_components(dimension):
    a = plate()
    b = replace(a, id="flap", x=1.5, z=.4)
    scene = Scene((a,b))
    for shift in (0., .125, .5, .875):
        state = scene.sample(.05, dimension=dimension, phase=(shift,0.,shift))
        assert ndimage.label(state.solid_mask, structure=np.ones((3,3,3)))[1] == 2
        assert state.source_sha256 == scene.scene_sha256


def test_canonical_json_stable_and_fail_closed():
    a = plate()
    scene = Scene((a,),ground=-1.)
    encoded = scene.to_json()
    assert Scene.from_json(encoded).to_json() == encoded
    assert hashlib.sha256(encoded.encode()).hexdigest() == scene.scene_sha256
    assert replace(scene, components=(replace(a, angle=.1),)).scene_sha256 != scene.scene_sha256
    altered = json.loads(encoded)
    altered["typo"] = 1
    with pytest.raises(ValueError):
        Scene.from_json(json.dumps(altered))
    altered = json.loads(encoded)
    altered["components"][0]["kind"] = "unknown"
    with pytest.raises(ValueError):
        Scene.from_json(json.dumps(altered))
    with pytest.raises(ValueError):
        Scene((a,a))
    with pytest.raises(ValueError):
        Scene((a,),ground=float("nan"))
    with pytest.raises(ValueError):
        scene.sample(.05,max_nodes=10)


def test_explicit_merged_element_roundtrip_and_union():
    a = plate()
    b = replace(a,id="other",x=.4)
    merged = MergedElement("merged:main:other", (a,b))
    scene = Scene((merged,))
    p = np.array([[0.,0.], [.4,0.], [1.,.3]])
    np.testing.assert_allclose(scene.phi(p), np.minimum(a.phi(p), b.phi(p)))
    assert Scene.from_json(scene.to_json()).scene_sha256 == scene.scene_sha256


def test_v18_two_plate_control_uses_same_section_and_extrusion():
    # WP4 polygon implementation is absent at base 08e0ea38: specified v18 fallback.
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
    from v18_plate import plate_phi
    a = plate()
    b = replace(a,id="flap",x=1.3,z=.35,angle=.2)
    scene = Scene((a,b))
    state = scene.sample(.08)
    fields = []
    for body in (a,b):
        fields.append(plate_phi(state, {"xc":body.x,"zc":body.z,"alpha":body.angle,
            "L":body.chord,"t":body.thickness,"y_tip":body.span/2,"camber":0.,"reflex":0.}))
    np.testing.assert_allclose(scene.phi(scene.grid_points(state)),np.minimum(*fields),atol=1e-14,rtol=1e-14)
