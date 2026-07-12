# Contributing to CFD_opt_sdf

## Branches

`main` is the only long-lived branch and must remain integratable. Create a
short-lived branch from `main` for each change:

- `feat/<issue>-<slug>` for functionality
- `fix/<issue>-<slug>` for bug fixes
- `chore/<topic>` for documentation, CI, and maintenance
- `exp/<topic>` for experiments that are not intended to merge directly
- `release/vX.Y.Z` only during a release freeze
- `hotfix/vX.Y.Z-<slug>` only for a released version

Do not create or maintain a permanent `develop` branch. Open a pull request
for every change to `main`; delete the short-lived branch after merging.

## Commits and pull requests

- Keep commits small and describe one coherent change.
- Use an imperative, concise commit subject, for example
  `Add generic flow-case compiler manifest`.
- Include tests and diagnostic artifacts when changing solver or optimizer
  behavior.
- The pull request body must state the motivation, scope, validation commands,
  and any evidence limitations (especially capability versus target-physics
  evidence).

## Required local checks

From the repository root, run:

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
python -m compileall src tests
python -m pytest -q
git diff --check
```

OpenFOAM/Docker checks are profile-specific and should be recorded separately
from the default Python CI result.
