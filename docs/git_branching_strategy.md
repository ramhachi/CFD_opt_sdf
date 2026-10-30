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

## Cleanup

Merged branches must not accumulate. GitHub deletes the head branch on merge
(`delete_branch_on_merge`), and `fetch.prune=true` drops stale remote refs.
After a merge, remove the worktree (`git worktree remove <path>`), then run
`git sweep` (a local alias for `git fetch && git branch -d` on every merged,
non-checked-out branch; recreate with the command in `git config alias.sweep`
of the main checkout if it is missing). It never force-deletes.

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

## Current practice (as of 2026-10-30)

The rules above are the intended end state. Since 2026-09-11 all integration has happened on
`codex/kaggle-batch-migration`, merged with `--no-ff` only (no rebase, squash or force-push). Branch experiments from it, record results on
it, and read its `docs/phase_plan.md` and `docs/STATE.md` as the current status. Since PR #71/#72 (2026-10-30) changes may be proposed as pull
requests whose base is `codex/kaggle-batch-migration`; GitHub creates a merge commit and deletes the head branch on merge.

`main` is a mirror of the integration branch: it is synced by a `--no-ff` merge of `codex/kaggle-batch-migration` into `main` at milestones
(first sync 2026-10-30, after PR #71/#72), never by rebase or force-push, and nothing is committed to `main` directly. `main` stays the
default branch, so a default-branch search sees the last synced milestone rather than live work; branch protection was not enabled. The
Python CI (`.github/workflows/ci.yml`: compileall, `git diff --check`, `pytest -q` on Linux/macOS/Windows) runs on pushes to `main`, so each
sync is also the first CI run of that milestone on GitHub runners; a CI failure there is recorded, not fixed on `main`. Since 2026-10-30 CI also
runs on pull requests to the integration branch and on demand (`workflow_dispatch`), on Python 3.12 for ubuntu and macOS only; Python 3.10 and
Windows are not tested (reasons in the workflow file), and two exact replays of macOS-produced records are skipped off macOS (`tests/conftest.py`).

Cleanup rule (user decision 2026-10-14): after a `--no-ff` merge, delete the local and remote feature branches that are fully contained in the
integration branch (`git branch -r --merged origin/codex/kaggle-batch-migration`), remove their worktrees, and leave untouched any branch
that is unmerged, checked out in another worktree, or `main`. The historical 2026-10-13 wording of this section is superseded by this one.
