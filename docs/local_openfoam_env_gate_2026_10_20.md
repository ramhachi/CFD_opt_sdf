# LOCAL-OF-01: local Docker OpenFOAM v2512 environment gate for the OpenFOAM studies of #57 (T2-0c) and #61 (UNC-01 U3)

Registration status: `DRAFT` -> one adversarial review (numerical and controls angles, sonnet; section 9) -> **`FROZEN`** (freeze record
`docs/evidence/local_openfoam_env_2026_10_20/freeze.json`: full SHA-256 of this file, the comparator, the runtime script, the tests, the lock, the image,
every runner, dataset and reference) -> runs -> result appended in section 10. Evidence class: **environment and harness reproduction evidence** (as the
#45 XFID environment gate). It is not a physics, grid-independence, solver-equivalence or benchmark result, and it changes no qualification flag (all stay
false).

## 1. Decision, question and scope

User decision, verbatim (2026-10-20): 「そうだね、タスクが重そうなのでopen formはローカルにしようか」 ("open form" = OpenFOAM). The OpenFOAM work that
ran on Kaggle CPU moves to the local machine: the UNC-01 U3 kernels (#61, M2) and the T2-0c registered kernels R, M, S (#57). WaterLily (GPU) stays on
Kaggle T4. The study registrations are amended by their own sessions (`REGISTERED_AMENDED`), not here.

Question: does a pinned local Docker runtime run the registered Kaggle CPU runners and reproduce the Kaggle CPU outputs that the two studies' decisions
depend on, with any environment difference negligible against each study's decision scale? The precedent is #45 (the Kaggle CPU environment reproduction
gate and the OpenCFD package locks, `docs/issues/45_xfid_openfoam_environment_gate.md`).

## 2. Local environment (lock)

- **Image** `cfd-local-openfoam:2512-noble-amd64`, built by `scripts/local_openfoam.py build` from `infra/local_openfoam/Dockerfile`; identity = the Docker
  image ID `sha256:e9ceb8a79fd8ceb928983000fffa5a4f2056c354c2e599d098fbcabbce8a25eb` (content address of the config and every layer), recorded in
  `infra/local_openfoam/local_openfoam_lock.json` with the base image digest, the Dockerfile and requirement-lock SHA-256, the full package list
  (`infra/local_openfoam/dpkg_list.txt`, 297 packages), the OpenFOAM packages, `foamVersion`, the Python stack and the host. The image is a local build and
  has no registry RepoDigest; it is saved with `docker save` to `work/local_openfoam/image/e9ceb8a79fd8ceb9.tar` (SHA-256 and the restore command
  `docker load -i …` in the lock; the file is git-ignored). **A rebuild is a new environment** (apt and the Ubuntu archive move), and losing both the image
  and the tarball voids this gate for later runs. Every run is started by image ID, never by tag.
- **Base:** `ubuntu:24.04` linux/amd64 manifest `sha256:a2d43bffc46670d7108bb3c0468c67c5557c4c92e83e1e34cbff1322ad1b94dc` = Ubuntu 24.04.5 noble, the
  OS the Kaggle CPU runtime reported in T2-0b, the T2-0c smokes and X3 formal. The jammy lock suite is not exercised locally.
- **OpenFOAM:** OpenCFD v2512 `2512.0-2` (`openfoam2512`, `-common`, `-tools`), installed at build time **by the registered X3 formal runner's own
  `install_openfoam`** with the registered noble lock `infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json` (SHA-256
  `8bcf141db29d18800a55a70bca93175a37465ac18494e473efd32985317c7340`): official installer, apt index and `.deb` SHA-256 checked, the same `.deb` bytes
  Kaggle installs; `WM_OPTIONS` `linux64GccDPInt32Opt`, `FOAM_MPI` `sys-openmpi`. Every runner repeats its own `install_openfoam` at start (as on Kaggle;
  internet required). That step fails closed unless the installer and both apt indexes still have their locked SHA-256; the wrapper then re-lists the
  image's packages after the runner and records whether the list still equals the lock (`dpkg_after_matches_lock`), so "changes nothing" is checked on
  every run.
- **Python:** CPython 3.12.3 (noble) venv with `numpy 2.5.4`, `scipy 1.18.1`, `gmsh 4.15.2`, `psutil 7.2.2`, hash-pinned
  (`infra/local_openfoam/requirements.lock`).
- **Why linux/amd64 under Rosetta, not the arm64 `opencfd/openfoam-default:2512` image:** every registered runner requires
  `dpkg --print-architecture == amd64` and an Ubuntu-codename OpenCFD lock, and the T2-0c runner has no install bypass, so only an amd64 noble image runs
  them byte for byte; the opencfd image is a different build from the locked `.deb` files. Other local images are not used or touched.
