# P22-v2 / v17 volume-reference migration proposal

Status: proposal only, not a registered contract. Prepared 2026-10-12 from the
audit plan frozen on 2026-10-11; requires a separate explicit user decision before any
registration or implementation. Existing P22 v1 and its limit remain unchanged.

This is a contingent design proposal: source-mapping reproducibility must be
resolved before it is eligible for a registration decision. The terminal audit
is INCONCLUSIVE. Retained-state arithmetic suggests migrating the **reference
representation**, because the
canonical v17 baseline already exceeds v1's v16-derived absolute limit before
LOWDIM-03. The candidate reference must be the original pre-optimization
physical source geometry, never the selected optimized parent.

## Content to consider only after reproducibility is resolved and separately approved

Use the original source STL SHA-256
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`.
Its v16 and v17 representations in this audit are hash-pinned. Oct11 exact replay is historical; Oct12 v17 source replay failed
with nonzero near-surface differences. The intended mapping uses existing `sdf_native_genesis_v17_2026_09.resample`, which calls
`cfd_sdf.sdf.signed_distance`, casts to Float32, and samples specified lattice
nodes. Freeze the source files, runtime/dependency versions, source surface,
mask-projection lineage and immutable mapped reference artifact before any
future optimizer data is used.

The proposed v17 lattice is origin `(-1.0,-0.8,-0.6) m`, h=`0.025 m`, node
shape `(121,65,49)`, cell shape `(120,64,48)`. It retains the original design
bounds. Freeze sign convention, dtype, exact-zero fluid handling, ordered
Float32 eight-corner averaging, all-cell sampling, and hard formula
`count(center_phi < 0)*h³`. The retained lineage identifies the pre-optimization
v17 reference as state SHA
`02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb`.

Define the new limit only by:

```
V_limit_v17 := P22_hard_volume(original_reference_geometry mapped to v17 lattice)
```

The existing audit observes 8272 solid centers and `0.12925000000000003 m³`
for that candidate reference. This number is **not registered here**. It is
derived from B, which predates LOWDIM-03. That C currently has the same number
does not make C the reference or qualify it for acceptance.

Retain the one-sided cosine smooth rule and epsilon=h if approved, but version
its denominator/reference binding consistently with the new hard reference.
Freeze gradient mask ownership and units. A separate new contract ID and
canonical payload SHA must bind physical reference identity, v16/v17 mapping,
lattice/origin/h/count, hard arithmetic, smooth rule and acceptance rule.
No final contract hash is generated in this proposal. Grid and state hashes
remain separate from that future static contract hash.

## Required acceptance checks before any later experimental restart

1. Resolve the recorded source-mapping discrepancy without post-hoc tolerance
   relaxation. Independently replay each reference lattice, verify
   all hashes, and check the v16 original contract still reproduces exactly.
2. Register the new reference/contract under a separate version only after user
   approval; retain all v1 registrations and #51's historical blocker.
3. Re-evaluate the fixed parent and any authorized perturbations under that
   new contract, including the independent hard gate. Smooth gV alone never
   grants feasibility or permission for a shape update.
4. Obtain separately authorized LOWDIM-04A preregistration before any CFD or
   coefficient solve. Existing aerodynamic results are not retroactively
   volume-qualified by this reference migration.

If the user's intended constraint is instead a physical continuum volume cap
independent of design lattice, a separate physical-volume specification and
accuracy/uncertainty study is needed. This two-lattice audit cannot provide
that convergence claim, and does not silently convert v1 into such a contract.
