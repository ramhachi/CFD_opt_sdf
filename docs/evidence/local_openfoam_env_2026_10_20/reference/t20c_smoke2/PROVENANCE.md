# Provenance of the copied Kaggle T2-0c smoke-2 records

- Kaggle kernel `ramhachi888/cfd-opt-sdf-t20c-smoke` version 2 (development smoke of T2-0c, #57), runner SHA-256
  `c52a27f98b148a1b52eed7a670784bd2548e8802e6caa9484cd449008f41eef7` (rendered by `scripts/build_t20c_kernel.py` at source commit
  `993623917a53a6c4e01973ed039755dd676760b6`, branch `claude/t20c-morph-mesh`), Kaggle CPU Intel Xeon @ 2.20GHz, 4 vCPU, Ubuntu noble lock suite.
- Source: the T2-0c session's download of the kernel output (its scratchpad `dl_smoke2b/t20c/`, announced to this session on 2026-10-21 with the
  manifest SHA-256 below). Copied on 2026-10-21 by the LOCAL-OF-01 session.
- `DONE` (SHA-256 `3129de35fcc1a11e97050eb41338b515db416d329521578c73f5e229432c6621`): `FINISHED_SMOKE`, MESH_OK 256, COMPLETED 7, and
  `artifact_manifest_sha256` = `191c131a4bf37aaee73556066fba74033c349c85e3721269e095a67ee9312226` = the SHA-256 of the copied `artifact_manifest.json`.
- Filter: only `result.json`, `environment.json`, `install.json`, `bases.json` and the 263 `cases/*/case_result.json` (267 of the 3970 manifest
  entries), each checked against its manifest SHA-256 before copying; plus `artifact_manifest.json` and `DONE`. No force value is in these files (the
  smoke runner suppresses them).
- The T2-0c session will archive the full output under `docs/evidence/t20c_registered_2026_10_20/smoke/attempt2/` on its branch; this copy is the
  reference of LOCAL-OF-01 and is pinned in `../../freeze.json`.
