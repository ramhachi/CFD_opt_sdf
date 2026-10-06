import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

root = Path.cwd()
dataset_id = "ramhachi888/cfd-opt-sdf-fd08-v2-r6"
local = root / "work/kaggle_fd08_v2_r6_registered_r1"
remote = root / "work/kaggle_fd08_v2_r6_remote_exact_v4"
evidence_path = root / "docs/evidence/fd08_v2_r6_2026_10_06/r6_dataset_verification.json"
criteria_path = root / "docs/evidence/fd08_v2_r6_2026_10_06/r6_criteria.json"
criteria = json.loads(criteria_path.read_text())
criteria_sha = hashlib.sha256(criteria_path.read_bytes()).hexdigest()

def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()

def sha_file(path):
    return sha_bytes(path.read_bytes())

def run(argv):
    return subprocess.run(argv, check=True, capture_output=True)

if evidence_path.exists():
    raise FileExistsError(evidence_path)
remote.mkdir(parents=True, exist_ok=True)
started = datetime.now(timezone.utc)
version_run = run(["kaggle", "--version"])
status_run = run(["kaggle", "datasets", "status", dataset_id])
files_run = run(["kaggle", "datasets", "files", dataset_id, "--format", "json", "--page-size", "200"])
remote_rows = json.loads(files_run.stdout.decode())
expected = {name: (local / name).stat().st_size for name in criteria["dataset_files"]}
expected.update({
    "criteria.json": (local / "criteria.json").stat().st_size,
    "criteria.json.sha256": (local / "criteria.json.sha256").stat().st_size,
})
expected["fd08_v2_dataset_manifest.json"] = (local / "fd08_v2_dataset_manifest.json").stat().st_size
remote_sizes = {row["name"]: row["size"] for row in remote_rows}
if remote_sizes != expected:
    raise ValueError({"missing": sorted(set(expected) - set(remote_sizes)),
                      "extra": sorted(set(remote_sizes) - set(expected)),
                      "size_mismatch": sorted(k for k in set(expected) & set(remote_sizes)
                                               if expected[k] != remote_sizes[k])})
if status_run.stdout.decode().strip().lower() != "ready":
    raise ValueError("R6 Kaggle dataset is not ready")

rows = []
for index, name in enumerate(sorted(expected), 1):
    completed = run(["kaggle", "datasets", "download", dataset_id, "--file", name,
                     "--path", str(remote), "--force"])
    downloaded = remote / name
    if not downloaded.is_file():
        raise FileNotFoundError(downloaded)
    actual_sha = sha_file(downloaded)
    expected_sha = sha_file(local / name)
    row = {
        "path": name,
        "size_bytes": downloaded.stat().st_size,
        "expected_size_bytes": expected[name],
        "sha256": actual_sha,
        "expected_sha256": expected_sha,
        "matches": downloaded.stat().st_size == expected[name] and actual_sha == expected_sha,
        "stdout_sha256": sha_bytes(completed.stdout),
        "stderr_sha256": sha_bytes(completed.stderr),
        "argv": ["kaggle", "datasets", "download", dataset_id, "--file", name,
                 "--path", "<remote-download-dir>", "--force"],
    }
    rows.append(row)
    if not row["matches"]:
        raise ValueError("remote file byte mismatch: " + name)
    print(json.dumps({"verified": index, "total": len(expected), "file": name}, sort_keys=True), flush=True)

inventory = {row["path"]: row["sha256"] for row in rows}
evidence = {
    "kind": "fd08_v2_r6_dataset_remote_verification",
    "status": "PASS_EXACT_REMOTE_CONTENT",
    "captured_start_utc": started.isoformat().replace("+00:00", "Z"),
    "captured_end_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "cli_version": version_run.stdout.decode().strip(),
    "dataset_id": dataset_id,
    "dataset_version": 4,
    "dataset_status": status_run.stdout.decode().strip(),
    "criteria_sha256": criteria_sha,
    "source_commit": criteria["source_commit"],
    "expected_file_count": len(expected),
    "remote_file_count": len(remote_sizes),
    "path_set_exact": True,
    "size_exact": True,
    "sha256_exact": True,
    "remote_inventory_sha256": sha_bytes((json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode()),
    "files_listing_stdout_sha256": sha_bytes(files_run.stdout),
    "files_listing_stderr_sha256": sha_bytes(files_run.stderr),
    "status_stdout_sha256": sha_bytes(status_run.stdout),
    "status_stderr_sha256": sha_bytes(status_run.stderr),
    "files": rows,
}
evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
evidence_path.with_suffix(evidence_path.suffix + ".sha256").write_text(sha_file(evidence_path) + "\n")
print(json.dumps({key: evidence[key] for key in ("status", "dataset_version", "criteria_sha256",
                                                    "expected_file_count", "remote_inventory_sha256")}, sort_keys=True))
