"""Reproduce the Amendment 2 short CPU checks, never full-window/GPU jobs.

Each flow subprocess has a 480 s safety limit. This is independent of the
uncapped, separately recorded result-side full pytest run.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent
ENV = {**os.environ, "G2_BACKEND": "cpu", "G2_DRYRUN_T_END": "0.4",
       "TA1_PREFLIGHT_ONLY": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
ENV.pop("TA1_BLOCK_LIMIT", None)
ENV.pop("GRAD00_PREFLIGHT_ONLY", None)
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
REFERENCE = ROOT / "docs/evidence/grad00_lambda_2026_11/reference.json"
PHI = ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
INPUTS = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
JOB = ROOT / "scripts/waterlily_grad00_lambda_2026_11.jl"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def execute(name, command, env, source_paths):
    directory = OUT / name
    directory.mkdir()  # Refuse any reused validation output.
    print("CPU_CHECK_BEGIN", name, flush=True)
    before = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    started = time.monotonic()
    with (directory / "output.txt").open("w") as log:
        try:
            code = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=480).returncode
        except subprocess.TimeoutExpired:
            code = 124
    result = {"evidence_class": "short_cpu_software_validation", "command": command,
              "env": {k: env[k] for k in ("G2_BACKEND", "G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY",
                                          "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "GRAD00_ARM", "GRAD00_T") if k in env},
              "process_cap_s": 480, "wall_seconds": time.monotonic() - started,
              "exit_code": code, "source_sha256_before": before,
              "source_sha256_after": {str(p.relative_to(ROOT)): sha(p) for p in source_paths},
              "log_sha256": sha(directory / "output.txt")}
    index_path = directory / "grad00_index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text())
        result.update(index_status=index["status"], preflight_pass=index.get("preflight", {}).get("pass"),
                      index_sha256=sha(index_path))
    dump(directory / "execution.json", result)
    print("CPU_CHECK_END", name, code, result.get("index_status"), round(result["wall_seconds"], 2), flush=True)
    return result


def main():
    reference = json.loads(REFERENCE.read_text())
    profiles = [("CFDSDFWaterLily", arm, "Float32")
                for arm in ("quick", "quick_nobound", "cds", "vanLeer", "vanLeer_safe")]
    profiles += [("CFDSDFWaterLily110", "quick", "Float32"),
                 ("CFDSDFWaterLily", "quick", "Float64"),
                 ("CFDSDFWaterLily", "quick_nobound", "Float64")]
    results = {}
    for project, arm, precision in profiles:
        name = f"{project}_{arm}_{precision}"
        env = {**ENV, "GRAD00_ARM": arm, "GRAD00_T": precision}
        command = ["julia", "--startup-file=no", "-O2", "-t", "10", f"--project={ROOT / 'julia' / project}",
                   str(JOB), str(PHI), sha(PHI), str(OUT / name)]
        for direction in DIRECTIONS:
            path = INPUTS / f"{direction}.dir_f4_fortran.raw"
            command += [str(path), sha(path)]
        command += [str(reference["directions"][d]["epsilon_m"]) for d in DIRECTIONS]
        sources = [JOB, ROOT / "scripts/quick_nobound.jl", ROOT / "scripts/vanleer_safe.jl", REFERENCE,
                   ROOT / f"julia/{project}/Project.toml", ROOT / f"julia/{project}/Manifest.toml"]
        results[name] = execute(name, command, env, sources)

    for suffix in ("", "plain_"):
        source = OUT.parent / f"ta1_{suffix}reference_capture.jl"
        wrapper = OUT / source.name
        capture_dir = OUT / f"ta1_{suffix}reference"
        text = source.read_text()
        old = f'const OUT = "/tmp/grad00-validation/ta1_{suffix}reference"'
        assert text.count(old) == 1
        wrapper.write_text(text.replace(old, "const OUT = " + json.dumps(str(capture_dir))))
        command = ["julia", "--startup-file=no", "-O2", "-t", "10",
                   f"--project={ROOT / 'julia/CFDSDFWaterLily'}", str(wrapper)]
        name = f"ta1_{suffix}capture_execution"
        results[name] = execute(name, command, ENV, [wrapper, ROOT / "scripts/waterlily_grad_ta1_2026_10_15.jl",
                               ROOT / "scripts/quick_tie.jl", ROOT / "julia/CFDSDFWaterLily/Project.toml",
                               ROOT / "julia/CFDSDFWaterLily/Manifest.toml"])
    dump(OUT / "cpu_results.json", results)


if __name__ == "__main__":
    main()
