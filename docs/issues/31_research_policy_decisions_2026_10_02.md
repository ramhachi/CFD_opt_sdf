# #31: research topology policy decisions, 2026-10-02

Evidence class: user decision record. This is a partial decision, not a
canonical policy registration, executable transition permission, or topology
qualification.

The user selected: **「研究段階は分離成分を許可し、root 接続は任意」**.
The research successor policy must therefore allow detached solid components
and must not require every component to intersect a root mask. Existing fixed
solid, forbidden-region, design-domain, and explicitly supplied root-mask
constraints still apply. A required support connection would need a separately
registered physical specification; it cannot be inferred from an empty mask.

The historical v1 policy and its evidence remain immutable. Its required-root
semantics conflict with this newly selected research policy. Implementing the
choice requires a new policy identity and explicit state binding; historical
v16/v17 states are not retrospectively rebound. The historical registration
file SHA-256 is
`1c5953c3733b77d99958e89aa153911cc36ffbea87dfd8b3bb7b27bde44c1f2f`.

The separate event-policy question remains unanswered:

| Choice | Effect | Recommendation |
| --- | --- | --- |
| Permit birth, split, merge, and whole-component deletion in the research contract | Allows broad topology exploration, subject to masks and feature gates; execution still waits for qualification | Recommended research default, awaiting explicit user selection |
| Permit split and merge only; prohibit birth and whole-component deletion | Narrows transitions to existing material components | Alternative |
| Defer event choices | Leaves the successor policy incomplete and transition checks unresolved | Available |

No option above has been selected by inference or by a preselected UI answer.
Physical minimum solid/void widths, any minimum gap, measurement provenance,
and source ProblemSpec binding also remain unresolved where not already
specified. No length is inferred from grid spacing or the observed shape.

The next implementation can retain 26-neighbour component detection and the
existing immutable-state/mask checks. It must distinguish optional connectivity
from required connectivity and fail closed on undecided event permissions or
missing feature measurements. A partial decision cannot produce an
admissibility PASS.

`shape_update_allowed`, FD oracle, field gradient, reverse, optimizer, and
topology qualification flags remain false. No solver was run for this record.
