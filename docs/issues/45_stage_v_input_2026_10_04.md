# #45 X1: practical Stage V STL inputs (XFID45-STAGEV-INPUT-01)

Evidence class: `solver_free_practical_stage_v_input_derivation_uncertified_geometry`.
Registered before evaluation (`9ce4c1b`); two post-run amendments, neither touches a gate, rule, input or
coordinate (`preregistration_amendment_01.json` reporting-only; `_02` STL-normal defect fix to the registered rule).
Authority: user decisions D1-D4 of 2026-10-04 (see `docs/phase_plan.md` and `45_next_steps_plan_2026_10_04.md`).
All six qualification flags remain false. No solver, mesh or XFID response was run.

## Result

Derived from the saved Round 3 `r=8` surfaces (read-only), 7 shapes (baseline, D0/D1/D2 at ±epsilon):

- **Practical gate: 7/7 PASS in both storages** (double kept surface and float32 STL read back from the written bytes):
  watertight, winding-consistent, edge- and vertex-link-manifold, no duplicate/degenerate faces, positive signed
  volume, Stage V clearance (min 0.6458 m), every remaining component outward at delta/h = 0.02, 0.05, 0.1.
- **Components removed (rule: bounding-box diagonal < one lattice cell, 25 mm):** 4 in total, all 8-16 faces,
  diagonal 0.65-4.13 mm, signed volume 7.6e-12 to 3.3e-10 m^3 (about 1e-9 of the 0.129 m^3 body), none for
  baseline, D0 and D1-plus. Each case ends with exactly one component (diagonal about 1.5 m, 0.67-0.71 M triangles).
- **Independent recomputation** (sonnet, written from the registered text only; it did not see the build script):
  all gates, component removals, triangle counts, signed volumes and the **sha256 of all 7 STLs agree**. The first
  hash mismatch exposed a script defect (normals from float32-rounded vertices), fixed by AMEND-02 after the
  triangle-coordinate bytes were verified identical.
- Derived STL sha256 (binary, float32; files are reproducible by the script and not committed, 34 MB each):

| case | sha256 | triangles |
|---|---|---:|
| baseline | 1d0f25786aebf771a73e884e3e52f92073ddff82e80ba501104b18e775f7fc2a | 681,504 |
| D0_interface_offset_minus | 79db0b4b9fb699930d302cfee09a7301675841de87160ffd21b2c0807c6b0214 | 699,300 |
| D0_interface_offset_plus | 7e73189ec2daf490ad7cdb361541c910e1a948205774fd4374e99b362f1ea3b9 | 670,764 |
| D1_filtered_seed11_minus | e2c736ce08408e01a15ba30bae89da71638a5254e12a5c02fe8ccd6f31ec5ca4 | 711,266 |
| D1_filtered_seed11_plus | 16ae2cad296f718f7756f5a061ffbc07578efec0e29e844da00879fee4df04f2 | 712,438 |
| D2_filtered_seed2026_minus | af240d1362051e03ac4975399d75cf218e75d79d876c97fb121c4c0d5d60558e | 713,236 |
| D2_filtered_seed2026_plus | 4f30168ff954a9a9dfd0ff9be09787006b9acc02c9cc3c8fdce756f1061ee464 | 713,244 |

Reproduce: `python scripts/build_xfid45_stage_v_input_2026_10_04.py <out dir>` (about 9 minutes);
output `docs/evidence/xfid45_stage_v_input_2026_10_04/result.json`.

## Reported, not gated (descriptive)

- Own-field first-order distance `|phi|/|grad phi|` at kept vertices: median ~1e-8 m for every case; max
  4.5e-4 to 1.35e-3 m for D1/D2 (fraction above 0.5 mm: at most 8e-6); baseline has 2 vertices with zero
  cell-local gradient (distance undefined; excluded and counted). This is a first-order estimate, not a bound.
- **Realized displacement of each perturbed surface from the baseline field, in units of the nominal epsilon
  (5 mm):** D0 median 0.833 (p95 1.39), i.e. about 4.2 mm, not 5 mm; D1/D2 median 0.18 (about 0.9 mm), p95
  0.63-0.65 (about 3.2 mm). The D0 value matches the 4.1667 mm target root seen in CERT-01 sample 691.
  Consequence: D1/D2 perturbations are well below one Stage V surface cell (25-50 mm) over most of the surface;
  this raises the mesh-noise question for X2, and "epsilon" must be read as nominal, not realized displacement.

## Not claimed

No certified 0.5 mm geometry, no physical accuracy, no XFID response/sign/ranking, no qualification flag change.
Certified geometry, CERT-02 and all-component orientation remain deferred to #29 GEOM-01. An XFID verdict built on
these inputs is scoped to uncertified geometry with the error statistics above.
