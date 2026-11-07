# Opus source review 2 of WP6 phase A (PR #82, 6dcd7c62), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions: `06_geom_s1.md` Amendment 4.

# WP6 phase A (GEOM-S1) source review, round 2: feat/gen01-w1-06-geom-s1 @ 6dcd7c62, Draft PR #82

Read-only; the worktree is still clean. Repros: `scratchpad/wp06r2/*.py`; round-1 `scratchpad/wp06/gates1.py`/`gates2.py` re-run. `pytest tests/scene`: 198 passed.

## Round-1 findings

**M1: CLOSED.** `_bounds_gates` now takes the bounding box from `scene.components` (`gates.py:414-416`). `_masks_gate` gets `movable_solid` and `movable_labels` (`gates.py:510-516`). `_pair_gate` still checks movable-vs-fixed pairs (`gates.py:372`). Round-1 repro (a), wing plus a fixed tyre touching z=0, now passes; both new fixed-context tests are behavioural. The thickness gate still covers fixed context; see N1.

**M2: CLOSED (minimal translation), with a robustness caveat (N2).**
- `merge_candidates` now moves b by `(pa-pb)(1+δ/gap)` (`events.py:236`), using the SLSQP nearest pair (`events.py:154-205`).
- Round 1's realistic main+flap: nearest gap 0.0633708 = dense oracle; post-merge min φ_a on the flap is −δ; the flap stays at the trailing edge.
- Across 124 random separated cambered/reflexed pairs, the maximum of (d−oracle)/t is 9.6e-8.
- The non-identical merge passes in 2D and 3D, and `classify_change` returns `merge` (`test_events.py:122-147`).

**M3: PARTIALLY CLOSED.**
- What is fixed: child chord (L−t−gap)/2 keeps the footprint L+t (`events.py:323-330`). A test confirms this for angle 0.3, camber and reflex. No split overlaps any more.
- What is not: the "N=1..5 pass at 4h" acceptance holds only when the AABB certifies the gap, which means angle 0. Repro `split.py` uses t at the floor and gap=4h in 2D:
  - angle 0: N=1..5 pass.
  - angle 0.2 or −0.15: N=2..5 all come back `gap_within_sampling_guard` (unmeasured).
- They pass only once the gap reaches g_min plus the guard. Repro `split2.py`: 4.3h in 2D for flat plates, 4.5h in 2D for cambered plates, 4.7h in 3D.
- The test (`test_events.py:249-262`) uses angle 0 only. The report's "N=1..5 がすべて gate に合格" is therefore over-general. See N3.

**M4 / m2: CLOSED.**
- `SceneSamplingLimit` is raised before allocation (`scene.py:251-254`). `evaluate_scene_gates` converts it into `sampling: unmeasured` (`gates.py:479-485`). Round-1 repro c″ no longer raises.
- The R3 cap is recorded with `node_count`/`max_nodes` and reproduces `[281,1137,57]`.
- `src/cfd_gen/README.md` and the report give the 2M, 8M (18,211,329) and O(P·T) re-hash figures.
- `distance_contract_exemptions` lists the merged IDs (`gates.py:455`), and a test covers this.

**m1: CLOSED.** `d < g_min` now fails, and the guard applies only above g_min (`gates.py:399-405`). In round 1's (b) sweep, gap 3.9h now gives `fail` in every phase. The non-sphere BoxBody stays `unmeasured`, because its field is not an upper bound; that is justified and tested.

**m3: CLOSED.** The shared helper `_parameter_floor` (`gates.py:228-251`) computes minimum·√(1+s²) and feeds both the gate record and `thickness_knockout_ids`, which now supports a per-row `parameter_floors`. A cambered element at the floor passes the gate and triggers the knock-out (test). In repro (b2), t·0.999 fails and t·1.001 passes. One residual: the legacy scalar path remains (N4).

**m4: CLOSED.** `elements` is now restricted to Plate/Merged (`gates.py:341`), and so is `knockout_candidates`. The pod no longer needs a joint (repro f: `[]`), and an endplate is never knocked out (repro g).

**m5: CLOSED.** `_number` normalises −0.0 (`primitives.py:31`). `scene_sha256` drops the mesh `path`. The `MergedElement` ID goes through `_validate_id`. Rejections use the separator `|`, which the ID regex excludes. All four have tests.

**m6, n6, n3, n2: CLOSED.**
- The BoxBody docstring now says the field is non-monotone, and a test pins (−0.4, −1.0, 0).
- `_finite` is gone, and the code has one ID regex.
- Early returns carry `scene_sha256` and `state_sha256=None`.
- Signed z offsets come with `allowed_quadrants` (default both).
- The v18 parity claim now says undeformed only.

