# LOWDIM-04A Stage A independent pre-freeze review

Reviewer: one independent Claude Sonnet subagent (adversarial brief, read-only, no freeze or Kaggle access), resumed for the delta check; not a human reviewer. Final freeze `c0532d145f2b6a8813a3ca0372b8bc4148c01944ee0920622cedc8331aa53b43`.

| Round | Commit | Verdict |
| --- | --- | --- |
| 1 | `14087b2` | PASS_WITH_REQUIRED_CHANGES, no blocker |
| 2 (delta) | `67dddba` | PASS_WITH_REQUIRED_CHANGES, no blocker; all seven round-1 findings confirmed fixed; one new should-fix and one note |

Round 1 verified by experiment: the analytic cone case (predicted gain `a*1.25e-3` N, robust lower bound `(a-0.012)*1.25e-3`, 300 random linear worlds with 0 mismatches in the predicted response and the
max-norm 1.25 mm), 600 fuzzed degenerate cases with no solver failure, the runner derivation (only renames, the direction-keyed perturbation and the removed proposal), the parent gate preceding any perturbation, the
import closure (41 files), the inventory arithmetic and lemma, and that the real retained LOWDIM-03 summaries equal the 04A parent row. Required changes (all applied): a strict registration validation (required file set, fixed
budgets, re-rendered workers, metadata, pins, exact flag set, identity proof and parent commit), a registered rule for analyzer defects after the run (none: INCOMPLETE), an implemented and tested SHA256SUMS tracking gate, a test that
really isolates main-pass/robust-fail, and note corrections (parent hash, 2.407/3.228 mm, the replay description, the removed vacuous runtime-count sentence, authority wording, flow_32 drag wording, the near-certain FOUND disclosure),
the solver-exception path, and the spatial cosine next to the coefficient cosine.

Round 2 new findings, fixed after the delta review **without a third review round** (small corrections, each with tests; 26 tests pass): the manifest gate did not understand the older `./name` entries (it now resolves them against the
manifest directory, rejects absolute and `..` paths and uses literal pathspecs; a test covers it, and it reports the known 19 untracked logs of the LOWDIM-03 failed-attempt manifest); the identity proof and the parent commit were only
weakly checked (now compared with the committed `identity_free_check.json` and the `PARENT_INTEGRATION_COMMIT` constant, with mutation tests). Not checked by the reviewer: real Kaggle behaviour (byte-identity of the parent rerun on a T4, the sparse
fetch, instantiate), `--check` on another machine, the full suite.
