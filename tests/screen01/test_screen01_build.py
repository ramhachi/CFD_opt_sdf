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
            "gating": [{**r, "name": r["name"], "u": u[r["name"]], "target_index": i % 3, "y_pred": 1e-2, "z_pred": -2e-3, "admissible": True} for i, r in enumerate(sel)],
            "comparable": {"g1_controls": {"invalid_at_step_2": False}}, **kw}


def write_json(path, obj):
    path.write_text(json.dumps(obj))
    return path


def cfg(kernel):
    return [kernel["config"][x] for x in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")]


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
        assert len({r["env"]["W4_CANONICAL_ORIGIN_M"] for r in kern["runs"]}) == 1             # one phase per kernel
    assert [cfg(k[x]) for x in ("g1k11", "g1k12")] == [[900, 24300, 27600], [900, 23700, 27000]]
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
    assert cfg(g2) == [900, 6300, 9600] and SB.FB.estimate_s(g2) == 10 * 415 + 260 == 4410
    new = json.loads(files[env / "states_g2.json"])
    assert sorted((r["order"], r["role"], n) for n, r in new["states"].items()) == [(i, "proposal", n) for i, n in enumerate(props)]
    assert new["rs_json_sha256"] == SB.FB.sha(env / "rs.json") and set(c["states"]) == {"v18__parent", *props}
    assert all(SC.sha256_bytes(files[SB.ROOT / new["states"][n]["direction_path"]]) == new["states"][n]["direction_sha256_fortran_raw"] for n in props)
    small = SB.campaign_files("g2", write_json(env / "rs3.json", rs_fixture(3)))
    assert len(json.loads(small[env / "harness" / "screen01_g2_campaign.json"])["kernels"]["g2"]["runs"]) == 8


def test_g2_refusals(env):
    assert SB.campaign_files("g2", write_json(env / "rs0.json", rs_fixture(0, proposals=[], gating=[]))) == {}   # no proposal, no g2 kernel
    with pytest.raises(SystemExit, match="lack comparable.g1_controls"):
        SB.campaign_files("g2", write_json(env / "rsx.json", {"proposals": [], "gating": []}))                  # fail-closed: the chain-control report is required
    with pytest.raises(SystemExit, match="invalid_at_step_2"):
        SB.campaign_files("g2", write_json(env / "rsi.json", rs_fixture(2, comparable={"g1_controls": {"invalid_at_step_2": True}})))
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
                          ["v18__camber_m21.959_pitch_m2.307_reflex_m24.023"]["u"]}], "gating": [], "comparable": {"g1_controls": {"invalid_at_step_2": False}}}
    with pytest.raises(SystemExit):                                                              # a design point is not a new state
        SB.campaign_files("g2", write_json(env / "e.json", dup))


# ---- F ---------------------------------------------------------------------------------------------------------------------------------------------
def f_files(env, finalist, r_best, invalid=False):
    return SB.campaign_files("f", finalist_path=write_json(env / "finalist.json", {"finalist": finalist, "r_best": r_best, "comparable": {"g1_controls": {"invalid_at_step_2": invalid}}}))


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
        assert cfg(kern) == [6000, 10600, 13900] and SB.FB.estimate_s(kern) == 7280
    a, b = f32["kernels"]["f32a"], f32["kernels"]["f32b"]
    assert names(a) == [f"{s}__k{k}" for k in (13, 14) for s in ctrl] + ["v18__parent__k11", "v18__parent__repeat__k13"] and len(a["runs"]) == 12   # replay, then the repeat last
    assert names(b) == [f"{s}__k{k}" for k in (15, 16) for s in ctrl] and len(b["runs"]) == 10
    assert cfg(a) == [900, 7500, 10800] and cfg(b) == [900, 6300, 9600]
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
    with pytest.raises(SystemExit, match="invalid_at_step_2"):                                  # a decided INVALID: F is not generated (as a null finalist)
        f_files(env, "v18__pitch_p3.1", None, invalid=True)
    with pytest.raises(SystemExit, match="lack comparable.g1_controls"):
        SB.campaign_files("f", finalist_path=write_json(env / "fx.json", {"finalist": "v18__pitch_p3.1", "r_best": None}))
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


