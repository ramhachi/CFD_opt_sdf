"""Scene/serialization and common lattice contracts (solver-free)."""
from dataclasses import replace
import hashlib
import json

import numpy as np
import pytest
import trimesh
from scipy import ndimage

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_gen.scene.primitives import MeshBody, PlateElement
from cfd_gen.scene.scene import MergedElement, Scene


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


@pytest.mark.parametrize("bad_id", ["", "with space", "nonascii_ü", "has|separator", None])
def test_merged_ids_use_the_primitive_ascii_contract(bad_id):
    with pytest.raises(ValueError, match="ASCII identifier"):
        MergedElement(bad_id, (plate(), plate("other")))
    valid = MergedElement("Merged.1:main-other", (plate(), plate("other")))
    assert Scene.from_json(Scene((valid,)).to_json()).components[0].id == valid.id


def test_negative_zero_has_one_scene_identity_including_ground_and_merge():
    scene = Scene((MergedElement("merged", (plate(), plate("other"))),), ground=0.)
    negative = replace(scene, components=(MergedElement("merged", (
        replace(plate(), x=-0., z=-0., y=-0., angle=-0., camber=-0., reflex=-0.), plate("other"))),), ground=-0.)
    assert scene.to_json() == negative.to_json()
    assert scene.scene_sha256 == negative.scene_sha256
    assert "-0.0" not in negative.to_json()


@pytest.mark.parametrize("fixed", [False, True])
def test_mesh_scene_identity_uses_bytes_while_transport_keeps_paths(tmp_path, fixed):
    payload = trimesh.creation.box().export(file_type="stl")
    sha = hashlib.sha256(payload).hexdigest()
    scenes = []
    for name in ("host.stl", "worker.stl"):
        path = tmp_path / name
        path.write_bytes(payload)
        body = MeshBody("mesh", str(path), sha)
        scene = Scene((), (body,)) if fixed else Scene((body,))
        scenes.append(scene)
        assert Scene.from_json(scene.to_json()).bodies[0].path == str(path)
    assert scenes[0].to_json() != scenes[1].to_json()
    assert scenes[0].scene_sha256 == scenes[1].scene_sha256
    changed_path = tmp_path / "changed.stl"
    changed_path.write_bytes(trimesh.creation.box(extents=(2, 1, 1)).export(file_type="stl"))
    changed = MeshBody("mesh", str(changed_path), hashlib.sha256(changed_path.read_bytes()).hexdigest())
    assert (Scene((), (changed,)) if fixed else Scene((changed,))).scene_sha256 != scenes[0].scene_sha256


@pytest.mark.parametrize("dimension", [2, 3])
@pytest.mark.parametrize("max_nodes", [2_000_000, 10])
def test_sample_resource_limit_reports_shape_before_allocation(monkeypatch, dimension, max_nodes):
    from cfd_gen.scene.scene import SceneSamplingLimit

    def unexpected_allocation(*args, **kwargs):
        pytest.fail("over-budget sampling must stop before lattice allocation")

    monkeypatch.setattr(np, "arange", unexpected_allocation)
    monkeypatch.setattr(np, "meshgrid", unexpected_allocation)
    shape = (2001, 2001) if dimension == 2 else (201, 201, 201)
    with pytest.raises(SceneSamplingLimit) as caught:
        Scene((plate(),)).sample(1., dimension=dimension, padding_cells=0,
            bounds=(np.zeros(dimension), np.array(shape) - 1), max_nodes=max_nodes)
    assert caught.value.shape == shape
    assert caught.value.node_count == np.prod(shape)
    assert caught.value.max_nodes == max_nodes


def test_sample_large_shape_does_not_overflow_int64():
    from cfd_gen.scene.scene import SceneSamplingLimit

    with pytest.raises(SceneSamplingLimit) as caught:
        Scene((plate(),)).sample(1., dimension=2, padding_cells=0, bounds=((0., 0.), (1e20, 1e20)))
    assert caught.value.shape == (10**20 + 1, 10**20 + 1)
    assert caught.value.node_count == (10**20 + 1)**2


def test_sample_at_resource_bound_and_invalid_arguments():
    from cfd_gen.scene.scene import SceneSamplingLimit

    scene = Scene((plate(),))
    state = scene.sample(1., dimension=2, padding_cells=0, bounds=((0., 0.), (1., 1.)), max_nodes=4)
    assert state.shape == (2, 1, 2)
    for kwargs in ({"h": 0.}, {"h": 1., "max_nodes": True},
                   {"h": 1., "phase": (0., float("nan"), 0.)},
                   {"h": 1., "dimension": 2, "bounds": ((0., 0.), (0., 1.))},
                   {"h": 1e-308, "dimension": 2, "bounds": ((-1e308, -1e308), (1e308, 1e308))}):
        with pytest.raises(ValueError) as caught:
            scene.sample(**kwargs)
        assert not isinstance(caught.value, SceneSamplingLimit)


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