- **Remaining differences from Kaggle (disclosed, not tested one by one; the gate tests their combined effect):** the CPU (Apple M4 through Rosetta,
  reporting `VirtualApple` with SSE4.2/AVX/AVX2/FMA and no AVX-512; Kaggle reports "Intel(R) Xeon(R) CPU @ 2.20GHz" without flags), the kernel, Python
  3.12.3 vs Kaggle 3.13.15, numpy/scipy (Kaggle's versions are not recorded), patch versions of the OpenFOAM dependencies (Kaggle installs current noble
  packages at run time; here they are frozen in the image), and the container limits (4 CPUs, 8 GB, no swap).
- **Runner wrapper** `scripts/local_openfoam.py run KERNEL_DIR --out DIR [--dataset DIR]`: refuses unless the lock equals the frozen lock and the image
  with the lock's ID exists; mounts the kernel's `runner.py` at `/kaggle/src/runner.py`, `DIR` at `/kaggle/working`, the dataset at
  `/kaggle/input/<dataset slug>`; `--cpus 4` (`--cpus 1` for the serial X3-type runners) `--memory 8g --memory-swap 8g`; writes `DIR/local_run.json`
  (lock SHA-256, image ID, runner and script SHA-256, Docker arguments, return code, package-list check, host load before and after, wall time). Only the
  `/kaggle` paths are provided by mounts and the submission is replaced by `docker run`.
