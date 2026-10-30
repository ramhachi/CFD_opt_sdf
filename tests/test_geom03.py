"""Known tiny development inputs and protocol failures; no registered fixture/seed runs."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import geom03_run as R  # noqa: E402
import geom03_check as C  # noqa: E402

H = 0.025


def masks(shape, *, slab=False):
    design = np.zeros(shape, bool)
    if slab:
        design[:, :, 1:-1] = True
    else:
        design[1:-1, 1:-1, 1:-1] = True
    return {name: design if name == "design_mask" else np.zeros(shape, bool) for name in R.MASK_NAMES}


def development_input(name):
    """Five deliberately distinct inputs, never R's registered builders or schedule."""
    if name == "cylinder":
        shape = (17, 17, 17)
        q = np.indices(shape, dtype=np.float64) - np.asarray((8.23, 7.89, 8.07)).reshape(3, 1, 1, 1)
        d, v = np.hypot(q[0], q[2]) - 2.3, np.abs(q[1]) - 3.1
        phi = np.minimum(np.maximum(d, v), 0) + np.hypot(np.maximum(d, 0), np.maximum(v, 0))
    elif name == "box":
        shape = (15, 15, 15)
        q = np.indices(shape, dtype=np.float64) - np.asarray((7.17, 7.13, 6.81)).reshape(3, 1, 1, 1)
        d = np.abs(q) - np.asarray((3.2, 2.2, 1.8)).reshape(3, 1, 1, 1)
        phi = np.sqrt(np.square(np.maximum(d, 0)).sum(axis=0)) + np.minimum(d.max(axis=0), 0)
    else:
        shape = (9, 11, 13)
        phi = np.ones(shape, np.float64)
        if name == "points":
            phi[4, 5, 6] = phi[5, 6, 7] = -0.25
        elif name == "clipped_slab":
            phi = np.broadcast_to(np.abs(np.arange(13, dtype=np.float64) - 6.21) - 0.8, shape).copy()
        elif name != "empty":
            raise ValueError(name)
    return (phi * H).astype("<f4"), masks(shape, slab=name == "clipped_slab")


