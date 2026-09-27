"""K0 background batch smoke."""

import hashlib
import json
import subprocess
from pathlib import Path


OUT = Path("/kaggle/working/k0")
STAGE = "smoke"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if STAGE != "smoke":
        raise ValueError("unsupported K0 stage")
    gpu_csv = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"],
        check=True, capture_output=True, text=True,
    ).stdout
    (OUT / "nvidia_smi.csv").write_text(gpu_csv)
    rows = [row.strip() for row in gpu_csv.splitlines() if row.strip()]
    fingerprint = {"stage": "smoke", "gpu_count": len(rows), "gpu_csv": rows}
    write_json(OUT / "fingerprint.json", fingerprint)
    if len(rows) != 2 or any("Tesla T4" not in row for row in rows):
        raise RuntimeError("K0-B requires exactly two Tesla T4 devices")
    files = {path.name: sha256(path) for path in OUT.iterdir() if path.is_file()}
    write_json(OUT / "sha256.json", files)
    (OUT / "DONE").write_text("K0-A smoke completed\n")
    print("K0_SMOKE_DONE", json.dumps(fingerprint, sort_keys=True))


if __name__ == "__main__":
    main()
