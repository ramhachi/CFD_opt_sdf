#!/bin/bash
# LOCAL-OF-01 pre-freeze generator probe (no OpenFOAM, no force): the T2-0b generator call for the probe geometry sa-wf h/c 0.09 coa30 0 deg,
# 8 runs in each of 3 fresh containers of the locked image; one JSON line per run (mesh.msh SHA-256, node/element/cell counts).
# Usage (repo root): bash docs/evidence/local_openfoam_env_2026_10_20/prefreeze/probe_gmsh_variants.sh > docs/evidence/local_openfoam_env_2026_10_20/prefreeze/probe_gmsh_variants.jsonl
set -eu
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
IMG=$(python3 -c "import json; print(json.load(open('infra/local_openfoam/local_openfoam_lock.json'))['image']['image_id'])")
for c in 1 2 3; do
  docker run --rm --platform linux/amd64 --cpus 4 --memory 8g -v "$PWD":/repo:ro -e PYTHONPATH=/repo/scripts "$IMG" bash -c '
    for i in 1 2 3 4 5 6 7 8; do
      python /repo/scripts/t20_case.py --h-over-c 0.09 --model sa-wf --mesh coa30 --delta-alpha-deg 0.0 --iters 5000 --out /tmp/p$i >/dev/null 2>&1
      python - /tmp/p$i '"$c"' $i <<PY
import hashlib, json, sys
d, c, i = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
t = open(d + "/mesh.msh").read()
m = json.load(open(d + "/case_manifest.json"))
print(json.dumps({"container": c, "run": i, "mesh_msh_sha256": hashlib.sha256(t.encode()).hexdigest(), "nodes": int(t.split("\$Nodes\n")[1].split("\n")[0]),
                  "elements": int(t.split("\$Elements\n")[1].split("\n")[0]), "cells_3d": m["mesh_stats"]["cells_3d"], "n_layers": m["mesh_stats"]["n_layers"],
                  "generator_sha256": m["generator_sha256"]}, sort_keys=True))
PY
    done'
done
