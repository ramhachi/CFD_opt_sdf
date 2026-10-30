"""G2 pre-registration: the freeze matches the files that will run; scope, directions, semantics and the no-delta rule hold."""
import hashlib
import json
from pathlib import Path

from scripts import build_grad_g2_freeze as freeze_builder

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08"
FREEZE = json.loads((E / "prerun_freeze.json").read_text())
SCOPE = "3f8b7d3e43f32633aa67106ba57f36e5be16f3e74e655bc54f862e463cc608d0"


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_every_frozen_file_hash_matches_the_working_tree():
    for name, path in freeze_builder.FILES.items():
        assert FREEZE["file_hashes"][name] == sha(path), name


def test_runner_pins_agree_with_the_freeze():
    runner = (ROOT / "infra/kaggle/kernel_grad_g2_bridge/runner.py").read_text()
    assert f'SOURCE_COMMIT = "{FREEZE["source_commit"]}"' in runner
    for rel, digest in FREEZE["pins"].items():
        assert digest in runner and sha(rel) == digest


def test_oracle_scope_semantics_and_directions_are_the_authoritative_ones():
    assert FREEZE["fd08"]["scope_record_sha256"] == SCOPE == hashlib.sha256((ROOT / "docs/evidence/fd08_v2_oracle_scope_record_2026_10_08/record.json").read_bytes()).hexdigest()
    assert FREEZE["fd08"]["response_semantics_sha256"] == {
        "drag": "068eb21bf0f4e33f8c3275210bea3369e10bc0d56e9fb80be73f31b2071d765b",
        "downforce": "346fcec44db9829121709dc9a541b270568c76eaf3c834a6cd4d2a950ce708ef"}
    assert FREEZE["fd08"]["fd_backend_fingerprint_sha256"] == "d17c81e430aaf2667009847ebaa18df0c57e203f7315ddeb2ddd61ddb9559b8e"
    assert FREEZE["fd08"]["formal_criteria_sha256"] == "31b29cccc9d3fd6912a910b09694a8230f9ee0aa84e6a418161881ffbcf907be"
    assert FREEZE["directions"]["order"] == ["D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe"]
    for name, digest in FREEZE["directions"]["fortran_raw_sha256"].items():
        assert hashlib.sha256((ROOT / f"docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/{name}.dir_f4_fortran.raw").read_bytes()).hexdigest() == digest
    assert FREEZE["canonical_state"]["state_sha256"].startswith("02f48f64")


def test_model_a_rows_are_loaded_from_the_scope_record_and_cover_eight_series():
    rows = FREEZE["fd08"]["g_hat_rows"]
    assert len(rows) == 8 and {(r[0], r[1]) for r in rows} == {(d, x) for d in FREEZE["directions"]["order"] for x in ("drag", "downforce")}
    assert all(r[2] != 0 and r[3] > 0 for r in rows)


def test_declarations_run_inventory_and_flags():
    assert FREEZE["declarations"] == {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "fd08_refit": False, "dual4": False}
    assert FREEZE["dual_width"] == 1 and len(FREEZE["run_inventory"]) == 5
    assert set(FREEZE["qualification_flags"].values()) == {False}
    assert FREEZE["fd08"]["measurement_block"]["time_window_t_u_l"] == [80.0, 120.0]
    assert FREEZE["gates"] == {"dual_vs_plain_window_mean_primal_rel": 1e-3, "plain_vs_formal_baseline_v17_rel": 1e-6, "host_vs_kernel_summary_rel": 1e-9}
