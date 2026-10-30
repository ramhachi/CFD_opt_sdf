# Rejected pre-run diagnostic plan 1

The immutable parent-reviewed record is in the parent directory:

- `../plan.json` SHA-256 `23a40e6388a7add8f9a70b88a34fc5c5683f756cff87e897ee4165cc6a674f03`
- `../runner_sources.sha256` SHA-256 `9417075ccfa5e9a02f5dcf1cb4ee6f3e7c776cc7d2b1e286cb5225a44e464559`
- the runner snapshot in this directory has SHA-256
  `f227981e836f61e897ac9da371d5d12bd69d45a55119473d4f1f80bb73d86d24`

No solver step or fixture measurement was run under plan 1. Parent review
rejected it before execution because it used the wrong force conversion
(`1/900 N` instead of `rho*U^2*dx^2 = 0.0025 N` for this profile), compared
native analytic geometry directly against Candidate C without a same-GridSDF
upstream arm, averaged adaptive solver samples without endpoint interpolation,
did not implement its registered fail-closed checks, and described a short
non-W2 sphere as the W2 comparison. Plan 2 supersedes it and corrects those
points while preserving this record and its source snapshot.
