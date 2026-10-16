"""harness v1: the single schema shared by the Kaggle runner, the build/freeze/smoke tools and the verifier (one place for every name).

Stdlib only (plus scripts/fd08_v2_campaign_io.py): the rendered runner loads this file by path from the pinned source checkout, so it must not import `cfd_sdf`.
Nothing here is a measurement or a qualification: it only fixes the names, the shapes and the integrity checks of the WaterLily T4 campaign outputs.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path

try:
    from fd08_v2_campaign_io import FORCE_COLUMNS, recompute_force_n
except ImportError:  # imported from src/ without scripts/ on the path (repo or sparse checkout: <root>/src/cfd_harness/this file)
    sys.path.append(str(Path(__file__).resolve().parents[2] / "scripts"))
    from fd08_v2_campaign_io import FORCE_COLUMNS, recompute_force_n

HARNESS_VERSION = "harness v1"
INDEX_NAME_DEFAULT = "harness_index.json"
IDENTITY_NAME, MANIFEST_NAME, DONE_NAME, ERROR_NAME, JOB_DONE_NAME = "run_identity.json", "output_manifest.json", "DONE", "ERROR.txt", "W4_JOB_DONE"
SMI_NAME, PROBE_NAME, PROBE_LOG_NAME, SELF_TEST_NAME = "nvidia_smi.csv", "gpu_device_probe.json", "gpu_device_probe.log", "self_test.json"
RUNNER_FILE, METADATA_FILE = "runner.py", "kernel-metadata.json"
PIN_BEGIN, PIN_END = "# --- PIN BEGIN (the only lines that differ between a formal and a smoke render) ---", "# --- PIN END ---"

SHA = re.compile("[0-9a-f]{64}")
COMMIT = re.compile("[0-9a-f]{40}")
SLUG = re.compile("[a-z0-9]+(-[a-z0-9]+)*")
NAME = re.compile("[A-Za-z0-9_.-]+")

# ---- campaign.json -------------------------------------------------------------------------------------------------------------------------------
CAMPAIGN_KEYS = ("harness_version", "campaign_id", "owner", "repo_url", "index_name", "out_prefix", "job_env_common", "scrub_env", "measurement", "domain", "baseline", "directions",
                 "states", "kernels", "sparse", "pins")
# state identity: phi_fortran = SHA of the Fortran-order float32 bytes (what the Julia DeviceGridSDF roundtrip hashes), phi_c = SHA of the C-order bytes: two DIFFERENT fields
STATE_IDENTITY_KEYS = ("state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "zero_level_margin_m", "margin_tolerance_m", "changed_node_count", "maximum_pointwise_change_m")
STATE_KEYS = ("kind", "direction", "step_mm", "sign") + STATE_IDENTITY_KEYS
STATE_KINDS = ("parent", "parent_repeat", "candidate", "control")
STATE_ENV = {"W4_STATE_SHA256": "state_sha256", "W4_STATE_NPZ_SHA256": "npz_sha256", "W4_PHI_C_ORDER_SHA256": "phi_c_order_sha256", "W4_PHI_FORTRAN_SHA256": "phi_fortran_order_sha256",
             "W4_EXPECTED_MARGIN_M": "zero_level_margin_m"}
DEVICE_ENV = ("CUDA_DEVICE_ORDER", "CUDA_VISIBLE_DEVICES", "JULIA_NUM_THREADS")
COMMON_ENV_KEYS = ("W4_CANONICAL_DESIGN_SPACING_M", "W4_CANONICAL_STATE_LABEL", "W4_POINT_SHAPE", "W4_CELL_SHAPE", "W4_SOURCE_SURFACE_SHA256", "W4_MARGIN_GATE_M")
ORIGIN_ENV = "W4_CANONICAL_ORIGIN_M"  # in job_env_common or (per state, per kernel) in a run's env
BUDGET_KEYS = ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s", "instantiate_timeout_s", "gpu_probe_timeout_s", "reserve_s")
CASE_KEYS = ("case_id", "flow_dims", "flow_spacing_m", "solver_length", "solver_time_unit_s", "solver_viscosity", "reynolds", "density_kg_m3", "dynamic_viscosity_pa_s", "reference_length_m",
             "reference_area_m2", "freestream_mps")
KERNEL_KEYS = ("kernel_id", "job", "case", "config", "runs")
KERNEL_OPTIONAL = ("pins", "first_state_csv_sha256")  # extra pinned repo paths of this kernel; SHA-256 of the retained historical force CSV the first state must reproduce byte for byte

# ---- runner outputs ------------------------------------------------------------------------------------------------------------------------------
INDEX_KEYS = ("kernel", "kernel_id", "case_id", "states", "status")
INDEX_OPTIONAL = ("solver_process_wall_seconds_total", "parent_forces_csv_sha256")
INDEX_STATUS = ("RUNNING", "COMPLETE", "ERROR")
INDEX_ENTRY_KEYS = ("name", "kind", "direction", "step_mm", "sign", "exit_code", "seconds", "forces_csv_sha256", "complete")
IDENTITY_KEYS = ("runner_sha256", "python_version", "numpy_version", "platform", "kernel", "kernel_id", "source_commit", "pins", "direction_files", "config", "expected_names", "case_id",
                 "failure_stage", "verified", "selected_gpu", "cuda_device_order", "cuda_visible_devices")
IDENTITY_HARNESS_KEYS = ("harness_version", "campaign_sha256", "smoke")  # absent in the pre-harness GRID-02 outputs (replay), required of a harness runner
GPU_EXPECTED = {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}
FREEZE_KIND, TABLE_KIND = "harness_prerun_freeze", "harness_state_force_table"
# job summary: the keys the verifier reads (Julia jobs write more; these are the ones that bind identity, grid, budget and force means)
SUMMARY_FORCE_KEYS = {"drag": "drag_time_weighted_n", "downforce": "downforce_time_weighted_n"}
SUMMARY_NUMERIC_KEYS = ("flow_spacing_m", "solver_length", "solver_time_unit_s", "solver_viscosity", "reynolds", "density_kg_m3", "dynamic_viscosity_pa_s", "reference_length_m", "reference_area_m2")
SUMMARY_FLAG_KEYS = ("finite_u", "finite_p", "finite_forces")
SUMMARY_TOL = 1e-9
FORCE_PROJECTION = "drag=+Fx; downforce=-Fz"
STATE_TABLE_KEYS = ("drag_n", "downforce_n", "forces_csv_sha256", "summary_sha256", "solver_process_wall_seconds", "julia_summary_wall_seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path) -> str:
    """File SHA-256, or for a directory the SHA-256 of 'relative  filehash' lines (no __pycache__)."""
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo"))
        return sha256_bytes(("\n".join(f"{p.relative_to(path)}  {sha256_path(p)}" for p in files) + "\n").encode())
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def jload(path):
    def reject(value):
        raise ValueError(f"nonfinite JSON constant {value}")
    return json.loads(Path(path).read_text(), parse_constant=reject)


def req(ok, message):
    if not ok:
        raise ValueError(message)


def is_sha(v):
    return isinstance(v, str) and SHA.fullmatch(v) is not None


def finite(x, label="value"):
    req(not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x), f"{label} must be a finite number")
    return float(x)


def equal(actual, expected, label):
    """JSON-level equality (keeps the bool-versus-number and int-versus-float distinction)."""
    req(json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False), f"{label} differs from the declaration")


def safe_rel(relative):
    rel = Path(relative) if isinstance(relative, str) else None
    req(rel is not None and rel.parts and not rel.is_absolute() and ".." not in rel.parts and rel != Path("."), f"unsafe path: {relative!r}")
    return rel


def forces_name(case_id):
    return f"{case_id}.forces.csv"


def summary_name(case_id):
    return f"{case_id}.summary.json"


def index_name(c):
    return c["index_name"]


def out_dir_name(c, kernel):
    return f"{c['out_prefix']}{kernel}"


def run_names(kernel):
    return [r["state"] for r in kernel["runs"]]


def effective_env(c, run):
    """The job environment a run sees apart from the per-state identity variables and the GPU UUID."""
    return {**c["job_env_common"], **run["env"]}


def force_scale_n(case):
    """N per solver force unit: rho U^2 dx^2 (same expression as recompute_force_n)."""
    return case["density_kg_m3"] * case["freestream_mps"][0] ** 2 * case["flow_spacing_m"] ** 2


def floats(text):
    return [float(v) for v in text.split(",")]


# ---- campaign validation -------------------------------------------------------------------------------------------------------------------------
def validate_state(name, row, directions):
    req(isinstance(name, str) and NAME.fullmatch(name), f"bad state name {name!r}")
    req(isinstance(row, dict) and set(row) == set(STATE_KEYS), f"state {name}: keys must be exactly {STATE_KEYS}")
    req(row["kind"] in STATE_KINDS, f"state {name}: unknown kind")
    for k in ("state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256"):
        req(is_sha(row[k]), f"state {name}: {k} is not a SHA-256")
    for k in ("zero_level_margin_m", "margin_tolerance_m", "maximum_pointwise_change_m", "step_mm"):
        finite(row[k], f"state {name} {k}")
    req(type(row["changed_node_count"]) is int and type(row["sign"]) is int, f"state {name}: integer fields")
    if row["direction"] is None:  # the baseline phi itself
        req(row["step_mm"] == 0 and row["sign"] == 0 and row["changed_node_count"] == 0, f"state {name}: a baseline state has no step, sign or change")
    else:
        req(row["direction"] in directions and row["step_mm"] > 0 and row["sign"] in (1, -1) and row["changed_node_count"] > 0, f"state {name}: unregistered perturbation")


def validate_kernel(c, k, kernel):
    req(NAME.fullmatch(k) and isinstance(kernel, dict) and set(KERNEL_KEYS) <= set(kernel) <= set(KERNEL_KEYS + KERNEL_OPTIONAL), f"kernel {k}: keys")
    kid = kernel["kernel_id"]
    req(isinstance(kid, str) and kid.startswith(c["owner"] + "/") and SLUG.fullmatch(kid.split("/", 1)[1]), f"kernel {k}: kernel_id must be <owner>/<slug>")
    req(isinstance(kernel["job"], str), f"kernel {k}: job")
    safe_rel(kernel["job"])
    case = kernel["case"]
    req(isinstance(case, dict) and set(case) == set(CASE_KEYS) and NAME.fullmatch(case["case_id"]), f"kernel {k}: case keys must be exactly {CASE_KEYS}")
    for key in CASE_KEYS[2:-1]:
        finite(case[key], f"kernel {k} case {key}")
    req(isinstance(case["flow_dims"], list) and len(case["freestream_mps"]) == 3, f"kernel {k}: case shape")
    cfg = kernel["config"]
    req(isinstance(cfg, dict) and set(BUDGET_KEYS) <= set(cfg), f"kernel {k}: config needs {BUDGET_KEYS}")
    for key in BUDGET_KEYS:
        req(finite(cfg[key], key) > 0, f"kernel {k}: {key} must be positive")
    req(cfg["per_state_timeout_s"] <= cfg["solver_wall_time_cap_s"] and cfg["solver_wall_time_cap_s"] + cfg["reserve_s"] + cfg["instantiate_timeout_s"] + cfg["gpu_probe_timeout_s"] <= cfg["kernel_timeout_s"],
        f"kernel {k}: the aggregate solver cap is vacuous or does not fit the kernel timeout once setup and reserve are paid")
    runs = kernel["runs"]
    req(isinstance(runs, list) and runs and len({r.get("state") for r in runs}) == len(runs), f"kernel {k}: runs must be a nonempty list of distinct states")
    for r in runs:
        req(set(r) == {"state", "env"} and r["state"] in c["states"] and isinstance(r["env"], dict) and all(isinstance(a, str) and isinstance(b, str) for a, b in r["env"].items()), f"kernel {k}: run {r}")
        req(all(cfg[a] == b for a, b in r["env"].items() if a in cfg), f"kernel {k}: a run env contradicts the kernel config")
        env = effective_env(c, r)
        req(ORIGIN_ENV in env and len(floats(env[ORIGIN_ENV])) == 3, f"kernel {k}: {ORIGIN_ENV} missing for {r['state']}")
    req(c["states"][runs[0]["state"]]["direction"] is None, f"kernel {k}: the first state must be a baseline state")
    req(all(isinstance(p, str) and safe_rel(p) for p in kernel.get("pins", [])), f"kernel {k}: pins must be safe repository paths")
    req(kernel.get("first_state_csv_sha256") is None or is_sha(kernel["first_state_csv_sha256"]), f"kernel {k}: first_state_csv_sha256")


def validate_campaign(c):
    req(isinstance(c, dict) and set(c) == set(CAMPAIGN_KEYS), f"campaign keys must be exactly {CAMPAIGN_KEYS}")
    req(c["harness_version"] == HARNESS_VERSION, "harness version differs")
    req(isinstance(c["campaign_id"], str) and re.fullmatch("[a-z0-9_]+", c["campaign_id"]) and re.fullmatch("[a-z0-9-]+", c["owner"]), "campaign_id / owner")
    req(isinstance(c["repo_url"], str) and NAME.fullmatch(c["index_name"]) and NAME.fullmatch(c["out_prefix"]), "repo_url / index_name / out_prefix")
    req(isinstance(c["job_env_common"], dict) and set(COMMON_ENV_KEYS) <= set(c["job_env_common"]) and all(isinstance(v, str) for v in c["job_env_common"].values()), f"job_env_common needs {COMMON_ENV_KEYS}")
    req(isinstance(c["scrub_env"], list) and all(isinstance(v, str) for v in c["scrub_env"]), "scrub_env")
    m = c["measurement"]
    req(set(m) == {"candidate_operator", "time_window_t_u_l"} and isinstance(m["candidate_operator"], str) and len(m["time_window_t_u_l"]) == 2 and 0 <= finite(m["time_window_t_u_l"][0]) < finite(m["time_window_t_u_l"][1]),
        "measurement must be {candidate_operator, time_window_t_u_l: [start, end]}")
    req(set(c["domain"]) == {"flow_origin_m", "physical_box_max_m"} and all(len(v) == 3 for v in c["domain"].values()), "domain")
    for label, d in [("baseline", c["baseline"])] + [(f"direction {n}", d) for n, d in c["directions"].items()]:
        req(set(d) == {"path", "sha256_fortran_raw"} and is_sha(d["sha256_fortran_raw"]), f"{label}: {{path, sha256_fortran_raw}}")
        safe_rel(d["path"])
    req(isinstance(c["states"], dict) and c["states"] and isinstance(c["kernels"], dict) and c["kernels"], "states / kernels must be nonempty objects")
    for name, row in c["states"].items():
        validate_state(name, row, c["directions"])
    ids = []
    for k, kernel in c["kernels"].items():
        validate_kernel(c, k, kernel)
        ids.append(kernel["kernel_id"])
    req(len(set(ids)) == len(ids), "kernel ids must be distinct")
    req(all(isinstance(p, str) and safe_rel(p) for p in c["sparse"] + c["pins"]), "sparse / pins must be safe repository paths")


# ---- runner / output records ---------------------------------------------------------------------------------------------------------------------
def new_index(kernel, kernel_id, case_id=None):
    return {"kernel": kernel, "kernel_id": kernel_id, "case_id": case_id, "states": [], "status": "RUNNING"}


def index_entry(name, row, exit_code, seconds, csv_sha, complete):
    return {"name": name, "kind": row["kind"], "direction": row["direction"], "step_mm": row["step_mm"], "sign": row["sign"], "exit_code": exit_code, "seconds": seconds,
            "forces_csv_sha256": csv_sha, "complete": complete}


def validate_index(index, terminal=False):
    req(isinstance(index, dict) and set(INDEX_KEYS) <= set(index), "index keys")
    req(index["status"] in INDEX_STATUS and (not terminal or index["status"] == "COMPLETE"), "index status")
    for e in index["states"]:
        req(set(INDEX_ENTRY_KEYS) <= set(e) and isinstance(e["complete"], bool), f"index entry keys: {e.get('name')}")


def validate_identity(identity, harness=True):
    req(isinstance(identity, dict) and set(IDENTITY_KEYS + (IDENTITY_HARNESS_KEYS if harness else ())) <= set(identity), "run identity keys")
    req(not harness or (identity["harness_version"] == HARNESS_VERSION and is_sha(identity["campaign_sha256"]) and type(identity["smoke"]) is bool), "harness identity fields")


def build_manifest(out):
    out = Path(out)
    return {"files": {str(p.relative_to(out)): sha256_path(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != MANIFEST_NAME}}


def required_files(c, kernel, names, harness=True):
    case = kernel["case"]["case_id"]
    files = {index_name(c), IDENTITY_NAME, SMI_NAME, PROBE_NAME, PROBE_LOG_NAME, DONE_NAME} | ({SELF_TEST_NAME} if harness else set())
    return files | {f"states/{n}/{f}" for n in names for f in (forces_name(case), summary_name(case), JOB_DONE_NAME)}


def check_manifest(out, required):
    out = Path(out)
    req(not out.is_symlink() and not any(p.is_symlink() for p in out.rglob("*")), "symlinks are not permitted in kernel output")
    files = jload(out / MANIFEST_NAME)["files"]
    req(isinstance(files, dict) and files, "manifest files map is missing or empty")
    req(set(files) == {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p.name != MANIFEST_NAME}, "manifest path set differs from actual output")
    req(set(required) <= set(files), "manifest omits required output files")
    for relative, digest in files.items():
        safe_rel(relative)
        req(is_sha(digest) and sha256_path(out / relative) == digest, f"manifest hash mismatch or malformed digest: {relative}")


def job_env(c, run, row, base_env, gpu_uuid):
    """The environment of one state's Julia job: common env, per-state identity, the selected GPU, then the run's own overrides (origin, GRID02_CASE, ...)."""
    env = dict(base_env)
    for key in c["scrub_env"]:
        env.pop(key, None)
    env.update(c["job_env_common"])
    for key in DEVICE_ENV:
        if env.get(key) != base_env.get(key):
            raise RuntimeError(f"state environment changes probed device/thread configuration: {key}")
    env["W4_SELECTED_GPU_UUID"] = gpu_uuid
    env.update({var: str(row[key]) for var, key in STATE_ENV.items()})
    env.update(run["env"])
    return env


def expected_summary(c, kernel, run, row, gpu_uuid):
    """Exact-equality expectations for one state's job summary (device_roundtrip_sha256 is the Fortran-order phi SHA: DeviceGridSDF hashes the Fortran-order bytes)."""
    env, case, ints = effective_env(c, run), kernel["case"], lambda s: [int(v) for v in s.split(",")]
    return {"canonical_sdf_origin_m": floats(env[ORIGIN_ENV]), "canonical_design_spacing_m": float(env["W4_CANONICAL_DESIGN_SPACING_M"]), "canonical_state_label": env["W4_CANONICAL_STATE_LABEL"],
            "canonical_design_point_shape": ints(env["W4_POINT_SHAPE"]), "canonical_design_cell_shape": ints(env["W4_CELL_SHAPE"]), "source_surface_sha256": env["W4_SOURCE_SURFACE_SHA256"],
            "device_roundtrip_sha256": row["phi_fortran_order_sha256"], "flow_origin_m": c["domain"]["flow_origin_m"], "physical_box_max_m": c["domain"]["physical_box_max_m"],
            "cells_per_reference_length": int(case["solver_length"]), "case_id": case["case_id"], "gpu_name": "Tesla T4", "gpu_uuid": gpu_uuid, "phi_fortran_sha256": row["phi_fortran_order_sha256"],
            "phi_c_order_sha256": row["phi_c_order_sha256"], "state_sha256": row["state_sha256"], "state_npz_sha256": row["npz_sha256"], "force_integration_body": c["measurement"]["candidate_operator"],
            "force_projection_semantics": FORCE_PROJECTION, "flow_dims": case["flow_dims"], "freestream_mps": case["freestream_mps"]}