def test_caps_timeouts_and_smoke_kernels_follow_registration_4_2(env):
    from cfd_harness import campaign_build as CB
    table = {"g1k11": (900, 24300, 27600), "g1k12": (900, 23700, 27000), "g2": (900, 6300, 9600), "f48k13": (6000, 10600, 13900), "f48k14": (6000, 10600, 13900),
             "f32a": (900, 7500, 10800), "f32b": (900, 6300, 9600)}                                # the §4.2 table
    assert {k: SB.cap_rule(k) for k in SB.FORMAL} == table
    rows = SB.load_rows()
    camps = {}
    for f in (SB.campaign_files("g1"), f_files(env, "v18__camber_p19.7", SB.by_role(rows, "random")[0]),
              SB.campaign_files("g2", write_json(env / "rs.json", rs_fixture(2)))):
        camps.update({json.loads(t)["campaign_id"]: json.loads(t) for p, t in f.items() if p.parent == env / "harness"})
    assert set(camps) == {"screen01", "screen01_f", "screen01_f48", "screen01_g2"}
    kernels = {k: v for c in camps.values() for k, v in c["kernels"].items()}
    for k, v in kernels.items():
        assert v["config"]["solver_wall_time_cap_s"] + 3000 <= v["config"]["kernel_timeout_s"], k      # reserve + instantiate + probe fit the timeout
        assert v["config"]["kernel_timeout_s"] <= 27600 < 12 * 3600                                    # inside the 12 h session
        if k in table:
            assert cfg(v) == list(table[k]), k
    assert cfg(kernels["f32smk"]) == [890, 890, 4200] and cfg(kernels["f48smk"]) == [5990, 5990, 9300]
    assert {c: CB.smoke_kernel(camps[c]) for c in camps} == dict(SB.SMOKE_KERNEL)                  # the harness default picks the registered smoke kernel, also without --kernel
    # a kernel with fewer runs keeps the registered cap (empty R-best)
    dropped = SB.f_kernels(rows, "v18__camber_p19.7", None)
    assert cfg(dropped["screen01_f"]["f32a"]) == [900, 7500, 10800] and cfg(dropped["screen01_f48"]["f48k13"]) == [6000, 10600, 13900]


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
    """git without a repository: clean tree, HEAD on a remote branch, every listed path 'tracked' if it exists (a missing non-glob path fails like `git ls-files`).
    Returns the dict whose "untracked" entry is what `git status --porcelain` (with untracked files) prints."""
    state = {"untracked": ""}

    def tracked(p):
        found = list(ROOT.glob(p)) if "*" in p else [ROOT / p]
        SC.req(all(f.exists() for f in found) and found, f"not tracked: {p}")
        return [SB.rel(x) for f in found for x in ([f] if f.is_file() else f.rglob("*")) if x.is_file()]

    def git(*a):
        if a[0] == "status":
            return "" if "--untracked-files=no" in a else state["untracked"]
        return {"rev-parse": "a" * 40, "fetch": "", "ls-remote": "a" * 40 + " refs/heads/x"}[a[0]]
    monkeypatch.setattr(F, "EV", ev)
    monkeypatch.setattr(F, "tracked", tracked)
    monkeypatch.setattr(F, "git", git)
    monkeypatch.setattr(F.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    return state


def test_freeze_refuses_untracked_files_under_the_registered_directories(tmp_path, monkeypatch):
    state = fake_repo(monkeypatch, tmp_path)
    for path in ("scripts/screen01/new.py", "tests/screen01/", "src/cfd_sdf/x.py", "docs/harness/screen01_campaign.json", "docs/evidence/screen01_2026_10_30/inputs/"):
        state["untracked"] = f"?? {path}"
        with pytest.raises(ValueError, match="untracked files under the registered directories"):
            F.record("freeze9", [], {})
    state["untracked"] = "?? work/screen01_pool_prescreen/\n?? docs/other/note.md"                      # elsewhere an untracked file is not a freeze input
    assert F.record("freeze9", [], {}).name == "freeze9.json"


def test_freezes_2_to_3_refuse_when_the_harness_tools_differ_from_freeze_1(tmp_path, monkeypatch):
    fake_repo(monkeypatch, tmp_path)
    (tmp_path / "freeze1.json").write_text(json.dumps({"harness_tool_sha256": {**SC.tool_hashes(), "scripts/harness.py": "0" * 64}}))
    with pytest.raises(ValueError, match="harness tool hashes differ from freeze 1"):
        F.freeze2(tmp_path / "t.json")
    with pytest.raises(ValueError, match="harness tool hashes differ from freeze 1"):
        F.freeze2_1(tmp_path / "rs.json")
    with pytest.raises(ValueError, match="harness tool hashes differ from freeze 1"):
        F.freeze3(tmp_path / "f.json", tmp_path / "rs.json")


def test_reused_covers_the_pool_dependencies():
    assert set(P.DEPENDENCIES) <= set(F.REUSED) and len(P.DEPENDENCIES) >= 60 and all((ROOT / f).is_file() for f in F.REUSED)
    assert {"scripts/analyze_unc01.py", "scripts/fid01/fid01_harness.py", "scripts/unc01_verify.py", "docs/evidence/unc01_2026_10_20/states.json"} <= set(F.REUSED)


@pytest.fixture
def p0_current(tmp_path, monkeypatch):
    """A copy of the committed P0 record whose summary carries the fields the P0 re-run writes (fingerprint, dependencies, error_rows), so freeze 1 can be exercised before and after the re-run."""
    d = tmp_path / "p0"
    d.mkdir()
    for f in ("pools.json", "rows.jsonl", "summary.json", "design_check.json"):
        (d / f).write_text((SB.P0 / f).read_text())
    summ = json.loads((d / "summary.json").read_text())
    summ.update(fingerprint=P.fingerprint(), dependencies=P.DEPENDENCIES)
    for pool in summ["pools"].values():
        pool.setdefault("error_rows", [])
    (d / "summary.json").write_text(json.dumps(summ))
    monkeypatch.setattr(SB, "P0", d)
    monkeypatch.setattr(SB, "emit", lambda files, check: None)                                    # the states byte check is test_states_on_disk_byte_check's (the copy's file hashes differ)
    return d


@ON_DISK
def test_freeze1_refuses_without_the_infra_signature_table(tmp_path, monkeypatch, p0_current):
    fake_repo(monkeypatch, tmp_path)
    monkeypatch.setattr(F, "BOUND_EVIDENCE", ["docs/evidence/screen01_2026_10_30/no_such_infra_signatures.json", *F.BOUND_EVIDENCE[1:]])
    with pytest.raises(ValueError, match="infra_signatures.json .* is missing"):
        F.freeze1()
    assert not (tmp_path / "freeze1.json").exists()


@ON_DISK
def test_freeze1_refuses_a_p0_record_that_is_not_the_reviewed_one(tmp_path, monkeypatch, p0_current):
    fake_repo(monkeypatch, tmp_path)
    good = json.loads((p0_current / "summary.json").read_text())
    for edit, match in (({"fingerprint": "0" * 64}, "re-run P0 from empty caches"), ({"fingerprint": None}, "re-run P0 from empty caches"),
                        ({"dependencies": P.DEPENDENCIES[:-1]}, "dependency list differs"), ({"dependencies": None}, "dependency list differs")):
        (p0_current / "summary.json").write_text(json.dumps({**good, **edit}))
        with pytest.raises(ValueError, match=match):
            F.freeze1()
    for pool in good["pools"]:                                                                  # any pool with an error row (Q7) or without the key (an old record)
        bad = json.loads(json.dumps(good))
        bad["pools"][pool]["error_rows"] = ["v18__x"]
        (p0_current / "summary.json").write_text(json.dumps(bad))
        with pytest.raises(ValueError, match="gate evaluation raised"):
            F.freeze1()
        del bad["pools"][pool]["error_rows"]
        (p0_current / "summary.json").write_text(json.dumps(bad))
        with pytest.raises(ValueError, match="gate evaluation raised"):
            F.freeze1()
    assert not (tmp_path / "freeze1.json").exists()


@ON_DISK
def test_freeze1_content(tmp_path, monkeypatch, p0_current):
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
              "tests/screen01/test_screen01_build.py", "tests/screen01/test_screen01_pool.py", "scripts/fid01/fid01_designs.py", "scripts/v18_plate.py", "scripts/unc01_verify.py",
              "scripts/analyze_unc01.py", "docs/evidence/screen01_2026_10_30/states.json", "docs/evidence/unc01_2026_10_20/states.json", "docs/evidence/screen01_2026_10_30/oc.json",
              "docs/evidence/screen01_2026_10_30/pool_prescreen_rev1/rows.jsonl", "docs/evidence/screen01_2026_10_30/pool_prescreen_rev1/design_check.json",
              "docs/evidence/screen01_2026_10_30/source_review/adoption.md", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.7_pitch_m0.38.dir_f4_fortran.raw", *P.DEPENDENCIES):
        assert f in sha, f
    assert all(f in sha for f in bound) and "scripts/screen01/INTERFACE.md" in sha and "docs/evidence/screen01_2026_10_30/crosscheck_reconciliation.md" in sha   # §10 (2026-10-31)
    assert sum(f.startswith("docs/evidence/screen01_2026_10_30/inputs/") for f in sha) == 36
    assert all("/" in k for k in sha) and len({Path(k).name for k in sha}) < len(sha)           # repo-relative keys: two states.json live side by side
    p0 = rec["p0"]
    assert p0["fingerprint"] == P.fingerprint() and p0["n_dependencies"] == len(P.DEPENDENCIES)
    assert len(p0["random_control"]["names"]) == 19 and len(p0["design"]["names"]) == 9 and p0["ladder"]["M"]["M_for_m_D_0.0015"] == "v18__camber_m19.7_pitch_m0.38"
    assert len(p0["stl_sha256"]) >= 6 + 9 + 1 + 1 + 19 and p0["parent_stl"]["stl_volume_m3"] > 0
    assert set(rec["analysis_sha256"]) == {"fid01", "unc01"} and {"numpy", "scipy", "scikit-image", "python"} <= set(rec["environment"]) and "src/cfd_harness/campaign_schema.py" in rec["harness_tool_sha256"]
    with pytest.raises(ValueError, match="refusing to overwrite freeze1.json"):
        F.freeze1()


@ON_DISK
def test_freeze1_record_is_accepted_by_the_analyzer(tmp_path, monkeypatch, p0_current):
    """B1/R7: the analyzer looks every frozen file up by its repo-relative key; the real freeze-1 record (two states.json in it) passes `frozen_sources` and `load_roles`."""
    import analyze_screen01 as AN
    fake_repo(monkeypatch, tmp_path)
    if not (ROOT / F.BOUND_EVIDENCE[0]).exists():
        pytest.skip("infra_signatures.json is not written yet")
    rec = json.loads(F.freeze1().read_text())
    AN.frozen_sources(rec)
    roles = AN.load_roles(SB.STATES, rec)
    assert roles["v18__parent"]["role"] == "parent" and roles["v18__parent__repeat"]["role"] == "parent_repeat" and len(roles) == 39
    bad = json.loads(json.dumps(rec))
    bad["file_sha256"]["docs/evidence/screen01_2026_10_30/states.json"] = "0" * 64
    with pytest.raises(ValueError):
        AN.load_roles(SB.STATES, bad)


def prerun_freeze(cid, smoke_sha="b" * 64, campaign_sha=None):
    """A stand-in for the harness prerun freeze of a scratch campaign file."""
    campaign = SB.HARNESS / f"{cid}_campaign.json"
    fz = campaign.with_name(f"{cid}_campaign.prerun_freeze.json")
    fz.write_text(json.dumps({"campaign_sha256": campaign_sha or SC.sha256_path(campaign), "smoke_verified_sha256": smoke_sha, "source_commit": "c" * 40}))
    fz.with_name(fz.name + ".sha256").write_text("x\n")
    return fz


def smoke_table(cid, kernel=None):
    """A stand-in for `harness.py verify --smoke --out` of a scratch campaign (kernel defaults to the registered smoke kernel), with the prerun freeze that verified it."""
    campaign = SB.HARNESS / f"{cid}_campaign.json"
    table = SB.HARNESS / f"{cid}_smoke_table.json"
    table.write_text(json.dumps({"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "smoke": True, "campaign_sha256": SC.sha256_path(campaign),
                                 "kernel_manifest_sha256": {kernel or SB.SMOKE_KERNEL[cid]: "e" * 64}}))
    prerun_freeze(cid, smoke_sha=SC.sha256_path(table))
    return table


def test_campaign_record_checks_the_prerun_freeze_and_the_smoke_table(env):
    SB.emit(SB.campaign_files("g1"), False)
    good = smoke_table("screen01")
    rec, paths = F.campaign_record("screen01", good)
    assert rec["kernels"] == {"g1k11": {"runs": 39, "estimate_s": 16445}, "g1k12": {"runs": 38, "estimate_s": 16030}} and rec["smoke_kernel"] == "g1k11"
    assert rec["smoke_verified_sha256"] == SC.sha256_path(good) and len(paths) == 4 and SB.rel(good) in paths                      # the table is bound with the freeze
    other = smoke_table("screen01", kernel="g1k12")                                              # wrong kernel (the table of kernel g1k12 verified by the prerun freeze)
    with pytest.raises(ValueError, match="must verify exactly kernel g1k11"):
        F.campaign_record("screen01", other)
    two = SB.HARNESS / "two.json"
    two.write_text(json.dumps({**json.loads(good.read_text()), "kernel_manifest_sha256": {"g1k11": "e" * 64, "g1k12": "e" * 64}}))
    prerun_freeze("screen01", smoke_sha=SC.sha256_path(two))
    with pytest.raises(ValueError, match="must verify exactly kernel g1k11"):                  # a table of two kernels is not the registered smoke
        F.campaign_record("screen01", two)
    good = smoke_table("screen01")
    prerun_freeze("screen01", smoke_sha="d" * 64)                                                # the prerun freeze verified another table (wrong SHA-256)
    with pytest.raises(ValueError, match="not the one the prerun freeze verified"):
        F.campaign_record("screen01", good)
    prerun_freeze("screen01", smoke_sha=SC.sha256_path(good))
    t = json.loads(good.read_text())
    good.write_text(json.dumps({**t, "smoke": False}))
    prerun_freeze("screen01", smoke_sha=SC.sha256_path(good))
    with pytest.raises(ValueError, match="must verify exactly kernel"):                          # a formal table is not a smoke table
        F.campaign_record("screen01", good)
    with pytest.raises(ValueError, match="smoke table is missing"):
        F.campaign_record("screen01", None)
    good = smoke_table("screen01")
    prerun_freeze("screen01", smoke_sha=SC.sha256_path(good), campaign_sha="d" * 64)
    with pytest.raises(ValueError, match="another campaign"):
        F.campaign_record("screen01", good)


def test_smoke_dirs_are_required(env, monkeypatch):
    monkeypatch.setattr(F, "EV", env)
    with pytest.raises(ValueError, match="smoke output directories missing"):
        F.smoke_dirs("smoke")
    (env / "wl" / "smoke").mkdir(parents=True)
    assert F.smoke_dirs("smoke") == [SB.rel(env / "wl" / "smoke")]


def budget_record(path, walls, pending, monkeypatch):
    """A record written by the analyzer's own `budget` function (log reader stubbed: a 'log' is its wall in s), so the freeze validates the real format."""
    import analyze_screen01 as AN
    monkeypatch.setattr(AN.A, "log_wall", float)
    path.write_text(json.dumps(AN.budget([(k, str(v)) for k, v in walls], pending)))
    return path


F_PENDING = [("f48k13", None), ("f48k14", None), ("f32a", None), ("f32b", None)]


def expected_of(f_kernels):
    return {k: SB.FB.estimate_s(v) for ks in f_kernels.values() for k, v in ks.items() if k in SB.FORMAL}


def test_budget_record_is_validated_against_the_campaigns(env, monkeypatch):
    rows = SB.load_rows()
    fk = SB.f_kernels(rows, "v18__camber_p19.7", SB.by_role(rows, "random")[0])
    est, finished = expected_of(fk), {"g1k11", "g1k12"}
    ok = budget_record(env / "ok.json", [("g1k11", 7000.0), ("g1k11", 100.0), ("g1k12", 7100.0)], F_PENDING, monkeypatch)
    b = F.budget(ok, est, finished)
    assert b["T_s"] == 14200 + 2 * 7280 + 5240 + 4410 and b["decision"] == "go" and b["record_sha256"] == SC.sha256_path(ok) and b["finished_session_wall_s"]["g1k11"] == 7100.0
    with pytest.raises(ValueError, match="budget record missing"):
        F.budget(env / "none.json", est, finished)
    with pytest.raises(ValueError, match="budget record missing"):
        F.budget(None, est, finished)
    stop = budget_record(env / "stop.json", [("g1k11", 40000.0), ("g1k12", 40000.0)], F_PENDING, monkeypatch)
    with pytest.raises(ValueError, match="says stop"):
        F.budget(stop, est, finished)
    with pytest.raises(ValueError, match="finished kernels are not exactly"):
        F.budget(budget_record(env / "a.json", [("g1k11", 7000.0)], F_PENDING, monkeypatch), est, finished)
    with pytest.raises(ValueError, match="finished kernels are not exactly"):                    # g2 ran: its wall is required
        F.budget(ok, est, finished | {"g2"})
    for pending in (F_PENDING[:3], F_PENDING + [("g2", None)], [("f48k13", 2), ("f48k14", 3), ("f32a", None), ("f32b", None)]):
        with pytest.raises(ValueError, match="differ from the campaigns"):
            F.budget(budget_record(env / "c.json", [("g1k11", 7000.0), ("g1k12", 7100.0)], pending, monkeypatch), est, finished)
    dropped = expected_of(SB.f_kernels(rows, "v18__camber_p19.7", None))                         # no R-best: 10 / 8 flow_32 and 2 / 2 flow_48 runs
    with pytest.raises(ValueError, match="differ from the campaigns"):                           # the record of the full 12 / 10 / 3-run kernels does not fit the dropped campaigns
        F.budget(ok, dropped, finished)
    assert F.budget(budget_record(env / "d.json", [("g1k11", 7000.0), ("g1k12", 7100.0)], [("f48k13", 2), ("f48k14", 2), ("f32a", 10), ("f32b", 8)], monkeypatch), dropped,
                    finished)["T_s"] == 14100 + 2 * 4940 + 4410 + 3580
    bad = json.loads(ok.read_text())
    bad["T_s"] += 1.0
    with pytest.raises(ValueError, match="not the sum of its parts"):
        F.budget(write_json(env / "e.json", bad), est, finished)
    with pytest.raises(ValueError, match="not the registered"):
        F.budget(write_json(env / "f.json", {**json.loads(ok.read_text()), "kind": "fid01_budget_decision"}), est, finished)


def test_handoff_skeleton(env):
    rows = SB.load_rows()
    h = F.handoff_skeleton("v18__camber_p19.7", rows, {"gating": []}, {})
    assert h["finalist"]["admissibility_row"]["admissible"] and h["finalist"]["phi_fortran_order_sha256"] == rows["v18__camber_p19.7"]["phi_fortran_order_sha256"]
    assert h["parent"]["name"] == "v18__parent" and SC.is_sha(h["gate_profile_sha256"]) and h["policy_sha256"] == SC.sha256_path(ROOT / F.POLICY) and SC.is_sha(h["source_review_adoption_sha256"])


@pytest.fixture
def scratch_raws(monkeypatch):
    """Proposal raws go to a gitignored scratch directory (a campaign direction path must be repository-relative) that is removed afterwards."""
    d = ROOT / "work/_screen01_test_inputs"
    monkeypatch.setattr(SB, "dir_rel", lambda n: f"work/_screen01_test_inputs/{n}.raw")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def scratch_freeze_dir(env, monkeypatch):
    """freeze 1 stand-in (harness tools as running), the wl/ smoke directories and an `inputs` directory under the scratch evidence directory."""
    fake_repo(monkeypatch, env)
    (env / "harness").mkdir()
    (env / "inputs").mkdir()
    (env / "inputs" / "x.raw").write_bytes(b"")
    for n in ("smoke", "smoke_g2", "smoke_f", "smoke_f48"):
        (env / "wl" / n).mkdir(parents=True)
        (env / "wl" / n / "x").write_text("x")
    (env / "freeze1.json").write_text(json.dumps({"harness_tool_sha256": SC.tool_hashes()}))


G2_PENDING = lambda n: [("g2", n), *F_PENDING]  # noqa: E731


def analyzer(env, monkeypatch):
    """The analyzer pointed at the scratch evidence directory (its freeze-chain keys are then the scratch paths, as the writer records them)."""
    import analyze_screen01 as AN
    monkeypatch.setattr(AN, "EV", env)
    monkeypatch.setattr(AN, "EV_REL", env.as_posix())
    return AN


def freezes(env, *names):
    return {n: json.loads((env / f"{n}.json").read_text()) for n in names}


def prerun_sha(cid):
    return SC.sha256_path(SB.HARNESS / f"{cid}_campaign.prerun_freeze.json")


def test_freeze2_2_1_and_3_records_in_order(env, monkeypatch, scratch_raws):
    """freeze 2 -> 2.1 -> 3 on scratch files: byte checks, prerun-freeze and smoke-table binding, proposals with their gating rows, the §4.3 budget records and the handoff skeleton."""
    scratch_freeze_dir(env, monkeypatch)
    AN = analyzer(env, monkeypatch)
    camp = lambda cid: SB.HARNESS / f"{cid}_campaign.json"  # noqa: E731
    SB.emit(SB.campaign_files("g1"), False)
    smoke_table("screen01")
    rec = json.loads(F.freeze2(SB.HARNESS / "screen01_smoke_table.json").read_text())
    assert rec["campaign"]["kernels"]["g1k11"]["runs"] == 39 and rec["campaign"]["smoke_kernel"] == "g1k11" and SB.rel(SB.HARNESS / "screen01_smoke_table.json") in rec["file_sha256"]
    AN.check_chain(freezes(env, "freeze1", "freeze2"))
    assert AN.campaign_entry(rec, camp("screen01"))["prerun_freeze_sha256"] == prerun_sha("screen01")        # the analyzer finds exactly this campaign's record
    rs = rs_fixture(2)
    SB.emit(SB.campaign_files("g2", write_json(env / "rs.json", rs)), False)
    smoke_table("screen01_g2")
    walls = [("g1k11", 7000.0), ("g1k12", 7100.0)]
    with pytest.raises(ValueError, match="budget record missing"):                               # the G2 push is a push after G1 (§4.3): its record is required
        F.freeze2_1(env / "rs.json", None, SB.HARNESS / "screen01_g2_smoke_table.json")
    with pytest.raises(ValueError, match="smoke table is missing"):
        F.freeze2_1(env / "rs.json", budget_record(env / "b21.json", walls, G2_PENDING(6), monkeypatch), None)
    with pytest.raises(ValueError, match="differ from the campaigns"):                           # every unfinished kernel counts, the confirmation kernels at their registered run counts
        F.freeze2_1(env / "rs.json", budget_record(env / "b21x.json", walls, [("g2", 6)], monkeypatch), SB.HARNESS / "screen01_g2_smoke_table.json")
    assert not (env / "freeze2_1.json").exists()
    b21 = budget_record(env / "b21.json", walls, G2_PENDING(6), monkeypatch)
    rec = json.loads(F.freeze2_1(env / "rs.json", b21, SB.HARNESS / "screen01_g2_smoke_table.json").read_text())
    props = [p["name"] for p in rs["proposals"]]
    assert rec["rs_json_sha256"] == SC.sha256_path(env / "rs.json") and rec["g2"]["kernels"] == {"g2": {"runs": 6, "estimate_s": 6 * 415 + 260}} and rec["g2"]["smoke_kernel"] == "g2"
    assert rec["budget"]["record_sha256"] == SC.sha256_path(b21) and rec["budget"]["T_s"] == 14100 + 2750 + 2 * 7280 + 5240 + 4410 and rec["invalid_at_step_2"] is False
    assert {n: r["gating_row"] for n, r in rec["proposals"].items()} == {g["name"]: g for g in rs["gating"]} and list(rec["proposals"]) == sorted(props)
    AN.check_chain(freezes(env, "freeze1", "freeze2", "freeze2_1"))
    assert AN.campaign_entry(rec, camp("screen01_g2"))["prerun_freeze_sha256"] == prerun_sha("screen01_g2")
    with pytest.raises(ValueError, match="no campaign record"):                                  # freeze 2.1 does not name the g1 or the confirmation campaigns
        AN.campaign_entry(rec, camp("screen01"))
    fin = write_json(env / "finalist.json", {"finalist": props[1], "r_best": SB.by_role(SB.load_rows(), "random")[2], "comparable": {"g1_controls": {"invalid_at_step_2": False}}})
    SB.emit(SB.campaign_files("f", finalist_path=fin), False)
    smoke_table("screen01_f")
    smoke_table("screen01_f48")
    tf, tf48 = SB.HARNESS / "screen01_f_smoke_table.json", SB.HARNESS / "screen01_f48_smoke_table.json"
    f3 = [("g1k11", 7000.0), ("g1k12", 7100.0)]
    with pytest.raises(ValueError, match="finished kernels are not exactly"):
        F.freeze3(fin, env / "rs.json", budget_record(env / "wl_a.json", f3, F_PENDING, monkeypatch), tf, tf48)       # g2 ran (states_g2.json exists): its wall is required
    with pytest.raises(ValueError, match="budget record missing"):
        F.freeze3(fin, env / "rs.json", env / "wl_missing.json", tf, tf48)
    with pytest.raises(ValueError, match="says stop"):
        F.freeze3(fin, env / "rs.json", budget_record(env / "wl_stop.json", [("g1k11", 60000.0), ("g1k12", 7100.0), ("g2", 3000.0)], F_PENDING, monkeypatch), tf, tf48)
    budget = budget_record(env / "wl_b.json", f3 + [("g2", 3000.0)], F_PENDING, monkeypatch)
    with pytest.raises(ValueError, match="is not the one frozen in freeze2_1.json"):
        F.freeze3(fin, write_json(env / "rs_other.json", {**rs, "x": 1}), budget, tf, tf48)
    with pytest.raises(ValueError, match="not the one the prerun freeze verified"):              # the f48 table where the flow_32 one belongs
        F.freeze3(fin, env / "rs.json", budget, tf48, tf48)
    assert not (env / "freeze3.json").exists()
    rec = json.loads(F.freeze3(fin, env / "rs.json", budget, tf, tf48).read_text())
    assert rec["file_sha256"][SB.rel(budget)] == SC.sha256_path(budget) and rec["budget"]["record_sha256"] == SC.sha256_path(budget) and rec["pushed"] is True   # hashed with the freeze
    assert rec["finalist"] == props[1] and rec["budget"]["T_s"] == 17100 + 2 * 7280 + 5240 + 4410 and set(rec["campaigns"]) == {"screen01_f", "screen01_f48"}
    assert {c["smoke_kernel"] for c in rec["campaigns"].values()} == {"f32smk", "f48smk"} and rec["file_sha256"][SB.rel(env / "rs.json")] == SC.sha256_path(env / "rs.json")
    assert rec["handoff_skeleton"]["finalist"]["name"] == props[1] and rec["handoff_skeleton"]["finalist"]["spec"] == dict(sorted(P.u_to_spec(rs["proposals"][1]["u"]).items()))
    assert SC.is_sha(rec["handoff_skeleton"]["policy_sha256"])
    AN.check_chain(freezes(env, "freeze1", "freeze2", "freeze2_1", "freeze3"))                   # the whole pushed chain
    for cid in ("screen01_f", "screen01_f48"):
        assert AN.campaign_entry(rec, camp(cid))["prerun_freeze_sha256"] == prerun_sha(cid)
    with pytest.raises(ValueError, match="no campaign record"):
        AN.campaign_entry(rec, camp("screen01_g2"))
    (env / "freeze2_1.json").write_text((env / "freeze2_1.json").read_text() + " ")             # an edited earlier freeze is refused: freeze 3 binds freeze 2.1 as it was
    with pytest.raises(ValueError, match="freeze3.json does not bind freeze2_1.json"):
        AN.check_chain(freezes(env, "freeze1", "freeze2", "freeze2_1", "freeze3"))
    (env / "freeze1.json").write_text(json.dumps({"edited": True}))
    with pytest.raises(ValueError, match="freeze2.json does not bind freeze1.json"):
        AN.check_chain(freezes(env, "freeze1", "freeze2"))


def test_freeze2_1_without_a_g2_campaign_needs_no_budget_or_smoke(env, monkeypatch):
    fake_repo(monkeypatch, env)
    AN = analyzer(env, monkeypatch)
    (env / "freeze1.json").write_text(json.dumps({"harness_tool_sha256": SC.tool_hashes()}))
    (env / "freeze2.json").write_text("{}")
    rec = json.loads(F.freeze2_1(write_json(env / "rs.json", rs_fixture(0, proposals=[], gating=[]))).read_text())
    assert rec["g2"].startswith("none (no proposal") and rec["invalid_at_step_2"] is False and "budget" not in rec and "proposals" not in rec
    AN.check_chain(freezes(env, "freeze2", "freeze2_1"))
    with pytest.raises(ValueError, match="no campaign record"):                                  # there is no g2 campaign record for the analyzer to find
        AN.campaign_entry(rec, ROOT / "scripts/screen01/screen01_build.py")
    (env / "freeze2_1.json").unlink()
    invalid = write_json(env / "rs_inv.json", rs_fixture(2, comparable={"g1_controls": {"invalid_at_step_2": True}}))
    rec = json.loads(F.freeze2_1(invalid).read_text())                                           # a decided INVALID: no G2 campaign even though proposals exist
    assert rec["g2"].startswith("none (invalid_at_step_2") and rec["invalid_at_step_2"] is True and "proposals" not in rec
    AN.check_chain(freezes(env, "freeze2", "freeze2_1"))
    (env / "freeze2.json").write_text("{ }")                                                    # an edited earlier freeze is refused
    with pytest.raises(ValueError, match="freeze2_1.json does not bind freeze2.json"):
        AN.check_chain(freezes(env, "freeze2", "freeze2_1"))


def test_freeze3_is_written_without_f_for_a_null_finalist_and_for_invalid_at_step_2(env, monkeypatch):
    fake_repo(monkeypatch, env)
    AN = analyzer(env, monkeypatch)
    (env / "freeze1.json").write_text(json.dumps({"harness_tool_sha256": SC.tool_hashes()}))
    (env / "freeze2.json").write_text("{}")
    rs = write_json(env / "rs.json", rs_fixture(0, proposals=[], gating=[]))
    F.freeze2_1(rs)                                                                              # the chain through the writer: freeze 2.1 without a G2 campaign, then freeze 3
    for name, fin in (("null", {"finalist": None, "r_best": None}), ("invalid", {"finalist": "v18__pitch_p3.1", "r_best": None})):
        fj = write_json(env / f"finalist_{name}.json", {**fin, "comparable": {"g1_controls": {"invalid_at_step_2": name == "invalid"}}})
        rec = json.loads(F.freeze3(fj, rs).read_text())                                          # no --budget, no smoke tables, no campaigns
        assert rec["pushed"] is False and rec["finalist_json_sha256"] == SC.sha256_path(fj) and rec["invalid_at_step_2"] is (name == "invalid") and rec["finalist"] == fin["finalist"]
        assert not {"campaigns", "budget", "handoff_skeleton"} & set(rec) and SB.rel(fj) in rec["file_sha256"] and SB.rel(rs) in rec["file_sha256"]
        AN.check_chain(freezes(env, "freeze2", "freeze2_1", "freeze3"))
        with pytest.raises(ValueError, match="no campaign record"):                              # nothing for the analyzer to find: the confirmation campaigns were not generated
            AN.campaign_entry(rec, ROOT / "scripts/screen01/screen01_build.py")
        (env / "freeze3.json").unlink()
    F.freeze3(fj, rs)
    AN.check_chain(freezes(env, "freeze2_1", "freeze3"))
    rec21 = env / "freeze2_1.json"
    rec21.write_text(rec21.read_text() + " ")                                                    # an edited freeze 2.1: freeze 3 no longer binds it as it is on disk
    with pytest.raises(ValueError, match="freeze3.json does not bind freeze2_1.json"):
        AN.check_chain(freezes(env, "freeze2_1", "freeze3"))
    with pytest.raises(ValueError, match="is not the one frozen in freeze2_1.json"):
        F.freeze3(fj, write_json(env / "rs_other.json", {"x": 1}))
    with pytest.raises(SystemExit, match="lack comparable.g1_controls"):                         # the chain-control report is required of every finalist.json
        F.freeze3(write_json(env / "f_old.json", {"finalist": None}), rs)