- **Subset harness (used by R2-R5, disclosed):** `run RUNNER --subset KIND ID…` runs `scripts/local_openfoam.py subset` inside the container, which
  imports the registered runner module unchanged and calls its own `fetch_source`, `install_gmsh`, `install_openfoam`, `make_specs` (T2-0b) or
  `discover_inputs` plus the criteria and input hash checks (X3), and `run_case`, for the listed ids. Deviations from the runners' `main()`: only the listed
  cases run; the T2-0b runner's mesh probe and 200-iteration infrastructure smoke stage are skipped; the output directory is set through the runners'
  own `T20B_OUTPUT`/`X3_OUTPUT` variables; the case deadline is 6 h from the start (the registered per-case caps inside `run_case` are unchanged); the
  T2-0b cases run 4 at a time (the runner's `WORKERS`), the X3 cases one after another in the listed order. A stub-runner test checks that exactly the
  listed ids reach `run_case`.

## 3. What was visible before the freeze

- All Kaggle reference outputs used below (existing evidence): T2-0b wf (`docs/evidence/t20b_registered_2026_10_19/kernel_wf_run1/`), X3 formal
  (`docs/evidence/xfid_gridphase_x3_2026_10_04/formal_result/`, `analysis_openfoam.json`), the T2-0c smoke-2 records (copied, each file verified against the
  Kaggle `artifact_manifest.json` bound by its `DONE`, into `docs/evidence/local_openfoam_env_2026_10_20/reference/t20c_smoke2/`, see its
  `PROVENANCE.md`), the sanitised Kaggle U3 smoke archive (M2, commit `011066ba`). The comparator was run on the Kaggle references against themselves
  (a test): every check passes and is bitwise. The raw Kaggle U3 smoke (with forces) was hash-verified, not read.
- **The gmsh generator is not run-to-run deterministic, on Kaggle or here.** T2-0b wf (2026-10-19) and T2-0c smoke 2 (2026-10-20) share 41 gmsh
  geometries: 34 have the same `mesh.msh` SHA-256, 7 differ (`h0.09 coa30 0`, `h0.09 med30 0`, `h0.134 coa30 0`, `h0.134 fine30 +1`, `h0.134 fine30 0`,
  `h0.179 coa30 0`, `h0.224 med30 -1`) with identical cell counts and 8-digit checkMesh statistics.
- **Pre-freeze generator probe (no OpenFOAM, no force; its geometry is excluded from T1).** The pinned T2-0b generator call for `sa-wf h/c 0.09 coa30 0`
  in the locked image, recorded by `prefreeze/probe_gmsh_variants.sh` -> `prefreeze/probe_gmsh_variants.jsonl` (2026-10-21; 3 fresh containers x 8 runs):
  three mesh files, `3dbb16b8a752e29a116c57ed45dbf85d0af1b11f93eeaa5cb17ec0ad2cad1b6c` (18 runs; **= Kaggle smoke 2**),
  `67510d1267e77c282e96725aee8552bce1192681dbea245ba4492d4da70fa60d` (4 runs; **= Kaggle T2-0b**) and
  `01f64bc2a8f81e5ec183a5cdd9dea52d32242511b8fcd4acd105447eda986cf5` (2 runs), all with 9656 nodes, 22440 elements, 7349 cells and 7 layers. An earlier
  unrecorded exploration of 24 runs gave the same three files (17/4/3) and showed that `PYTHONHASHSEED` does not select the variant; node-by-node
  comparison: `01f64bc2` vs `3dbb16b8` has the same node ids with 200 nodes moved by at most 1.1e-15 m and three triangles with rotated node order;
  `67510d12` is a renumbering. The variants look like one geometric mesh with different numbering; the solver result on them can differ at the
  iterative-solver level. **Design consequences fixed before the freeze:** mesh-file and OpenFOAM topology hashes never gate a comparison between runs;
  bitwise force agreement is required only between runs with identical mesh files; the spread between variants is reported as a property of the pipeline
  (it exists on Kaggle too). The finding was sent to the T2-0c session.
- **Probability that T3 finds its pairs:** with the probe frequencies, a case whose Kaggle mesh is the common variant (p about 0.75) gets a same-mesh local
  run in 2 runs with probability 0.94 (4 runs 0.996); a rare one (p about 0.17) 0.31 (4 runs 0.52). The 5 T3 cases have the same mesh file in both
  Kaggle sessions (common variants are likely), so 2 of 5 is expected; an `INCOMPLETE` that ends as `FAIL` after 4 runs would reflect the gmsh draw.
- **Case selection:** the four steady T2-0b cases were chosen for relevance before the variants were noticed (the T2-0c verdict level fine30 at h/c 0.224
  with +-1 deg, and T2-0b's G6 pair med30 h/c 0.134 +-0.25 deg); they turned out to be among the 34 geometries whose mesh files agree between the two
  Kaggle sessions, which favours stable cases (disclosed). The unsteady case and the X3 pair rule were added at the review (section 9).
- **Infrastructure smoke (no case, no solver):** a dummy kernel through the wrapper that calls the X3 formal runner's `install_openfoam` at container
  start: mounts work, the runtime re-install verifies installer, indexes and `.deb` hashes, installs nothing ("already the newest version"), `foamVersion`
  = `OpenFOAM-v2512`, and the package list after the run equals the lock (94 s).
- No local solver output existed before the freeze.

## 4. Registered runs

Each run is one container with `--memory 8g` and `--cpus 4` (`--cpus 1` for the serial X3-type runs, which run side by side); concurrent runs never
exceed 4 CPUs in total (the host also runs another study). Commands: `work/local_openfoam/run_gate.sh` (copied into the evidence). Runner bytes:

| run | runner (SHA-256) | input | cases |
| --- | --- | --- | --- |
| R1a `t20c_smoke2_a`, R1b `t20c_smoke2_b` | T2-0c smoke-2 runner `c52a27f98b148a1b52eed7a670784bd2548e8802e6caa9484cd449008f41eef7` (= the Kaggle smoke-2 runner; rendered by `scripts/build_t20c_kernel.py` at `99362391` mode `smoke`; copy in the evidence) | source fetched by the runner (GitHub, commit `993623917a53a6c4e01973ed039755dd676760b6`) | the whole smoke unchanged, twice: 256 mesh-only geometries + 7 solver paths at <= 200 iterations incl. xfine30, morph, B', linear blend, shape and the forced continuation (forces suppressed by the runner) |
| R2 `t20b_a`, R3 `t20b_b` (+ `t20b_c`, `t20b_d` only under section 6) | T2-0b wf runner `b10aea0d1095e335a3810ff7aca4c3f115d6dfbf46fb0f46ab3df42fe8202602` (= the Kaggle wf runner; rendered by `scripts/build_t20b_kernel.py` at `941e8a76` mode `wf`; copy in the evidence), subset harness | source fetched by the runner (commit `941e8a766376cb8c87cda9a344ee1f6350f9bb95`) | `sa-wf_h0.224_fine30_da-1`, `sa-wf_h0.224_fine30_da+1`, `sa-wf_h0.134_med30_da-0.25`, `sa-wf_h0.134_med30_da+0.25`, and the unsteady `sa-wf_h0.09_fine30_da+1` (raw tail Cl relative std 1.9 % on Kaggle); registered 5000 iterations and continuation rule |
| R4 `x3_a`, R5 `x3_b` | X3 formal runner `0a649b433b7e85a11bdbff586bd9e96d64ced9b5b8a92af99aa4afeed9e2e9f3` (criteria `c2523b2348a986a287a3183ff67d17951187b859bb7d479c791792283776acbc`), subset harness | dataset re-derived by `scripts/local_openfoam.py stage-x3` (states from the X1 surfaces) and verified file by file against the criteria inputs | the 7 states at the first mirror pair of the formal case order, `17p` and `17m` (14 cases), fixed by order, not by value |
| R6a `u3_smoke_a`, R6b `u3_smoke_b` | UNC-01 U3 smoke runner `1e3d71aa07719957d590c9a8e02eb6c6c4ed9e4ba89454c03819b8d3752d8db3` (`feat/unc01-m2` at `a646e918`; the X3 formal runner with its criteria SHA line) | the M2 smoke dataset (criteria `51f36570c4505fe5080ba6f08d6cf41f501a867a1f254458d6190d5d6fab92fb`), verified file by file against the criteria inputs | the whole smoke unchanged, twice (8 v18 states at shift `33p`) |

R6a is sanitised after it ends by the frozen M2 sanitiser (`scripts/unc01_u3_prepare.py strip-smoke` at `a646e918`, SHA-256
`18de7c67d69d90a7578ce2984b57d99b2228a9eff5da60c7040b4201a44e9e07` = UNC-01 freeze 1) applied to the runner's own output directory (not to the wrapper
log); the sanitised copy and the wrapper record are the only parts of R6 that enter the repository. The raw R6a/R6b outputs stay under the git-ignored
`work/local_openfoam/runs/` until the result is committed; they and the raw Kaggle U3 smoke (supplied by the M2 session outside the repository:
`result.json` `719cc4d91f84f8e8f95616383e4ef71542f3ea2a90c03ad60a3cd2579c0559dc`, `artifact_manifest.json`
`97d9f8c10e5599f0d276943b7c6d4036d79883b73920bfe986740dc0aabbfd5e`, all 61 entries verified, bound by its `DONE`) are read only by the comparator's U4
function, which returns no force value and no state difference. The U3 runner prints no force to standard output (it prints only `FAIL_CLOSED` lines).
The M2 session stated that U3 force values enter no UNC-01 rule (registration §6, §15) and asked that a comparison of values be disclosed; this is that
disclosure, and it governs over the earlier draft wording that no v18 force would be compared.

## 5. Criteria (computed once by the frozen `scripts/local_openfoam_gate.py`)

**What counts as a run.** A run counts only if its `local_run.json` has return code 0, the frozen image ID, lock SHA-256, script SHA-256 and runner
SHA-256, the registered CPU and memory arguments and `dpkg_after_matches_lock`, and the runner wrote `DONE`. Anything else is an infrastructure loss
(section 6). A completed run whose case timed out, hit the deadline or ended in another status is a result (it fails the checks below), not a loss.

**Agreement of a record:** integers, booleans, hashes, integer strings and other strings identical; floats and decimal strings (checkMesh prints 8
digits) within relative 1e-6 with an absolute floor 1e-12; wall-clock, memory and raw log fields ignored. The runners' force statistics used below are
first checked against an independent recomputation from `coefficient.dat` (T2-0b tail over the last 20 %, at least 50 rows; X3 window over the last
25 %, at least 20 rows); a mismatch fails the part.

**T family (T2-0c pipeline: gmsh generator, gmshToFoam, simpleFoam SA wall functions).**
- **T1 mesh replay:** R1a against Kaggle smoke 2 for every geometry except the probe geometry `sa-wf_h0.09_coa30_da0_mesh` (262): status, cells, layer
  count, layer thickness, lowest point, the full checkMesh record and return code, the local quality proxy, stage return codes and the morph diagnostics
  agree; `bases.json` agrees on the same fields; the status counts are equal. Within a run the runner itself fails a morph whose topology differs from its
  base (`TOPOLOGY_CHANGED`), so the status check covers that. Mesh-file and topology-hash identity with Kaggle is counted, not required. The 7 solver
  paths' residual, y+ and continuation blocks are compared; where the mesh file is identical their last initial residuals must agree within relative
  1e-3 (bitwise expected).
- **T2 determinism:** (i) over all local T2-0b runs, every pair of runs of a case with the same mesh-file SHA-256 has a byte-identical
  `coefficient.dat`, at least one such pair, all runs completed; (ii) R1a against R1b: every solver path whose mesh file is identical in both has identical
  solver, continuation and y+ blocks.
- **T3 environment identity:** every local run of a case whose mesh file is identical to Kaggle's T2-0b mesh file has either a byte-identical
  `coefficient.dat`, or all of: the same plateau flags, history rows, continuation and solver iterations, the same unsteady class (raw tail Cl relative std
  above 0.5 %), the raw tail Cl standard deviation within 10 % of Kaggle's, and |Cl_local - Cl_Kaggle| <= 0.1 x Kaggle's raw tail Cl standard deviation
  for the tail mean (7e-6 to 2.6e-3 for the five cases). Such pairs are required for at least 2 of the 5 cases. Every local run has Kaggle's cell count and
  checkMesh record.
- **Generator-variant spread (descriptive, not part of the verdict):** the largest |delta Cl| of the steady cases between runs whose mesh files differ
  (local-local and local-Kaggle), labelled against 0.1 x T2-0b's G6 sigma_mesh at h/c 0.224 (2.28e-4): `VARIANT_SPREAD_WITHIN_SCALE` or
  `VARIANT_SPREAD_ABOVE_SCALE`. Also descriptive: the Kaggle self-consistency count (34 of 41), wall time per case local vs Kaggle, peak RSS.

**U family (U3 pipeline: blockMesh, snappyHexMesh, simpleFoam on the XFID coarse Stage V mesh).** Scales from X3 formal: pooled per-case residual std
sigma (drag 2.01e-4 N, downforce 5.76e-4 N), the 32-phase contrast SE (2.51e-5 N, 7.20e-5 N) and the calibration floor (3.94e-5 N, 2.23e-4 N).
- **U1 determinism:** R4 and R5: all 14 completed, byte-identical `coefficient.dat`; R6a and R6b: all 8 completed, byte-identical `coefficient.dat` (compared
  inside U4 without reading a value).
- **U2 X3 forces and mesh:** R4 against X3 formal: status, STL SHA-256, triangle count, checkMesh record and snappy statistics agree; per case
  |delta F| <= 0.1 sigma (2.0e-5 N drag, 5.8e-5 N downforce); the signed mean of (local - Kaggle) over the 14 cases <= 0.1 floor (3.9e-6 N, 2.2e-5 N);
  every difference (each state minus baseline at each shift, (plus - minus)/2 of D0, D1, D2 at each shift, and their mirror-pair means) moves by at most
  0.1 max(3 SE, floor) (7.5e-6 N drag, 2.2e-5 N downforce). The direction contrasts are reported next to their SE. Solver blocks (iterations, final
  residuals) are compared descriptively.
- **U3 v18 mesh replay:** the sanitised R6a against the sanitised Kaggle U3 smoke (M2, commit `011066ba`, `docs/evidence/unc01_2026_10_20/u3/smoke/output/`,
  8/8 completed on Kaggle CPU): statuses, stage return codes, STL SHA-256, triangle counts, checkMesh record and snappy statistics agree for all 8 cases;
  both archives must hold exactly one `result.json`, an `EXCLUDED_SHA256.json`, no force field and no `coefficient.dat*` or `log.simpleFoam*` file. Solver
  blocks compared descriptively; the Kaggle OS codename is reported.
- **U4 v18 forces, blinded:** raw R6a against the raw Kaggle U3 smoke for the 8 cases: per case |delta F| <= 0.1 sigma; |signed mean of (local -
  Kaggle)| <= 0.1 floor; every state-minus-parent difference at the smoke shift moves by at most 0.1 max(3 SE, floor). The record holds only these
  discrepancies, byte identities and pass flags.

**Verdict per family:** a definite failure of any part is `LOCAL_ENV_FAIL` (it dominates); otherwise a missing run or reference, or T2/T3 without their
required same-mesh pairs, is `INCOMPLETE`; otherwise `LOCAL_ENV_PASS_BITWISE` if every compared force history and every same-mesh solver block equals
Kaggle's (T: every T3 pair and every T1 same-mesh solver path; U: the 14 X3 and the 8 v18 `coefficient.dat`), else `LOCAL_ENV_PASS_TOLERANCE`.
"Bitwise" refers to force histories and same-mesh solver blocks only; mesh records compare to relative 1e-6.

**Why these scales.** The parent decision asked for tolerances on the quantities that drive each study's decision: T2-0c's difference noise (the morph
gates use sigma_eff = max(sigma_fit, sigma_iter) with sigma_iter = the largest raw tail Cl std of a scan, so 0.1 x a case's own tail std is at most 0.1
sigma_eff) and the sign and size of U3's paired differences (judged against the 32-phase SE and the calibration floor: per-case noise averages down over
phases, a systematic bias does not, hence the separate bias and difference checks).

