
## Kernel version 3 environment harness failure

Round4 was pushed and registered before dispatch. Exact private CPU kernel version 3 installed all three locked OpenCFD v2512 packages at `2512.0-2` with matching hashes, then exited 127: `foamVersion: command not found`. Exact package `etc/config.sh/setup` lines 240–245 sources aliases only when `PS1` is nonempty. Noninteractive `bash -lc` does not load the `foamVersion` function from `etc/config.sh/aliases`. The raw package sources, installation inventory, ERROR and compressed kernel log are retained under `docs/evidence/xfid_v16_environment_reproduction_2026_10_02_round4/terminal_failure_kernel_v3/`. ERROR SHA-256 `b4314b528a6eb3ac7643564e7946f61a6a4c2b6337368aa06e9e2e8f90071e3d`; audit SHA-256 `0e73ef45094e2f8434dd05771fd193e6598a0c7633b11ffbe2d3b050cd93f74a`. No meshing or solver ran. This is an environment harness FAIL, not XFID DISAGREE; it does not trigger the Track C stop condition. All qualification flags remain false. A future immutable harness round must explicitly load the package version function without changing numeric gates or fixtures.

## Round 5 source validation (Kaggle kernel not submitted)

Round 5 explicitly sources the pinned OpenCFD v2512 package aliases after
bashrc for the noninteractive `foamVersion` probe. The recorded command is
generated from the same helper as the actual subprocess command. Local checks
pass: 6 focused tests, compileall, direct and copied-runner-only embedded
self-checks, and diff check. The final full suite has 37 failed, 1291 passed,
5 skipped, with exact equality to the pinned baseline failure IDs. This is
source/harness evidence only: no Kaggle submission, package installation,
meshing or solver execution occurred. See the
[Round 5 validation record](../evidence/xfid_v16_environment_reproduction_2026_10_02_round5/validation.json)
and the [environment gate details](45_xfid_openfoam_environment_gate.md).

## Round 5 exact Kaggle CPU version 4: environment reproduction PASS

The exact preregistered private Kaggle CPU kernel
`ramhachi888/cfd-opt-sdf-xfid-v16-openfoam-reproduction/4` completed the
v16 environment-reproduction fixture. The unchanged host verifier passed
using the required `.venv/bin/python` (Python 3.12.13); the independent parent
audit verified all 64 retained artifact hashes. Runner SHA-256 is
`19e336893f7b9dc8f1c84503a1218d654fa50eb8b3b3ba4d1530eedfa80f3195`,
criteria SHA-256 is
`7d5215fd3ba681230ffe183952a8e2a91cca1cbb6fc06eecaa85ff6cd67c2867`,
registration SHA-256 is
`aad3e8bdf7dc04dde4c4d8ed9b890fce66dc876e7bb187c25cd81e26b5c0ffb7`, and
parent audit SHA-256 is
`80d2e34b155479976d126332c51767bcf176952f5839c375d388b56f3c53c702`.

Host-recomputed drag is `0.37426349429041095 N`, downforce is
`0.24225913050301373 N`, and normalized mass imbalance is
`1.753881451723771e-8`. The qualified mesh has 2,969 concave cells of 42,619
within the registered allowance; this is not a raw clean `checkMesh` pass. The
Kaggle Python runtime was not recorded by the registered runner. An earlier
system-Python host-verification failure is preserved as a diagnostic; no
criteria or thresholds changed, and the required-environment verifier passed.

Evidence class: exact-version Kaggle CPU environment reproduction with
independent host verification. It establishes no WaterLily comparison,
response sign/ranking, solver equivalence, or production qualification. Formal
XFID remains unrun until #44 freezes the composite C operator and the paired
response-resolution floors are independently measured. All six qualification
flags remain false. See the
[retained exact `/4` artifacts](../evidence/xfid_v16_environment_reproduction_2026_10_02_round5/terminal_kernel_v4_parent_verified/)
and the [comparison-contract draft](45_xfid_comparison_contract_draft.md).

## XFID contract preparation checks

The preparation-only N arithmetic helper and draft were checked without
starting either solver:

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_xfid_response.py` —
  12 passed. Test file SHA-256:
  `6e71e429e7cde020a22bda57fdc65ab3db0d8f0ceb0d82201820f1926243bcbd`.
- `.venv/bin/python -m compileall src tests` — passed.
- `PYTHONPATH=src .venv/bin/python -m pytest -q --tb=short` — 37 failed,
  1318 passed, 5 skipped. Sorted failure IDs exactly match the pinned 37-ID
  baseline (zero new/removed). Baseline IDs SHA-256:
  `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`;
  full log SHA-256:
  `69d2ebc15deb5df09c182b3f038c0b8579f964317eb32fe4db062c74e508aa35`.
- `git diff --check` — passed.

Arithmetic source SHA-256:
`1fa4c452e2f3156c800a7bd1040797d0f3da673469a7e8a43027987e138a03e4`.
Full log is available in the issue worktree at
`work/issue_45_xfid_contract/full_pytest_final.log`. This is contract and
software-test evidence only; the draft remains unregistered, and no XFID
solver comparison was run. The durable compressed log, exact failure-ID list,
source hashes and command/results manifest are in
[`xfid_comparison_contract_preparation_2026_10_02`](../evidence/xfid_comparison_contract_preparation_2026_10_02/).
