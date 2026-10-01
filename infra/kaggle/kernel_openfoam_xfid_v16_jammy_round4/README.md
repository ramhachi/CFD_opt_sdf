# XFID v16 OpenFOAM Jammy reproduction: round 4 harness checkpoint

This directory is a separate successor to the immutable
`kernel_openfoam_xfid_v16_jammy` round 3. Round 3's criteria, package lock,
case inputs, mesh/solver parameters and numerical gates are preserved byte for
byte except for the round identity, predecessor/error binding and registration
note in this new criteria file. The predecessor is exact Kaggle version 2,
which installed and hash-verified the pinned OpenCFD v2512 packages, then
stopped before `foamVersion` because its shell init path was incorrect.

Round 4 uses the package-provided
`/usr/lib/openfoam/openfoam2512/etc/bashrc`, records the OS and exact package
inventory before calling `foamVersion`, and writes any failed command's
captured stdout/stderr into `ERROR.json`. The pinned common package defines
`foamVersion()` to write its version token on stderr, so the runner stores both
raw streams before extracting the unique expected `OpenFOAM-v2512` line. The
embedded payload and exact file inventory are recomputed for this directory
and verified by `runner.py --self-check`.

This is only the source-side, preregistered harness repair. No Kaggle kernel was
submitted, no solver was run, and no environment reproduction or XFID verdict
is claimed. The v16 CPU replay is the only permitted first execution after
parent review and registration.

Local criteria SHA-256: `687dc69c16e48c914115754e22da370abc1629ae6331ffdfff67fc8a947b1ae8`.
Package-lock SHA-256: `b5e59f8a7da34820fc3c6bda93b3524204dcaf4fa6e4f7f11d6c46ddddb66746`.
Runner SHA-256: `2bf07d2ea3182254ce335b5f69a4689111d90d5ce00dc6a1fb5529092efe0d4f`.
