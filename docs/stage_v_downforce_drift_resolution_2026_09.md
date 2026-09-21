# Stage V downforce drift — scheme factor result (2026-09-21)

Status: DF2/DF5 blocker resolution record. The failing finest-transition drift
was screened against the convection-scheme factor. The drag drift is resolved;
the downforce drift is **not** scheme-dominated and remains non-monotone, so
the registered stop rule applies: no GCI, escalate to the next factor.

## Campaigns

- `docs/evidence/stage_v_scheme_factor_manifest_2026_09.json` +
  `docs/evidence/stage_v_scheme_factor_2026_09.json` — V1→V2 screen
  (closed: that transition was already inside the bound, baseline 0.00461).
- `docs/evidence/stage_v_scheme_factor_v23_manifest_2026_09.json` +
  `docs/evidence/stage_v_scheme_factor_v23_2026_09.json` — the registered
  V2→V3 finest-transition screen (this record).
- Runner: `scripts/run_stage_v_scheme_factor_2026_09.py`,
  `scripts/run_stage_v_scheme_factor_v23_2026_09.py`.
- Control: the upwind V1 case re-run in the campaign root reproduced the
  recorded baseline exactly (Cd 1.7395051369863013, downforce
  0.5138805915205479, 292 iterations), proving the copy-and-patch path.

## Measured finest transition (V2 → V3)

| arm | Cd V2 → V3 | drag relative drift | downforce V2 → V3 | downforce absolute drift |
| --- | --- | --- | --- | --- |
| baseline `bounded Gauss upwind` | 1.68009 → 1.62968 | 3.00% (fails 2%) | 0.50927 → 0.52217 | 0.012907 (fails 0.005) |
| treatment `bounded Gauss linearUpwind grad(U)` | 1.54480 → 1.55043 | **0.364% (passes)** | 0.50103 → 0.51141 | **0.010374 (fails)** |

All four qualification gates pass in both arms; V3 treatment converged in 2289
iterations.

## Findings

1. **Drag**: the first-order scheme was the dominant factor. The second-order
   scheme brings the finest drag drift to 0.36%, inside the registered 2%
   bound. The drag reference family is qualified with `linearUpwind`.
2. **Downforce**: the scheme is not the dominant factor. The drift improves
   only from 0.01291 to 0.01037 and remains above the 0.005 bound.
3. **Non-monotonicity**: downforce goes down then up in both arms
   (baseline 0.5139 → 0.5093 → 0.5222; treatment 0.5026 → 0.5010 → 0.5114),
   so the family is not in an asymptotic range and no GCI is reported.

## Consequences

- DF5 ranking may proceed on drag with the qualified `linearUpwind` family.
- For downforce, the honest state is a **measured candidate-specific band**
  (≈0.0104 for this candidate at the V2→V3 transition) with no
  grid-independent claim; required-pair improvements must exceed that band.
- The next registered factor is **domain and boundary**: the far-field box is
  currently the declared fixed domain; the registered manifest
  `docs/evidence/stage_v_domain_boundary_factor_manifest_2026_09.json`
  describes the factor matrix (domain extension and far-field boundary
  treatment) but is not run in this campaign.