def check_summary(summary, c, kernel, run, row, gpu_uuid):
    """Identity, grid, finiteness, window, margin and wall-time checks of one job summary; raises ValueError on the first failure."""
    for key, want in expected_summary(c, kernel, run, row, gpu_uuid).items():
        equal(summary.get(key), want, f"summary {key}")
    case, env, (start, end) = kernel["case"], effective_env(c, run), c["measurement"]["time_window_t_u_l"]
    for key in SUMMARY_NUMERIC_KEYS:
        req(math.isclose(finite(summary.get(key), key), finite(case[key], key), rel_tol=1e-12, abs_tol=1e-15), f"summary {key} differs from the case")
    req(all(summary.get(key) is True for key in SUMMARY_FLAG_KEYS), "state fields or forces are not finite")
    req(type(summary.get("julia_threads")) is int and summary["julia_threads"] == 1, "summary Julia thread count differs")
    req(finite(summary.get("t_end_reached"), "horizon") >= end and finite(summary.get("burn_in_t_u_l"), "burn in") == start, "summary time window/horizon differs")
    req(abs(finite(summary.get("phi_margin_m"), "SDF margin") - row["zero_level_margin_m"]) <= row["margin_tolerance_m"] and finite(summary.get("phi_margin_gate_m"), "margin gate") == float(env["W4_MARGIN_GATE_M"]),
        "summary SDF margin differs")
    wall = finite(summary.get("wall_seconds"), "Julia wall time")
    req(0 < wall <= kernel["config"]["per_state_timeout_s"], "Julia summary wall time exceeds budget")
    return wall


