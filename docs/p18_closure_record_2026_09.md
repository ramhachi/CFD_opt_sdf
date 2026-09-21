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
   measured mismatch machine-readable; (3) extraction `not_measured`;
   (4) candidate/response-specific grid uncertainty registered; (5) a newly
   preregistered report re-judging required pairs — **not performed**; only
   the scope-repair manifest exists.

## Verdict

The original claim "downforce ranking transfers exactly within the reachable
set" is narrowed to **provisional: within the measured minimum-width subset
and the declared bands, while extraction sensitivity is not measured**. P18
remains **scope-bounded monitoring** until extraction sensitivity is measured
and a preregistered re-judged report exists. The WP6-2 observation itself
(8 shapes, zero resolvable inversions at V1/V2) stands as a diagnostic-set
finding.
