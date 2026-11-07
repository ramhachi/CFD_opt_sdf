"""Record only the result-side suite, with the requested Metal exclusion and no cap."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent
COMMAND = [".venv/bin/python", "-m", "pytest", "--ignore=tests/test_lbm_metal.py",
           "-q", "-rf", "-p", "no:cacheprovider", f"--junitxml={OUT / 'pytest_full.xml'}"]
SOURCES = [ROOT / name for name in (
    "scripts/analyze_grad00.py", "scripts/build_grad00_kernels.py", "scripts/run_grad00_cpu.py",
    "scripts/waterlily_grad00_lambda_2026_11.jl", "scripts/vanleer_safe.jl",
    "scripts/grad00_selftest.jl", "scripts/grad00_orchestration_selftest.jl",
    "tests/test_grad00.py", "tests/test_grad00_reference.py", "tests/test_grad00_kernels.py",
    "tests/test_grad00_cpu.py")]


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}


def main():
    if any((OUT / name).exists() for name in ("pytest_full.txt", "pytest_full.xml", "pytest_full_result.json")):
        raise FileExistsError("refusing to reuse a full-suite record")
    record = {"command": COMMAND, "timeout_s": None, "baseline_rerun": False, "source_sha256_before": hashes()}
    dump("pytest_full_command.json", record)
    started = time.monotonic()
    with (OUT / "pytest_full.txt").open("w") as output:
        code = subprocess.run(COMMAND, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False).returncode
    record.update(exit_code=code, wall_seconds=time.monotonic() - started, source_sha256_after=hashes())
    record["sources_unchanged_during_run"] = record["source_sha256_before"] == record["source_sha256_after"]
    dump("pytest_full_command.json", record)
    log = (OUT / "pytest_full.txt").read_text()
    suites = list(ET.parse(OUT / "pytest_full.xml").getroot().iter("testsuite"))
    counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    failed_nodes = sorted(set(line.split(" - ", 1)[0] for line in re.findall(r"^(?:FAILED|ERROR) (.+)$", log, re.M)))
    result = {"evidence_class": "result_side_full_python_test_run", "completed": True,
              "exit_code": code, "failed_nodes": failed_nodes, "junit_counts": counts,
              "passed": counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"],
              "timeout_s": None, "baseline_rerun": False, "process_wall_seconds": record["wall_seconds"],
              "sources_unchanged_during_run": record["sources_unchanged_during_run"],
              "baseline_comparison": "Host baseline belongs to Claude; no base run performed here"}
    dump("pytest_full_result.json", result)
    print(json.dumps(result, indent=2), flush=True)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