**Carried conditions (both verdict classes).** (1) Every gate input of a study's verdict comes from one environment: no Kaggle and local cases mixed in one
gate input. (2) For `PASS_TOLERANCE` the largest observed discrepancies are handed to the study, which compares them with its own measured noise and
labels that comparison in its analysis. (3) If the variant spread is `ABOVE_SCALE`, T2-0c must treat generator-variant noise as part of its remeshing
noise (its replication labels `REPLICATED_BITWISE` and `CROSS_KERNEL_IDENTICAL` inherit it).

## 6. Consequences, repeats and fixes (fixed now)

- **T `PASS_*`:** T2-0c kernels R, M, S may run locally with this lock, within the scope of section 8 (the T2-0c session amends its registration and
  cites the lock SHA-256 and this result). **T `FAIL`:** T2-0c stays on Kaggle CPU.
- **U `PASS_*`:** the U3 formal kernel may run locally (the M2 session amends). **U `FAIL`:** U3 stays on Kaggle CPU.
- **Infrastructure loss** (non-zero container exit, no `DONE`, a wrapper record that differs from the freeze, a mount, network or apt index/installer hash
  failure before the first case record): the run is repeated once as `NAME.attempt2`; both attempts are archived; the first complete attempt counts.
  A persistent apt index or installer hash failure stops the gate (`INCOMPLETE`, recorded); the lock is never edited to pass it.
