# P22-v2 registration: independent post-run review

Reviewer: independent Claude Sonnet subagent with fresh context (not the pre-run reviewer), orchestrated by the authoring session;
not a human reviewer. Scope: approve or reject only the **recording** of this registration result; no downstream use (LOWDIM-04A
restart, any preregistration) is approved or rejected.

## Review at commit `6bc7ec3`: PASS_WITH_REQUIRED_CHANGES, no blocker

Reproduced with its own code (no use of the registrar or the v2 module): counts 8272 for the baseline and the parent; sharp volume
0.12925000000000003; v1 residuals and smooth volumes; the v2 residuals by hand (-0.311641597769021, -0.3197839831285443, bit-exact);
the eight recorded perturbation volumes divided by h^3 are integers equal to 8272; baseline phi Float32 C-bytes sha256, NPZ hashes, contract
sha256 `caaa38ef…f0a4`; the registration JSON equals its sidecar and a scratch rerun of a copy of the registrar is byte-identical. Integrity:
15 frozen hashes match at the run commit `3b8c486` and frozen files are unchanged at HEAD; `volume_semantics.py` and every v1 file are unchanged
against `e1e8587` (additions only, plus the two disclosed living-doc sections); approval and review hashes match; 48 failure IDs identical to the
SRCMAP-02 record (2211 passed = 2197 + 11 + 3); no environment fields and no physical-volume claim in the JSON; 14 tests pass.

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| F1 | should-fix | `phase_plan.md` said all ten states "exactly at 8272" without saying the eight are recorded, not re-derived | qualified |
| F2 | should-fix | result heading said "all ten evaluated states" | heading now "two re-measured, eight from recorded volumes" |
| F3 | should-fix | `SHA256SUMS` named in the approval but absent | added |
| F4 | should-fix | `logs/run.log` and `compileall.log` excluded by `.gitignore` (`*.log`) and uncommitted, so run-once rests on an untracked file | force-added. The same defect existed in the merged SRCMAP-03a record (`run.log`, `attempt1_run.log`, `compileall.log` listed in its `SHA256SUMS` but untracked); their hashes were verified against that manifest and they were force-added in this branch, disclosed on #54 |
| F5 | note | "independent pre-run PASS" without "subagent" in the result | added |
| F8 | note | certificate does bound the baseline smoothed volume and parent change via its gate-classification bound | stated in the result as a coverage note (the registration JSON is immutable and keeps the conservative wording) |
| F6, F7, F10 | note | the -0.31..-0.32 range is baseline and parent only (hashed text is frozen, the result record says so); precision of the figure; first half of the tampered-blocker test | informational / unchanged |
| F9 | note | the supersession of the proposal's precondition rests on conversational authority that is not verifiable from the repository | surfaced to the user for explicit acknowledgement when accepting the record |

Not checked by the reviewer: run-once on a clean tree (now supported by the committed `logs/run.log`), the quoted user instruction, whether
the full suite ran at exactly HEAD, the eight perturbation states' phi (not retained), that the three-sign-difference replay lies inside the
band beyond the certificate's own controls.
