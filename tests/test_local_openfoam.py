"""LOCAL-OF-01 comparator (scripts/local_openfoam_gate.py) and subset harness (scripts/local_openfoam.py): synthetic records and the real Kaggle
references compared with themselves (every check must pass and be bitwise)."""
import gzip
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import local_openfoam as L  # noqa: E402
import local_openfoam_gate as G  # noqa: E402

needs_refs = pytest.mark.skipif(not (G.REF_T20B / "result.json").is_file() or not (G.REF_T20C / "DONE").is_file()
                                or not (G.REF_X3 / "result.json").is_file(), reason="Kaggle reference evidence not present")


def test_same_rules():
    assert G.same(7349, 7349) and not G.same(7349, 7350)
    assert G.same("49.437042", "49.437042") and G.same(0.1, 0.1 * (1 + 1e-9)) and not G.same("49.437042", "49.437142")
    assert G.same(9.8879238130678e-17, 0.0)                                       # absolute floor (morph contour_err_m ~ 1e-16)
    assert not G.same("99362391", "99362392") and not G.same("a" * 64, "b" * 64) and not G.same(True, 1.0)
    assert G.diff_keys({"a": [1, {"b": 2.0}]}, {"a": [1, {"b": 2.0000000001}]}) == []
    assert G.diff_keys({"a": [1, {"b": 2.0}]}, {"a": [1, {"b": 2.1}]}) == [".a[1].b"]


def test_verdict_failure_dominates_incomplete():
    ok, bad, miss, few = {"pass": True}, {"pass": False}, {"incomplete": "x"}, {"pass": False, "enough_pairs": False}
    assert G.verdict({"x": bad, "y": miss}, True) == "LOCAL_ENV_FAIL"
    assert G.verdict({"x": ok, "y": miss}, True) == "INCOMPLETE"
    assert G.verdict({"x": ok, "y": few}, True) == "INCOMPLETE"
    assert G.verdict({"x": ok, "y": ok}, True) == "LOCAL_ENV_PASS_BITWISE"
    assert G.verdict({"x": ok, "y": ok}, False) == "LOCAL_ENV_PASS_TOLERANCE"
    assert "incomplete" in G.part(lambda: G.load(Path("/nonexistent/DONE"))) and G.part(lambda: 1 / 0)["pass"] is False


def test_run_dir_checks_wrapper_record(tmp_path):
    fz = {"image_id": "sha256:i", "lock_sha256": "l", "script_sha256_allowed": ["s"], "runner_sha256": {"x3": "r"}, "cpus": {"x3": "1"}}
    rec = {"returncode": 0, "image_id": "sha256:i", "lock_sha256": "l", "script_sha256": "s", "runner_sha256": "r", "dpkg_after_matches_lock": True,
           "docker_args": ["run", "--cpus", "1", "--memory", "8g"]}
    (tmp_path / "x3_a/subset_x3").mkdir(parents=True)
    (tmp_path / "x3_a/local_run.json").write_text(json.dumps(rec))
    with pytest.raises(G.Missing):                                                 # no DONE yet: infrastructure, not a result
        G.run_dir(tmp_path, "x3_a", "subset_x3", "x3", fz)
    (tmp_path / "x3_a/subset_x3/DONE").write_text("{}")
    assert G.run_dir(tmp_path, "x3_a", "subset_x3", "x3", fz) == tmp_path / "x3_a/subset_x3"
    (tmp_path / "x3_a/local_run.json").write_text(json.dumps({**rec, "runner_sha256": "other"}))
    with pytest.raises(G.Missing):
        G.run_dir(tmp_path, "x3_a", "subset_x3", "x3", fz)


