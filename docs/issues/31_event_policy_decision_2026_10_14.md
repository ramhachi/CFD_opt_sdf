# #31: research topology event policy decision, 2026-10-14

Evidence class: decision record plus a registered contract (`sdf_topology_policy_v2_research`); no solver was run. This records the research successor policy begun by the partial decision of 2026-10-02
([record](31_research_policy_decisions_2026_10_02.md)); the historical `sdf_topology_policy_v1` (registration SHA-256 `1c5953c3…1f2f`, immutable) and every v16/v17 state binding are unchanged.

## Decision

**Permit birth, split, merge and whole-component deletion in the research policy** (the recommended research default of the earlier record), together with the user's earlier partial choice (detached components allowed, root connectivity optional). The permission is **policy-level only**:

- it executes nothing; a detected birth is rejected unless the caller passes `birth_qualified=True` (default False; `topology_birth_qualified` stays false);
- `allowed_events` is a required keyword with no default; a step that must keep the solid-component topology (OPT-01 #30 is "topology-fixed") passes `()`, which rejects any detected solid-component event, and the argument can only narrow the policy;
- the check judges solid components only: a change of genus or of void topology (an interior cavity, a through-tunnel) is **not** detected here, and v1's void-connectivity and eroded-connectivity flags are not carried over (the geometry gates of #29 own them), so "topology-fixed" here means no solid-component birth/split/merge/deletion;
- explicit design, fixed-solid, forbidden and root masks remain hard constraints (material only where design, fixed or root; fixed and root material retained; nothing in the forbidden mask); an empty solid is inadmissible.

## Authority and its limits

The earlier record said the event choices were "awaiting explicit user" selection and that no option had been picked by inference. This record **reads** the user's blanket words of 2026-10-13 (「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」) as delegating that choice; it is an interpretation, not a #31-specific grant,
and an explicit later user decision supersedes it. The chosen option is the one that record already recommended; the narrower alternatives remain expressible (`permitted_events` is a field of the policy, and a different value is a different content-addressed policy). Reviewers are Claude subagents, not humans.

## What stays unresolved (and why nothing can pass yet)

Physical minimum solid width, minimum void width, the minimum gap between detached components and the source ProblemSpec binding are **not specified by the user and are not inferred** from the grid spacing or the observed shape. In the registered policy they are `None`; an unresolved width makes every transition inadmissible
(`unresolved_inputs`: `minimum_solid_width_m`, `minimum_void_width_m`, `minimum_gap_m`; the gap is listed because detached components are allowed). A resolved limit must be a finite positive number, and a policy instance with resolved limits is a **new content-addressed policy that needs its own registration**. No admissibility PASS exists until real limits are supplied, which is a requirement of the geometry hard gates (#29), not of this policy. `geometry_gates.py` is still typed to the v1 policy; moving it to v2 is #29 work. A required support connection would need a separately registered physical specification.

## Effects

| Choice | Effect |
| --- | --- |
| Selected: all four events permitted by policy | broad research freedom subject to masks and feature gates; execution waits for qualification; topology-fixed steps narrow to no events |
| Alternative: split and merge only | expressible as another policy value (new content hash) |
| Not chosen: defer | would leave the successor incomplete |

Registration: `docs/evidence/sdf_topology_policy_v2_research_2026_10_14.json` (+ `.sha256`). Implementation: `src/cfd_sdf/design/topology_policy_research.py`; tests: `tests/test_sdf_topology_policy_research.py`. All six qualification flags remain false; `shape_update_allowed=false`.
