# Git branching strategy

This repository uses a trunk-based GitHub Flow variant.

## Long-lived state

`main` is the only long-lived branch. It is the integration and release
baseline. There is intentionally no permanent `develop` branch: the project
needs frequent integration of solver contracts, geometry gates, and benchmark
evidence, so a second long-lived integration line would increase divergence.

## Short-lived branches

Create branches from the latest `main` and delete them after merge:

| Prefix | Use |
| --- | --- |
| `feat/` | A user-visible capability or roadmap implementation |
| `fix/` | A defect correction with a regression test |
| `chore/` | CI, packaging, documentation, or repository maintenance |
| `exp/` | An experiment whose result is evidence, not necessarily mergeable code |
| `release/` | A temporary release hardening line |
| `hotfix/` | A fix for an already released tag |

Use a short issue or task identifier and a descriptive slug, for example
`feat/g2-case-runtime` or `fix/mesh-patch-compatibility`.

## Pull requests and releases

- Every change to `main` goes through a pull request.
- CI must pass before merge; solver/Docker evidence is reported separately
  from the default Python CI.
- Keep feature branches short-lived and rebase or merge `main` before review
  when they become stale.
- Create `release/vX.Y.Z` only when a release is being hardened. Prefer a tag
  from `main` when no release-specific fixes are needed.
- Fix the defect on `main` first, then cherry-pick to a release branch when a
  release branch exists.

This follows the lightweight GitHub Flow guidance and the trunk-based
development recommendation to use short-lived review branches rather than
multiple permanent development branches.
