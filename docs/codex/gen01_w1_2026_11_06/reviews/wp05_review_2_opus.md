# Opus source review 2 of WP5 (PR #87, 45917d8c), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions: `docs/topo2d00_registration_2026_11_01.md` Amendment 3, `05_tr00_rans.md` Amendment 2, `04_topo2d_waterlily.md` Amendment 3.

# WP5 source review, round 2 (feat/gen01-w1-05-tr00-rans @ 45917d8c, PR #87)

Read-only. Scratch scripts and meshes are in `scratchpad/r2/`. `pytest -q tests/topo2d00` gives **190 passed in 53.8 s**. `git diff e3dcdf61 HEAD` on the 17 frozen files plus `analyze_t20b/c.py` is empty. The WP4 inputs below are the **uncommitted working copy** of the WP4 worktree, which I only read.

## Round-1 findings

**A1: CLOSED.** `_density` (t2d_multibody_case.py:28-46) refuses a non-cap turn above 5° and any segment longer than `ds`, cap included, with element/index/value in the message. There is no resampling: one gmsh line per segment.

| Input | Result |
| --- | --- |
| The five old polygons | refused (segment 0.0115 m > ds) |
| One 6° kink on a dense WP4 polygon | refused ("vertex 292 turn 6.12 deg") |
| NACA 4412, uniform 0.25 mm | accepted (max turn 4.15°) |
| NACA 4412, uniform 0.5 mm | **refused** (8.28° at the LE) |
| NACA 4412, uniform 1 mm | refused (16.4°) |
| All 10 WP4 WIP scenes | accepted (max turn 3.02°, max segment 0.99 mm) |

The local `runner.py`/`kernel_plan.json` files now read `ready=False`/`development`; `render_invalidation.json` holds 36 before/after SHAs. See N1 and N3.

**A2: CLOSED.** Classification uses the inherited `force_summary`, then `analyze_t20c.classify`. There is no `limit_cycle`/`urans_stats`/`steady_stats`, and `t2d_foam_case.CONVERGENCE is collect_rans.CONVERGENCE`. Re-run:

| Series | Result |
| --- | --- |
| period-2 alternation, 0.3 % | VALID |
| period-7 sine, 0.28 % | VALID |
| Gaussian, 0.2 % | VALID |
| period-2, 1 % | UNSTEADY |
| Gaussian, 1 % | UNSTEADY |
| period-200 sine, 1 % | SOLVER_FAIL (plateau fails) |

All unusable rows export as `NUMERICAL`.

**A3: CLOSED.** The plan is computed once from all six geometries. With the WP4 WIP scenes the minimum gap is 8.395 mm (E3), giving 4 layers / 3.2208 mm in both families; the ground block uses the same values.

E3_sharp missing fails closed:
- the complete-plan call raises;
- the render comes out `development`;
- `write_case(5000)` refuses a non-study plan.

The collector asserts equality within one `collect`. NOTE-level residuals:
- plan rows have no `n_layers`, so the plan cross-check never fires;
- TR-00 and main sets collected separately are not cross-checked;
- `boundary_layer_settings` does not recompute `T.layers`, so a hand-edited n=3 plan is accepted.

**A4: CLOSED (code).** Duplicate mesh SHAs produce `DEGENERATE_REALISATIONS`: point estimate kept, `ci90=null`, `ratio_test_status=INCOMPLETE`, run statuses INCOMPLETE. In practice the mechanism is degenerate; see N2.

**A5: CLOSED (WP5 side).**
- `observable` is on every row, force, summary and reference, and a mismatch is refused.
- h/c₁ and h/c are reported.
- Four thickening-alone descriptors use the same observable on both arms.
- The estimator is Σ|d1−d2| over elements.

WP4 does **not** yet document this in a committed state:
- WP4 HEAD's schema is still 04ebcf76, with no observable.
- WP4 WIP's schema and `analyze.py` check the observable but treat `cell_summary`/`thickening_alone` as optional.
- WP5's schema (d96200bc) requires them.

The two schemas must be reconciled into one file.

**B1: CLOSED.** The proxy is informational; checkMesh decides.

**B2: CLOSED.** A non-finite row gives `SOLVER_DIVERGED`, including timed-out runs. numpy parses `nan`, `-nan` and `inf`.

**B3: PARTIALLY CLOSED.** Ready requires a clean whole tree, six VERIFIED geometries and a matching freeze record. But:
- the freeze record is any external JSON;
- the committed `wp05_validation/rendered_kernels_and_inputs.tar.gz` still holds `runner.py` with `'ready_for_execution': True` and the attempt-1 code, revoked only by the receipt.

