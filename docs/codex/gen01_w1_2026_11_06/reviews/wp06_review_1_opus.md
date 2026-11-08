# Opus source review 1 of WP6 phase A (PR #82, 6536cbf0), 2026-11-06

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions taken on it: `docs/gen_system_plan_2026_11_01.md` §3.1 amendment paragraph (2026-11-06 b) and `06_geom_s1.md` Amendment 3.

# WP6 phase A (GEOM-S1) source review — branch feat/gen01-w1-06-geom-s1 @ 6536cbf0, Draft PR #82

Read-only review. Repro scripts are in `scratchpad/wp06/` (`dist.py`, `gates1.py`, `gates2.py`, `misc.py`, `width.py`). They write nothing to the repo, and `git status` stayed clean. `pytest tests/scene` gives 86 passed.

## Findings (most severe first)

### MAJOR

**M1 (D). The envelope, clearance, forbidden-mask and root checks are applied to fixed context as well as to the design.** `gates.py:370` uses `scene.bbox()`, and `Scene.bbox` includes `fixed` (`scene.py:145-150`). The ground and domain clearance (`gates.py:381-385`) and `_masks_gate(finite_phi<0, …)` (`gates.py:437,452`) do the same, so every fixed tyre or chassis must sit inside the rules box, clear the ground, stay out of the forbidden mask and own a root. Repro `gates1.py (a)`: a wing that passes alone (`passed=True`) fails `outside_rules_envelope` and `minimum_clearance_violation:ground_m` once a fixed tyre stand-in that touches z=0 is added. Plan §2 A puts tyres, body and ground into the scene, so every realistic MW-01/RW-01 scene is rejected. Fix: evaluate envelope, clearance, forbidden and roots on `scene.components` only, and keep the movable-vs-fixed pair gap check as it is.

**M2 (C). `merge_candidates` moves the second plate wholesale; it does not merge neighbours.** `events.py:156-157` translates b by the full anchor difference so that its mid-chord sits on a's mid-chord. Repro `gates2.py (e)`: in a realistic main+flap (flap above and behind), the flap moves from x=0.215 to −0.0004. The result is a cross-shaped body at the main-plane position and fails `closed_void_cavity` and `void_opening_defect`. The merge tests pass only because the two plates have identical parameters, so after the move the flap coincides exactly with the main plane (`test_birth.py:76-80`, `test_events.py:51-61`). The Birth-1 "merge" classification is therefore never exercised on a non-degenerate geometry. Fix: use a minimal translation along the nearest-point direction (gap plus a declared overlap δ), or a bridging rule. Add a test in which a non-identical main+flap merge passes the scene gate.

**M3 (C). `element_count_designs` builds overlapping warm starts from N=3 onward.** Each split makes the footprint longer by t+gap (`events.py:212-217`, `offset=(chord+t+gap)/2` with child chord L/2), while the existing neighbour gap is only `gap`. Repro `gates2.py (h)` (t=5h, gap=4h): N=1 and N=2 pass, but N=3 and N=4 fail `component_overlap` and `solid_component_count_mismatch`. With N_max=5, three of the five outer-loop starts are invalid by construction. The test (`test_events.py:80-87`) checks only counts and hashes. Fix: keep the parent footprint with child chord = (L−t−gap)/2 and test that N=1..5 pass the gate at the 4h defaults.

**M4 (D/A). The 3D path cannot admit a scene at MW-01 scale, and this limit is not stated.**
- The R3 crop is capped at 8M refined nodes (`gates.py:32,172-174`), roughly a 50³-node crop. Repro `gates2.py (c)`: a single 1.4 m-span element at h=5 mm gives refined shape [281, 1137, 57] → `R3_refinement_resource_limit`, so `passed` can never be true in 3D.
- `Scene.sample` raises `ValueError` above 2M nodes (`scene.py:218-219`) instead of returning an enumerated `unmeasured` rejection. `evaluate_scene_gates` propagates the exception (repro c″).
- `MeshBody.phi` is O(points × triangles) through a Python-chunked winding loop, and it re-hashes the STL on every call (`primitives.py:382-407`). `boundary_points` loops over triangles in Python. Neither is usable at car-body triangle counts.

All of this fails closed, and TOPO-2D-00 (2D) is unaffected. The report should still record these limits before MW-01, and the sample overflow should become a gate record.

