# LOCAL-OF-01 evidence: local Docker OpenFOAM v2512 environment gate (round 1)

Registration and result: [`docs/local_openfoam_env_gate_2026_10_20.md`](../../local_openfoam_env_gate_2026_10_20.md) (section 10). Evidence class:
environment and harness reproduction evidence. Qualification flags unchanged (all false).

**Verdicts:** T family (T2-0c pipeline) **`LOCAL_ENV_FAIL`** -> T2-0c stays on Kaggle CPU. U family (UNC-01 U3 / XFID X3 pipeline)
**`LOCAL_ENV_PASS_BITWISE`** -> the U3 formal kernel may run locally with `infra/local_openfoam/local_openfoam_lock.json`.

| item | value |
| --- | --- |
| user decision (2026-10-20, verbatim) | 「そうだね、タスクが重そうなのでopen formはローカルにしようか」 (open form = OpenFOAM) |
| image | `sha256:e9ceb8a79fd8ceb928983000fffa5a4f2056c354c2e599d098fbcabbce8a25eb` (linux/amd64 Ubuntu 24.04.5 noble under Rosetta; OpenFOAM `2512.0-2` from the registered noble lock); saved tarball SHA-256 in the lock |
| lock | `infra/local_openfoam/local_openfoam_lock.json` SHA-256 `c105b7df7faa310561c0fb607f8dcc8a82be3b21789520489677c7326be11fcd` |
| wrapper | `scripts/local_openfoam.py` SHA-256 `10fee253e66111…` (full value in `freeze.json` `script_sha256_allowed`) |
| freeze | `freeze.json` SHA-256 `29429f6d28c684df8a07eb7be937857be9cffd1a2d8ae57776f35c65e6fd606e` (commit `e8579970`) |
| comparator | `scripts/local_openfoam_gate.py` SHA-256 `41c6ff987e6d369761b5089dd34ce5d4fae2796688709a6d066d2541845f6715`, run once (`gate_ledger.jsonl`) |
| result | `gate_result.json` SHA-256 `0496603b617e6057079e6214c05dc156f48b3f955c9f3c93f40181daaa6d2c7f` |
| commands | `run_gate.sh` (phases `t20c`, `t20b`, `x3u3`, `sanitise`, `compare`); phase logs `phase_*.log.gz`; concurrency deviation `deviations.log.gz` |

Contents:
- `freeze.json`, `gate_result.json`, `gate_ledger.jsonl`: the frozen identities, the comparator output, the invocation ledger.
- `prefreeze/`: the gmsh variant probe (script and 24 JSON lines).
- `reference/t20c_smoke2/`: the Kaggle T2-0c smoke-2 records used by T1 (`PROVENANCE.md`).
- `runners/`: the rendered T2-0c smoke-2 and T2-0b wf runners and the UNC-01 U3 smoke runner (byte copies; SHA-256 in `freeze.json`).
- `runs/<run>/`: per run the wrapper record (`local_run.json`, `local_run.log.gz`, `dpkg_after.sha256`) and the runner records (`result.json`, `DONE`,
  `environment.json`, `install.json`, case records, `case_manifest.json.gz` and `coefficient.dat.gz` where public). `u3_smoke_a_sanitized/` is the
  sanitised U3 smoke (no force field or force file). The raw U3 runs are not archived (UNC-01 blinding); `u3_smoke_*_raw_not_archived/` holds their
  hashes and wrapper records. Mesh files (`mesh.msh`) and solver logs are not archived.
- Integrity: `SHA256SUMS` (repo-root paths), checked with `scripts/check_sha256sums_tracked.py`.

Not archived but referenced: the Kaggle raw U3 smoke (M2, outside the repository, hashes in `freeze.json`), the saved image tarball
(`work/local_openfoam/image/`, git-ignored, SHA-256 in the lock), the datasets under `work/local_openfoam/datasets/` (re-derivable; listing hashes in
`freeze.json`).
