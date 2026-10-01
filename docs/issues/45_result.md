
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
