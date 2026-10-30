"""LOWDIM-01 recorded result: the kept kernel output is intact and bound to the freeze, the analysis is the registered one and reproducible, the quoted observations hold."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_lowdim01 as A  # noqa: E402
import lowdim01_states as L  # noqa: E402

E = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
K = E / "kernel_output"
FREEZE = json.loads((E / "prerun_freeze.json").read_text())
ANALYSIS = json.loads((E / "lowdim01_analysis.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_terminal_state_complete_and_the_baseline_is_byte_identical_to_fd08():
    index = json.loads((K / "lowdim01_index.json").read_text())
    assert (K / "DONE").is_file() and not (K / "ERROR.txt").exists() and index["status"] == "COMPLETE" and [e["name"] for e in index["states"]] == [p["name"] for p in L.plan()]
    assert index["states"][0]["matches_fd08_baseline_v17"] is True and index["states"][0]["forces_csv_sha256"] == FREEZE["fd08_baseline"]["forces_csv_sha256"]
    ident = json.loads((K / "run_identity.json").read_text())
    assert ident["source_commit"] == FREEZE["source_commit"] and ident["failure_stage"] is None and all(ident["verified"][r] == v for r, v in FREEZE["pins"].items())
    assert all(sha(K / rel) == digest for rel, digest in json.loads((K / "output_manifest.json").read_text())["files"].items())


def test_the_analysis_is_the_registered_one_and_reproduced_from_the_kept_output():
    assert ANALYSIS["verdict"] == "LOWDIM_ACCEPT" and ANALYSIS["selected"] == "lowdim01__prop__s1.25mm" and ANALYSIS["integrity"]["pass"] is True
    assert ANALYSIS["provenance"]["freeze_sha256"] == sha(E / "prerun_freeze.json") and ANALYSIS["provenance"]["analyzer_sha256"] == FREEZE["file_hashes"]["analyzer"] == sha(ROOT / "scripts/analyze_lowdim01.py")
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_gradient_claim"] is True and ANALYSIS["not_opt01"] is True and ANALYSIS["reinitialization"] == "none"
    assert set(ANALYSIS["qualification_flags"].values()) == {False}
    again = A.analyze(K, FREEZE)
    assert again["verdict"] == "LOWDIM_ACCEPT" and A.clean(again["candidates"]) == json.loads(json.dumps(A.clean(ANALYSIS["candidates"]))) and A.clean(again["controls"]) == json.loads(json.dumps(A.clean(ANALYSIS["controls"])))


def test_the_quoted_observations_hold():
    c, ctl = ANALYSIS["candidates"], ANALYSIS["controls"]
    a = c["lowdim01__prop__s1.25mm"]
    assert a["accepted"] is True and 4.0e-4 < a["downforce_change_n"] < 4.1e-4 and a["drag_change_n"] < 0 and all(a["geometry_gates"].values())
    assert sum(1 for v in c.values() if v["accepted"]) == 1 and c["lowdim01__prop__s7.5mm"]["hard_geometry_gates_pass"] is False
    assert c["lowdim01__prop__s2.5mm"]["downforce_change_n"] < 0 and c["lowdim01__prop__s5mm"]["downforce_change_n"] < c["lowdim01__prop__s2.5mm"]["downforce_change_n"]
    assert all(v["downforce_change_n"] < 0 and v["never_accepted_or_selected"] is True for v in ctl.values())
    odd = ANALYSIS["proposal_sign_check_descriptive"]
    for s in ("1.25", "2.5"):
        lin = c[f"lowdim01__prop__s{s}mm"]["linear_predicted_downforce_change_n_reference_only"]
        assert abs(odd[s]["odd_part_n"] / lin - 1) < 0.04 and odd[s]["even_part_n"] < 0                 # the odd part follows the FD prediction; the even part is negative and ~s^2
    assert abs(odd["2.5"]["even_part_n"] / odd["1.25"]["even_part_n"] - 4.0) < 0.1
    assert ANALYSIS["baseline"] == {"downforce_n": 0.3316344583180616, "drag_n": 0.3239039699743226}


def test_earlier_records_are_untouched():
    assert FREEZE["step01_analysis_sha256"] == sha(ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json")
    assert FREEZE["file_hashes"]["formal_criteria"] == sha(ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json")
