# OpenCode Repository Instructions

Read these files before changing code or evidence:

1. [`docs/opencode_handoff_2026_09.md`](docs/opencode_handoff_2026_09.md)
2. [`docs/README.md`](docs/README.md)
3. [`docs/phase_plan.md`](docs/phase_plan.md)
4. [`docs/problem_register_2026_09.md`](docs/problem_register_2026_09.md)
5. [`docs/problem_resolution_plan_2026_09.md`](docs/problem_resolution_plan_2026_09.md)

Authority is deliberately split: `docs/phase_plan.md` is the sole roadmap,
status, and execution-order authority; `docs/problem_register_2026_09.md` is
the issue ledger. The v2 problem and fixed-grid contracts are authoritative
for schemas and artifact semantics. Prefer links to those documents over
copied historical prose.

Keep every claim evidence-scoped. Contract or capability evidence is not
target-physics or benchmark evidence. Do not claim grid-independent downforce,
full-vehicle/high-Re FSAE qualification, or a qualified Stage T/Stage V
ranking. A raw `checkMesh` line saying `Failed 1 mesh checks.` on the registered
correct V0-V3 cases is allowed concave-cell output under the qualification
profile, not a raw clean pass.

Validate the smallest relevant slice, then on macOS/Linux run
`.venv/bin/python -m compileall src tests`, `.venv/bin/python -m pytest -q`, and
`git diff --check` when applicable. On Windows PowerShell, use
`.\.venv\Scripts\python.exe -m compileall src tests` and
`.\.venv\Scripts\python.exe -m pytest -q`. Record commands, results, artifact
paths, hashes, and evidence class separately from conclusions.

Inspect `git status`, `git diff`, and recent history before editing. Use the
branching rules in `docs/git_branching_strategy.md`. After an authorized
implementation or documentation task is complete and validated, commit and push
only the intended files to the current feature branch. Explicit review-only,
no-edit, or no-push instructions are exceptions. Never force-push, reset,
checkout, or overwrite unrelated work.