def host_forces(csv_path, c, kernel, summary):
    """Host recomputation of the time-weighted forces with the case's force scale; must agree with the Julia summary at 1e-9 relative."""
    host = recompute_force_n(csv_path, {"measurement": {"case": kernel["case"], "time_window_t_u_l": c["measurement"]["time_window_t_u_l"]}})
    req(host["force_scale_n_per_solver_force"] == force_scale_n(kernel["case"]), "host force scale differs from the case force scale")
    for q, key in SUMMARY_FORCE_KEYS.items():
        want = finite(summary.get(key), f"summary {q}")
        req(abs(host[f"{q}_n"] - want) / max(abs(want), 1e-300) <= SUMMARY_TOL, "host recomputation differs from Julia force summary")
    return host


def selftest_force_check():
    """Planted truth: a constant synthetic force history must recompute to exactly its known mean times the force scale (drag = Fx, downforce = -Fz, components consistent)."""
    case = {"density_kg_m3": 1.0, "freestream_mps": [1.0, 0.0, 0.0], "flow_spacing_m": 0.5}
    rows = ["," .join(FORCE_COLUMNS)] + [",".join(repr(float(v)) for v in (i, 10 + i, 2.0, 0.0, -3.0, 2.0, 3.0, 1.0, 0.0, -2.0, 1.0, 0.0, -1.0)) for i in range(8)]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.csv"
        path.write_text("\n".join(rows) + "\n")
        got = recompute_force_n(path, {"measurement": {"case": case, "time_window_t_u_l": [11.0, 15.0]}})
    req(got["drag_n"] == 2.0 * 0.25 and got["downforce_n"] == 3.0 * 0.25, "self-test: planted force means were not recovered")
