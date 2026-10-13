# P22-v2 registration: independent pre-run review

Reviewer: independent Claude Sonnet subagent, adversarial brief, read-only on the frozen state (scratch rehearsals of the
registrar with its output redirected were allowed and the default output was never written). Not a human reviewer.
Orchestrated by the authoring session. Scope: the frozen plan, module, registrar and tests of #55.

| Round | Commit | Freeze | Verdict |
| --- | --- | --- | --- |
| 1 | `1912082` | `6b4934c0…` | PASS_WITH_REQUIRED_CHANGES, no blocker |
| 2 | `6f868d3` | `62d260ce…` | PASS_WITH_REQUIRED_CHANGES, no blocker |
| 3 | `5210476` | `459c2864f0f31a219ae561e85d97dad924d8c7b5f317e7781cbefcdb10fd20af` | PASS |

Round 1 required changes (all applied): the authority paragraph over-stated the SRCMAP-03a post-run review (it approved only
recording, reviewers are subagents); static record statements ("expected 8272 for all ten states", zero slack) were not backed by
stop rules (now required by the registrar); the LOWDIM-04A blocker hash was compared only with its own sidecar (now pinned to the
literal); the v1 caveat on sub-voxel sensitivity was dropped (restored, with the recorded +-2.8% D0 illustration); the supersession was
narrower than it read (disposition table of the proposal's items). Round 1 notes also taken: certificate wording qualified, `report_v2`
carrying the scope, the inactive smooth constraint at N_max, STL volume wording, `hard_constraint` key, environment fields removed from the
payload, sidecar checks, validation order, sdf_state.py in the freeze, stronger tests. Round 2 required change (applied): the registration
JSON still described a single-precondition supersession and its validity text lacked "hard count only"; notes taken: partial-write recovery
disclosed as manual and fail-closed, constraint figure range, `report_v2` placement, two extra negative-control tests.

Round 3 (PASS): the diff `6f868d3..5210476` contains only those changes; all 15 frozen hashes match disk; the module tests and the v1
volume tests pass (42); a scratch rehearsal gave all ten states at 8272, v1 residuals equal to the recorded `-0.2945861368614151` and
`-0.3029302661594796`, smooth contract `caaa38ef…`; `volume_semantics.py` is unchanged against `e1e8587`. Remaining notes, none blocking:
the payload range "about -0.31 to -0.32 on the retained states" holds for the baseline and the parent only (the recorded D0 perturbations
span about -0.30 to -0.34), so any restatement in the post-run record says "baseline and parent"; the first half of the tampered-blocker test
does not assert that nothing was written (the second half does). Not checked by the reviewer: the full suite, the post-run artifact test and the
living-docs update.
