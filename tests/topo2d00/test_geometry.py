"""TOPO-2D-00 geometry contracts; source identity has separate transcription tests."""
import json

import numpy as np
import pytest

from cfd_gen.topo2d.geometry import (
    GeometryError,
    _controlled_minimum,
    _closed_from_surfaces,
    _normal_ray_minimum,
    build_scene,
    polygon_gap,
    polygon_sdf,
    save_npz,
    scene_sdf,
    thicken_element,
    validate_scene,
    write_scene,
)


DX = 223.4 / 120


@pytest.mark.parametrize("configuration", ["E1", "E2", "E3", "E2_sharp", "E3_sharp"])
def test_spline_density_and_arclength_cap_are_registered(configuration):
    scene = build_scene(configuration, height_mm=100, dx_mm=DX)
    assert scene["sampling"]["method"] == "natural-cubic-spline-arclength"
    assert all(s["spline_max_arc_mm"] <= 1 for s in scene["sources"])
    for element in scene["elements"]:
        polygon = np.asarray(element["polygon_mm"])
        # TE closure is an intentional finite-width cap, densified like surfaces.
        assert np.linalg.norm(np.diff(polygon, axis=0), axis=1).max() <= 1 + 1e-9
        assert element["sampling"]["max_noncap_turn_deg"] <= 5 + 1e-9
        for surface in ("suction_mm", "pressure_mm"):
            curve = np.asarray(element[surface])
            edges = np.diff(curve, axis=0)
            lengths = np.linalg.norm(edges, axis=1)
            arc = np.r_[0, np.cumsum(lengths)]
            cosine = (edges[:-1] * edges[1:]).sum(axis=1) / (lengths[:-1] * lengths[1:])
            turns = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
            assert max(turns[arc[1:-1] > .02 * element["nominal_chord_mm"]]) <= 5 + 1e-9
        if not configuration.endswith("_sharp"):
            assert element["thickening"]["preserved_cap_arc_mm"] == pytest.approx(
                .02 * element["nominal_chord_mm"])


@pytest.mark.parametrize("configuration,count", [("E1", 1), ("E2", 2), ("E3", 3)])
def test_series_has_closed_disjoint_polygons_and_prescribed_height(configuration, count):
    scene = build_scene(configuration, height_mm=100, dx_mm=DX)
    assert scene["schema"] == "topo2d-scene-v1"
    assert len(scene["elements"]) == count
    assert scene["gates"]["accepted"]
    assert scene["gates"]["clearance_mm"] >= 4 * DX
    assert scene["normalizations"]["h_over_c1"] == 100 / 223.4
    assert scene["normalizations"]["h_over_c"] == 100 / 380
    for element in scene["elements"]:
        polygon = np.asarray(element["polygon_mm"])
        np.testing.assert_array_equal(polygon[0], polygon[-1])
    assert min(np.asarray(scene["elements"][0]["polygon_mm"])[:, 1]) == pytest.approx(100)
    for gap in scene["gates"]["pair_gaps_mm"]:
        assert gap["distance_mm"] >= 4 * DX - 1e-9
    for element in scene["gates"]["controlled_minima"]:
        assert element["thickness_mm"] >= 4 * DX - 1e-9
    for element in scene["elements"]:
        assert element["bulk_core_probe_stations_mm"]
        probes = np.asarray(element["bulk_core_probe_stations_mm"])
        assert np.max(polygon_sdf(probes, element["polygon_mm"])) <= -(1 + np.sqrt(2) / 2) * DX + 1e-9


def test_main_is_identical_and_e2_signed_placement_is_exact_after_thickening():
    scenes = [build_scene(c, height_mm=100, dx_mm=DX) for c in ("E1", "E2", "E3")]
    for scene in scenes[1:]:
        assert scene["elements"][0] == scenes[0]["elements"][0]
    main, flap = scenes[1]["elements"]
    te = np.asarray(main["trailing_edge_midpoint_mm"])
    le = np.asarray(flap["leading_edge_mm"])
    assert te[0] - le[0] == pytest.approx(9, abs=1e-10)
    assert min(np.asarray(flap["suction_mm"])[:, 1]) - te[1] == pytest.approx(12, abs=1e-10)