- **Missing same-mesh pairs** (T2 < 1 or T3 < 2 cases): the extra replicate `t20b_c`, then `t20b_d`, with the same runner and cases; the comparator reads
  every `t20b_*` run present. Still missing after that: the T family is `FAIL` (wording in the result: the local generator did not draw Kaggle's mesh
  files often enough to compare).
- **Comparator invocations:** the result file is created exclusively and every invocation is appended to `gate_ledger.jsonl` (time, output hash, the
  comparator and freeze SHA-256, the input hash). A second invocation is allowed only after an `INCOMPLETE` that section 6 resolves (repeat or replicate),
  to a new output file; its ledger line records why.
- **Harness fixes:** only mount, path and exec defects of `scripts/local_openfoam.py run` may be fixed after the freeze, with the diff and the reason
  recorded and the new script SHA-256 appended to `script_sha256_allowed` in the freeze record before the repeat; the case lists, the subset harness,
  the Docker resource arguments, the comparator, the criteria and every runner are never changed. A change of the comparator voids this round.
- A failure is recorded fail-closed with its diagnosis; both sessions are told to stay on Kaggle CPU.

## 7. Procedure

Draft -> one adversarial review (numerical and controls; sonnet) -> adoption table (section 9) -> freeze (freeze record, commit, push, #57 and #61
comments) -> R1a/R1b, R2/R3, then R4/R5/R6a/R6b side by side -> sanitise R6a -> the comparator once -> section 10, evidence and `SHA256SUMS` (checked by
`scripts/check_sha256sums_tracked.py`) -> `STATE.md`, `docs/phase_plan.md`, comments on #57 and #61 -> the two sessions are told the result.

