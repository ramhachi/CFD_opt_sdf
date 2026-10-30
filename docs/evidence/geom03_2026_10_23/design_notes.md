# GEOM-03 design integration, 2026-10-23

Evidence class: source inspection and prospective design, not a study result. No registered fixture array, registered seed or held-out R3 outcome was generated. Known tiny development fixtures are permitted separately for implementation tests. The scientific candidate and old FID contract are unchanged.

Three OpenCode Go contributions were requested before implementation: exact-design author (MiMo-V2.6-Pro), measurement-semantics contributor (DeepSeek V4.1 Flash), and execution-plan author (MiMo-V2.6-Flash). Initial read permissions were misconfigured in the local wrapper; the parent fixed only that temporary configuration and resumed the same models. Source and execution-plan contributions completed. The exact-design author exhausted its reasoning/output limit without a delivered document. It is not a passed review or a completed design. The parent integrated the completed contributions with the existing source into the dated protocol.

## Source constraints adopted by the parent

1. R0 and R3 use different representations/crops. Both measure the complement within their respective finite crop; R0's void-None label does not implement an exterior-removal algorithm. Preserve the exact helpers rather than inferring new topology from that label.
2. P1 uses the complement of the actual active mask (`design & ~fixed & ~forbidden & ~root`), not merely `~design`. Empty frozen masks never pass by an inferred infinite minimum.
3. The existing topology classifier uses component-overlap relations and can detect birth/deletion/split/merge even when total component counts coincide. Reuse that classifier in the study; keep an independent overlap check in verification.
4. Coarse 26-neighbour topology, refined sampled topology and continuous trilinear topology are different claims. The old proposal's assertion that P2 covers all previously observed dense splits is unproved. The new thin-neck rows test coverage and do not discard a miss.
5. The old draft's `fin 1h x 4h` was not an unambiguous short protrusion. The new F1 states a .5h protrusion from the broad face and retains a deliberately thin 1h cross-section. This changes only an unfrozen fixture definition; it does not change r, tau or the nominal limit.
6. K5's spanning slabs cannot have the ordinary full halo. A prospectively named K5-only finite-array convention, explicit frozen fluid planes and a finite-array comparison resolve that contradiction without inventing missing exterior nodes.
7. Independent code agreement is not a geometric truth oracle. Independent construction, known analytic primitive checks and invariants are also required. The formal review and source review must inspect boundary equivalence and input identities.
8. New seeds alone do not establish separation. Synthetic array dimensions differ from the old study; new v18 combination schedules and complete field identities require comparison with known old inputs, with no replacement draws on collision.

The numerical, geometry and governance formal reviews form one subsequent review round on the same protocol snapshot. Their findings/resolutions and source review are recorded separately; none of the formative work above substitutes for those gates. The original 2026-10-22 draft remains a dated historical artifact.

The one formal three-angle plan-review round is preserved in `plan_review_snapshot.md`, `plan_review.json`, `plan_review_go_reports.json` and `geometry_review.md`. Its initial168-row design was extended prospectively to180 to include the missing long fin and open slots. Engineering drafts overlapped review; final source integration and the single source review must follow the recorded resolutions.
