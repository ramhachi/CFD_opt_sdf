# XFID-01 Stage V environment reproduction gate

Status: **round 2 criteria preregistered; kernel not submitted**. This is an
OpenFOAM environment and harness reproduction gate for issue #45, not a
WaterLily/OpenFOAM comparison or scientific verdict. Formal XFID remains gated
on #44 freezing the composite Candidate C moment-blend plus `normal_floor=0.25`
operator.

## Preregistered round 2

The immutable criteria are in
`infra/kaggle/kernel_openfoam_xfid_v16/criteria.json` (SHA-256
`5718d0c3013a826504e4f8389d35958a67e3b10c3093954ac8958d9a2ef1ac56`). Round
2 supersedes the preexecution candidate with criteria SHA
`5d67d5a8ecf35ff4fad795d30c505e82bc6d4669c0785499ac684bd069098ff0`. That
candidate is preserved at
`infra/kaggle/kernel_openfoam_xfid_v16/rejected_preexecution_round_01/`, with
its original criteria, runner, package lock, metadata and complete case-input
snapshot, each covered by `SHA256SUMS`. It was rejected before any solver or
Kaggle run because its shell runner stopped on the historical `checkMesh`
exit 1 and ignored `surfaceFeatureExtract` failures. Round 2 changes only the
harness behavior and resulting `Allrun` identity; scientific thresholds and
historical reference values are unchanged.

Round 2 selects the archive's v16 PASS parent case
`stage_sv_v2_expanded_domain_v2` at archive commit
`aa2e9d5f702044419c2a63a1eeea52fb421ab5af`. This is the base domain in
`blockMeshDict`, `[-2.5,-1.2,-0.9]` to `[2.5,1.2,0.9]`, with `h=0.05 m`;
it is not the later far-field-extended child. Candidate STL SHA is
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`,
design-domain STL SHA is
`25c04275da0467193932f3d0f05235c49080c039c2a29e2834a9e75da7169446`, and
physical-profile SHA is
`a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca`.
Criteria bind the historical metadata, qualification, result, manifest,
run-manifest and domain-comparison artifact hashes. All 13 case input files
are individually hashed, including `Allrun`, every initial field, boundary
condition, mesh and solver dictionary, and both STLs. The extracted case
inventory must match exactly before use.

`Allrun` now propagates failures from `blockMesh`, `surfaceFeatureExtract`,
`snappyHexMesh` and `simpleFoam`. It captures `checkMesh`'s exit status and
permits solver execution only for exit 1 with exactly one failed-check marker
and exactly one concave-cell diagnostic whose fraction is at most 8%. All other
mesh failures stop before `simpleFoam`. The runner's post-run gate independently
checks the full registered mesh, residual, mass, stationarity and response
criteria.

The standalone runner embeds the criteria, package lock, metadata, 13 case
inputs and three STL/profile fixtures as deterministic gzip-compressed tar
bytes (payload SHA-256
`c17e58a09fab081d2505466b8e8db3cad9b31f240951294bde97b34ca867c16a`), because
Kaggle mounts only `runner.py`. It verifies the payload hash and inventory,
then checks each input hash after extraction. A cached payload must pass the
same inventory and content checks. Prior meshes, solution times, logs and
solver outputs are excluded.

Historical references are Cd `1.1693991415068494` and downforce coefficient
`0.7565514657808219` (0.32 N per coefficient), or `0.3742077253 N` drag and
`0.2420964690 N` downforce. Round 2 preregisters a conservative reproduction
acceptance ceiling of 2% relative Cd and 0.005 absolute downforce coefficient,
plus the existing Stage V mesh, residual, mass-balance and force-stationarity
limits. The response ceilings were adopted from the v16 domain-comparison
bounds; they are not same-environment replay repeatability estimates or
measurements of environment uncertainty. They are unchanged from the rejected
preexecution candidate and were not adjusted after solver results.

These ceilings do not establish future XFID response-resolution floors. Before
formal comparisons, each solver's floor must be registered independently and
must include a measured environment-reproduction uncertainty bound. A
response at or below its solver's floor is **UNRESOLVED**, never PASS or a
sign/rank vote.

## OpenFOAM package identity

The runtime accepts Ubuntu Noble `amd64` only. The package-lock SHA-256 is
`8bcf141db29d18800a55a70bca93175a37465ac18494e473efd32985317c7340`. Before
apt update or installation, the runner fetches and verifies the pinned official
repository indices: `InRelease` SHA-256
`50cb05b774c0038b0cea099e68c8ba69544881aa79ce8fef2dfc4a719c2b0887` and
amd64 `Packages.gz` SHA-256
`235cee0e6311c836ac13b7fc11092345f06cd06524772f62b9cd55a630402cd2`. It
pins OpenCFD v2512 packages to `2512.0-2`, checking each `.deb` before
installation:

| Package | Architecture | SHA-256 |
| --- | --- | --- |
| `openfoam2512` | amd64 | `c59e65ffd99c9143fd7c2594dc9776e9d7190124965efdb667e28677d93f3fed` |
| `openfoam2512-common` | all | `f438ecbfaff0248b9273502f3b43a6cb1b4f81c07224dbda811f1b48d989026f` |
| `openfoam2512-tools` | amd64 | `fc0d19c1152819cc7d2a6165eec911c0f1ea3ab7d88cc04ee4a8070d11aa2e62` |

The official repository bootstrap script is pinned by SHA-256
`f7fa288327e936b5a85e3e4a0b29bf039c06d214916f39400b830b63a3310b5b`. The
kernel metadata preregisters private script execution with internet enabled,
GPU disabled, and no datasets/competitions/kernels/models. The runner records
OS version, architecture, index hashes, exact installed package versions and
hashes, and `foamVersion`. Official package availability was checked in
OpenCFD's Noble amd64 v2512 index on 2026-10-02: [OpenCFD Noble v2512 package
index](https://dl.openfoam.com/repos/deb/dists/noble/main/pool/2512_0/binary-amd64/).

## Verification and evidence

Local shell regression tests mock solver commands to prove (1) the registered
concave-cell `checkMesh` exit reaches `simpleFoam`, (2) another mesh failure
stops before the solver, (3) multiple failed-check markers stop before the
solver, and (4) `surfaceFeatureExtract` failure propagates.
The runner writes append-only `ERROR.json` on run failure. A successful run
writes `result.json`, an output hash manifest and a `DONE` sentinel only after
all in-kernel checks pass. After downloading the Kaggle output, independently
recompute the mesh, residual, mass and force gates from raw logs and fields,
then verify exact runner, criteria and metadata hashes against the parent
registration manifest:

```bash
python3 infra/kaggle/kernel_openfoam_xfid_v16/verify_artifact.py \
  /path/to/downloaded/openfoam_xfid_v16 \
  infra/kaggle/kernel_openfoam_xfid_v16/criteria.json \
  infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json \
  /path/to/parent-registration-manifest.json
