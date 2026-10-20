# Local OpenFOAM runtime (LOCAL-OF-01)

Runs a registered Kaggle CPU OpenFOAM kernel unchanged in a pinned local Docker image (linux/amd64 Ubuntu 24.04.5 noble under Rosetta, OpenFOAM v2512
`2512.0-2` from the registered noble lock). Use it for a study only after the environment gate allows that study's pipeline:
`docs/local_openfoam_env_gate_2026_10_20.md` section 10 (T family = T2-0c pipeline, U family = UNC-01 U3 / XFID X3 pipeline).

- Lock: `local_openfoam_lock.json` (image ID, base digest, `dpkg_list.txt`, OpenFOAM packages, Python stack, saved tarball). The wrapper refuses to run
  if the local image ID differs from the lock or the lock differs from the frozen one. If the image is gone: `docker load -i work/local_openfoam/image/
  e9ceb8a79fd8ceb9.tar` (the tarball is git-ignored; its SHA-256 is in the lock). A rebuilt image is a new environment and needs a new gate round.
- Run a kernel directory (its `runner.py` and `kernel-metadata.json`; a dataset is mounted under `/kaggle/input/<slug of the first dataset_sources entry>`):

```bash
python3 scripts/local_openfoam.py run infra/kaggle/kernel_unc01_u3 --out work/local_openfoam/u3_formal --dataset work/kaggle_unc01_u3_dataset --cpus 1
```

```bash
python3 scripts/local_openfoam.py run work/t20c_kernel_remesh --out work/local_openfoam/t20c_remesh --cpus 4
```

  The runner writes where it writes on Kaggle, under `--out` (`openfoam_xfid_gridphase_x3/` for X3/U3 runners, `t20c/` for T2-0c). `--out/local_run.json`
  records the lock and image identity, runner and wrapper SHA-256, the Docker arguments, return code, the post-run package-list check
  (`dpkg_after_matches_lock` must be true) and the host load. Defaults: `--cpus 4 --memory 8g` (no swap); a serial X3/U3 runner needs one CPU. The runner
  still runs its own hash-locked `install_openfoam` at start (internet needed; it installs nothing new).
- Docker Desktop must be running; `docker` is in `/Applications/Docker.app/Contents/Resources/bin` if it is not on `PATH`.
- Known property of the T2-0 generator (also on Kaggle): gmsh writes one of a few numbering variants of the same mesh per run, so mesh-file hashes and the
  last digits of forces can differ between two runs of one geometry; see the gate's section 3 and its variant-spread label.
