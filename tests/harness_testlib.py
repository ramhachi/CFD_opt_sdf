"""Shared helpers of the harness v1 tests: the GRID-02 replay campaign description (derived from the committed inventory) and the grid02 evidence paths."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_harness import campaign_schema as SC  # noqa: E402

EV = ROOT / "docs/evidence/grid02_trend_2026_10_16"
REPLAY = ROOT / "docs/harness/replay_grid02_campaign.json"
GRID02_JOB = "scripts/waterlily_grid02_job.jl"


def replay_campaign():
    """The five GRID-02 kernels as a harness v1 campaign (identical inputs to the proven grid02 runners; for replay verification only: its Kaggle slugs already exist)."""
    inv = json.loads((EV / "inventory.json").read_text())
    states = {r["name"]: {k: r[k] for k in SC.STATE_KEYS} for r in inv["states"]}
    kernels = {}
    for k, cfg in inv["kernel_config"].items():
        case = {key: cfg["measurement"]["case"][key] for key in SC.CASE_KEYS}
        env = {"W4_CANONICAL_ORIGIN_M": cfg["W4_CANONICAL_ORIGIN_M"], **({"GRID02_CASE": cfg["GRID02_CASE"]} if cfg["GRID02_CASE"] else {})}
        config = {key: cfg[key] for key in ("W4_CANONICAL_ORIGIN_M", "canonical_origin_m", "GRID02_CASE") + SC.BUDGET_KEYS}
        kernels[k] = {"kernel_id": cfg["kernel_id"], "job": cfg["job"], "case": case, "config": config, "runs": [{"state": n, "env": env} for n in inv["kernels"][k]],
                      **({"pins": ["scripts/grid02_case.jl"]} if cfg["job"] == GRID02_JOB else {})}
    m = inv["kernel_config"]["s24"]["measurement"]
    return {"harness_version": SC.HARNESS_VERSION, "campaign_id": "grid02", "owner": "ramhachi888", "repo_url": "https://github.com/ramhachi/CFD_opt_sdf.git",
            "index_name": "grid02_index.json", "out_prefix": "grid02_", "job_env_common": inv["job_env_common"], "scrub_env": ["GRID02_CASE"],
            "measurement": {"candidate_operator": m["candidate_operator"], "time_window_t_u_l": m["time_window_t_u_l"]},
            "domain": {"flow_origin_m": [-2.5, -1.2, -0.9], "physical_box_max_m": [2.5, 1.2, 0.9]},
            "baseline": {"path": inv["parent"]["raw_path"], "sha256_fortran_raw": inv["parent"]["phi_fortran_order_sha256"]},
            "directions": {"robust_opt01a": {"path": inv["proposal"]["file"], "sha256_fortran_raw": inv["proposal"]["sha256_fortran_raw"]}},
            "states": states, "kernels": kernels, "sparse": [], "pins": ["docs/evidence/grid02_trend_2026_10_16/inventory.json"]}


if __name__ == "__main__":  # python tests/harness_testlib.py  (writes docs/harness/replay_grid02_campaign.json once)
    REPLAY.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY.open("x") as handle:
        handle.write(json.dumps(replay_campaign(), indent=2, sort_keys=True, allow_nan=False) + "\n")