**B4: CLOSED.** One line reference is wrong: "t20_case 92–99" should be 82–90.

**C1: PARTIALLY CLOSED.** Reader-B copies of reader-A CSVs whose bytes differ but whose content is identical are **accepted with sensitivity 0.0**:
- a UTF-8 BOM added;
- CRLF line endings;
- `0.1` written as `0.10`.

Fix: compare the parsed points, not file hashes.

**C2: CLOSED.** Per-reading positive Cl per element, refusal of swapped surfaces and refusal of surfaces with fewer than 10 points all work.

**E1: CLOSED.**

## Regressions (git diff cb4df650)

Unchanged:
- `read_force_parts`, `NORMALIZATION` and the convention (Cl = −Fy/(q·Aref));
- the closure checks and last-segment analysis.

Changed:
- `usable` now checks only the selected observable (it required both);
- `PARSE_FAILED` moved to the solver statuses;
- see N4.

## New findings

**N1 MAJOR: the density guard is one-sided (no minimum segment or adjacent-ratio check).**
- Every WP4 WIP main polygon has a **5.6 µm segment** at about (27.3, 127.1) mm, next to segments of about 0.9 mm.
- Meshed at fine30 with the study plan, E1, E1_sharp, E2, E2_sharp and E3 all give `det_min` 1.46e-4 and `weight_min` 0.0097, with the worst cell at that segment.
- The T2-0 proxy is calibrated tighter than checkMesh, and it predicts a checkMesh rejection. I did not run checkMesh.
- If so, every realisation is MESH_FAILED.
- Fix: a floor such as ds/10, or an off-cap adjacent ratio of at most 3; plus a WP4 fix.

**N2 MAJOR: realisations collapse locally.**
- E2_sharp med30 generated in **8 separate processes** (the production path) gave 8 byte-identical meshes.
- Of 3 in-process repeats, two were identical; the third shares 99.5 % of its nodes with the first.
- If the same holds on Kaggle, every cell is `DEGENERATE_REALISATIONS` and TR-00 is always INCOMPLETE.
- This triggers the contingency in Amendment 1 §4. The docstring's "not run-to-run reproducible" is contradicted.

**N3 MINOR: the sampling rule contradicts the guard.** Amendment 1 §1's "≤ 1 mm (T2-0 `airfoil_points` rule)" fails the 5° guard: T2-0's own section is refused (11.4°). The wording needs curvature-adaptive sampling.

**N4 MINOR (regression): integrity failures are recorded as MESH_FAILED.** Generator/mesh-phase exceptions (run_rans.py:212) were `RUNNER_EXCEPTION` in attempt 1. They include mismatches of the boundary-layer plan SHA, the geometry SHA and the convergence policy. A checkMesh cut short by the session deadline is also MESH_FAILED.

**N5 MINOR: a test runs another worktree's uncommitted code.** test_collect_rans.py:354-363 executes the sibling worktree's uncommitted `analyze.py` and asserts `TR00_PASS_RATIO`.

**N6 MINOR: thickening-alone can use an unsettled observable.** Its pairs rely on `usable`, which certifies only each row's own observable.

NOTES:
- The two analyzers rank cell states differently (WP5: MESH_FAILED before NUMERICAL; WP4 the reverse).
- `E1_h80.json` loads as `E1` while the export hard-codes `height_mm=100`; only the freeze geometry SHA guards this.

## Report honesty

Everything is backed under `wp05_amendment1_validation/`:
- 190 tests passed (JUnit);
- the full suite at 3672/74/0 (3482 + 190);
- 17 frozen files unchanged (I verified this);
- the renders expired;
- the 12 script/test/schema hashes match HEAD byte for byte.

N2 is not mentioned in the report.

## Verdict

**INTEGRATE_AFTER_FIXES.** Attempt 2 closes the blocker and the three majors. Force bookkeeping is unchanged and nothing is runnable. Before integration:
1. Add the minimum-segment guard and get WP4 to fix the sliver (N1).
2. Check reader distinctness on content (C1).
3. Send integrity and deadline failures to RUNNER_EXCEPTION/INCOMPLETE (N4).
4. Make the test hermetic (N5).
5. Reconcile one shared schema with WP4 (A5).

Before any freeze or render:
6. Run the Kaggle reproducibility check and decide the realisation mechanism under Amendment 1 §4 (N2).
7. Amend the §1 wording (N3).