## 8. Scope of a pass, and what is not claimed

A T pass covers the T2-0c runner paths exercised here: remeshed and morphed meshing over all 262 registered geometries, the gmsh-to-OpenFOAM chain, SA
wall-function `simpleFoam` to 5000 iterations on 5 T2-0b cases (one unsteady), and 7 solver paths (xfine30, morph, B', linear blend, shape, forced
continuation) at <= 200 iterations for determinism. It does not cover 15000-iteration continuations with forces or long xfine30 runs against a Kaggle
reference; T2-0c's own budget rule applies (its kernels were estimated at 3.4-4.2 h of an 11 h budget on Kaggle; the wall-time ratio is reported). A U
pass covers the X3/U3 runner, the coarse Stage V mesh and both v17 (X3) and v18 (U3 smoke) STLs. Not claimed: any physics, accuracy, grid-independence,
solver-equivalence or benchmark statement; any T2-0c or UNC-01 result; other runners, other OpenFOAM applications, parallel (MPI) runs, the jammy lock
suite, other hosts or a rebuilt image.

## 9. Review record (one round, 2026-10-21, before any local solver run)

Two sonnet reviewers read the draft, the comparator, the runtime script, the tests, the lock and the precedent: numerical (13 findings) and controls (15).
Both judged it not ready to freeze. A = adopted, P = partly adopted.

