"""SCREEN-01 (#64): the P0 derivations pinned (source review Q6): the pools, the hand-design ladder, the D-optimal design, the `u_to_spec` rounding, the dependency fingerprint and the
random-control set, all against the committed P0 record (`pool_prescreen_rev1/`).  Read-only: nothing here writes the record or touches the work/ caches."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01"), str(ROOT / "scripts/screen01")]
import fid01_designs as D  # noqa: E402
import screen01_pool as P  # noqa: E402

REC = P.OUT                                                                                       # docs/evidence/screen01_2026_10_30/pool_prescreen_rev1


def rows(slot=None):
    out = [json.loads(line) for line in (REC / "rows.jsonl").read_text().splitlines()]
    return [r for r in out if slot is None or r["slot"] == slot]


def summary():
    return json.loads((REC / "summary.json").read_text())


# the registered (frozen) names, pinned from the 2026-10-30 record; the P0 re-run must reproduce them (registration §3.4)
RS_FIRST3 = ["v18__camber_p0.507_pitch_m0.744_reflex_p11.354", "v18__camber_m10.959_pitch_p0.27_reflex_m25.616", "v18__camber_p8.327_pitch_p2.795_reflex_p23.291"]
LADDER_1_5E3 = ["v18__camber_m19.7_pitch_m0.38", "v18__camber_m19.7_reflex_p10.5", "v18__camber_m19.7_pitch_m0.29", "v18__camber_m19.7_pitch_m0.47",
                "v18__camber_m19.7_pitch_m0.19_reflex_p5.2"]
DESIGN = ["v18__camber_m21.959_pitch_m2.307_reflex_m24.023", "v18__camber_p3.261_pitch_m3.085_reflex_p28.738", "v18__camber_m19.789_pitch_m0.621_reflex_p26.168",
          "v18__camber_m25.466_pitch_p2.31_reflex_p4.633", "v18__camber_m0.502_pitch_m2.372_reflex_m27.474", "v18__camber_p16.113_pitch_p1.042_reflex_p28.057",
          "v18__camber_p15.009_pitch_p2.043_reflex_m11.687", "v18__camber_m23.394_pitch_p0.776_reflex_m21.432", "v18__camber_p15.396_pitch_m1.812_reflex_m17.01"]


def test_rs_pool_is_the_registered_scrambled_sobol_sequence():
    """What `screen01_pool.py gen` writes to pools.json (recomputed here without writing): 256 points of seed 20261030, the first three names pinned."""
    gen = [P.u_to_spec(u) for u in P.sobol_u(P.N_RS_MAX, P.SEED_RS)]
    assert [D.name(s) for s in gen[:3]] == RS_FIRST3
    assert P.SEED_RS == 20261030 and P.N_RS0 == 64 and P.N_RS_MAX == 256 and P.MIN_ADM_RS == 12
    pools = json.loads((REC / "pools.json").read_text())["pools"]
    assert pools["rs"] == gen and [D.name(s) for s in pools["rs"][:3]] == RS_FIRST3
    assert pools["rand3"] == [P.u_to_spec(u) for u in P.sobol_u(P.N_RAND_MAX, P.SEED_RAND)] and P.SEED_RAND == 20261033
    assert [r["name"] for r in rows("rs")[:3]] == RS_FIRST3 and [r["index"] for r in rows("rs")] == list(range(len(rows("rs"))))


def test_manual_ladder_for_m_d_1_5e3_is_the_registered_one():
    assert P.M_D == 1.5e-3
    assert [D.name(s) for s in P.manual_ladder(1.5e-3)] == LADDER_1_5E3                              # registration §3.3
    first_admissible = next(r["name"] for n in LADDER_1_5E3 for r in rows("manual") if r["name"] == n and r["admissible"])
    assert first_admissible == "v18__camber_m19.7_pitch_m0.38" == summary()["pools"]["manual"]["M_for_m_D_0.0015"]


def test_d_optimal_design_is_the_registered_nine_points():
    adm = [r for r in rows("rs") if r["admissible"]]
    U = np.array([P.spec_to_u(r["spec"]) for r in adm])
    idx, X = P.d_optimal9(U, 9)
    assert [adm[j]["name"] for j in idx] == DESIGN
    sv = np.linalg.svd(X, compute_uv=False)
    dc = json.loads((REC / "design_check.json").read_text())
    assert X.shape == (15, 9) and np.linalg.matrix_rank(X) == 9 and abs(sv[0] / sv[-1] - dc["cond"]) <= 1e-9 and abs(sv[0] / sv[-1] - 3.5070) <= 1e-4
    assert dc["design_points"] == DESIGN and dc["design_admissible"] is True and dc["rank"] == 9


def test_u_to_spec_rounding_and_sorted_keys():
    assert P.u_to_spec([-0.0, 0.0, 0.0]) == {} and P.u_to_spec([0.0, -0.0, 0.0]) == {}              # a zero amplitude is dropped, a negative zero too
    assert P.u_to_spec([0.0, 0.0, 0.0004 / 29.3]) == {} and P.u_to_spec([-0.0004 / 3.1, 0.0, 0.0]) == {}   # below the 1e-3 rounding: no amplitude, no "-0.0" key
    assert P.u_to_spec([0.0005 / 3.1, 0.0, 0.0]) == {"pitch": 0.001}                                 # 0.0005 deg rounds (as float arithmetic gives it) to one rounding step
    assert P.u_to_spec([0.0, -1.5, 0.0]) == {"camber": -29.55}                                       # the camber extension limit, exact
    spec = P.u_to_spec([1.0, -1.0, 0.5])
    assert spec == {"camber": -19.7, "pitch": 3.1, "reflex": 14.65} and list(spec) == sorted(spec)  # keys sorted: the §3.2 name order
    assert D.name(spec) == "v18__camber_m19.7_pitch_p3.1_reflex_p14.65"
    assert P.spec_to_u({"camber": -19.7, "pitch": 3.1}) == [1.0, -1.0, 0.0]


def test_fingerprint_covers_existing_dependency_files():
    fp = P.fingerprint()
    assert re.fullmatch("[0-9a-f]{64}", fp) and fp == P.fingerprint()
    assert P.DEPENDENCIES == sorted(set(P.DEPENDENCIES)) and len(P.DEPENDENCIES) >= 60
    assert all((ROOT / f).is_file() for f in P.DEPENDENCIES) and set(D.DEPENDENCIES) <= set(P.DEPENDENCIES)
    assert {"scripts/fid01/fid01_designs.py", "scripts/fid01/fid01_build.py", "src/cfd_sdf/design/geometry_gates_v2.py",
            "docs/evidence/geom02_v17_gates_2026_10_14/geom02_resolved_research_policy.json", "docs/evidence/v18_genesis_2026_10_19/v18_parent.npz"} <= set(P.DEPENDENCIES)


def test_selfcheck_passes_in_a_fresh_interpreter():
    """`selfcheck` asserts that the gate stack's import closure is inside DEPENDENCIES; that reads sys.modules, so it needs an interpreter of its own (pytest has loaded the test modules)."""
    out = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/screen01/screen01_pool.py"), "selfcheck"], capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    res = json.loads(out.stdout[out.stdout.index("{"):])
    assert res["ok"] is True and res["fingerprint"] == P.fingerprint() and res["n_dependencies"] == len(P.DEPENDENCIES)


def test_random_control_set_is_the_first_19_admissible_members_in_sequence_order():
    rand = sorted(rows("rand3"), key=lambda r: r["index"])
    adm = [r for r in rand if r["admissible"]]
    first19 = adm[:P.K_RAND]
    assert P.K_RAND == 19 and len(first19) == 19 and len(rand) >= first19[-1]["index"] + 1
    assert [r["name"] for r in first19] == summary()["pools"]["rand3"]["control_set"]
    assert first19[-1]["index"] + 1 == 36                                                            # registration §3.4: the 19th admissible member is sequence point 36
    assert [r["index"] for r in rand] == list(range(len(rand)))


def test_p0_record_after_the_rerun_carries_fingerprint_dependencies_and_n_consumed():
    summ = summary()
    if "fingerprint" not in summ:
        pytest.skip("the committed P0 summary predates the P0 re-run (no fingerprint yet; registration §3.4)")
    assert summ["fingerprint"] == P.fingerprint() and summ["dependencies"] == P.DEPENDENCIES
    assert all(pool["error_rows"] == [] for pool in summ["pools"].values())
    last = max(i for i, r in enumerate(sorted(rows("rand3"), key=lambda r: r["index"])) if r["name"] in set(summ["pools"]["rand3"]["control_set"]))
    assert summ["pools"]["rand3"]["n_consumed"] == last + 1 == 36                                  # the 19th admissible member's index + 1 (the chunk end is n_evaluated)
    assert json.loads((REC / "design_check.json").read_text())["rand3"]["n_consumed"] == 36