def assert_record_equal(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_record_equal(actual[key], expected[key])
    elif isinstance(expected, float) and math.isfinite(expected):
        assert actual == pytest.approx(expected, rel=1e-10, abs=1e-11)
    else:
        assert actual == expected


@pytest.mark.parametrize("name", ("cylinder", "box", "empty", "points", "clipped_slab"))
def test_five_known_inputs_match_actual_independent_checker(name):
    phi, mm = development_input(name)
    policy = R.load_policy()
    origin = (-0.41, 0.17, 0.09)
    actual = R.evaluate_pair(phi, phi, mm, H, policy, origin)
    expected = C.check_pair(phi, phi, mm, H, policy, origin)
    assert_record_equal(actual, expected)
    assert R.sign_body_hashes(phi) == C.sign_body_hashes(phi)
    if name == "empty":
        assert actual["r3"] == {"solid": None, "void": None, "status": "unmeasured"}


def test_exact_p1_rounding_block_and_empty_frozen_mask():
    phi, mm = development_input("empty")
    phi[0, 0, 0] = np.float32(np.float64(H) / 2)
    assert int(phi[0, 0, 0].view(np.uint32)) == 0x3C4CCCCD
    assert float(phi[0, 0, 0]) >= np.float64(H) / 2
    assert R.p1_gate(phi, phi, mm, H)["status"] == "pass"
    candidate = phi.copy()
    candidate[0, 0, 0] = np.float32(np.float64(0.3) * H)
    p1 = R.p1_gate(candidate, phi, mm, H)
    assert p1["status"] == "fail"
    assert R.composite_status("pass", ("pass",), p1["status"]) == "blocked"
    mm["design_mask"][:] = True
    with pytest.raises(R.ProtocolError, match="empty frozen"):
        R.p1_gate(phi, phi, mm, H)


@pytest.mark.parametrize("event", ("birth", "deletion", "split", "merge", "same_count_replacement"))
def test_real_component_overlap_events_including_equal_counts(event):
    shape = (9, 11, 13)
    left = np.full(shape, H, dtype="<f4")
    left[2:4, 4:7, 5:8] = -H
    two = left.copy()
    two[6:7, 4:7, 5:8] = -H
    connected = two.copy()
    connected[4:6, 4:7, 5:8] = -H
    right = np.full(shape, H, dtype="<f4")
    right[6:7, 4:7, 5:8] = -H
    parent, phi = {"birth": (left, two), "deletion": (two, left), "split": (connected, two),
                   "merge": (two, connected), "same_count_replacement": (left, right)}[event]
    policy, mm = R.load_policy(), masks(shape)
    got = R.p2_gate(phi, parent, mm, H, policy)
    assert got == C.check_pair(phi, parent, mm, H, policy)["p2"]
    assert got["statuses"]["topology_change_classification"] == "fail"
    assert got["events"] == (["birth", "deletion"] if event == "same_count_replacement" else [event])
    if event == "same_count_replacement":
        assert got["parent_components"] == got["candidate_components"] == 1
    assert R.p2_gate(two, two, mm, H, policy)["statuses"]["component_connectivity"] == "pass"


def test_scale_sign_halo_void_and_original_p1_recomposition(tmp_path, monkeypatch):
    phi, mm = development_input("cylinder")
    policy = R.load_policy()
    original = R.evaluate_pair(phi, phi, mm, H, policy)
    assert R.has_halo(phi) is True
    assert R.halo_pair(phi, phi, "ordinary", "analytic") == {"candidate": True, "parent": True}
    clipped, _ = development_input("clipped_slab")
    assert R.has_halo(clipped) is False
    assert R.halo_pair(clipped, clipped, "k5_slabs", "k5")["rule"] == "inapplicable_k5_finite_array_contract"
    monkeypatch.setitem(R.G, "policy", policy)
    monkeypatch.setattr(R, "assert_rss_budget", lambda: None)
    for scale in (0.5, 2.0):
        scaled = (phi.astype(np.float64) * scale).astype("<f4")
        spec = {"id": f"dev@k6_{scale:g}", "base_id": "dev", "kind": "k6", "scale": scale,
                "family": "development", "build": "development"}
        arrays = {"phi": scaled, "parent_phi": scaled.copy(), **mm, "origin_m": np.array((0., 0., 0.)), "spacing_m": np.array(H)}
        row = R.make_row(tmp_path, spec, arrays, {"candidate": original})
        for rule in ("r0", "r3"):
            assert row["candidate"][rule]["status"] == original[rule]["status"]
        assert row["candidate"]["p2"] == original["p2"]
        assert row["candidate"]["p1"] == original["p1"]
        assert row["candidate"]["composite"] == original["composite"]
        assert row["sign_body_hashes"] == R.sign_body_hashes(phi)
    empty = np.zeros((3, 4, 6), bool)
    assert R.W.opening_defect(empty, H / 4, 0.75 * H) is None
    assert C._opening_defect(empty, H) is None
    empty[1, 2, 3] = True
    assert R.W.opening_defect(empty, H / 4, 0.75 * H) == math.inf
    assert R.W.defect_status(None, H, void=True) == "pass"


def test_metadata_and_waiting_gates_never_generate_inputs(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("registered input/schedule execution during metadata/preflight")
    for name in ("build_row_arrays", "combo_schedule", "prepare_inputs", "analytic_field"):
        monkeypatch.setattr(R, name, forbidden)
    assert R.main([]) == 0
    assert json.loads(capsys.readouterr().out)["total_rows"] == 534
    work = tmp_path / "uncreated"
    for status in ("WAITING_FOR_DEPENDENCY", "WAITING_FOR_RESOURCES"):
        monkeypatch.setattr(R, "preflight", lambda *args, status=status: {"status": status, "reason": "development refusal"})
        assert R.run_controller(work)["status"] == status
        assert not work.exists()
    with pytest.raises(SystemExit) as exc:
        R.main(["--help"])
    assert exc.value.code == 0


def test_freeze_requires_real_source_and_review_pins(tmp_path):
    required = {path for path, _ in R.REQUIRED_SOURCE_PINS}
    assert {"scripts/geom03_check.py", "tests/test_geom03.py", "scripts/mode01_v18_prescreen.py",
            "src/cfd_sdf/design/topology_policy_research.py"} <= required
    with pytest.raises(R.ProtocolError, match="missing required"):
        R.validate_manifest([], R.REQUIRED_SOURCE_PINS)
    with pytest.raises(R.ProtocolError, match="missing required"):
        R.validate_manifest([], R.REQUIRED_REVIEW_PINS)
    registration = tmp_path / "registration.json"
    registration.write_text('{"schema":"geom03_registration_v1","status":"REGISTERED_FROZEN"}')
    with pytest.raises(R.ProtocolError):
        R.validate_registration(registration)
    release = tmp_path / "release.json"
    release.write_text('{"schema":"geom03_execution_release_v1","purpose":"FID01_GO_R3_VALIDATION"}')
    with pytest.raises(R.ProtocolError):
        R.validate_release(release, "a" * 64)
    assert R.canonical({"path": Path("development"), "infinite": math.inf, "empty": None}) == '{"empty":null,"infinite":"inf","path":"development"}'
    with pytest.raises(R.ProtocolError, match="NaN"):
        R.canonical({"bad": np.float32(np.nan)})


def test_docker_mount_and_unavailable_probe_refuse_resources(monkeypatch):
    def probe(command):
        if command == ["mount"]:
            return "development host: no FID mount"
        if command == ["docker", "ps", "--quiet"]:
            return "dev-container\n"
        return json.dumps([{"State": {"Running": True}, "Mounts": [{"Type": "bind", "Source": "/repo/work/fid01_of_out/case"}]}])
    monkeypatch.setattr(R, "run_probe", probe)
    with pytest.raises(R.ProtocolError, match="bind-mounts FID"):
        R.resource_evidence()
    monkeypatch.setattr(R, "run_probe", lambda cmd: (_ for _ in ()).throw(R.ProtocolError("unavailable")))
    with pytest.raises(R.ProtocolError, match="unavailable"):
        R.resource_evidence()
    monkeypatch.setattr(R, "run_probe", lambda cmd: "" if cmd[0] in ("mount", "docker") else "")
    monkeypatch.setattr(R.os, "getloadavg", lambda: (4.01, 0, 0))
    monkeypatch.setattr(R, "available_memory_bytes", lambda: R.BUDGET_RSS)
    with pytest.raises(R.ProtocolError, match="load/memory"):
        R.resource_evidence()


def test_cache_is_pickle_free_immutable_and_resume_prefix_is_interleaved(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "assert_rss_budget", lambda: None)
    phi, mm = development_input("empty")
    spec = {"id": "dev", "family": "development", "build": "development"}
    arrays = {"phi": phi, "parent_phi": phi.copy(), **mm, "origin_m": np.array((0., 0., 0.)), "spacing_m": np.array(H)}
    cache = R.cache_input(tmp_path, spec, arrays)
    original_bytes = (tmp_path / cache["input_npz"]).read_bytes()
    assert R.cache_input(tmp_path, spec, arrays) == cache
    assert (tmp_path / cache["input_npz"]).read_bytes() == original_bytes
    changed = {**arrays, "phi": phi.copy()}
    changed["phi"][4, 5, 6] *= 2
    with pytest.raises(R.ProtocolError, match="cached input changed"):
        R.cache_input(tmp_path, spec, changed)
    ident = R.field_identity(phi, phi, mm, (0., 0., 0.), H, spec)
    row = {"id": "dev", "spec": spec, "field_identity": ident, **cache}
    (tmp_path / "rows.jsonl").write_text(R.canonical(row) + "\n")
    assert len(R.verify_rows(tmp_path, [spec])) == 1
    with pytest.raises(R.ProtocolError, match="interleaved prefix"):
        R.verify_rows(tmp_path, [{**spec, "id": "dev@k6_0.5"}])
    (tmp_path / cache["input_npz"]).write_bytes(b"corrupt development input")
    with pytest.raises(R.ProtocolError, match="path/hash mismatch"):
        R.verify_rows(tmp_path, [spec])


def test_terminal_retry_and_cumulative_resume_budget(tmp_path):
    fingerprint = "a" * 64
    state = {"schema": R.SCHEMA_STATE, "status": "INTERRUPTED", "run_started_epoch": 100.,
             "fingerprint": fingerprint, "attempts": 1, "resume_count": 0, "observations": {}}
    R.write_state(tmp_path, state)
    resumed = R.prepare_state(tmp_path, fingerprint, resume=True, now=120.)
    assert resumed["run_started_epoch"] == 100.
    assert resumed["attempts"] == 1 and resumed["resume_count"] == 1
    with pytest.raises(R.ProtocolError, match="cumulative wall"):
        R.prepare_state(tmp_path, fingerprint, resume=True, now=100. + R.BUDGET_WALL_S + 1)
    (tmp_path / "results.json").write_text('{}')
    with pytest.raises(R.ProtocolError, match="terminal result/stop"):
        R.prepare_state(tmp_path, fingerprint, resume=True, now=121.)


def test_watchdog_stops_only_owned_child_and_keeps_first_stop(tmp_path, monkeypatch):
    child = SimpleNamespace(pid=123, returncode=None, stopped=False)
    child.poll = lambda: 1 if child.stopped else None
    child.terminate = lambda: setattr(child, "stopped", True)
    child.wait = lambda timeout: 1
    state = {"run_started_epoch": 0., "status": "RUNNING", "observations": {}}
    R.write_state(tmp_path, state)
    monkeypatch.setattr(R.time, "time", lambda: R.BUDGET_WALL_S + 1)
    monkeypatch.setattr(R, "child_rss_bytes", lambda pid: 1024)
    assert R.supervise(child, tmp_path, state) == 1
    assert child.stopped
    first = (tmp_path / "stop_reason.json").read_bytes()
    R.write_stop(tmp_path, "later reason", state)
    assert (tmp_path / "stop_reason.json").read_bytes() == first
    assert R.read_json(tmp_path / "stop_reason.json")["verdict"] == "GEOM03_INCOMPLETE"


@pytest.mark.parametrize("resume", (False, True))
@pytest.mark.parametrize("waiting", R.WAITING_STATUSES)
def test_parent_ready_child_waiting_preserves_preparation_or_original_attempt(tmp_path, monkeypatch, resume, waiting):
    """The fake child reaches only the real CLI's pre-input WAITING branch."""
    fingerprint = "a" * 64
    started = R.time.time() - 20
    if resume:
        R.write_state(tmp_path, {"schema": R.SCHEMA_STATE, "status": "INTERRUPTED", "fingerprint": fingerprint,
                                 "attempts": 1, "generation_started": True, "run_started_epoch": started,
                                 "resume_count": 0, "observations": {}})
    monkeypatch.setattr(R, "WORK", tmp_path)
    registration, release = tmp_path / "development_registration.json", tmp_path / "development_release.json"
    monkeypatch.setattr(R, "REGISTRATION", registration)
    monkeypatch.setattr(R, "RELEASE", release)
    calls = []
    def preflight(*args):
        calls.append(1)
        return ({"status": "READY", "fingerprint": fingerprint, "resources": {}, "registration": {}}
                if len(calls) % 2 else {"status": waiting, "reason": "development-only child wait"})
    monkeypatch.setattr(R, "preflight", preflight)
    for name in ("prepare_inputs", "combo_schedule", "build_row_arrays", "analytic_field", "execute_child"):
        monkeypatch.setattr(R, name, lambda *a, **k: pytest.fail("target generation on a pre-input WAITING path"))
    class FakeChild:
        pid = R.os.getpid()
        returncode = None
        def __init__(self, command, env, cwd):
            self.args = command[2:]
            for name in (R.SUPERVISE_ENV, R.LAUNCH_ENV):
                monkeypatch.setenv(name, env[name])
        def poll(self):
            if self.returncode is None:
                self.returncode = R.main(self.args)
            return self.returncode
    monkeypatch.setattr(R.subprocess, "Popen", FakeChild)
    for launch in (1, 2):
        result = R.run_controller(tmp_path, registration, release, resume=resume)
        state = R.read_json(tmp_path / "state.json")
        assert result["status"] == state["status"] == waiting
        assert state["attempts"] == (1 if resume else 0)
        assert state["run_started_epoch"] == (started if resume else None)
        assert state["resume_count"] == (launch if resume else 0)
        assert not R.terminal_exists(tmp_path)
        assert not (tmp_path / "inputs").exists()
    if resume:
        state["run_started_epoch"] = R.time.time() - R.BUDGET_WALL_S - 1
        R.write_state(tmp_path, state)
        with pytest.raises(R.ProtocolError, match="cumulative wall budget"):
            R.record_waiting(tmp_path, state, {"status": waiting})
        with pytest.raises(R.ProtocolError, match="cumulative wall budget"):
            R.run_controller(tmp_path, registration, release, resume=True)
        assert (tmp_path / "stop_reason.json").is_file()


def test_tiny_analytic_primitive_distance_and_orientation_oracles():
    points = np.asarray(((0., 0., 0.), (1., 0., 0.), (2., 0., 0.), (3., 0., 0.), (3., 4., 0.), (3., 4., 5.)))
    actual = R.box_sdf(*points.T, (2., 2., 2.))
    # Interior face distance, boundary, single-axis outside and Pythagorean corner distances.
    np.testing.assert_allclose(actual, (-2., -1., 0., 1., math.sqrt(5), math.sqrt(14)), rtol=0, atol=1e-14)
    np.testing.assert_allclose(R.product(np.array((-2., 0., 3., 3.)), np.array((-1., -2., 4., -2.))),
                               (-1., 0., 5., 3.), rtol=0, atol=1e-14)
    np.testing.assert_allclose(R._wedge_planar(np.array((4., 0., 5., -5.)), np.zeros(4), 90.),
                               (0., -2.5, 1., 1.), rtol=0, atol=1e-14)
    q = R.local_coords(90., (0., 0., 0.), n=9, center=(4., 4., 4.))
    np.testing.assert_allclose([a[5, 4, 4] for a in q], (0., 0., 1.), rtol=0, atol=1e-14)


def test_translated_linear_field_preserves_distances_gates_and_bound_state():
    # Dyadic coordinates give an exact translation identity, independent of either metric path.
    shape, h = (9, 11, 13), 1 / 32
    origin = np.array((1 / 8, -1 / 4, 1 / 2))
    translation = np.array((1 / 2, 1 / 4, -1 / 8))
    nodes = origin.reshape(3, 1, 1, 1) + h * np.indices(shape, dtype=np.float64)
    plane_z = origin[2] + h * 6.125
    phi = (nodes[2] - plane_z).astype("<f4")
    translated = ((nodes[2] + translation[2]) - (plane_z + translation[2])).astype("<f4")
    np.testing.assert_array_equal(phi, translated)
    assert phi[0, 0, 6] == -h / 8 and phi[0, 0, 7] == 7 * h / 8
    mm = masks(shape, slab=True)
    mm["fixed_solid_mask"][:, :, 0] = True
    policy = R.load_policy()
    before = R.evaluate_pair(phi, phi, mm, h, policy, tuple(origin))
    after = R.evaluate_pair(translated, translated, mm, h, policy, tuple(origin + translation))
    assert_record_equal(before, after)
    assert R.sign_body_hashes(phi) == R.sign_body_hashes(translated)
    state = R._p2_state(translated, mm, h, policy, tuple(origin + translation))
    assert state.origin_m == tuple(origin + translation)
    assert state.spacing_m == h and state.narrow_band_width_m == 8 * h > 0
    assert state.topology_policy_id == policy.state_binding_id
    for name in R.MASK_NAMES:
        np.testing.assert_array_equal(getattr(state, name), mm[name])


def test_closed_digital_ball_and_clipped_boundary_slab_oracles():
    ball = C._r3_ball()
    assert ball.shape == (7, 7, 7) and int(ball.sum()) == 123
    assert ball[6, 3, 3] and ball[5, 5, 4]  # squared radius exactly nine, included
    assert not ball[6, 4, 3] and not ball[5, 5, 5]  # squared radius ten and twelve
    np.testing.assert_array_equal(ball, ball[::-1, ::-1, ::-1])
    body = np.zeros((7, 8, 9), bool)
    body[:, :, :4] = True
    # A four-step slab touching the lower face has a radius-three opening equal to itself.
    assert R.W.opening_defect(body, H / 4, 0.75 * H) == 0.
    assert C._opening_defect(body, H) == 0.
    body[:, :, 2:] = False
    assert R.W.opening_defect(body, H / 4, 0.75 * H) == math.inf
    assert C._opening_defect(body, H) == math.inf
