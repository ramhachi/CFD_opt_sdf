# v16 OpenFOAM environment reproduction kernel

This private Kaggle CPU kernel replays only the archived v16 Stage V PASS
parent fixture. The `runner.py` script embeds the criteria, package lock,
input STL files, and fresh case template so the kernel runs when Kaggle mounts
only the submitted script. It installs the OpenCFD v2512 package family from
the official Ubuntu Noble amd64 apt repository after checking the pinned official apt-index hashes, exact versions and package
SHA-256 values.

The immutable round 2 criteria are in `criteria.json`; package and apt-index
SHA pins are in `openfoam_package_lock.json`. Round 1 is preserved as a rejected
preexecution snapshot. Run `python3 test_allrun.py` for the shell fail-closed
regressions. After downloading a successful Kaggle output, verify it independently
with `python3 verify_artifact.py ARTIFACT_DIR criteria.json openfoam_package_lock.json PARENT_REGISTRATION_MANIFEST`. Run locally without installing OpenFOAM:

```bash
python3 runner.py --self-check
```

Kaggle execution writes its captured case, logs, exact package files and
`result.json` under `/kaggle/working/openfoam_xfid_v16/`. The only allowed
early pilot is this environment reproduction. It cannot issue an XFID verdict;
that comparison needs the frozen composite Candidate C contract under #44.
