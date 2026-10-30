"""SCREEN-01 (#64): the state/campaign builder and the freeze writer: kernel run lists, caps, estimates, states.json schema, byte determinism, refusals."""
from __future__ import annotations

import json
import shutil
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01"), str(ROOT / "scripts/screen01")]
import fid01_designs as D  # noqa: E402
import screen01_build as SB  # noqa: E402
import screen01_freeze as F  # noqa: E402
import screen01_pool as P  # noqa: E402
from cfd_harness import campaign_schema as SC  # noqa: E402

REAL_STATES = SB.STATES
ON_DISK = pytest.mark.skipif(not REAL_STATES.exists(), reason="states.json not built: run screen01_build.py states")


@pytest.fixture(scope="module")
def built():
    """Every G1 state through the harness model (no write); refuses on any mismatch with the P0 gated bytes."""
    return SB.states_files()


@pytest.fixture
def env(built, tmp_path, monkeypatch):
    """The builder pointed at a scratch states.json / harness directory (nothing is written to the repository)."""
    (tmp_path / "states.json").write_text(built[REAL_STATES])
    monkeypatch.setattr(SB, "STATES", tmp_path / "states.json")
    monkeypatch.setattr(SB, "STATES_G2", tmp_path / "states_g2.json")
    monkeypatch.setattr(SB, "HARNESS", tmp_path / "harness")
    return tmp_path


def rs_fixture(n=4, **kw):
    """A synthetic rs.json shaped like the analyzer's: the first n admissible P0 design-pool members that are not design points, as proposals
    ({name, u, spec, target_index, y_pred, z_pred, rank}) with their gating rows (the P0 gate row plus name, u, target_index, y_pred, z_pred, admissible)."""
    _, rows, _, dc = SB.p0_record()
    sel = [r for r in rows.values() if r["slot"] == "rs" and r["admissible"] and r["name"] not in dc["design_points"]][:max(n, 1)]
    u = {r["name"]: P.spec_to_u(r["spec"]) for r in sel}
    return {"proposals": [{"name": r["name"], "u": u[r["name"]], "spec": P.u_to_spec(u[r["name"]]), "target_index": i % 3, "y_pred": 1e-2, "z_pred": -2e-3, "rank": i}
                          for i, r in enumerate(sel[:n])],
            "gating": [{**r, "name": r["name"], "u": u[r["name"]], "target_index": i % 3, "y_pred": 1e-2, "z_pred": -2e-3, "admissible": True} for i, r in enumerate(sel)], **kw}


def write_json(path, obj):
    path.write_text(json.dumps(obj))
    return path


def names(kernel):
    return [r["name"] for r in kernel["runs"]]


# ---- states.json -----------------------------------------------------------------------------------------------------------------------------------
def test_states_schema_roles_order_and_u(built):
    rec = json.loads(built[REAL_STATES])
    st, _, _, dc = rec["states"], None, None, SB.p0_record()[3]
    assert rec["schema"] == "screen01-states-v1" and rec["parent"] == "v18__parent" and len(st) == 39
    roles = {}
    for n, r in st.items():
        roles.setdefault(r["role"], []).append((r["order"], n))
    assert {k: len(v) for k, v in roles.items()} == {"parent": 1, "parent_repeat": 1, "axial": 6, "design": 9, "manual": 1, "ref": 1, "nc": 1, "random": 19}
    ordered = lambda role: [n for _, n in sorted(roles[role])]  # noqa: E731
    assert ordered("axial") == ["v18__pitch_p3.1", "v18__pitch_m3.1", "v18__camber_p19.7", "v18__camber_m19.7", "v18__reflex_p29.3", "v18__reflex_m29.3"]
    assert [st[n]["u"] for n in ordered("axial")] == [[1.0, 0, 0], [-1.0, 0, 0], [0, 1.0, 0], [0, -1.0, 0], [0, 0, 1.0], [0, 0, -1.0]]
    assert ordered("design") == dc["design_points"] and np.allclose([st[n]["u"] for n in ordered("design")], dc["design_u"], atol=1e-12)
    assert ordered("random") == SB.p0_record()[2]["rand3"]["control_set"] and len(roles["random"]) == P.K_RAND
    assert ordered("manual") == ["v18__camber_m19.7_pitch_m0.38"] and ordered("ref") == ["v18__camber_m11.3_reflex_m11.3"] and ordered("nc") == ["v18__roll_p25"]
    for n in ("v18__parent", "v18__parent__repeat", "v18__roll_p25"):
        assert st[n]["u"] is None and st[n]["spec"] is None and st[n]["order"] == 0
    for n, r in st.items():
        if r["role"] in ("axial", "design", "manual", "ref", "random"):
            assert r["spec"] == dict(sorted(r["spec"].items())) and D.name(r["spec"]) == n and r["u"] == P.spec_to_u(r["spec"]) and r["kind"] == "candidate"
            assert SC.is_sha(r["direction_sha256_fortran_raw"]) and r["step_mm"] > 0


