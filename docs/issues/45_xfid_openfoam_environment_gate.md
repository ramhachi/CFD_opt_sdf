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
