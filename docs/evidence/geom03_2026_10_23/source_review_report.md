# GEOM-03 single formal source review — delivered findings

Evidence class: read-only static source review by the native geometry reviewer,
independent of both source authors. This is the one formal source-review round,
after the one three-angle plan-review round. No registered generator, seed,
CFD/GPU, test or Git mutation was executed by the reviewer. The parent had
reported 18/18 known-development tests passing. Findings below precede freeze
and any registered input execution. Parent corrections and validation are
recorded separately in `source_review.json`.

Reviewed SHA-256 identities:

- Protocol: `d415926c8848f248b9e6d121810fe7483c56a99ba15c7e07259788b82649c67c`
- Runner: `4fac45020188eb8da62fb3d500f34d758f7dd18f6f78f6193b0507171dd78250`
- Checker: `9e23a18c9110e06ab48f26326c54cffe310e6766415a63d704f3857492091fb4`
- Tests: `7130c427c0de7f1b099119a9afdc06138a3a387a686bc9c7e226fd0135fc4415`

Delivered outcome: **NEEDS_FIXES**.

1. **[P2] Child-side waiting consumes the sole attempt before registered input.**
   In the reviewed runner, the controller creates the attempts=1 RUNNING state
   at lines1296–1308; child `preflight()` at line1360 can then return WAITING.
   Line1362 writes terminal INCOMPLETE even though `execute_child()` has not
   generated input. This violates protocol118's waiting/no-attempt contract.
   Handle returned waiting separately from genuine changed/corrupt identities
   and exhausted cumulative budgets. A fresh pre-input refusal remains waiting
   preparation without consuming an attempt; a resumed attempt retains its
   original identity/start while waiting. Add a known-development test driving
   parent READY and child WAITING, proving no terminal scientific record.

2. **[P2] Analytic/translation development oracles are missing.**
   The reviewed tests at lines66 and117 compare the two implementations and
   scaling/halo conventions but lack pointwise analytic expectations for the
   new constructors and a translated-field invariant required by protocol106.
   Shared primitive/frame expressions cannot validate themselves through
   agreement. Add explicit expected distances/signs on nonregistered point/tiny
   arrays and a translated known linear/primitive field. Include a small exact
   digital-ball/boundary reference for the claimed morphology equivalence.
   Do not call registered27³/121³ builders or seed20261023.

No additional blocking issue was found in this bounded static review. The
180/354/534 definitions and K1–K6/H0 tallies, dimensions/frames/masks/parents,
F1/F2/V4/V5 observables, independent corner/refinement/morphology/overlap paths,
strict JSON, premeasurement99+250+28 identity checks, source ancestor/tree/blob
and release pins, workdir/cache/terminal locks, and cumulative wall/RSS
supervision were internally consistent. This is source-contract evidence,
not a GEOM study verdict or an analytic proof of the candidate rule.
