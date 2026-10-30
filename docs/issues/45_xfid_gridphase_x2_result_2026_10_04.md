# #45 X2 result: OpenFOAM grid-phase probe (round 2, host-verified)

Evidence class: `openfoam_stage_v_gridphase_probe_diagnostic_uncertified_geometry`. Measurement only: **not an XFID
response, sign or ranking; no floor is adopted; all six qualification flags remain false.** Registration and design:
`45_xfid_gridphase_x2_2026_10_04.md`. Evidence: `docs/evidence/xfid_gridphase_x2_2026_10_04/round2_result/`.

## Run identity

- Round 1 (kernel v1) stopped fail-closed at ~2 s on host-image drift (Jammy-only OS gate); preserved in
  `round1_terminal_failure/`, not a measurement.
- Round 2: kernel v2, criteria SHA-256 `dea2d558...491f`, runner SHA-256 `6e33b431...` (equals the committed runner),
  source `39e4c3c`. Host: **Ubuntu 24.04.5 (Noble)**, Python 3.13.15, 4 CPUs, 32 GB; OpenFOAM v2512 `2512.0-2`
  installed from the noble lock (hashes verified in-kernel).
- Host-side verification: all 236 files of `artifact_manifest.json` re-hashed, 0 mismatches, 0 missing; DONE reports
  33 of 33 cases COMPLETED; the first case (v16 fixture) ran as a smoke test. Total kernel time 0.73 h.

## Findings

1. **OS does not matter.** The v16 fixture on Noble reproduces the Round 5 (Jammy) result bit-for-bit
   (Cd 1.1695734196575343 in both; 42,619 cells in both; informational reproduction check within tolerance:
   Cd 1.16957 vs 1.16940, downforce coefficient 0.75706 vs 0.75655).
2. **Cost is a non-issue.** The 681,504-triangle surface meshes with snappyHexMesh in about 12 s (peak ~0.4 GB), surfaceFeatureExtract
   ~2.5 s, simpleFoam ~60 s (581-587 iterations, peak ~0.13 GB); about 77 s per case. All cases pass the single allowed
   concave-cell checkMesh exception (2,882-3,001 concave cells, raw `Failed 1 mesh checks` as registered).
3. **The solver is deterministic.** Baseline and baseline repeat agree exactly (difference 0.0 N). Force windows are steady
   (downforce window std at most 3.5e-5 N).
4. **Grid-phase sensitivity is real and not a smooth function of the shift.** Cell count varies 42,374-42,814 and the
   surface-refinement cell counts change with sub-cell shifts (baseline levels 0..3: 2094/3894/18702/17908; y+1 mm:
   2095/3888/18622/18172). Baseline forces: drag 0.374269 N, downforce 0.242241 N.
   - **One-sided differences from the baseline are large.** y-shifts of either sign, from 0.5 mm onward, move drag by +2.2e-3 N
     (+0.6%) and downforce by +1.3e-3 N (+0.5%) and then stay almost flat; this is an even-in-shift jump (the baseline sits on a
     symmetric grid phase), not a physical response. Across all 30 shifted cases the one-sided difference reaches 2.7e-3 N in
     drag (0.72%) and 2.3e-3 N in downforce (0.94%).
   - **Centered secants are much quieter.** S = (R(+s) - R(-s))/2 over all axes and shifts 0.5-8 mm: drag RMS 9.2e-5 N, max 1.8e-4 N
     (0.05% of baseline); downforce RMS 2.9e-4 N, max 4.9e-4 N (0.20%). These are upper bounds for grid-phase noise because
     they include any real response to the translation (x or z shifts are not null perturbations): x drag shows a trend to -1.5e-4 N
     at 8 mm, and z downforce S is -4.9e-4 N at 0.5 mm but not proportional to the shift, which indicates mesh phase.
   - Quadratic fit residual RMS per axis: downforce 3.3e-4 (x), 5.1e-4 (y), 3.6e-4 (z) N; drag 6.8e-5 (x), 7.8e-4 (y), 8.0e-5 (z) N
     (y is dominated by the baseline-phase jump).

## What this means for the plan (proposals, not decisions)

- Use **centered secants** and sign-consistency, never baseline-subtracted one-sided differences, as the OpenFOAM XFID response;
  baseline-phase jumps cancel in S only if the +/- states share a phase, so this must be checked, not assumed.
- Because a case costs about 77 s, **grid-phase ensembles are affordable**: running each state at M small rigid shifts and averaging
  reduces phase noise roughly as 1/sqrt(M) (to be verified, not assumed). 32 phases x 7 states is about 5 h on one kernel.
- Whether D1/D2 (realized displacement median ~0.9 mm) is resolvable cannot be decided from X2 alone: it needs the size of the
  WaterLily-C responses next to the OpenFOAM noise (about 3e-4 N downforce, 1e-4 N drag in S per single state). D0 (about 4.2 mm uniform)
  is more likely to resolve. This is the main input to the X3 registration (epsilon, directions, ensemble size, floors).
- Finer surface refinement would lower grid-phase noise and is affordable, but it changes the Stage V mesh profile and would need
  its own qualification; not proposed without the user.
- Registered floors come only from X3 (calibration disjoint from the formal runs).

## Not claimed

No XFID verdict, no adopted response floor, no certified geometry, no grid independence or physical accuracy claim, no flag change.
