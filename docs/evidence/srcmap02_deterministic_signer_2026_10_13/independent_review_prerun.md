# SRCMAP-02 independent pre-run review

**Verdict: PASS.**

Exact freeze SHA256: `58fe2853fe2b913b82555bd4a5cbcefd2b6fcf93740e88c3c644e9c893d0d707`.

Native Codex independent read-only subagent /root/srcmap02_review; inherited model, exact model ID not exposed.

Reviewed UTC: 2026-10-13T02:40:34.905573+00:00.

No target distance/sign queries were executed by the reviewer. The campaign execution marker was absent during review. All161 frozen file hashes,32 unique planned jobs, the two identical loaded-mesh inventories, and13 actual libigl artifact hashes per inventory were independently checked.

## Findings

No blocking findings remain. This review approves the frozen design for the once-only campaign; it makes no pre-measurement qualification claim.

## Reviewed predicates

- A is preregistered preferred pseudonormal; B is winding control, with no post-result selection.
- Official libigl exact2.6.3 wheel identity, imported module and binaries are frozen and shared by the two runtime bundles.
- Explicit closest_point unsigned query is separate from libigl scalar sign; randomized signed distance and abs thereof are not used.
- No tolerance relaxation, old-field hash objective, clipping, adaptive node queries or measurement rerun is present.
- Formal fixture stage runs before target queries and failure stops the campaign; smooth-sphere versus convex-polyhedron feature truths are explicitly distinguished.
- Unsigned negative zero rejected; +0 unsigned produces +0 combined; signer zero at unsigned>0 fails closed; Float32 cast zero normalized and underflow counted.
- Five independent process repeats per candidate and full3x3 chunk/order products restore canonical order and use exact unsignedF64/sign/combinedF64/F32/state identity.
- Cross-environment gate requires exact Float64 unsigned and combined field bytes as well as Float32/sign/state; Float32-only agreement cannot rescue the gate.
- A/B nonzero and exact-zero disagreements are evaluated on v16 and v17 and wired into terminal classification.
- Classifer precedence preserves integrity/analytic/zero/runtime blockers, candidate instabilities, disagreement, cross-environment exactness and only then qualification.
- Known nodes are frozen saved-evidence union; closest features derive from already saved outputs with no additional geometry query.
- Current evaluators compute hard and descriptive smooth volumes; no reference migration or hard-feasibility substitution.
- Exclusive execution marker/output writes and runtime/source/mesh/array checks preserve fail-closed partial evidence.
- Self-intersection absence and unconditional global orientation are not independently certified; method corroboration and finite environment claims are bounded.

## Preliminary issues resolved before freeze

- Sphere mesh approximation shell distinguished from smooth-sphere observations; shared .9 and1.1 radial points added before freeze.
- Float32 zero normalization implemented before freeze.
- v16 whole-field A/B comparison and classifier wiring implemented before freeze.
- Unexpected metadata preflight exceptions receive INCONCLUSIVE classification before target execution.
- Existing volume contract identifier references corrected before freeze.

## Scope and remaining completion checks

- This PASS approves the frozen design for execution; it does not assert any candidate qualified or field deterministic before observing results.
- Full final pytest baseline comparison remains a completion gate for root; reviewer did not duplicate it.
- Runtime wheel/build identity is frozen; release-source provenance is not a reproducible binary build attestation.
- Topology evidence does not certify non-self-intersection or physical aerodynamic qualification.

Primary method reference: https://libigl.github.io/tutorial/#signed-distance. The frozen release-source excerpts and installed module identities provide version-specific context.
