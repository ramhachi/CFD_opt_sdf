# GEOM-03 prospective protocol — 2026-10-23

Document role: **PROSPECTIVE_SPECIFICATION**. One three-angle formal plan review returned NEEDS_FIXES; the parent resolved its findings prospectively below and in the review record. This specification itself grants no launch permission and contains no study result. The separate hash-bound `registration.json`, `execution_release.json` and terminal result record establish whether later gates were actually passed; writing this text does not establish those facts. It supersedes the incomplete [2026-10-22 draft](geom03_registration_2026_10_22.md) prospectively; that file and its evidence remain unchanged. Order authority is [phase_plan](phase_plan.md), issue [#70](https://github.com/ramhachi/CFD_opt_sdf/issues/70). The [execution plan](next_execution_plan_2026_10_23.md) is subordinate to it.

## 1. Question and claim ceiling

Test the proposed R3 opening-defect rule + P1 frozen-node margin + P2 registered topology/mask rules, on new input arrays before SCREEN can adopt that composite. Reuse `scripts/width_rule_study.py` and `geometry_gates_v2._topology_gates`; do not change either, the registered 1.5h limit, or FID-01's R0. No adoption follows from writing or running this program. Even a PASS is bounded evidence on this fixture family, not a CAD/manufacturing minimum, continuous-topology certificate, meshing/flow qualification, grid-independent force or FSAE result. SCREEN requires its own registered geometry profile and the other geometry/constraint checks. All qualification flags and `shape_update_allowed=false` stay unchanged.

Known before design: WIDTH-RULE, its unit fixtures, all its published synthetic/phase/combination results, the prior draft, source/mask metadata and the formative source analysis. Shape families and parameter choices are informed by those known data. Novelty is new arrays and schedules, not an unseen scientific hypothesis or an independent parent. No FID force output is an input.

## 2. Exact candidate and statuses

`h=0.025 m`, `k=4`, `pad=3`, `r=0.75h`, `tau=h`, `LENGTH_TOLERANCE_M=1e-9 m`. Import R0 and R3 directly, not `measure()` which also computes unneeded R1/R2/R4. R0 occupancy is exactly `volume_semantics._corner_mean(phi)<0`, including its left-to-right float32 eight-corner addition and float32 multiplication by .125; neither node signs nor a float64 mean may replace it.

- R3: coarse solid is `phi<0`; crop its node AABB with three nodes of padding, clipped exactly as the existing helper. Trilinearly refine at h/4, then use the strict-negative sampled body B. Opening uses erosion `EDT(B)>r` followed by dilation through distances `<=r`. Defect is the maximum distance of rejected material to the opening. Compute solid B and void `~B` independently on the original crop. Do not apply one phase's opening to the other phase.
- Empty helper body gives None; nonempty body with no eroded point gives infinity. Solid None is unmeasured; void None passes. Otherwise D<=tau+tolerance passes, D<=tau+h/4+tolerance is unmeasured, larger/infinite D fails. Top-level empty-solid R3 returns both defects None and unmeasured. None is not an experimental uncertainty or a zero defect.
- P1: for both specified parent and candidate, `min(abs(phi[~active_mask])) >= h/2`, without adding a new tolerance. The margin-control value is `np.float32(np.float64(h)/2)` = 0.012500000186264515, float32 bits 0x3c4ccccd (little-endian bytes cdcc4c3c); this is compared against the unrounded float64 h/2. R1 uses `np.float32(np.float64(.3)*h)`. The frozen mask must be nonempty; missing/empty mask is an input error, not infinity/pass. `active_mask` is the existing design & ~fixed & ~forbidden & ~root definition.
- P2: create valid same-grid SDFDesignStates with identical masks and the resolved research policy `d4cd9aa42f0062923cdc8713d14d10fd334888a3c9dd5db9be15f7ac9d378d41`; call `_topology_gates(..., allowed_events=(), birth_qualified=False)`. Include its mask-preservation, component-connectivity and topology-change statuses. `max_components=null` is no fixed count cap, not a ban on multiple existing bodies. A forbidden birth/deletion/split/merge still fails. Use the existing component-overlap event classifier, not a count-equality shortcut.
- Composite: P1 violation is blocked; otherwise worst R3/P2 with pass < unmeasured < fail. Blocked is a non-pass. Invalid construction/checker disagreement is an experiment-level INCOMPLETE, not a physical rejection.

P2 judges coarse solid-node 26-connectivity and component overlaps. It does not certify the continuous trilinear set or void cavities/tunnels. Record coarse and refined sampled component counts separately. Do not assume it covers every dense split reported by the old WIDTH-RULE study.

## 3. Frames, fields and masks

Synthetic lattice: 27^3 nodes, origin (0,0,0), spacing h. Old WIDTH-RULE synthetic arrays are 26^3; shape+dtype+grid are part of input identity. Write all phi as little-endian float32, identity SHA over Fortran-order bytes plus separately recorded grid/mask identity. Evaluate formulas in float64 then cast once. Coordinates below are in h units; multiply the resulting distance field by h. Constructive fields are labelled as such; their signs/zero sets are analytic, but they are not asserted to be exact Euclidean SDFs at overlapping CSG interiors.

For local q, define `box(q,b)=norm(max(abs(q)-b,0))+min(max(abs(q)-b),0)`. For product of a 2D signed distance d and interval distance v, use `product(d,v)=min(max(d,v),0)+hypot(max(d,0),max(v,0))`. Capped x-cylinder: `product(hypot(q_y,q_z)-radius, abs(q_x)-half_length)`. Sphere: `norm(q-center)-radius`. CSG union=min; contained void subtraction=max(body,-void).

Orientation `R_y(theta)` is the ordinary right-handed rotation, theta in {0,45} degrees; local `q=R_y(theta).T @ (node_index-(13,13,13)-phase)`. Except the explicit merge-center offset, all bodies use this formula. Synthetic design mask is all nodes except the outer two layers (a node is frozen if any index<2 or >24); fixed/root/forbidden masks are empty. Every ordinary nonempty scored row must have the full three-node coarse solid halo. Missing halo gives INCOMPLETE, with the row retained. Parent and candidate use exactly the same mask, grid, phase and orientation.

`P8[j] = ((2j+1)/16-1/2, (2((3j) mod 8)+1)/16-1/2, (2((5j) mod 8)+1)/16-1/2)`, j=0..7. Each coordinate samples eight distinct subcell offsets. `Q2={(1/8,3/16,5/16),(-5/16,-3/16,-1/16)}`. No random rotation. These are deterministic placement samples, not iid observations or confidence intervals.

Static analytic rows use an identity parent. Transition and margin controls below name distinct parents. A parent field may be an input to several comparisons; it is not silently counted as a new scored row each time.

## 4. Input enumeration (180 base rows, including diagnostics)

### K1 analytic controls: 24 rows

Three shapes × P8, theta=0, ordinary masks/halo, identity parent; each is expected composite pass:

1. Round bar: `product(hypot(q_x,q_z)-2.75, abs(q_y)-3.5)`.
2. Stadium prism: `product(hypot(max(abs(q_x)-5,0),q_z)-2.75, abs(q_y)-3.5)`.
3. Thick box: `box(q,(4.5,3.5,2.5))`.

### K1 optimizer-like fields: 28 rows

Use the existing hash-bound v18 parent, its masks/grid, the ordered `basis.proposed_basis` and `a_star` in `docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json`. Order/values currently are heave31.1, pitch3.1, camber19.7, reflex29.3, twist1.1, sweep11.3, surge31.1, with units from the existing builders. Pin the file and builder hashes; do not substitute the FID d_set or select on forces.

Use `numpy.random.Generator(PCG64(SeedSequence([20261023,1])))`. For i=0..27 in order, draw n=`rng.integers(2,4)`, choose n distinct basis names with `rng.choice(names,size=n,replace=False)` in returned order, then draw one coefficient U[-1,1) per selected name in that order. Build each basis field with `mode01_v18_prescreen.state_phi(parent,params,name,a_star)` and combine in float64 as `parent_phi + sum(c*(basis_phi-parent_phi))`; keep frozen nodes exactly parent-valued and cast once to float32. For i=20..27 also draw a full `parent_phi.shape` float64 C-order array of U[-h/16,h/16) noise using `PCG64(SeedSequence([20261023,2,i]))`, then add `np.where(active_mask, noise, 0)` before the final cast. Drawing only the active-node count is a different, forbidden schedule. Accumulate the selected coefficient-times-difference terms left-to-right in the returned basis order, then add parent_phi once. All 28 belong to K1; none are dropped after R3/P2 results. Their parent is the v18 parent. No reinitialization or scalar volume projection.

This deliberately includes non-SDF fields, as WIDTH-RULE D3 does. A PASS does not certify their other geometry/volume gates. A failed expected control is a counterexample to this bounded claim, never a reason to reduce amplitude or noise.

### Fixed analytic/control rows: 87 rows

The first 19 IDs below each have theta=0 and45, each at Q2: 19×2×2=76 rows. S/V/T dimensions are full widths w, with other dimensions explicitly below. The checker verifies the family-specific observables below and analytic construction without using R3 output to label it. A missing required observable or unverifiable parent label is INCOMPLETE, never an exclusion/resample. A universal coarse-feature-presence predicate is deliberately not used for F1 or N2.

| ID | Field/parent | Prospective expectation |
|---|---|---|
| S1,S2 | `box(q,(4.5,4,w/2))`, w=.875,1.125 | thin solid: composite non-pass (K2) |
| S3 | same, w=4.75 | thick: pass (K3) |
| V1,V2 | `max(box(q,(6.5,6.5,5.5)),-box(q,(w/2,4.25,3.5)))`, w=.875,1.125 | thin internal void: non-pass (K2) |
| V3 | same, w=3.5 | thick void: pass (K3) |
| V4,V5 | `max(box(q,(6.5,6.5,5.5)),-box(q-(0,0,3.5),(w/2,4.25,4)))`, w=.875,3.5; void prism reaches z=7.5 above body top z=5.5 | open thin slot V4: non-pass (K2); thick open slot V5: pass (K3) |
| N0,N1,N2 | minimum of spheres radius2.5 at x=+-4.75 and capped x-cylinder half-length4.75, diameters d=2.5,.875,.375 respectively | N0 thick pass; N1 thin non-pass; N2 split rejected by P2 (K4). N1/N2 parent=N0; N0 identity parent |
| F1 | minimum of `box(q,(3.5,3,2.5))` and `box(q-(3.625,0,0),(.375,1.5,.5))`; parent=first box | 1h-thick fin protruding only .5h beyond the broad face: tolerated short, pass (K3) |
| F2 | minimum of `box(q,(3.5,3,2.5))` and `box(q-(5.625,0,0),(2.375,1.5,.5))`; parent=first box | 1h-thick fin protruding 4.5h: non-pass (K2) |
| W20,W40,W60,W90 | exact wedge-prism field below, opening angle20,40,60,90 | 20/40 thin non-pass (K2); 60/90 tolerated tips pass (K3) |
| T1,T2 | S-family box, w=1.625,1.875 | above nominal 1.5h: must not fail/blocked (K4); pass or unmeasured allowed |

Required K2 feature observables use coarse nodes and analytic local coordinates: S1/S2 have at least one negative node in the box; V1/V2 have at least one positive node inside their analytic void; V4 has at least one positive node in its slot with local z below 5.5 (inside the original body); N1 has a negative node in the inter-sphere neck region abs(q_x)<2.25; F2 has a negative node with q_x>3.5 outside the parent; W20/W40 have a negative node in the thin tip region `4-1.5/(2*tan(angle/2)) < q_x < 4`. None of these labels are inferred from an R3 pass/fail. F1 is an analytic/refined-feature tolerance control: record protruding coarse/refined node counts, but no positive coarse-node count is mandatory; its analytic .5h protrusion exists even when the coarse sampling represents no addition. N2 is an intentional lost-neck control: require the registered coarse overlap transition from one parent component to two candidate components, rather than a surviving neck node. A1 similarly requires the two-to-one coarse merge relation. Missing N2 neck nodes are expected, not an input error. The 26-node observations make no continuous topology claim.

Wedge construction: in x-z plane, let t=tan(theta_w/2), a=min(8t,2.5), v=4-a/t. Ordered polygon vertices `(-4,-a),(v,-a),(4,0),(v,a),(-4,a)`; remove adjacent duplicates. Signed planar distance is the minimum distance to the closed line segments (orthogonal projection clamped to each segment), negative exactly for `-4<=x<=4` and `abs(z)<=min((4-x)*t,2.5)`. Extrude with `product(planar_distance,abs(y)-3)`. The wedge angle is independent of the 0/45 lattice orientation.

Four further IDs at Q2, theta=0 only: 4×2=8 rows:

- A0/A1: two separated boxes with b=(2,2.5,2.5), x-centers `+-(2+g/2)` relative to center `(13.5,13,13)+phase`; g=2.5 for A0, .25 for A1; union=min. A0 identity parent is allowed with two components; A1 parent=A0 and must be rejected by P2 as a merge. Verify overlap labels, not count alone.
- R0/R1: use the K1 round-bar field with ordinary mask. In both fields replace frozen corner index(0,0,0) by +h/2 (R0) or +.3h (R1). R0 identity parent passes P1; R1 parent=R0 must be composite blocked. These are logical numerical-margin controls, not exact-SDF or physical-rim claims.

Three diagnostics, no phase/orientation loop: D1 has phi=+.75h except nodes(12,12,13),(13,13,13) at -.25h; its parent is itself. Record node-26 versus refined component counts; no assumed dense count is a pass requirement. E1 is all +h, top-level empty-solid R3 convention. E2 directly calls the opening helper on a small all-true boolean array (5^3, step=h/4); records its void-empty convention, not a halo-valid body. D1/E1/E2 do not enter K1–K5.

### K5 finite-array slabs: 40 rows

Widths {1,1.25,1.5,1.75,2}h × P8. On the 27^3 lattice use phi=`h*(abs(index_z-13-P8[j]_z)-w/2)`, constant in x/y. Parent is the same phase's width3.5h slab. **K5-only finite-array convention:** R0 and R3 use their existing clipped crops/EDT semantics, without extra padding, periodicity or invented exterior nodes. The checker uses exactly the same array domain. Full x/y halo is intentionally inapplicable; this exception never covers ordinary rows. Frozen mask comprises z=0 and26 planes only; no frozen solid, other masks empty. Thus P1 is non-vacuous, P2 is still evaluated, and the slab is explicitly not a finite interior body or a continuum thickness certification.

### Historical diagnostic: 1 row

H0 is the frozen v18 parent (NPZ SHA in the existing source bindings). Its known native R0 from `docs/evidence/width_rule_2026_10_20/v18_phase_sweep.json`, task `[v18,parent,0,[0,0,0]]`, is pass, solid .09762812094883319m, void None, phi SHA `29d53b2318c54548da321f265aa2102d59e24d96bbd04fb2dd70d62fbc10c82a`. Reproduce status/hash; report composite descriptively. Optional OPT-01/reinitialization reconstructions from the old draft are omitted to avoid extra recovery work; the new margin and topology controls carry K4. Historical data never become held-out evidence.

Total: 24+28+76+8+3+40+1=180 base rows. K6 adds two evaluations per non-diagnostic scored row, not extra base IDs. Parent construction, checker, disjointness checks and scaling all count against the same budget.

## 5. Criteria and verdict, fixed before outcomes

- K1: all 52 clean-control/combination rows pass the composite; unmeasured/blocked is not pass.
- K2: S1/S2/V1/V2/V4/N1/F2/W20/W40 are non-pass on every registered placement/orientation. A thin neck lost in the dense representation while remaining node-connected is not silently removed: if composite passes, K2 fails. This explicitly tests the unproved P2 coverage assumption in the old proposal.
- K3: S3/V3/V5/N0/F1/W60/W90 pass every registered row.
- K4: on every registered row, R0 passes P1 and the composite; R1 blocked; N2 rejected by P2; A1 rejected by P2; A0 allows its pre-existing two components; T1/T2 are pass or unmeasured. Valid contrary outcomes fail K4; missing construction proof instead makes INCOMPLETE.
- K5: per rule, q(w)=number of pass slabs/8 (unmeasured/blocked are non-pass). Require nondecreasing q and a bracket: lo=max{w:q<.5}, hi=min{w:q>=.5}. Both composite endpoints must be >= the corresponding R0 endpoints, zero tolerance. Nonmonotone or missing bracket => INCOMPLETE; no extra widths. This is a discrete interval comparison, not a fitted continuous crossover or GCI.
- K6: at c=.5 and2, identical R0/R3/P2 statuses and R3 sampled sign bodies to unscaled phi for scored rows. P1 is evaluated only in original metre-valued phi; do not silently scale its margin. R0 remains descriptive except K5 and H0.

PASS requires complete enumeration, valid independent construction/label checks, study/checker agreement, H0 replay, and K1–K6. A completed valid counterexample => GEOM03_NO_GO, no second attempt; use the roadmap's R0-clean fixed-set/parent branch. Any missing/corrupt input, implementation disagreement, intended-label construction gap, budget stop, ordinary halo failure or K5 degeneracy => GEOM03_INCOMPLETE. If incompleteness and a valid counterexample coexist, INCOMPLETE is the terminal label and the counterexample is still reported; no claim of acceptance. Diagnostic observations alone add no acceptance gate.

## 6. Disjointness and independent verification

Synthetic 27^3 inputs cannot equal the old 26^3 array identities. No independence beyond this representation/placement family is claimed. For new v18 combinations, compare the complete coefficient/noise schedule with known old tasks and compare generated field identities with all 99 known native phi identities and all 250 reconstructed old combination input identities. Pin the exact old `v18_phase_sweep.json` file, its ordered combo tasks and canonical task-stream hash from `known_inputs.json`, plus the new generator/source/recipe hashes at freeze. New draws are recorded after frozen generation and before outcomes; no unexecuted new schedule hash is fabricated. An empty or partial old-combination hash set is an inability to verify separation. Reconstruction is input arithmetic only, not a replay of old measurements; count its cost. A duplicate or an inability to verify the required separation gives INCOMPLETE; never draw replacement coefficients. Check this before measuring new outcomes. The new seed is not executed during development tests.

The independent checker must not import the study generator, `width_rule_study`, or its decision function. It independently reconstructs the declared fields/masks and trilinear samples and compares exact input/sign hashes. Use SciPy morphology with the closed Euclidean digital ball `{(a,b,c): a*a+b*b+c*c<=9}` (r/(h/4)=3), erosion `border_value=1` and dilation `border_value=0` as a separate opening path, with boundary handling proved equivalent on ordinary rows and explicitly matched for K5; compare defects/statuses and event-overlap tables. Back agreement with analytic primitive checks, finite-array boundary controls and scaling/translation invariants on **known development fixtures**. Agreement between two implementations is not an analytic oracle by itself. Unsupported all-true-array details remain diagnostic; no invented continuity claim.

## 7. Minimal implementation, freeze and execution release

Only two study scripts and one test file: `scripts/geom03_run.py` (exact inputs, candidate, state machine and serial execution), `scripts/geom03_check.py` (independent reconstruction/checks), `tests/test_geom03.py` (known tiny development fixtures and orchestration/integrity failures). Standard library, existing NumPy/SciPy and existing helpers only. No framework or production gate modification. Imports/default CLI/help/tests do not execute the registered schedule. Explicit run requires a valid freeze and a recorded parent decision to release this branch.

One formal plan review with three angles, resolution of its findings, then one source review and regression validation before freeze. Engineering drafts were written in parallel with the plan review; they were not frozen or executed as registered fixtures. The final source must incorporate all accepted findings before that single source review. This overlap is recorded as a workflow deviation from the original strict drafting order, not presented as an earlier passed gate. The parent then pins document/code/helper/input hashes, source commit/tree identities, ordered task definitions, seeds, runtime versions/platform and review records in `docs/evidence/geom03_2026_10_23/registration.json`. No source/threshold/label changes after freeze; any such change is a new registration. Deterministic input generation and identity recording happen under the frozen generator before outcome measurement; do not pretend ungenerated phi bytes already have measured hashes.

One attempt only; resume only a nonterminal interrupted attempt with verified append-only artifacts and identical freeze/input identities, no existing terminal stop/result, and dependency/resource gates rechecked. Its original start time and cumulative 2-hour limit include downtime; stopping the process does not replenish wall or row budget. Terminal INCOMPLETE/NO_GO/PASS records are never resumed or retried. Existing result/analysis files are never overwritten. Rows carry ID/family/grid/mask/parent/phi hashes, prospective labels, halo/P1/P2/R0/R3/checker states and diagnostics. Encode empty and infinite defects explicitly in strict JSON, not NaN/Infinity literals. A final independent check produces K tallies, verdict and stop reason once. Partial rows are never called a completed validation.

Budgets: <=200 base rows, <=2h total wall including input generation/reconstruction/checker, <=3GiB measured RSS; a single numerical worker at a time, numerical library threads=1. A lightweight parent watchdog may supervise that child, terminate only its own child at the declared limit and record observed peak RSS/stop reason. This is a monitored limit, not an OS guarantee against sub-sampling memory spikes. No inherited FID retry right or free restart on timeout.

Before any held-out input generation/measurement: no active FID containers, load average<=4, sufficient memory within the existing 3GiB study budget, and a recorded need for this branch (FID GO with R3 selected for validation, or an explicit M4 geometry need). Missing dependency/resource evidence => WAITING_FOR_DEPENDENCY/WAITING_FOR_RESOURCES, no attempt consumed, no scientific verdict. Freeze may be prepared without consuming an attempt; it is not a launch permission. FID remains Claude-owned; do not read partial forces or write its registered analysis. No new CFD/GPU/paid compute.

## 8. Changes from the tentative prior draft

The old 136 count was never frozen. The initial 168 enumeration, extended prospectively to 180 before any new outcome, replaces incomplete shape descriptions with formulas, uses 27^3 synthetic arrays for input separation, adds noisy phi-space combinations, defines a K5-only finite-array/mask contract, fixes the fin's short protrusion, uses overlap-based topology events, and tests rather than assumes coverage of dense splits. The optional historical rebuilds and unbound taper/diagonal acceptance expectations are removed; above-limit slabs, a diagnostic diagonal case and explicit transition controls retain their purposes. The additional F2 and V4/V5 rows restore explicit long-fin and open-slot coverage that was absent from the initial exact draft; closed cavities and a short tolerated fin alone did not cover those requested defects. No observed new outcome motivated these changes. The thresholds/legacy/FID contracts are unchanged.
