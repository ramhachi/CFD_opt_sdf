# WP5 Cp reference tooling design

This design precedes implementation. Authority: the W1 `00_README.md`,
`AGENTS.md`, the current entries in the handoff / documentation map / issue
ledger / roadmap (parent review), GEN-01 rev 3.1, TOPO-2D-00 registration draft
§§2–4, research F §1 and EVAL-VALID-01's primary-reference audit. Historical
handoff, issue and resolution records remain historical evidence; this tool
does not change their outcomes. The completed T2-0 studies remain NO-GO.

## Purpose and evidence boundary

Accept user-supplied digitizations, compute a pressure-only centre-section
downforce reference and record its digitization sensitivity. No figure is
digitized here, and no TR-00 qualification is decided. Pressure-integrated
sectional Cl is distinct from finite-wing balance CL. Table 15's total
pressure-integration uncertainty remains unknown; the balance ±0.003 band and
the historical figure-reading ±0.005 cannot supply it. The two-digitization
spread is a sensitivity estimate, not a confidence interval or total error.

## Scientific interface

- Require explicit global streamwise abscissae `x/c` and physical upper / lower
  surfaces (upper means larger global z, regardless of suction/pressure side).
  With global +z upward and downforce = −Fz, calculate
  `Cl_down = [∫Cp_upper dX − ∫Cp_lower dX] / c1`. This is the vertical pressure
  line integral. Local-chord x at an incidence is insufficient without the
  surface geometry; reject that convention instead of inventing a pressure
  drag correction or silently projecting a normal force.
- Require declared global projected x extents and complete coverage on both
  surfaces. Upper and lower endpoints must coincide in x; connecting end caps
  are then vertical and contribute no vertical pressure force. Missing peaks,
  unmatched endpoints, duplicate/nonfinite x and extrapolation fail closed.
  Interior point spacing may differ between the two surfaces.
- Every config is normalized to the common main chord c1 = 0.2234 m, including
  E2. A publication's x/c or Cl normalized by c = 0.380 m is converted by its
  declared dimensional chord. Comparing separately normalized E1 and E2 Cl
  would not compare forces. Record all dimensional normalizations.
- Each Cp element has two independent digitizations with operator / tool /
  independence provenance. Estimate each element by the mean of the two
  trapezoidal results; use their absolute difference as a conservative
  digitization sensitivity. Sum element sensitivities (no cancellation), then
  retain E1 plus E2 sensitivity descriptively for an increment. Amendment 1
  uses E2's sensitivity alone for the registered 5% comparison. Preserve the
  absolute paired-total difference as a separate diagnostic.
- Accept Table 15 as an explicitly supplied scalar with source, source chord,
  reading sensitivity and its stated basis. It is never represented as a new
  Cp integral. The existing audit verifies 1.009 at h/c1 = 0.448; source
  rounding of height and unknown trip / total uncertainty remain visible.
- Accept two independently digitized Cl(h/c) CSV curves as an alternative;
  interpolate linearly at declared physical h, reject extrapolation, and retain
  the same sensitivity/provenance distinction.
- Report the fixed 5% digitization-sensitivity comparison descriptively for an
  explicitly requested increment. Do not alter [0.5, 2], issue a qualification
  label or manufacture a reference when the user's CSV files are absent.

## Files and implementation

`scripts/topo2d00/digitize_cp.py` exposes CSV parsing, trapezoidal integration
and `build_reference(manifest_path)` plus a local CLI. Use the standard library
(`csv`, `json`, `math`, `hashlib`, `pathlib`, `bisect`); no new dependency or
frozen source changes. Record manifest and CSV SHA-256 hashes in output JSON.
`docs/codex/gen01_w1_2026_11_06/reports/cp_digitised_format.md` describes the
versioned manifest, examples, exact CSV headers, signs and limitations.

## Test plan

Write deterministic tests before implementation. Cover known positive
downforce and nonuniform-grid trapezoids, common-chord rescaling, physical
surface labels, element summation without uncertainty cancellation, two-reader
spread, table provenance, Cl(h) interpolation, input hashes, and fail-closed
unknown conventions / incomplete coverage / malformed CSV / missing files /
nonfinite data / extrapolation. Parent runs the final baseline comparison and
repository-wide checks. This worker runs the targeted Cp tests and self-review.

## Unverified assumptions

The user must identify the plotted x direction and normalization, physical
upper/lower surfaces, complete projected coverage, free-transition series and
matching height / incidence. A metadata assertion records provenance; it does
not independently establish a figure's geometry or experimental conditions.
Real E2 Cp CSVs are not supplied, so no measured E2 Cl, reference increment or
TR-00 eligibility is produced by this implementation.

## Amendment 1 design (2026-11-06; before implementation)

The external registration Amendment 1 §6 and the Opus source review C1/C2
supersede the permissive initial input checks. Each physical Cp surface must
have at least 10 points. For each element, corresponding upper and lower CSVs
from the two readers must have different SHA-256 content hashes, even if their
paths differ. Each individual reader's element integral must be strictly
downforce-positive before averaging; negative and zero integrals are refused
with a surface-label diagnostic. The signed low-level integral remains useful
for mathematical checks; the wing-specific positive-downforce guard belongs to
the reference builder. Two Cl(h/c) CSVs must also be SHA-distinct, but they are
curves rather than physical surfaces and retain the two-point interpolation
minimum. Table 15 remains a scalar transcription with its separate provenance.

The registered E2 digitising uncertainty remains the sum over elements of the
absolute difference between reader integrals, with no cancellation. The 5%
comparison uses the target E2 uncertainty. The earlier increment field added
E1's reading sensitivity to that threshold; this amendment instead reports
the source sensitivity and the summed difference-reading sensitivity in
separate fields. Neither is promoted into total reference uncertainty.

Add explicit `observable: pressure_cl` to the output and to each reference,
while retaining the existing precise normalization provenance. Report
`h_over_c1 = height_m / 0.2234` and `h_over_c = height_m / 0.380`; preserve the
publication's rounded height ratio separately in source metadata. No actual
CSV, source figure, reference value, freeze, or registered threshold changes.

Only the existing Cp source, tests, format guide, and this design memo change.
Tests first cover copied contents under distinct names, copies on either
surface, a nonpositive individual element hidden by positive other readings,
the 9/10-point boundary, identical Cl(h/c) files, known integrals, unchanged
per-element uncertainty, and the E2-only 5% comparison with E1 reported apart.
