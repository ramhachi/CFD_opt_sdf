# Session coordination — 2026-09-20 (second session, Gate 0 → WP5 → WP6)

Two OpenCode sessions are live on `feat/p0-openfoam-closed-loop`. To keep their
worktrees non-overlapping, working assignments and rules are recorded here.
Authority remains `docs/phase_plan.md`; this file only coordinates.

## Division of labor (claimed areas)

| Session | Files claimed | Current slices |
| --- | --- | --- |
| Session A (this one, "WP5/WP6") | `src/cfd_sdf/analytic_candidate_shapes.py` (new), `src/cfd_sdf/cross_fidelity_ranking.py` (new), WP5/WP6 experiment drivers and manifests under `work/fixed_shape_ranking_2026_09/`, `docs/evidence/*` for the ranking program | Gate 0 C1 semantic binding (committed `6684f97`), WP5 analytic binary shape generator + same-grid T1 evaluation + Stage V anchor-STL runs, WP6 ranking report |
| Session B (other terminal) | `src/cfd_sdf/fixed_grid_primal.py`, `src/cfd_sdf/fixed_grid_gradient_gate.py`, `src/cfd_sdf/fixed_grid_canonical_state_injection.py` and their tests | WP4 Gate-0 convergence-qualification and candidate binding (committed `2bfbcbb` + in-flight edits) |

## Rules both sessions must follow

1. Never `git add -A` / `git commit -a`. Stage only files you authored or were
   assigned above; leave the other session's in-flight edits uncommitted.
2. `git pull --rebase` is forbidden while the other session is mid-edit; send
   commits with plain `push` and re-sync before the next commit.
3. Never commit the other session's files, even to "fix" their tests.
4. Long docker runs: name containers distinctly in logs (run root directory is
   already the disambiguator) and assume docker may be contended; keep each
   solver run ≤ ~3 GB RSS.
5. The measured Stage V downforce uncertainty band is explicitly carried as
   declared: **downforce abs 0.0129–0.0147** (V2→V3, plain and wake families,
   `docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json`) and **Cd rel
   ~0.03** per transition. Per user decision the reduced-case refinement
   question (P16 factor hunting) is CLOSED for this phase: the band is treated
   as given uncertainty in WP5/WP6, not something further V-levels must shrink.
6. Union-box force values remain non-comparable to fixed-domain values.

## Non-interference for evidence

- Session A pre-registers the fixed-shape ranking manifest BEFORE any run
  (`docs/evidence/fixed_shape_ranking_manifest_2026_09.json`).
- Neither session edits the other's evidence JSON files.