def test_e3_equal_source_half_chords_and_deflection_steps():
    scene = build_scene("E3", height_mm=100, dx_mm=DX)
    angles = [e["chord_angle_rad"] for e in scene["elements"]]
    assert angles[1] - angles[0] == pytest.approx(angles[2] - angles[1])
    assert scene["elements"][1]["source_chord_mm"] == scene["elements"][2]["source_chord_mm"]
    assert scene["elements"][1]["nominal_chord_mm"] == 82.85


def test_normal_thickening_preserves_cap_camber_and_te_midpoint():
    x = np.arange(7.0)
    suction = np.column_stack((x, [0, -0.3, -0.7, -1, -0.8, -0.3, -0.1]))
    pressure = np.column_stack((x, [0, 0.3, 0.7, 1, 0.8, 0.3, 0.1]))
    lower, upper, metadata = thicken_element(suction, pressure, t_min_mm=3)
    np.testing.assert_array_equal(lower[0], suction[0])
    np.testing.assert_array_equal(upper[0], pressure[0])
    np.testing.assert_allclose((lower + upper) / 2, (suction + pressure) / 2, atol=1e-15)
    assert metadata["controlled_min_thickness_mm"] >= 3 - 1e-12
    assert metadata["max_thickness_ratio"] == pytest.approx(15)
    assert metadata["preserved_cap_pairs"] == 1
    assert metadata["preserved_cap_arc_mm"] == pytest.approx(.12)


def test_thickening_is_independent_of_station_numbers_on_the_same_linear_surfaces():
    x = np.arange(7.0)
    thickness = np.array([0, .6, 1.4, 2, 1.6, .6, .2])
    s = np.column_stack((x, -thickness / 2))
    p = np.column_stack((x, thickness / 2))
    lower, upper, meta = thicken_element(s, p, t_min_mm=3)
    refined_x = np.unique(np.r_[x, np.linspace(0, .1, 20)])
    refined = np.interp(refined_x, x, thickness)
    lo, hi, dense_meta = thicken_element(np.column_stack((refined_x, -refined / 2)),
                                        np.column_stack((refined_x, refined / 2)), t_min_mm=3)
    indices = np.searchsorted(refined_x, x)
    np.testing.assert_allclose(lo[indices], lower, atol=1e-12)
    np.testing.assert_allclose(hi[indices], upper, atol=1e-12)
    assert dense_meta["preserved_cap_pairs"] > meta["preserved_cap_pairs"]


def test_sharp_named_original_retains_finite_te_and_discloses_exception():
    scene = build_scene("E2_sharp", height_mm=100, dx_mm=DX)
    assert not scene["gates"]["thickness_required"]
    assert scene["sharp_variant"]["mathematically_sharp"] is False
    assert np.linalg.norm(np.array(scene["elements"][0]["suction_mm"])[-1]
                          - np.array(scene["elements"][0]["pressure_mm"])[-1]) > 1
    assert all(s["verification"] == "UNVERIFIED_OCR" for s in scene["sources"])


def test_gate_rejects_too_small_height_or_gap_and_bad_inputs():
    with pytest.raises(GeometryError, match="clearance"):
        build_scene("E1", height_mm=1, dx_mm=DX)
    with pytest.raises(GeometryError, match="gap|overlap"):
        build_scene("E2", height_mm=100, dx_mm=DX, gap_mm=0)
    with pytest.raises(GeometryError):
        build_scene("E4", height_mm=100, dx_mm=DX)
    with pytest.raises(GeometryError):
        build_scene("E1", height_mm=100, dx_mm=float("nan"))


def test_gate_rejects_self_intersection_nonclosure_and_thin_controlled_region():
    scene = build_scene("E1", height_mm=100, dx_mm=DX)
    bad = json.loads(json.dumps(scene))
    bad["elements"][0]["polygon_mm"] = [[0, 100], [2, 102], [0, 102], [2, 100], [0, 100]]
    with pytest.raises(GeometryError, match="self.intersection"):
        validate_scene(bad)
    bad = json.loads(json.dumps(scene))
    bad["elements"][0]["polygon_mm"][-1][0] += 1
    with pytest.raises(GeometryError, match="closed"):
        validate_scene(bad)
    bad = json.loads(json.dumps(scene))
    bad["t_min_mm"] = 100
    with pytest.raises(GeometryError, match="thickness"):
        validate_scene(bad)