| finding | decision and change |
| --- | --- |
| C1 blocker: one-shot output vs repeats; partial runs became FAIL; crash on a missing `DONE`; INCOMPLETE masked FAIL; synthetic tests only | A: missing runs and files are `INCOMPLETE` (never a crash), a definite failure dominates, per-part error capture, exclusive output plus `gate_ledger.jsonl`, the repeat rule of section 6; self-comparison test on the real Kaggle references |
| C2 blocker: the comparator never checked what ran | A: every run's `local_run.json` is checked against the freeze record (image, lock, script, runner, CPU and memory arguments, return code, package list) plus `DONE` |
| C3 blocker: image not recoverable; runtime re-install unchecked; index drift | A: `docker save` tarball with SHA-256 and restore command; run by image ID; post-run package list compared with the lock on every run; index/installer drift = infrastructure, persistent drift stops the gate; a rebuild is a new environment |
| C4: blinding text vs UNC-01 §15; thin leak checks | A: section 4 states the U4 disclosure and which text governs; sanitised archives must hold one `result.json`, `EXCLUDED_SHA256.json` and no force file; the sanitiser is applied to the runner's directory only; raw outputs kept until the commit |
| C5: freeze record contents, truncated hashes | A: full SHA-256 in section 4 and in `freeze.json`; rendered runner copies in the evidence |
| C6: copied T2-0c smoke-2 records lack provenance | A: `PROVENANCE.md` and `SHA256SUMS` coverage |
| C7: probe prose only; design set after the data; pair probability not priced; selection effect | A: probe script and output recorded with full hashes and date; probability stated (section 3); the selection effect disclosed; T3 `FAIL` after replicates keeps its fail-closed consequence with the gmsh-draw wording |
| C8: X3 shift pair without a rule | A: the first mirror pair of the formal case order, stated as the rule; the vacuous sign rule replaced (N2) |
| C9: repeats, timeouts and fixes leave forking paths | A: mechanical infrastructure definition, timeouts and deadline hits are results, one repeat, attempts archived, fixes limited to mount/path/exec with the freeze record extended |
| C10: subset harness undisclosed and untested | A: section 2 lists its deviations; stub-runner test |
| C11: no independent recomputation or input hashes | A: force statistics recomputed from `coefficient.dat` and required to match; input hashes in the ledger; `SHA256SUMS` |
| C12: claims wider than the evidence | A: section 8 scope; carried condition (3) |
| C13, C14, C15 | A: sections 9 and 10 filled and append-only; lock SHA pinned at run time and `build`/`lock` refuse after the freeze; residual differences labelled untested |
| N1 blocker: relative-only float test fails on `contour_err_m` ~ 1e-16 | A: absolute floor 1e-12 (test included) |
| N2: the sign rule could never trigger | A: replaced by the bias and difference checks |
| N3: 0.1 sigma per case is not 0.1 of U3's decision scale; systematic bias | A: signed-bias check against 0.1 floor and difference check against 0.1 max(3 SE, floor), contrasts reported with SE |
| N4: tau_T from remeshing sigma, not T2-0c's morph sigma; plateau and convergence not compared | A: tolerance 0.1 x the case's own tail std; plateau flags, rows, continuation, iterations, unsteady class and tail std (10 %) compared |
| N5: no unsteady, morph, xfine30 or continuation coverage | P: the unsteady T2-0b case added to R2/R3; R1 run twice so the 7 solver paths (incl. xfine30, morph and forced continuation) give residual-level determinism; force-level coverage of those paths is not available without a new Kaggle reference and is excluded in section 8 |
| N6: U3 compared no solver quantity on v18 | A: U4 (blinded forces) and R6 run twice; solver blocks compared descriptively |
| N7, N8 | A: see C1 (crash handling; self-comparison test) |
| N9: same-mesh solver residuals unbounded; BITWISE scope | A: relative 1e-3 bound on same-mesh residuals as a failure; scope of "bitwise" stated |
| N10: integer strings parsed as floats | A: integer strings compare exactly |
| N11: throughput | A: wall time per case reported; section 8 cites T2-0c's budget |
| N12: jammy not covered; U3 OS | A: sections 2 and 8 state it; the Kaggle U3 smoke codename is reported |
| N13: variant spread as an input to T2-0c | A: carried condition (3) |

Added after the reviews were launched, before any run, in response to the M2 session (not to any data): U4 (blinded v18 force comparison). It was not
reviewed by the reviewers; its blinding is covered by a test (no value or state difference in its output).

## 10. Result (append-only)

### 2026-10-21, round 1: T `LOCAL_ENV_FAIL`, U `LOCAL_ENV_PASS_BITWISE`

Freeze: commit `e8579970` (pushed; #57 and #61 comments), freeze record SHA-256 `29429f6d28c684df8a07eb7be937857be9cffd1a2d8ae57776f35c65e6fd606e`.
Comparator invoked once (`gate_ledger.jsonl`, 2026-10-20T17:16:11Z UTC): `gate_result.json` SHA-256
`0496603b617e6057079e6214c05dc156f48b3f955c9f3c93f40181daaa6d2c7f`, comparator `41c6ff98…6715`, input hash `d3b3c87c…f9f`.

**Runs** (all ten counted: return code 0, `DONE`, frozen image, lock, script and runner, registered arguments, package list after the run = lock; no
repeat, no extra replicate, no harness fix):

| run | `--cpus` / `--memory` | wall (s) | outcome |
| --- | --- | --- | --- |
| R1a `t20c_smoke2_a` | 4 / 8g | 2123 | FINISHED_SMOKE, MESH_OK 256, COMPLETED 7 (= Kaggle counts) |
| R1b `t20c_smoke2_b` | 4 / 8g | 1571 | same counts |
| R2 `t20b_a`, R3 `t20b_b` | 4 / 8g | 1106, 1046 | 5/5 COMPLETED each, none continued |
| R4 `x3_a`, R5 `x3_b` | 1 / 8g | 1427, 1436 | 14/14 COMPLETED each |
| R6a `u3_smoke_a`, R6b `u3_smoke_b` | 1 / 8g | 953, 953 | 8/8 COMPLETED each; R6a sanitised by the frozen M2 sanitiser |

**Procedural deviation (no numerical effect):** section 4 limited concurrent runs to 4 CPUs in total because another study occupied the host. After that
study ended, the parent session allowed up to 8 CPUs (message of 2026-10-21); R2/R3 then ran alongside R1, and R4-R6b (4 x 1 CPU) alongside R1b. The
per-run arguments stayed the registered ones and the comparator verified them for every run (`deviations.log.gz`). Host load at the run starts: 76 (R1a,
while the other study was still running) down to 8.

**T family (T2-0c pipeline): `LOCAL_ENV_FAIL`.**
- T1 fails: of 262 geometries, 174 agree and 88 do not; 86 differ in cell count (med30, fine30 and xfine30, remeshed and morphed; coa30 all agree) and
  2 only in checkMesh statistics; `bases.json` differs in the six B' bases at +0.5 deg (cell counts), while the nine 0-deg baselines are bit-identical.
  Mesh files identical to Kaggle: 62 of 262.
- T2 passes: the local pipeline is deterministic. All 262 mesh files are identical between R1a and R1b and all 7 solver paths have identical residual,
  continuation and y+ blocks; the 5 T2-0b cases have identical mesh files and byte-identical `coefficient.dat` in R2 and R3.
- T3 has no pair to test: none of the 5 local T2-0b meshes equals Kaggle's (4 differ in cell count; `fine30 h/c 0.224 +1` has Kaggle's 26863 cells but a
  different file), so T3 alone would be `INCOMPLETE`; the definite T1 failure dominates (section 5), and no extra replicate was run (R2 and R3 already
  agree bit for bit, so a replicate would draw the same meshes).
