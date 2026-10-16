"""Shared helpers of the harness v1.1 tests: the GRID-02 replay campaign description (derived from the committed inventory), the grid02 evidence paths and the proven grid02 runner's fake-job harness."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_harness import campaign_schema as SC  # noqa: E402
import build_grid02_kernel as GK  # noqa: E402

EV = ROOT / "docs/evidence/grid02_trend_2026_10_16"
REPLAY = ROOT / "docs/harness/replay_grid02_campaign.json"
GRID02_JOB = "scripts/waterlily_grid02_job.jl"
OPT = ROOT / "docs/evidence/opt01b_stage_b_2026_10_15"
INV = json.loads((EV / "inventory.json").read_text())
DUMMY = "0" * 40
UUID = "GPU-11111111-2222-3333-4444-555555555555"
SMI = f"0, Tesla T4, {UUID}, 15360 MiB, 535.54.03\n"


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
            "index_name": "grid02_index.json", "out_prefix": "grid02_", "job_env_common": inv["job_env_common"], "job_env_keys": ["GRID02_CASE"], "scrub_env": ["GRID02_CASE"],
            "measurement": {"candidate_operator": m["candidate_operator"], "time_window_t_u_l": m["time_window_t_u_l"]},
            "domain": {"flow_origin_m": [-2.5, -1.2, -0.9], "physical_box_max_m": [2.5, 1.2, 0.9]},
            "baseline": {"path": inv["parent"]["raw_path"], "sha256_fortran_raw": inv["parent"]["phi_fortran_order_sha256"]},
            "directions": {"robust_opt01a": {"path": inv["proposal"]["file"], "sha256_fortran_raw": inv["proposal"]["sha256_fortran_raw"]}},
            "states": states, "kernels": kernels, "sparse": [], "pins": ["docs/evidence/grid02_trend_2026_10_16/inventory.json"], "legacy_replay": True}


# ---- the proven grid02 runner on a fake job (copied from tests/test_grid02_inputs_and_runner.py so that the harness tests do not depend on that file) ----------------------------------
def grid02_load(kernel):
    ns = {"__name__": "rendered_worker", "__file__": str(GK.TEMPLATE)}
    exec(compile(GK.render(DUMMY, kernel), f"runner_{kernel}.py", "exec"), ns)
    return ns


def grid02_source_tree(tmp):
    """A fake checkout: symlinks to the real julia/scripts/opt01b evidence and a copy of the inventory; returns (tree, inventory sha)."""
    src = tmp / "src"
    (src / "docs/evidence/grid02_trend_2026_10_16").mkdir(parents=True)
    (src / "julia").symlink_to(ROOT / "julia")
    (src / "scripts").symlink_to(ROOT / "scripts")
    (src / "docs/evidence/opt01b_stage_b_2026_10_15").symlink_to(OPT)
    target = src / "docs/evidence/grid02_trend_2026_10_16/inventory.json"
    shutil.copy(EV / "inventory.json", target)
    return src, hashlib.sha256(target.read_bytes()).hexdigest()


class Grid02Harness:
    def __init__(self, tmp, kernel, *, smi=SMI):
        self.kernel, self.calls = kernel, []
        self.ns = grid02_load(kernel)
        self.src, inv_sha = grid02_source_tree(tmp)
        self.ns["PINS"][self.ns["INVENTORY"]] = inv_sha
        (tmp / "out").mkdir()
        self.out = tmp / "out" / f"grid02_{kernel}"
        self.ns.update(OUT=self.out, nvidia_smi=lambda: smi, fetch_source=lambda base: self.src, install_julia=lambda base: Path("/fake/julia"), run=self.run)
        self.case = self.ns["CASE_ID"]
        self.rows = {r["name"]: r for r in INV["states"]}

    def run(self, args, log_path, env=None, timeout=3600):
        a = [str(x) for x in args]
        self.calls.append({"args": a, "env": env, "timeout": timeout})
        if "-e" in a:
            if "Pkg.instantiate()" in a[-1]:
                return 0
            Path(env["GRID01_GPU_PROBE_OUT"]).write_text(json.dumps({"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "visible_gpu_uuids": [UUID], "default_device_uuid": UUID,
                                                                    "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}))
            return 0
        phi, outdir = Path(a[-2]), Path(a[-1])
        name = phi.name[: -len(".phi.f32f")]
        assert hashlib.sha256(phi.read_bytes()).hexdigest() == self.rows[name]["phi_fortran_order_sha256"], "the job must receive the registered phi bytes"
        (outdir / f"{self.case}.forces.csv").write_text(f"fake forces {name}\n")
        (outdir / f"{self.case}.summary.json").write_text("{}\n")
        (outdir / "W4_JOB_DONE").write_text("done\n")
        return 0

    def jobs(self):
        return [c for c in self.calls if "-e" not in c["args"]]

    def go(self):
        try:
            self.ns["main"]()
            return 0
        except SystemExit as e:
            return e.code


if __name__ == "__main__":  # python tests/harness_testlib.py  (writes docs/harness/replay_grid02_campaign.json once)
    REPLAY.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY.open("x") as handle:
        handle.write(json.dumps(replay_campaign(), indent=2, sort_keys=True, allow_nan=False) + "\n")