```

No Kaggle job or solver run has been submitted. The only permitted first
execution is this v16 Kaggle CPU environment replay; no WaterLily pilot may
inform the XFID verdict or branch decision. Local self-check and mocked
harness results are contract evidence; historical JSON and logs are prior
Stage V evidence; only a fresh Kaggle replay verified independently from its
raw artifacts can establish environment reproduction.

## Parent source review and dispatch prerequisite checkpoint

Parent independently passed four shell regression tests using
`python -m pytest -q infra/kaggle/kernel_openfoam_xfid_v16/test_allrun.py`
and checked the isolated script-only embedded mount with `runner.py --self-check`.
Reading the historical parent case at time 584 reproduced Cd
`1.1693991415068499`, downforce coefficient `0.7565514657808217`, drag
`0.374207725282192 N`, downforce `0.24209646904986293 N`, and normalized mass
imbalance `1.9077502684040886e-8`. Its 2967 concave cells out of 42619 are below
the registered 8% ceiling. This remains a check of historical data and the
harness; it is not fresh environment evidence.

The integrated full-suite source binding was audited explicitly. Before the
pytest `pythonpath=["src"]` fix, the shared editable environment had imported
the original checkout package before discovering the new FD/STEP modules,
causing two collection errors. That log is retained. After the fix, the literal
integrated pytest command completed with **37 failed, 1245 passed, 4 skipped**.
A separate source-bound replay of the original `2fd7f6a` baseline completed
with **37 failed, 1225 passed, 5 skipped**. The exact 37 failure IDs match both
each other and the first baseline; zero new failures. Compileall and diff
checks passed. The pass/skip difference includes optional ignored fixtures.

The immutable parent registration and preserved validation logs are under
[`xfid_v16_environment_reproduction_2026_10_02_round2`](../evidence/xfid_v16_environment_reproduction_2026_10_02_round2/).
Registration SHA-256:
`8d40a6913a898b11fa7fc7d80c766af79ad5f9609fbfb5a0a7f88002d3696881`.
The runner SHA-256 is
`67d6021c7386d2297773be71d5bc5de234503506c70037b805e2c483bb91e447`;
the criteria SHA-256 is
`5718d0c3013a826504e4f8389d35958a67e3b10c3093954ac8958d9a2ef1ac56`.
The source checkpoint is `7ea5bf6`. Commit/push this registration before
dispatch. Submission and terminal results must be separate append-only
records; this registration alone cannot produce an XFID verdict or change a flag.

## Fresh Jammy environment round after kernel version 1 ERROR

The exact private Kaggle CPU version 1 observed Ubuntu 22.04.5 Jammy amd64,
whereas Round 2 required Noble. It terminated before apt installation, meshing
or solver execution. The ERROR and downloaded log are preserved under the
parent Round 2 terminal-failure directory. This is an environment-lock failure;
no XFID response or DISAGREE verdict exists. Track C is not stopped by this error.

A separate self-contained `infra/kaggle/kernel_openfoam_xfid_v16_jammy/`
registers Round 3 for the observed OS with official OpenCFD v2512 packages
exactly `2512.0-2`. Old Round 2 is unchanged. Every numerical gate, fixture
identity and case-template byte remains unchanged. New criteria SHA-256:
`b5e8d16838882c92f17d192cc5b1b0a1a525360ac4968cf5c40e359cb4f3190b`;
package-lock SHA-256:
`b5e59f8a7da34820fc3c6bda93b3524204dcaf4fa6e4f7f11d6c46ddddb66746`;
runner SHA-256:
`8a0605ee78d3dfe6ccbad1ccfba61488861f33ec988541116c5b6693120469b8`.
Official lock-input bytes, URLs, hashes and validation logs are retained in
`docs/evidence/xfid_jammy_apt_lock_inputs_2026_10_02/`. They are repository
metadata, not evidence that OpenFOAM has been installed or run on Kaggle.
[Official OpenCFD Jammy v2512 index](https://dl.openfoam.com/repos/deb/dists/jammy/main/pool/2512_0/binary-amd64/).

Focused shell tests: 4 passed. Isolated embedded mount self-check: PASS.
Compileall and diff-check: PASS. Source-bound full pytest: 37 failed, 1244 passed,
5 skipped, with exactly the initial 37 baseline failure IDs and no new failures.
The parent source registration must be committed/pushed before a new exact
Kaggle version is submitted. All six qualification flags remain false.