- Descriptive: local minus Kaggle Cl (tail means) on these different meshes: +0.0028 (`fine30 0.224 -1`), +0.0060 (`fine30 0.224 +1`), +0.0089
  (`med30 0.134 -0.25`), -0.0103 (`med30 0.134 +0.25`), -0.0206 (the unsteady `fine30 0.09 +1`), i.e. 0.2-0.75 % of Cl for the steady cases, the size of
  T2-0b's remeshing sigma (0.0023-0.0048): label `VARIANT_SPREAD_ABOVE_SCALE`. Kaggle self-consistency 34 of 41 (as in section 3).
- **Diagnosis (consistent with the data, not proven):** every geometry without displacement (0 deg, no shape: 28) has Kaggle's cell count (26 identical
  files, 2 numbering variants); the differences appear only where the generator applies a non-zero rotation or shape displacement in floating point (234
  geometries, 86 with other cell counts). OpenFOAM itself reproduces Kaggle bit for bit (U family below). The difference therefore enters in the Python
  numerical stack that computes the rotated or displaced contour (Python 3.12.3 / numpy 2.5.4 / scipy 1.18.1 under Rosetta without AVX-512 here; Kaggle's
  Python 3.13.15 with unrecorded numpy/scipy on a Xeon), and gmsh turns last-bit differences of the contour into different triangulations. This is also a
  reason for the 7 of 41 cross-session Kaggle differences being possible at all.
- **Consequence (section 6): T2-0c stays on Kaggle CPU.** Carried note for T2-0c: its meshes depend on the platform's floating-point arithmetic at the
  remeshing-noise level; its `REPLICATED_BITWISE` label against T2-0b can fail for that reason alone.

**U family (U3 / X3 pipeline): `LOCAL_ENV_PASS_BITWISE`.**
- U1: R4 and R5 byte-identical for 14/14 cases; R6a and R6b byte-identical for 8/8.
- U2: all 14 X3 cases have Kaggle's mesh records (cells, points, concave cells, snappy levels), solver blocks and **byte-identical `coefficient.dat`**;
  every discrepancy is 0 (per case, mean bias, all 42 differences); the mirror-pair direction contrasts equal Kaggle's exactly (for example D0 downforce
  0.0037185 N, D1 downforce 0.000116 N against the 32-phase SE 7.2e-5 N; these are public X3 values).
- U3: the sanitised v18 smoke agrees with the sanitised Kaggle archive for 8/8 cases (mesh records, stage return codes, STL hashes) with identical solver
  blocks; the Kaggle archive reports noble.
- U4 (blinded): the 8 v18 force histories are byte-identical to Kaggle's; mean bias 0 and every state-minus-parent discrepancy 0. No v18 force value or
  difference is in any record.
- **Consequence (section 6): the U3 formal kernel may run locally** with this lock (the M2 session amends #61). Throughput: the U3 smoke took 953 s for 8
  cases here (about 119 s per case at 1 CPU with three other containers on the host) against 682 s on Kaggle; X3 cases 64-131 s (mean 97) against 39-43 s.

Validation: `pytest -q tests/test_local_openfoam.py` 8 passed; full `pytest -q` 2941 passed, 73 skipped, 0 failed; `compileall` and `git diff --check`
pass. Evidence: `docs/evidence/local_openfoam_env_2026_10_20/` (`README.md`, `SHA256SUMS`). Qualification flags unchanged (all false).