### MINOR

**m1 (D). Definite gap violations are labelled `unmeasured`.** The sampled `d` is an upper bound on the true gap: it is a minimum over boundary samples, and the plate projection only overestimates. So `d < g_min` already proves a violation. The code fails only when `d < g_min − guard` (`gates.py:353-360`). Repro `gates1.py (b)`: a stack whose true gap is below 3.9h is reported `unmeasured`, not `fail`. Admission is still blocked, but INVALID_DEFECT and unmeasured accounting are mislabelled. Make the guard one-sided.

**m2 (A/C). `MergedElement` breaks the band distance contract.** Its `min` union (`scene.py:52-53`) is not a distance inside the overlap. Repro `misc.py`: two flat plates crossing at 20° with t=4h reach a max band error of 0.41 t; about 1 % of band points exceed 2 % t, and the exterior is exact. This contradicts the premise in plan §3.1 that overlaps never reach the band. Merges are the one place where overlaps are allowed, and no gate checks this. The gate should state the exemption or check it, and the plan text should say so.

**m3 (C/D). The thickness floor is inconsistent between knock-out and gate.** `thickness_knockout_ids` compares the parameter t against one scalar floor (`events.py:164-192`). The gate's floor applies to the normal width t/√(1+f′²) (`gates.py:193-205`); I checked that bound numerically, and it is conservative to within 0.5–1.6 %. At C=6 %, R=−4 % the gate's floor corresponds to a parameter t 9 % above t_min. A cambered element held at the gate's floor therefore never triggers the "two checkpoints at the floor" knock-out, and one held at t=t_min fails the gate. Accept a floor per ID, derived from `_normal_width`.

**m4 (D/C). The joint rule is applied too broadly.** `required = elements × endplates` (`gates.py:301-305`) includes boxes: a sidepod `BoxBody` component gets `joint_declaration_missing:pod:ep` (repro f). `knockout_candidates` also proposes removing an endplate component (`events.py:125-127`, repro g). Restrict both to `PlateElement`/`MergedElement`.

**m5 (B). Hash canonicality gaps.**
- `-0.0` and `0.0` give different `scene_sha256` for dataclasses that compare equal (`scene.py:159-165`, repro).
- The STL `path` string is hashed (`primitives.py:416-418`), so host and Kaggle paths change the scene SHA even though the STL SHA is already bound.
- The `MergedElement` id bypasses the ID regex (`scene.py:43-44`, `"merged with space ü"` is accepted).
- Rejection strings use `:` as the separator while IDs may contain `:`, which makes them ambiguous (e.g. `component_overlap:m:split2:0:split3:1:m:split2:1`).

The sampled-state hash is correctly separate (`source_sha256` = scene hash). Duplicate keys, unknown kinds, non-finite values and `schema_version` type are all rejected.

**m6 (A). `BoxBody` interior continuation is not monotone along rays.** It is continuous at the centre (tested), but with radii (2, .8, .4), φ along x runs −0.4 → −1.0 (at s=0.5) → 0, i.e. 2.5× the true depth (`primitives.py:298-307`). This is harmless for gates that use only the sign and for the near-surface band, but the docstring implies a well-behaved field. The sphere case is exact.

**m7 (F). Tests do not cover the stated acceptance criteria.**
- The "R0-alias" tests (`test_scene.py:58-66`, `test_gates.py:159-163`) use t/h = 4–5, wide gaps and 3–4 phases, which is not the 4h/4h limit.
- Birth-0 never runs the valid seed through `evaluate_scene_gates`, so there is no positive control for "obeys policy" (`test_birth.py:23-44`).
- There is no test with fixed context (M1), with N≥3 (M3), or with a non-identical merge (M2).

My own probes show the thickness, gap, R3 and connectivity statuses are invariant over 16 phases at t=4h and at vertical gaps of 3.9–5h (`gates1.py b/b2`). So this is a coverage gap, not a defect.

### NOTE

**n1 (A). The distance contract holds, and the projection is warranted.** Independent dense-oracle probe (`dist.py`): t/c ∈ {0.02, 0.05, 0.1}, h=t/4, |C|=6 %, |R|=4 %, all four sign pairs.
- Band max error: ≤ 1.1e-4 t (limited by the oracle). Over 2h–10h: ≤ 1.7e-8 t. Far field: ≤ 4e-7 m.
- The sign matches v18's raw field exactly. Undeformed plates use the exact stadium formula and match `plate_phi` to 1e-14.
- The raw v18 field (3.9–4.3 % t) and the |∇|-normalised raw field (1.6–3.9 % t) both fail 2 % t, so the multistart projection is not gold-plating.