def test_sdf_exact_distances_winding_and_gradient_away_from_medial_axis():
    square = np.array([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]], float)
    points = np.array([[1, 1], [3, 1], [3, 3], [2, 1]])
    np.testing.assert_allclose(polygon_sdf(points, square), [-1, 1, np.sqrt(2), 0])
    np.testing.assert_allclose(polygon_sdf(points, square[::-1]), [-1, 1, np.sqrt(2), 0])
    points = np.array([[3, 0.7], [0.8, -1], [3, 3], [0.4, 0.8]])
    eps = 1e-5
    gradient = np.column_stack([(polygon_sdf(points + np.eye(2)[j] * eps, square)
                                 - polygon_sdf(points - np.eye(2)[j] * eps, square)) / (2 * eps)
                                for j in range(2)])
    np.testing.assert_allclose(np.linalg.norm(gradient, axis=1), 1, atol=1e-8)


def test_euclidean_gap_detects_diagonal_distance_containment_and_touch():
    a = np.array([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]], float)
    assert polygon_gap(a, a + 3) == pytest.approx(np.sqrt(2))
    assert polygon_gap(a, a * 0.2 + 0.5) == 0
    assert polygon_gap(a, a + [2, 0]) == 0


def test_tangential_reconstruction_closes_the_normal_ray_at_finite_te():
    camber = np.column_stack((np.arange(7.0), np.zeros(7)))
    differences = np.column_stack(([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                                   [0, 0.6, 1.4, 2, 1.6, 0.6, 0.2]))
    suction, pressure = camber - differences / 2, camber + differences / 2
    lower, upper, metadata = thicken_element(suction, pressure, t_min_mm=3)
    assert metadata["controlled_min_thickness_mm"] >= 3 - 1e-9
    assert metadata["max_tangential_reconstruction_mm"] == pytest.approx(0.3)
    assert lower[-1, 0] == upper[-1, 0] == 6
    assert upper[-1, 1] - lower[-1, 1] >= 3
    np.testing.assert_allclose((lower + upper) / 2, camber, atol=1e-15)


def test_ray_gate_rejects_oblique_cap_even_when_paired_projection_stays_wide():
    scene = build_scene("E1", height_mm=100, dx_mm=DX)
    element = scene["elements"][0]
    lower, upper = np.array(element["suction_mm"]), np.array(element["pressure_mm"])
    camber = (lower + upper) / 2
    tangent = camber[-1] - camber[-2]
    tangent /= np.linalg.norm(tangent)
    # Equal/opposite tangential moves preserve the TE midpoint and every paired
    # normal projection, but tilt the cap across its nominal normal ray.
    lower[-1] += 0.5 * tangent
    upper[-1] -= 0.5 * tangent
    element["suction_mm"], element["pressure_mm"] = lower.tolist(), upper.tolist()
    element["polygon_mm"] = _closed_from_surfaces(lower, upper).tolist()
    with pytest.raises(GeometryError, match="normal ray|normal width|outside"):
        _controlled_minimum(lower, upper, element["thickening"]["controlled_from_index"])
    with pytest.raises(GeometryError, match="camber-normal|normal ray|normal width|outside"):
        validate_scene(scene)


def test_gate_derives_thickness_scope_from_source_not_advertised_metadata():
    scene = build_scene("E1", height_mm=100, dx_mm=DX)
    element = scene["elements"][0]
    lower, upper = np.array(element["suction_mm"]), np.array(element["pressure_mm"])
    camber = (lower + upper) / 2
    station = element["thickening"]["controlled_from_index"] + 5
    vector = upper[station] - lower[station]
    vector /= np.linalg.norm(vector)
    lower[station], upper[station] = camber[station] - vector / 2, camber[station] + vector / 2
    element["suction_mm"], element["pressure_mm"] = lower.tolist(), upper.tolist()
    element["polygon_mm"] = _closed_from_surfaces(lower, upper).tolist()
    element["thickening"]["controlled_from_index"] = station + 1
    candidates = np.arange(station + 1, len(camber))
    keep = polygon_sdf(camber[candidates], element["polygon_mm"]) <= -(1 + np.sqrt(2) / 2) * DX + 1e-9
    element["bulk_core_probe_station_indices"] = candidates[keep].tolist()
    element["bulk_core_probe_stations_mm"] = camber[candidates[keep]].tolist()
    with pytest.raises(GeometryError, match="scope|controlled|source"):
        validate_scene(scene)


@pytest.mark.parametrize("flag", [True, "false", 1])
def test_gate_derives_sharp_arm_from_configuration_not_flag(flag):
    scene = build_scene("E1", height_mm=100, dx_mm=DX)
    scene["sharp_variant"]["enabled"] = flag
    with pytest.raises(GeometryError, match="sharp"):
        validate_scene(scene)


def test_gate_rejects_source_provenance_or_preserved_camber_forgery():
    scene = build_scene("E1", height_mm=100, dx_mm=DX)
    scene["sources"][0]["sha256"] = "0" * 64
    with pytest.raises(GeometryError, match="source"):
        validate_scene(scene)
    scene = build_scene("E1", height_mm=100, dx_mm=DX)
    element = scene["elements"][0]
    lower, upper = np.array(element["suction_mm"]), np.array(element["pressure_mm"])
    lower[30, 1] += 0.1
    upper[30, 1] += 0.1
    element["suction_mm"], element["pressure_mm"] = lower.tolist(), upper.tolist()
    element["polygon_mm"] = _closed_from_surfaces(lower, upper).tolist()
    with pytest.raises(GeometryError, match="camber|source"):
        validate_scene(scene)


def test_normal_ray_partition_rejects_switch_between_disconnected_inside_branches():
    # Independent review's C-shaped polygon, sheared so all vertex tangential
    # projections lie outside [0,1]. Both camber-segment endpoints are inside,
    # but its midpoint is outside: projected-vertex events alone are inadequate.
    polygon = np.array([[-1, -1], [2, -1], [2, 1], [-0.5, 1], [-0.5, 3],
                        [2, 3], [2, 5], [-1, 5], [-1, -1]], float)
    polygon[:, 1] -= 4 * polygon[:, 0]
    assert np.all(polygon_sdf([[0, 0], [1, 0]], polygon) < 0)
    assert polygon_sdf([0.5, 0], polygon) > 0
    with pytest.raises(GeometryError, match="outside"):
        _normal_ray_minimum(polygon, np.array([[0, 0], [1, 0]], float), 0)


def test_scene_union_and_json_npz_are_deterministic(tmp_path):
    scene = build_scene("E3", height_mm=100, dx_mm=DX)
    assert scene == build_scene("E3", height_mm=100, dx_mm=DX)
    points = np.array([[0, 0], [150, 100], [300, 150]], float)
    expected = np.minimum.reduce([polygon_sdf(points, e["polygon_mm"]) for e in scene["elements"]])
    np.testing.assert_array_equal(scene_sdf(points, scene), expected)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    write_scene(scene, a)
    write_scene(scene, b)
    assert a.read_bytes() == b.read_bytes()
    assert json.loads(a.read_text()) == scene
    save_npz(scene, tmp_path / "a.npz")
    save_npz(scene, tmp_path / "b.npz")
    assert (tmp_path / "a.npz").read_bytes() == (tmp_path / "b.npz").read_bytes()
    with np.load(tmp_path / "a.npz", allow_pickle=False) as arrays:
        for i, element in enumerate(scene["elements"]):
            np.testing.assert_array_equal(arrays[f"polygon_{i}_mm"], element["polygon_mm"])


def test_generated_scene_sdf_gradient_and_source_cap_preservation():
    scene = build_scene("E3", height_mm=100, dx_mm=DX)
    raw = build_scene("E3_sharp", height_mm=100, dx_mm=DX)
    for thick, original in zip(scene["elements"], raw["elements"]):
        for surface in ("suction_mm", "pressure_mm"):
            a, b = np.array(thick[surface]), np.array(original[surface])
            arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(b, axis=0), axis=1))]
            cap = arc <= .02 * original["nominal_chord_mm"]
            np.testing.assert_allclose(a[cap] - a[0], b[cap] - b[0], atol=1e-13)
    points = np.array([[-30, 100], [120, 70], [120, 150], [300, 150], [400, 100]], float)
    eps = 1e-4
    gradient = np.column_stack([(scene_sdf(points + np.eye(2)[j] * eps, scene)
                                 - scene_sdf(points - np.eye(2)[j] * eps, scene)) / (2 * eps)
                                for j in range(2)])
    np.testing.assert_allclose(np.linalg.norm(gradient, axis=1), 1, atol=1e-7)
