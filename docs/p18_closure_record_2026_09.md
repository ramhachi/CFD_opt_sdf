# P18 closure record — DF0 evidence audit (2026-09-21)

Status: DF0 deliverable, subordinate to
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
section DF0 and to the P18 entry in
[`problem_register_2026_09.md`](problem_register_2026_09.md).

The P18 ledger entry (registration, symptoms, closure conditions) lives in
`problem_register_2026_09.md`. That file carries separate in-progress edits, so
this record is the DF0 closure artifact instead of an edit to the ledger; the
ledger's P18 status line should point here when its pending edits are
committed.

## Artifacts

- `docs/evidence/wp6_2_evidence_audit_2026_09.json` — fail-closed audit
  artifact (`ok=false`; blocking findings listed below).
- `docs/evidence/wp6_2_scope_repair_manifest_2026_09.json` — narrowed claim
  registration (`claim_status=provisional`).
- `work/evidence_audit/wp6_2_feature_sizes.json` — candidate dimension table
  (regenerable; `work/` is not tracked).
- `docs/optimizer_shape_preregistration_v1.md` — preregistration schema for
  future optimizer-generated shapes.
- Commands:
  - `.venv/bin/cfd-sdf audit-wp6-reports <manifest> <evidence> --output ... --repair-manifest ...`
    (exit 1 while blocking findings exist)
  - `.venv/bin/cfd-sdf measure-shape-feature-sizes --output ... --registry-dir ...`

## Measured facts (all recomputed from historical artifacts; no historical JSON rewritten)

1. **Declared-width conflict**: manifest `purpose` says `>= 0.15 m`,
   `definition.reachable_set` says `>= 0.10 m` (blocking finding
   `declared_min_width_conflict`).
2. **Feature sizes** (18 shapes, 4x supersampled distance transform): under
   the 0.15 m policy the below-policy shapes are `plate_a20_t05`,
   `plate_a20_t10`, `wing_endplate_a20`, `wing_gurney_a20`,
   `wing_two_element`; under 0.10 m they are `plate_a20_t05`,
   `wing_gurney_a20`. `box_bluff03` and `wing_endplate_a20` show
   +1-voxel rasterization over-read, recorded with classification rather than
   silently rounded.
3. **Extraction sensitivity**: empty in all 8 reports (reachable 8 + 17-pool)
   and therefore recorded `not_measured`; the reachable-set downforce `pass`
   is downgraded to provisional (`pass_requires_measured_extraction`).
4. **Candidate-specific V1->V2 drift**: exceeds the inherited band for five
   downforce candidates (max 0.03760, `wing_camber_bent`) and one drag
   candidate (5.77%, `wing_flat_ctrl_c30`). The common band may not be reused
   unconditionally.
5. **Closure conditions**: (1) union/part measurement done; (2) declared vs
   measured mismatch machine-readable; (3) extraction `not_measured` in the
   historical reports; (4) candidate/response-specific grid uncertainty
   registered; (5) preregistered re-judgment — **completed 2026-09-21**:
   `docs/evidence/wp6_2_rejudgment_manifest_2026_09.json` (registered before
   computation) and `docs/evidence/wp6_2_rejudgment_2026_09.json`.

## Re-judgment result (condition 5)

`scripts/rejudge_wp6_2_ranking_2026_09.py` re-judged the unchanged historical
measurements with candidate-specific bands
(`max(inherited, measured |V2 - V1|)`) and the Gate-4 rule, declaring the
extraction term **not applicable by construction** (analytic anchor shapes,
same-grid, no density-to-surface extraction in the loop — an applicability
declaration, not a zero measurement):

| set | response | V1 | V2 | signed pairs | inversions |
| --- | --- | --- | --- | --- | --- |
| reachable set (8) | downforce | pass | pass | 25 | 0 |
| reachable set (8) | drag | unresolved | unresolved | 22 / 23 | 0 |
| combined pool (17) | downforce | unresolved | unresolved | 121 | 0 |
| combined pool (17) | drag | unresolved | unresolved | 104 / 108 | 0 |

Aggregate verdict: `unresolved` for both responses (the 17-shape pool is
unresolved), with zero resolvable inversions everywhere.

## Verdict

The original claim "downforce ranking transfers exactly within the reachable
set" survives candidate-specific bands **for the 8-shape reachable set only**,
and only within the declared minimum-width subset and the not-applicable
extraction scope. The combined 17-shape pool remains `unresolved`. P18 is
**closed as a fixed-shape diagnostic finding**: no optimizer-generated-shape
capability, no absolute calibration, no grid-independent claim. Any future
production claim must come from DF2/DF3/DF5 evidence, not from this record.