However, plan §3.1 still describes the field as "一次近似 |∇φ|=√(1+f′²)" and needs updating. WP4/Julia must port 2 sides × 6 starts × 13 Newton steps, and the cost and accuracy under Float32 and AD (GRAD-00) are unmeasured.

**n2 (B/F). v18 parity was shown only for undeformed plates** (`test_scene.py:102-116`). The values of the deformed field intentionally differ from `plate_phi`; only the zero set is shared. The report's "1e-3c 以内を満たす" should say undeformed-only.

**n3 (C). Seed positions are hard-coded below the trailing edge.** `downstream_seed_positions` uses world −z (`events.py:37-56`), as the prompt says. For an inverted downforce wing, flaps and slots are conventionally placed downstream and *above* the trailing edge. This is a spec question; signed offsets would cover both cases.

**n4 (D). R3 is reused by verbatim reimplementation, with an exact-equality test against `scripts/width_rule_study.py::r3`** (3D, two fields). The 2D path is not compared. The radius 0.75h is still tied to the historical 1.5h width, while t_min and g_min default to 4h; R3 acts only as a defect detector.

**n5 (F). The report's numbers are verified.**
- 22/22 artifact SHA256 match, and the gzip SHA (compressed and uncompressed) and sizes match.
- JUnit: 3642 tests, 3568 passed, 74 skipped, 0 failures, 86 `tests.scene` cases (3482 + 86 = 3568).
- The band diagnostic reruns to identical cases and SHAs (max 5.04e-5 t, gradient error 2.1e-12).
- The diff against e3dcdf61 only adds files; no file under `src/cfd_sdf`, `julia/` or `scripts/` is touched (130/13 confirmed).
- There are three import-line edits, not two (scene.py 1, gates.py 2); the report says three, correctly.
- The scene-run time of 20.71 s has no log artifact; the full JUnit covers it.
- No primal claim anywhere. `cfd_evaluations = budget_charged = 0`, the 4h defaults are labelled `development_default_4h_not_RES00_registered`, and neither `r_c` nor FSAE numbers appear.

**n6 (ponytail). Small cleanups.**
- `_finite` is a pure alias of `_number` (`events.py:23-24`).
- There are three different ID validators.
- The empty-scene early return lacks `scene_sha256` and `state_sha256` (`gates.py:415-418`), which makes the report schema inconsistent.

## Checked and holding

- The undeformed plate is exact and has |∇φ|=1. The zero set of deformed plates is v18's.
- `min` union semantics are documented, and the overlap of independent bodies (including containment, and movable vs fixed) is refused.
- `MeshBody` signs by its own winding number with φ<0 meaning solid, does not use trimesh's sign, and its docstring cites #53. It rejects open, inverted and hash-mismatched STLs.
- Phase is applied as a fraction of a cell on a global h-aligned lattice. 2D uses a singleton-y state with an area-only measure, separate from `volume_semantics_v2`.
- Seed and merge candidates are deduplicated by scene hash. The ID-collision regression after a merge is tested. The two-consecutive-checkpoints rule is correct.
- `unmeasured` blocks admission. A forged or tampered state is rejected.

## Verdict

**INTEGRATE_AFTER_FIXES.**

The analytic distance contract is sound, and the evidence record is accurate down to the hashes. Three of the scene-level pieces are wrong in ways the synthetic tests hide.

Required before integration:
1. **M1**: apply envelope, clearance, forbidden and roots to the movable components only.
2. **M2**: replace the wholesale move in `merge_candidates` with a minimal-translation merge, and test it on a non-identical pair that passes the gate.
3. **M3**: make the split keep the parent footprint, and test that N=1..5 pass the gate at the 4h defaults.
4. **m1**: make the gap guard one-sided.
5. **m3**: use a thickness floor per element.
6. **m7**: add positive-control and limit-phase tests.

Fix or record as known limits before MW-01: M4, m2, m4, m5, m6. The plan author should update the §3.1 field description (n1) and settle the seed direction (n3).