**m7: CLOSED (coverage note).** Behavioural tests exist for the Birth-0 positive control (2D/3D), 16 limit phases (2D/3D), fixed context, N≥3 and the non-identical merge. However, the limit-phase pair is flat, parallel and AABB-certified, so it never exercises the sampled-gap path (as in N3).

## Regressions (item 9): none found
- `git diff 6536cbf0` over `src/cfd_sdf`, `julia/` and `scripts/` is empty.
- The `primitives.py` changes are confined to `_number`, `_validate_id` and docstrings. No φ code changed.
- The undeformed-exactness and R0-alias tests are unchanged, and no test was removed.
- I re-ran `wp06_band_check.py`: its JSON is byte-identical to the committed one (50 cases, max 5.040873e-5 t, gradient 2.107e-12).

## Report honesty (item 10)
- All 6 `wp06-amendment3-*` artifacts match their compressed and uncompressed SHA in `wp06_validation.json`.
- All current source and test SHAs match; the only mismatches are the historical `previous_amendment_2` entries, as expected.
- Full JUnit: 3754 tests = 3680 passed + 74 skipped, 0 failures, 0 errors; 198 `tests.scene` cases (3482 + 198 = 3680).
- Overstatements: the M3 sentence (N3) and the 16-phase limit test presented as general.

## New findings

**N1 (MINOR, D). The thickness and joint gates still evaluate fixed context.**
- `_thickness_gate(scene.bodies, …)` is at `gates.py:512`. Repro `fixed.py`:
  - a wing plus a fixed STL tyre (3D) gives `component_width_unmeasured|tyre`, so no scene with an STL context can pass unless the policy declares `minimum_widths_m` for it;
  - a fixed EndplatePlate panel 2h thick gives `minimum_thickness_violation|floor`;
  - a distant *fixed* EndplatePlate also gives `joint_declaration_missing|main|floor`, because `endplates` is taken from `scene.bodies` (`gates.py:340`).
- Fix: decide the scope. Either limit thickness and joints to movable components (keeping a separate record of context resolution), or document in the README the `minimum_widths_m` requirement and the fixed-endplate semantics.

**N2 (MINOR, C). The default merge overlap δ=t_min/4 gives phase-dependent merge admission at oblique junctions.**
- Round 1's realistic main+flap has a junction angle of about 0.35 rad. Repro `merge3.py`, 16 phases in 2D:
  - with default δ at t_flap/h=6: 12 pass and 4 fail `closed_void_cavity`;
  - at t/h=8: 12 pass and 4 fail;
  - with δ=t/2: 16/16 pass at both resolutions.
- A fine grid shows no real cavity. The junction crevice is a sub-cell alias.
- The passing test uses `overlap=.04` (0.4 t_min) with a 0.12 rad junction. Its default δ also passes, but at δ=h/2 it fails 7/16.
- The gates fail closed, but under §3.1's shared 16-phase evaluation the same proposal is admitted or rejected depending on phase.
- Fix: require all 16 phases to pass for a merge proposal. Raise the default δ (≥ t_min/2) or add a bridging fillet. Add a 16-phase test with an oblique junction.

**N3 (MINOR, F/C). The split gap default is incompatible with the gap gate at any non-zero angle.** Evidence is under M3 above. Fix one of two ways:
- either default `gap` to g_min plus the gate guard (and the camber extra), or
- document that 4h is admissible only where the AABB certifies.

In both cases, add an angled and cambered N=1..5 test in 2D and 3D, and correct the report sentence.

**N4 (NIT).**
- (a) The scalar fallback in `thickness_knockout_ids` re-enables the m3 inconsistency for cambered IDs. Drop it, or restrict it to flat plates.
- (b) `_nearest_boundary_pair` costs about 1–2 s per pair, and 24–26 s at |C|=6 % c (`fuzz3.py`). A single pair that fails to converge (C/c=7.9 %) raises after 28 s and aborts `merge_candidates` for the whole scene. Skip that pair and record the reason instead.

## Verdict

**INTEGRATE_AFTER_FIXES.**

Every MAJOR item is fixed in substance (fixed context out of the design constraints; a genuine minimal-translation merge with excellent nearest-pair accuracy; no split overlaps; resource limits recorded, not raised). The distance contract, band diagnostic and frozen closure are unchanged, and every artifact hash verifies.

Required before integration:
1. **N3/M3**: an angled and cambered split test, plus a gap default (or a documented rule) that admits non-zero angles; correct the report wording.
2. **N2**: make merge admission phase-robust (a 16-phase requirement or a larger default δ), with an oblique-junction test.
3. **N1**: settle and document the thickness/joint scope for fixed context.

N4 can be done at any time before MW-01.