def _smoke(root: Path, cells: int, sha: str, residual: float):
    case = {"id": "c1_mesh", "status": "MESH_OK", "mesh_cells_3d": cells, "mesh_msh_sha256": sha, "total_wall_s": 1.0,
            "check_mesh": {"max_skewness": "0.5034421"}, "stages": [{"stage": "checkMesh", "returncode": 0, "wall_s": 2.0}],
            "topology": {"faces": sha}, "morph": {"contour_err_m": 9.8e-17 if sha == "a" * 64 else 0.0}}
    solved = {"id": "c2_smoke", "status": "COMPLETED", "mesh_cells_3d": cells, "mesh_msh_sha256": sha,
              "solver": {"last_initial_residuals": {"p": residual}}, "forces": {"values": "suppressed"}}
    for c in (case, solved):
        (root / "cases" / c["id"]).mkdir(parents=True)
        (root / "cases" / c["id"] / "case_result.json").write_text(json.dumps(c))
    (root / "bases.json").write_text(json.dumps([{"mesh_msh_sha256": sha, "wall_s": 3.0, "topology": {"faces": sha}}]))
    (root / "DONE").write_text(json.dumps({"status_counts": {"MESH_OK": 1, "COMPLETED": 1}}))


def test_mesh_replay_hashes_descriptive_cells_gating(tmp_path):
    _smoke(tmp_path / "k", 100, "a" * 64, 1e-3)
    _smoke(tmp_path / "l", 100, "b" * 64, 2e-3)                                    # another gmsh variant: residuals may differ
    r = G.t20c_mesh_replay(tmp_path / "l", tmp_path / "k")
    assert r["pass"] and r["mesh_sha_identical"] == 0 and r["solver_paths_descriptive"]["same_mesh"] == 0
    _smoke(tmp_path / "s", 100, "a" * 64, 2e-3)                                    # same mesh file, residual off by a factor 2: fails
    assert not G.t20c_mesh_replay(tmp_path / "s", tmp_path / "k")["pass"]
    _smoke(tmp_path / "c", 101, "a" * 64, 1e-3)
    r = G.t20c_mesh_replay(tmp_path / "c", tmp_path / "k")
    assert not r["pass"] and ".mesh_cells_3d" in r["mismatches"][0]["keys"]


@needs_refs
def test_kaggle_references_against_themselves(tmp_path):
    t1 = G.t20c_mesh_replay(G.REF_T20C, G.REF_T20C)
    assert t1["pass"] and t1["compared"] == 262 and t1["mesh_sha_identical"] == 262
    det, force, variants = G.t20b_forces({"t20b_a": G.REF_T20B, "t20b_b": G.REF_T20B}, G.REF_T20B)
    assert det["pass"] and len(det["pairs"]) == len(G.T20B_CASES) and force["pass"] and force["bitwise"] and variants["label"] is None
    u1, u2 = G.x3_forces(G.REF_X3, G.REF_X3, G.REF_X3)
    assert u1["pass"] and u2["pass"] and u2["bitwise"] and max(abs(v) for v in u2["difference_discrepancy"].values()) == 0
    sc = G.kaggle_self_consistency(G.REF_T20B, G.REF_T20C)
    assert (sc["geometries"], sc["identical"]) == (41, 34)
    # one local run draws another gmsh variant of one case: that case leaves T2 and the T3 pair of that run, and enters the descriptive spread
    v = tmp_path / "t20b_v"
    (v / "cases").mkdir(parents=True)
    shutil.copy2(G.REF_T20B / "result.json", v / "result.json")
    for cid in G.T20B_CASES:
        shutil.copytree(G.REF_T20B / "cases" / cid, v / "cases" / cid)
    cid = G.T20B_CASES[0]
    m = json.loads(gzip.decompress((v / "cases" / cid / "case_manifest.json.gz").read_bytes()))
    (v / "cases" / cid / "case_manifest.json.gz").write_bytes(gzip.compress(json.dumps({**m, "mesh_msh_sha256": "f" * 64}).encode()))
    det, force, variants = G.t20b_forces({"t20b_a": G.REF_T20B, "t20b_b": v}, G.REF_T20B)
    assert force["pass"] and cid in force["cases_with_same_mesh_pair"] and variants["label"] == "VARIANT_SPREAD_WITHIN_SCALE"
    assert len(det["pairs"]) == len(G.T20B_CASES) - 1