def test_states_reproduce_the_p0_gated_bytes_and_raws(built):
    rec, rows = json.loads(built[REAL_STATES]), SB.p0_record()[1]
    st = rec["states"]
    for n, r in st.items():
        if r["role"] in ("axial", "design", "manual", "ref", "random"):
            assert r["phi_fortran_order_sha256"] == rows[n]["phi_fortran_sha256"] and rows[n]["admissible"]
            assert SC.sha256_bytes(built[SB.ROOT / r["direction_path"]]) == r["direction_sha256_fortran_raw"]
    assert len(built) == 1 + 36                                                            # states.json + the raws of the 36 candidates (parent and roll: UNC-01 bytes)
    ident = ("state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "zero_level_margin_m", "changed_node_count")
    assert st["v18__parent__repeat"]["kind"] == "parent_repeat" and all(st["v18__parent__repeat"][k] == st["v18__parent"][k] for k in ident)
    assert st["v18__roll_p25"]["direction_path"] == "docs/evidence/unc01_2026_10_20/inputs/v18__roll_p25.dir_f4_fortran.raw" and st["v18__roll_p25"]["kind"] == "control"
    unc = json.loads((ROOT / "docs/evidence/unc01_2026_10_20/states.json").read_text())["states"]
    assert all(st[n][k] == unc[n][k] for n in ("v18__parent", "v18__roll_p25") for k in ident)   # UNC-01 bytes
    assert all(st[n]["phi_fortran_order_sha256"] == unc[n]["phi_fortran_order_sha256"] for n in SB.by_role(st, "axial"))   # the axial states are the M2 / MODE-01 bytes
    fid = json.loads((ROOT / "docs/evidence/fid01_2026_10_21/states.json").read_text())["states"]["v18__camber_m11.3_reflex_m11.3"]
    assert st["v18__camber_m11.3_reflex_m11.3"]["phi_fortran_order_sha256"] == fid["phi_fortran_order_sha256"]   # C1 is the FID state
    assert len({r["phi_fortran_order_sha256"] for n, r in st.items() if n != "v18__parent__repeat"}) == 38


def test_states_are_deterministic(built):
    again = SB.states_files()
    assert again.keys() == built.keys() and all(again[k] == built[k] for k in built)


@ON_DISK
def test_states_on_disk_byte_check(built):
    SB.emit(built, True)


# ---- G1 kernels ------------------------------------------------------------------------------------------------------------------------------------
def test_g1_kernels(env):
    rows = SB.load_rows()
    k = SB.g1_kernels(rows)
    st = json.loads((env / "states.json").read_text())["states"]
    order = ["v18__parent"] + SB.by_role(st, "axial") + SB.by_role(st, "design") + SB.by_role(st, "manual") + SB.by_role(st, "ref") + SB.by_role(st, "nc") + SB.by_role(st, "random")
    assert set(k) == {"g1k11", "g1k12"} and len(order) == 38
    assert names(k["g1k11"]) == [f"{n}__k11" for n in order] + ["v18__parent__repeat__k11"]      # 39 runs, parent first, the repeat last
    assert names(k["g1k12"]) == [f"{n}__k12" for n in order] and "v18__parent__repeat__k12" not in names(k["g1k12"])   # 38 runs
    for kern in k.values():
        assert kern["case"]["case_id"] == "flow_32" and kern["runs"][0]["state"] == "v18__parent"
        assert [kern["config"][x] for x in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")] == [900, 20000, 23300]
        assert len({r["env"]["W4_CANONICAL_ORIGIN_M"] for r in kern["runs"]}) == 1             # one phase per kernel
    assert k["g1k11"]["runs"][0]["env"] != k["g1k12"]["runs"][0]["env"]
    assert [SB.FB.estimate_s(k[x]) for x in ("g1k11", "g1k12")] == [39 * 415 + 260, 38 * 415 + 260] == [16445, 16030]


def test_g1_campaign_validates_and_binds_the_repeat(env):
    files = SB.campaign_files("g1")
    (path, text), = files.items()
    c = json.loads(text)
    SC.validate_campaign(c)
    assert path == env / "harness" / "screen01_campaign.json" and c["campaign_id"] == "screen01" and set(c["kernels"]) == {"g1k11", "g1k12"}
    assert c["states"]["v18__parent__repeat"]["kind"] == "parent_repeat" and c["states"]["v18__parent__repeat"]["direction"] is None
    assert len(c["states"]) == 39 and len(c["directions"]) == 37 and "v18__parent" not in c["directions"]
    assert c["kernels"]["g1k11"]["kernel_id"] == "ramhachi888/cfd-opt-sdf-screen01-g1k11"


# ---- G2 --------------------------------------------------------------------------------------------------------------------------------------------
def test_g2_kernel_from_a_synthetic_rs(env):
    rs = rs_fixture(4)
    files = SB.campaign_files("g2", write_json(env / "rs.json", rs))
    c = json.loads(files[env / "harness" / "screen01_g2_campaign.json"])
    SC.validate_campaign(c)
    props = [p["name"] for p in rs["proposals"]]
    g2 = c["kernels"]["g2"]
    assert names(g2) == [f"{s}__k{k}" for k in (11, 12) for s in ["v18__parent", *props]] and len(g2["runs"]) == 10
    assert [g2["config"][x] for x in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")] == [900, 6000, 9000] and SB.FB.estimate_s(g2) == 4410
    new = json.loads(files[env / "states_g2.json"])
    assert sorted((r["order"], r["role"], n) for n, r in new["states"].items()) == [(i, "proposal", n) for i, n in enumerate(props)]
    assert new["rs_json_sha256"] == SB.FB.sha(env / "rs.json") and set(c["states"]) == {"v18__parent", *props}
    assert all(SC.sha256_bytes(files[SB.ROOT / new["states"][n]["direction_path"]]) == new["states"][n]["direction_sha256_fortran_raw"] for n in props)
    small = SB.campaign_files("g2", write_json(env / "rs3.json", rs_fixture(3)))
    assert len(json.loads(small[env / "harness" / "screen01_g2_campaign.json"])["kernels"]["g2"]["runs"]) == 8


def test_g2_refusals(env):
    assert SB.campaign_files("g2", write_json(env / "rs0.json", {"proposals": [], "gating": []})) == {}   # no proposal, no g2 kernel
    good = rs_fixture(2)
    with pytest.raises(SystemExit, match="at most 4"):
        SB.campaign_files("g2", write_json(env / "a.json", {**rs_fixture(5), "proposals": rs_fixture(5)["proposals"] * 2}))
    unsorted = json.loads(json.dumps(good))
    spec = P.u_to_spec(good["proposals"][0]["u"])
    unsorted["proposals"][0]["name"] = D.name({m: spec[m] for m in P.SUBSET if m in spec})      # pitch-camber-reflex key order: not the registered name
    with pytest.raises(SystemExit, match="sorted-key spec"):
        SB.campaign_files("g2", write_json(env / "b.json", unsorted))
    for bad in ({"admissible": False}, {"phi_fortran_sha256": None}):
        rs = json.loads(json.dumps(good))
        rs["gating"][0].update(bad)
        with pytest.raises(SystemExit, match="admissible gated state"):
            SB.campaign_files("g2", write_json(env / "c.json", rs))
    for key, val in (("rank", 1), ("spec", {"pitch": 0.5})):                                     # the analyzer's rank / spec must agree with the list position / u
        rs = json.loads(json.dumps(good))
        rs["proposals"][0][key] = val
        with pytest.raises(SystemExit, match="rank / spec differ"):
            SB.campaign_files("g2", write_json(env / "f.json", rs))
    rs = json.loads(json.dumps(good))
    rs["gating"][0]["phi_fortran_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="differ from the gated bytes"):
        SB.campaign_files("g2", write_json(env / "d.json", rs))
    dup = {"proposals": [{"name": "v18__camber_m21.959_pitch_m2.307_reflex_m24.023", "u": json.loads((env / "states.json").read_text())["states"]
                          ["v18__camber_m21.959_pitch_m2.307_reflex_m24.023"]["u"]}], "gating": []}
    with pytest.raises(SystemExit):                                                              # a design point is not a new state
        SB.campaign_files("g2", write_json(env / "e.json", dup))


# ---- F ---------------------------------------------------------------------------------------------------------------------------------------------
def f_files(env, finalist, r_best):
    return SB.campaign_files("f", finalist_path=write_json(env / "finalist.json", {"finalist": finalist, "r_best": r_best}))


def test_f_kernels(env):
    rows = SB.load_rows()
    rb = SB.by_role(rows, "random")[3]
    files = f_files(env, "v18__camber_p19.7", rb)
    f32, f48 = (json.loads(files[env / "harness" / f"screen01_{c}_campaign.json"]) for c in ("f", "f48"))
    for c in (f32, f48):
        SC.validate_campaign(c)
    assert set(f32["kernels"]) == {"f32a", "f32b", "f32smk"} and set(f48["kernels"]) == {"f48k13", "f48k14", "f48smk"}
    cand = ["v18__parent", "v18__camber_p19.7", rb]
    ctrl = cand + ["v18__camber_m19.7_pitch_m0.38", "v18__roll_p25"]
    for k in (13, 14):
        kern = f48["kernels"][f"f48k{k}"]
        assert names(kern) == [f"{s}__k{k}" for s in cand] and kern["case"]["case_id"] == "flow_48"
        assert [kern["config"][x] for x in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")] == [6000, 9200, 12500] and SB.FB.estimate_s(kern) == 7280
    a, b = f32["kernels"]["f32a"], f32["kernels"]["f32b"]
    assert names(a) == [f"{s}__k{k}" for k in (13, 14) for s in ctrl] + ["v18__parent__k11", "v18__parent__repeat__k13"] and len(a["runs"]) == 12   # replay, then the repeat last
    assert names(b) == [f"{s}__k{k}" for k in (15, 16) for s in ctrl] and len(b["runs"]) == 10
    assert [a["config"][x] for x in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")] == [900, 7000, 10000]
    assert [b["config"][x] for x in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")] == [900, 6000, 9000]
    assert [SB.FB.estimate_s(a), SB.FB.estimate_s(b)] == [5240, 4410]
    assert a["runs"][0]["state"] == "v18__parent" and a["runs"][len(ctrl)]["state"] == "v18__parent"   # the parent first at phases 13 and 14
    smk = {"f32smk": f32["kernels"]["f32smk"], "f48smk": f48["kernels"]["f48smk"]}                  # the confirmation smokes touch phase 20 only
    assert [names(v) for v in smk.values()] == [["v18__parent__k20"], ["v18__parent__k20"]]
    assert all(not {f"k{k}" for k in (13, 14, 15, 16)} & {n.rsplit("__", 1)[1] for n in names(v)} for v in smk.values())


def test_f_empty_r_best_and_proposal_finalist(env):
    files = f_files(env, "v18__pitch_p3.1", None)
    f32, f48 = (json.loads(files[env / "harness" / f"screen01_{c}_campaign.json"])["kernels"] for c in ("f", "f48"))
    assert [len(f32["f32a"]["runs"]), len(f32["f32b"]["runs"]), len(f48["f48k13"]["runs"]), len(f48["f48k14"]["runs"])] == [10, 8, 2, 2]   # -4 flow_32, -2 flow_48 runs
    g2 = SB.campaign_files("g2", write_json(env / "rs.json", rs_fixture(2)))
    (env / "states_g2.json").write_text(g2[env / "states_g2.json"])
    prop = rs_fixture(2)["proposals"][1]["name"]
    c = json.loads(f_files(env, prop, None)[env / "harness" / "screen01_f_campaign.json"])
    SC.validate_campaign(c)
    assert c["states"][prop]["direction"] == prop and c["directions"][prop]["path"].endswith(f"{prop}.dir_f4_fortran.raw")
    with pytest.raises(SystemExit, match="no finalist"):
        f_files(env, None, None)
    for bad in ("v18__camber_m19.7_pitch_m0.38", "v18__roll_p25", "v18__parent", "v18__nope"):   # M, NC, the parent and unknown states are not finalist candidates
        with pytest.raises(SystemExit, match="not registered"):
            f_files(env, bad, None)
    with pytest.raises(SystemExit, match="not registered"):
        f_files(env, "v18__pitch_p3.1", "v18__pitch_m3.1")                                      # R-best must be a random-control state


def test_formal_estimate_is_61095(env):
    rows = SB.load_rows()
    g2 = SB.campaign_files("g2", write_json(env / "rs.json", rs_fixture(4)))
    (env / "states_g2.json").write_text(g2[env / "states_g2.json"])
    kernels = {**SB.g1_kernels(rows), **SB.g2_kernels(list(json.loads(g2[env / "states_g2.json"])["states"]))}
    for ks in SB.f_kernels(SB.load_rows(), "v18__camber_p19.7", SB.by_role(rows, "random")[0]).values():
        kernels.update(ks)
    formal = {k: v for k, v in kernels.items() if k in SB.FORMAL}
    assert set(formal) == set(SB.FORMAL) and len(formal) == 7
    assert sum(SB.FB.estimate_s(v) for v in formal.values()) == 61095
    assert all(v["config"]["per_state_timeout_s"] <= v["config"]["solver_wall_time_cap_s"] for v in kernels.values())


# ---- byte check --------------------------------------------------------------------------------------------------------------------------------------
def test_emit_writes_checks_and_refuses_to_overwrite(env):
    files = SB.campaign_files("g1")
    SB.emit(files, False)
    SB.emit(files, True)                                                                         # regenerating reproduces the written file byte for byte
    SB.emit(files, False)                                                                        # an identical rewrite is allowed
    (path, text), = files.items()
    path.write_text(text.replace("v18__parent__k11", "v18__parent__k99", 1))
    with pytest.raises(SystemExit, match="byte check FAILED"):
        SB.emit(files, True)
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        SB.emit(files, False)
    path.unlink()
    with pytest.raises(SystemExit, match="byte check FAILED"):
        SB.emit(files, True)                                                                     # a missing file fails the check too


# ---- freeze writer -----------------------------------------------------------------------------------------------------------------------------------
def test_freeze_refuses_to_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "EV", tmp_path)
    (tmp_path / "freeze2_1.json").write_text("{}")
    with pytest.raises(ValueError, match="refusing to overwrite freeze2_1.json"):
        F.record("freeze2_1", [], {})


def fake_repo(monkeypatch, ev):
    """git without a repository: clean tree, HEAD on a remote branch, every listed path 'tracked' if it exists (a missing non-glob path fails like `git ls-files`)."""
    def tracked(p):
        found = list(ROOT.glob(p)) if "*" in p else [ROOT / p]
        SC.req(all(f.exists() for f in found) and found, f"not tracked: {p}")
        return [SB.rel(x) for f in found for x in ([f] if f.is_file() else f.rglob("*")) if x.is_file()]
    monkeypatch.setattr(F, "EV", ev)
    monkeypatch.setattr(F, "tracked", tracked)
    monkeypatch.setattr(F, "git", lambda *a: {"status": "", "rev-parse": "a" * 40, "fetch": "", "ls-remote": "a" * 40 + " refs/heads/x"}[a[0]])
    monkeypatch.setattr(F.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))


@ON_DISK
def test_freeze1_refuses_without_the_infra_signature_table(tmp_path, monkeypatch):
    fake_repo(monkeypatch, tmp_path)
    monkeypatch.setattr(F, "BOUND_EVIDENCE", ["docs/evidence/screen01_2026_10_30/no_such_infra_signatures.json", *F.BOUND_EVIDENCE[1:]])
    with pytest.raises(ValueError, match="infra_signatures.json .* is missing"):
        F.freeze1()
    assert not (tmp_path / "freeze1.json").exists()


@ON_DISK
def test_freeze1_content(tmp_path, monkeypatch):
    fake_repo(monkeypatch, tmp_path)
    bound = list(F.BOUND_EVIDENCE)
    if not (ROOT / bound[0]).exists():                                                           # written by the analyzer author; a stand-in keeps the rest of the record testable
        bound[0] = "docs/evidence/screen01_2026_10_30/decision_memo.md"
        monkeypatch.setattr(F, "BOUND_EVIDENCE", bound)
    target = F.freeze1()
    rec = json.loads(target.read_text())
    sha = rec["file_sha256"]
    assert target.name == "freeze1.json" and rec["kind"] == "screen01_freeze1" and rec["source_commit"] == "a" * 40 and rec["shape_update_allowed"] is False
    for f in (F.REG, F.ADOPTION, "scripts/screen01/screen01_build.py", "scripts/screen01/screen01_freeze.py", "scripts/screen01/screen01_pool.py", "scripts/screen01/screen01_oc.py",
              "tests/screen01/test_screen01_build.py", "scripts/fid01/fid01_designs.py", "scripts/v18_plate.py", "scripts/unc01_verify.py", "docs/evidence/screen01_2026_10_30/states.json",
              "docs/evidence/screen01_2026_10_30/oc.json", "docs/evidence/screen01_2026_10_30/pool_prescreen_rev1/rows.jsonl", "docs/evidence/screen01_2026_10_30/pool_prescreen_rev1/design_check.json",
              "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.7_pitch_m0.38.dir_f4_fortran.raw"):
        assert f in sha, f
    assert all(f in sha for f in bound) and "scripts/screen01/INTERFACE.md" in sha and "docs/evidence/screen01_2026_10_30/crosscheck_reconciliation.md" in sha   # §10 (2026-10-31)
    assert sum(f.startswith("docs/evidence/screen01_2026_10_30/inputs/") for f in sha) == 36
    p0 = rec["p0"]
    assert len(p0["random_control"]["names"]) == 19 and len(p0["design"]["names"]) == 9 and p0["ladder"]["M"]["M_for_m_D_0.0015"] == "v18__camber_m19.7_pitch_m0.38"
    assert len(p0["stl_sha256"]) >= 6 + 9 + 1 + 1 + 19 and p0["parent_stl"]["stl_volume_m3"] > 0
    assert set(rec["analysis_sha256"]) == {"fid01", "unc01"} and {"numpy", "scipy", "scikit-image", "python"} <= set(rec["environment"]) and "src/cfd_harness/campaign_schema.py" in rec["harness_tool_sha256"]
    with pytest.raises(ValueError, match="refusing to overwrite freeze1.json"):
        F.freeze1()


def prerun_freeze(cid, smoke_sha="b" * 64, campaign_sha=None):
    """A stand-in for the harness prerun freeze of a scratch campaign file."""
    campaign = SB.HARNESS / f"{cid}_campaign.json"
    fz = campaign.with_name(f"{cid}_campaign.prerun_freeze.json")
    fz.write_text(json.dumps({"campaign_sha256": campaign_sha or SC.sha256_path(campaign), "smoke_verified_sha256": smoke_sha, "source_commit": "c" * 40}))
    fz.with_name(fz.name + ".sha256").write_text("x\n")
    return fz


def test_campaign_record_checks_the_prerun_freeze(env):
    SB.emit(SB.campaign_files("g1"), False)
    fz = prerun_freeze("screen01")
    rec, paths = F.campaign_record("screen01")
    assert rec["kernels"] == {"g1k11": {"runs": 39, "estimate_s": 16445}, "g1k12": {"runs": 38, "estimate_s": 16030}} and rec["smoke_verified_sha256"] == "b" * 64 and len(paths) == 3
    prerun_freeze("screen01", campaign_sha="d" * 64)
    with pytest.raises(ValueError, match="another campaign"):
        F.campaign_record("screen01")


def budget_record(path, walls, pending, monkeypatch):
    """A record written by the analyzer's own `budget` function (log reader stubbed: a 'log' is its wall in s), so the freeze validates the real format."""
    import analyze_screen01 as AN
    monkeypatch.setattr(AN.A, "log_wall", float)
    path.write_text(json.dumps(AN.budget([(k, str(v)) for k, v in walls], pending)))
    return path


F_PENDING = [("f48k13", None), ("f48k14", None), ("f32a", None), ("f32b", None)]


def test_budget_record_is_validated_against_the_campaigns(env, monkeypatch):
    rows = SB.load_rows()
    fk = SB.f_kernels(rows, "v18__camber_p19.7", SB.by_role(rows, "random")[0])
    finished = {"g1k11", "g1k12"}
    ok = budget_record(env / "ok.json", [("g1k11", 7000.0), ("g1k11", 100.0), ("g1k12", 7100.0)], F_PENDING, monkeypatch)
    b = F.budget(ok, fk, finished)
    assert b["T_s"] == 14200 + 2 * 7280 + 5240 + 4410 and b["decision"] == "go" and b["record_sha256"] == SC.sha256_path(ok) and b["finished_session_wall_s"]["g1k11"] == 7100.0
    with pytest.raises(ValueError, match="budget record missing"):
        F.budget(env / "none.json", fk, finished)
    stop = budget_record(env / "stop.json", [("g1k11", 40000.0), ("g1k12", 40000.0)], F_PENDING, monkeypatch)
    with pytest.raises(ValueError, match="says stop"):
        F.budget(stop, fk, finished)
    with pytest.raises(ValueError, match="finished kernels are not exactly"):
        F.budget(budget_record(env / "a.json", [("g1k11", 7000.0)], F_PENDING, monkeypatch), fk, finished)
    with pytest.raises(ValueError, match="finished kernels are not exactly"):                    # g2 ran: its wall is required
        F.budget(ok, fk, finished | {"g2"})
    for pending in (F_PENDING[:3], F_PENDING + [("g2", None)], [("f48k13", 2), ("f48k14", 3), ("f32a", None), ("f32b", None)]):
        with pytest.raises(ValueError, match="differ from the campaigns"):
            F.budget(budget_record(env / "c.json", [("g1k11", 7000.0), ("g1k12", 7100.0)], pending, monkeypatch), fk, finished)
    dropped = SB.f_kernels(rows, "v18__camber_p19.7", None)                                      # no R-best: 10 / 8 flow_32 and 2 / 2 flow_48 runs
    with pytest.raises(ValueError, match="differ from the campaigns"):                           # the record of the full 12 / 10 / 3-run kernels does not fit the dropped campaigns
        F.budget(ok, dropped, finished)
    assert F.budget(budget_record(env / "d.json", [("g1k11", 7000.0), ("g1k12", 7100.0)], [("f48k13", 2), ("f48k14", 2), ("f32a", 10), ("f32b", 8)], monkeypatch), dropped, finished)["T_s"] == 14100 + 2 * 4940 + 4410 + 3580
    bad = json.loads(ok.read_text())
    bad["T_s"] += 1.0
    with pytest.raises(ValueError, match="not the sum of its parts"):
        F.budget(write_json(env / "e.json", bad), fk, finished)
    with pytest.raises(ValueError, match="not the registered"):
        F.budget(write_json(env / "f.json", {**json.loads(ok.read_text()), "kind": "fid01_budget_decision"}), fk, finished)


def test_handoff_skeleton(env):
    rows = SB.load_rows()
    h = F.handoff_skeleton("v18__camber_p19.7", rows, {"gating": []}, {})
    assert h["finalist"]["admissibility_row"]["admissible"] and h["finalist"]["phi_fortran_order_sha256"] == rows["v18__camber_p19.7"]["phi_fortran_order_sha256"]
    assert h["parent"]["name"] == "v18__parent" and SC.is_sha(h["gate_profile_sha256"])


@pytest.fixture
def scratch_raws(monkeypatch):
    """Proposal raws go to a gitignored scratch directory (a campaign direction path must be repository-relative) that is removed afterwards."""
    d = ROOT / "work/_screen01_test_inputs"
    monkeypatch.setattr(SB, "dir_rel", lambda n: f"work/_screen01_test_inputs/{n}.raw")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_freeze2_2_1_and_3_records_in_order(env, monkeypatch, scratch_raws):
    """freeze 2 -> 2.1 -> 3 on scratch files: byte checks, prerun-freeze binding, proposals with their gating rows, the §4.3 budget and the handoff skeleton."""
    fake_repo(monkeypatch, env)
    (env / "harness").mkdir()
    (env / "inputs").mkdir()
    (env / "inputs" / "x.raw").write_bytes(b"")
    (env / "freeze1.json").write_text("{}")
    SB.emit(SB.campaign_files("g1"), False)
    prerun_freeze("screen01")
    assert json.loads(F.freeze2().read_text())["campaign"]["kernels"]["g1k11"]["runs"] == 39
    rs = rs_fixture(2)
    SB.emit(SB.campaign_files("g2", write_json(env / "rs.json", rs)), False)
    prerun_freeze("screen01_g2")
    rec = json.loads(F.freeze2_1(env / "rs.json").read_text())
    props = [p["name"] for p in rs["proposals"]]
    assert rec["rs_json_sha256"] == SC.sha256_path(env / "rs.json") and rec["g2"]["kernels"] == {"g2": {"runs": 6, "estimate_s": 6 * 415 + 260}}
    assert {n: r["gating_row"] for n, r in rec["proposals"].items()} == {g["name"]: g for g in rs["gating"]} and list(rec["proposals"]) == sorted(props)
    fin = write_json(env / "finalist.json", {"finalist": props[1], "r_best": SB.by_role(SB.load_rows(), "random")[2]})
    SB.emit(SB.campaign_files("f", finalist_path=fin), False)
    for cid in ("screen01_f", "screen01_f48"):
        prerun_freeze(cid)
    walls = [("g1k11", 7000.0), ("g1k12", 7100.0)]
    with pytest.raises(ValueError, match="finished kernels are not exactly"):
        F.freeze3(fin, budget_record(env / "wl_a.json", walls, F_PENDING, monkeypatch))          # g2 ran (states_g2.json exists): its wall is required
    with pytest.raises(ValueError, match="budget record missing"):
        F.freeze3(fin, env / "wl_missing.json")
    with pytest.raises(ValueError, match="says stop"):
        F.freeze3(fin, budget_record(env / "wl_stop.json", [("g1k11", 60000.0), ("g1k12", 7100.0), ("g2", 3000.0)], F_PENDING, monkeypatch))
    assert not (env / "freeze3.json").exists()
    budget = budget_record(env / "wl_b.json", walls + [("g2", 3000.0)], F_PENDING, monkeypatch)
    rec = json.loads(F.freeze3(fin, budget).read_text())
    assert rec["file_sha256"][SB.rel(budget)] == SC.sha256_path(budget) and rec["budget"]["record_sha256"] == SC.sha256_path(budget)   # the record is hashed with the freeze
    assert rec["finalist"] == props[1] and rec["budget"]["T_s"] == 17100 + 2 * 7280 + 5240 + 4410 and set(rec["campaigns"]) == {"screen01_f", "screen01_f48"}
    assert rec["handoff_skeleton"]["finalist"]["name"] == props[1] and rec["handoff_skeleton"]["finalist"]["spec"] == dict(sorted(P.u_to_spec(rs["proposals"][1]["u"]).items()))
    with pytest.raises(ValueError, match="no finalist"):
        F.freeze3(write_json(env / "none.json", {"finalist": None}), budget)