def test_u4_blinded_returns_no_force_value(tmp_path):
    vals = {"u3_v18__parent_33p": (0.371234, 0.245678), "u3_v18__D0_p3_33p": (0.365432, 0.251234)}
    for side, eps in (("k", 0.0), ("a", 1e-6), ("b", 1e-6)):
        cases = []
        for cid, (dr, dn) in vals.items():
            d = tmp_path / side / "cases" / cid / "retained"
            d.mkdir(parents=True)
            rows = "".join(f"{i} {(dr + eps) / 0.32!r} {-(dn + eps) / 0.32!r}\n" for i in range(40))
            (d / "coefficient.dat.gz").write_bytes(gzip.compress(f"# Time Cd Cl\n{rows}".encode()))
            cases.append({"id": cid, "status": "COMPLETED", "forces": {"drag_n": {"window_mean": dr + eps}, "downforce_n": {"window_mean": dn + eps}}})
        (tmp_path / side / "result.json").write_text(json.dumps({"cases": cases}))
    r = G.u3_forces_blinded(tmp_path / "a", tmp_path / "b", tmp_path / "k")
    assert r["pass"] and r["determinism_pass"] and not r["bitwise"]
    text = json.dumps(r)
    assert not any(f"{v:.5f}"[:7] in text for pair in vals.values() for v in pair)   # no value leaks
    assert "0.0058" not in text and "0.00555" not in text                           # no state difference leaks


def test_sanitised_archive_refuses_forces(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "EXCLUDED_SHA256.json").write_text("{}")
    (tmp_path / "out/result.json").write_text(json.dumps({"cases": [{"id": "u", "status": "COMPLETED", "forces": {"drag_n": 1}}]}))
    assert G.part(G.sanitised_records, tmp_path)["pass"] is False


def test_subset_calls_the_runners_own_run_case(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    crit = {"inputs": {}, "environment": {"registered_lock_suites": ["noble"], "foam_version": "OpenFOAM-v2512"},
            "states": {"s": {"file": "s.stl"}}, "case_order": [{"id": "c1", "state": "s"}, {"id": "c2", "state": "s"}, {"id": "c3", "state": "s"}]}
    (data / "x3_criteria.json").write_text(json.dumps(crit))
    (data / "openfoam_package_lock_noble.json").write_text("{}")
    fake = tmp_path / "runner.py"
    fake.write_text(f"""
import json
from pathlib import Path
CALLS = []
CRITERIA_SHA256 = "c"
def sha(p): return "c"
def discover_inputs(): return Path({str(data)!r})
def install_openfoam(out, locks, version): return {{"foamVersion": version, "locks": sorted(locks)}}
def read_stl(p): return "tri:" + Path(p).name
def write_json(p, v): Path(p).write_text(json.dumps(v, default=str))
def run_case(spec, criteria, template, tri, root):
    CALLS.append(spec["id"])
    Path({str(tmp_path / "calls.txt")!r}).open("a").write(spec["id"] + "\\n")
    return {{"id": spec["id"], "status": "COMPLETED", "tri": tri}}
""")
    monkeypatch.setenv("LOCAL_OF_WORKING", str(tmp_path / "work"))
    L.subset(fake, "x3", ["c3", "c1"])
    out = json.loads((tmp_path / "work/subset_x3/result.json").read_text())
    assert (tmp_path / "calls.txt").read_text().split() == ["c3", "c1"] and [c["id"] for c in out["cases"]] == ["c3", "c1"]
    assert (tmp_path / "work/subset_x3/DONE").is_file() and out["install"]["foamVersion"] == "OpenFOAM-v2512"
