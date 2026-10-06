# Independent scientific contract review — FD-08 Stage 1.5

## Scope, independence, and evidence class

This review used only `/tmp/fd08-stage1p5-reviews/user_spec.md`. The reviewer did not read repository code, historical evidence artifacts, force/result/analysis data, primary conclusions, or another reviewer's outputs. No solver, fixture, numerical experiment, or direction calculation was run. Statements about Stage 1, exact-repeat behavior, R5 timing, and existing contracts below are **facts supplied by the specification, not independently verified measurements**.

This is a scientific design review. It does not establish a PASS, validate thresholds, verify current HEAD limits, register R6/formal/directions, or approve a scope change. The numeric stop conditions must be cleared by the separate numerical work before the parent may advance to the scientific decision packet. This prompt-only review can identify design dependencies but cannot certify that those conditions were cleared.

## Overall finding

The proposed Stage 1.5 scope is defensible as a preregistration/design exercise. Its strongest safeguards are preserving the 17 historical strict numeric mismatches, freezing comparison rules before unseen fixtures, separating response-model interpolation from noise validation, and requiring a user decision before R6 registration.

A decision-ready packet must avoid three upgrades of evidence: nominal WLS uncertainty is not an empirically established noise distribution; agreement of two response models is not proof of correct derivative recovery; and passing selected directions is not full-field gradient qualification. There is no specified numerical δ from #23, and B-3–B-7 have not been approved. Those gaps cannot be repaired by inventing δ or silently choosing a weaker coverage contract.

## B-3: estimator, covariance, and model discrimination

For odd response samples S_i and model A, define X_i = [ε_i, ε_i³]. With an OLS pilot prediction S_pilot,i, freeze the one-pass feasible-WLS procedure:

    v_i = σ0² + (ρ S_pilot,i)²
    w_i = 1/v_i
    β_hat = argmin_β sum_i w_i (S_i - X_i β)²
    Σ_nom = (Xᵀ W X)^−1.

The actual row multiplier is √w_i = 1/√v_i. A phrase such as “weight 1/√v_i” is correct only when it denotes that row multiplier; using it directly as the quadratic objective's weight changes the estimator. Freeze units of S, ε, σ0, g, c, W, and covariance entries together with the arithmetic contract.

Σ_nom has the usual known-variance interpretation when the linear mean model is adequate, errors have zero mean and independent covariance diag(v_i), the variances are correctly specified in the response being fitted, and X has full column rank. Here the pilot derives W from the same data. The reported matrix is therefore a **conditional plug-in nominal covariance**: it does not propagate uncertainty in the pilot weights, uncertainty in σ0/ρ, cross-sample correlations, or systematic solver/model discrepancy. Gaussian errors are additionally needed for exact normal-tail probability interpretations; a covariance formula by itself does not justify them.

If σ0/ρ understate variability, nominal SE becomes too small, magnitude tests can appear more decisive, and prediction checks can be too strict. Overstating variability has the opposite effects. Signal-dependent misspecification can also alter relative weighting and hence the fitted derivative, rather than merely rescale its uncertainty. Multiplying Σ_nom by fitted χ²/df would introduce a different variance-estimation assumption; leaving it unscaled is coherent only when σ0/ρ are treated as externally fixed nominal inputs. Neither convention cures mean-model bias.

A sandwich matrix has the form A^−1 Xᵀ W Ω W X A^−1, A = Xᵀ W X. A residual-based estimate of Ω has finite-sample and leverage issues, especially with six observations and two coefficients. It does not magically identify deterministic solver error as stochastic noise. Explain this alternative without changing the registered covariance estimator.

If S is formed from a ± force pair, its uncertainty must be specified at that response level. For S = (F_+ − F_−)/2, Var(S) = [Var(F_+) + Var(F_−) − 2 Cov(F_+, F_−)]/4. A force-level noise floor is not automatically the same floor for S. Drag and downforce from one state can also be correlated. Requiring both to pass is a logical conjunction, not a claim of independent tests or a calibrated joint confidence level.

The supplied Stage 1 statement that a 25% curvature ratio passed at a 5 mm upper endpoint is a stated synthetic detection limit, not newly verified data. On that finite interval an ε³ term can absorb enough of an ε|ε| response to make the fitted g values close. Thus A/B agreement only tests a specific discrepancy metric for a specific ladder, variance model, and tolerance. It cannot certify the physical response family or general derivative identifiability. “A4 PASS” must not serve as a model sufficiency argument.

Model A/B fits use the same observations. Any probabilistic test of their g difference must account for that dependence; treating their SEs as independent is unjustified. If the gate uses a deterministic normalized difference instead, label it a diagnostic with an engineering threshold. Freeze model identity and any selection/rejection rule before calibration; a post-calibration model switch can invalidate formal independence unless that selection procedure was itself preregistered.

## B-5: tolerance and the absent δ

T1 is a conditional error-budget design: “if the user supplies δ, allocate it among stated error sources using a stated propagation rule.” It is not a source of a numerical δ. Worst-case bounds combine differently from independent stochastic variances; do not use root-sum-square without an independence and stochastic interpretation. A relative derivative tolerance also needs a near-zero convention and a physical scale. The supplied specification alone does not contain #23's full criteria, so this reviewer cannot enumerate their exact conflicts; the parent must verify those against current authoritative text.

T2 can be presented without claiming qualification. Each parameter should have value, units, definition, provenance, evidence class, and the effect of being too large/small. Distinguish measured inputs from quantities derived under a model, engineering choices, synthetic calibration, and arbitrary provisional values. The actual provisional values are absent from the review input and are not reconstructed here. In particular, a deterministic exact-repeat floor of 1e−8 N, as stated in the prompt, does not establish σ0 as a physical noise variance.

Numerical implementation comparison tolerance and engineering derivative accuracy tolerance solve different problems. Cancellation-aware numerical agreement cannot substitute for B-5's scientific accuracy budget. Stage 1 synthetic success cannot independently anchor that budget. If δ is still absent, one defensible user choice is to approve a clearly provisional diagnostic R6 configuration under T2 while retaining all qualification flags false; that approval must explicitly state that it does not establish #23 accuracy qualification.

## B-4: coverage and gradient-space claims

Recommend COV-A: every registered direction must pass for both drag and downforce. This preserves the stated “every registered direction” interpretation. A failed direction remains registered and visible; a new lobe is not a replacement selected to hide D1.

COV-B can be a scientifically meaningful separate capability, but requires a preregistered general rule and an explicit user-approved change of claim. For example, 3 of 4 directions passing defines qualification of a selected subspace under that rule. It does not recover the failed component or qualify the original four-direction space. The optimizer must consume only the qualified components under a fixed policy, with the available subspace recorded per response; different qualified direction sets for drag and downforce can yield different feasible optimization spaces. LOWDIM-01 and the meaning of full-field qualification must be addressed explicitly.

General coverage also needs more than a count if geometric span matters. Four nearly collinear directions give little additional coverage. Freeze normalization, independence/span diagnostics, and rank policy before response results. Do not choose directions, exclusion rules, or a coverage denominator after observing response failure. Passing either COV-A or COV-B on a finite inventory remains evidence about that inventory, not about all field directions.

## B-6: lobe direction design requirements

One defensible candidate is a smooth compactly supported normal-displacement lobe defined on a fixed canonical surface chart. For chart coordinates (s1,s2), define

    b(t) = exp(1 − 1/(1 − t²)) for |t| < 1; b(t) = 0 otherwise
    h(p) = b((s1(p) − a1)/ℓ1) b((s2(p) − a2)/ℓ2).

Its support and center are geometry choices made before response data; its peak is one. Positive h means displacement along the chosen outward normal. Alternative candidates could use a second preselected region or two opposite-sign disjoint lobes, but are alternatives for inventory design, not a menu to select by force outcome. Sizes, center, chart, and any signed combination must be fixed, and correlations to D0/D1/D2 measured using only the canonical state and permitted direction generator.

The review input does not independently establish the canonical sign or distance convention. The final contract must verify them. Under φ < 0 for solid and a true metric signed-distance φ, n = +∇φ/|∇φ| is outward and φ_ε = φ_0 − ε h_extended produces outward positive displacement to first order. If φ is not a true signed distance, φ subtraction is not automatically a displacement of ε h; the existing admissible update definition must account for |∇φ| or otherwise establish the intended motion. Do not introduce geometry repair to make this design work.

Freeze surface extraction/chart assignment, normal evaluation, interpolation/projection, extension into a narrow band, band taper, zero-gradient and projection-ambiguity handling, mask boundaries, protected regions, and canonical v17 application. A normal projection requires a suitable local uniqueness domain; do not silently pick one of multiple nearby sheets. If an extension taper is used it should equal one on the intended boundary and vanish at a registered band boundary. These choices can change both support and discretized direction identity.

Use a clear normalization, preferably max surface |h| = 1 if ε represents maximum intended displacement. Record physical maximum/RMS displacement and the precise measure used for RMS. Surface-area-weighted RMS, grid-node RMS, and the L2 metric used by the existing generator are different measures and must not be conflated. Direction cosine/support overlap do not establish response identifiability but can expose redundant geometry directions.

The byte contract must include source canonical NPZ hash separately from raw Float32 φ hash, grid shape/spacing/origin, byte order, dtype, flattening order, direction parameters, arithmetic/casting order, and generator/source identity. Hash every relevant ± ε state after the actual Float32 operation, not a mathematically equivalent Float64 intermediate. Record changed-node count/support, signed and absolute change statistics, nonfinite checks, saturation/roundoff cases, and whether distinct intended perturbations produce distinct state bytes. A different file-container hash alone does not prove a different φ state. This review generated no lobe, correlations, audit, or hash.

## B-7: formal predict-then-run

Recommend frozen-coefficient predict-then-run at preregistered interior magnitudes. With x_f = [ε_f, ε_f³], use S_pred = x_f β_hat and nominal fitted-mean variance v_mean = x_f Σ_nom x_fᵀ. A standardized prediction residual requires an explicit denominator: fitted-mean uncertainty alone answers a different question from predictive uncertainty including a nominal observation variance at ε_f. Adding that variance assumes the covariance model and independence of the new response error from calibration errors; deterministic solver discrepancies need not satisfy that assumption. Call the resulting statistic nominal when those assumptions are not established.

Freeze the functional acceptance rule before calibration. Its numerical predicted SE may depend on the frozen calibration covariance, but its multiplier, absolute floor, relative denominator convention, handling of near-zero predictions, sign rule, and aggregation across directions/responses/formal points cannot be chosen after seeing calibration results. Do not refit using the formal point, choose whichever model predicts it better, or enlarge a threshold from its residual.

The formal ε selection rule must also be frozen before calibration and defined for any approved ladder. An interior geometric mean is defensible for positive magnitudes, but it must be absent from every fit and any held-out procedure later used for fitting/model selection. Fix which interval is selected by index; do not choose it from observed curvature. Require unused Float32 φ byte identities for both ± states. If quantization produces a collision, use a preregistered rejection/alternative rule, never an ad hoc magnitude change.

The check establishes interpolation performance at its sampled interior states for a deterministic solver and fixed model. It does not establish independent noise, extrapolation, all-interior uniform accuracy, time variability, grid independence, or physical truth. A single ± pair supplies one odd-response residual per direction/response. If even-response behavior or separate ± predictions are important, their model and acceptance rule need independent definition; an odd S model alone does not predict the even response.

## J-1: jitter options and degrees of freedom

The following reuses only the supplied specification's existing-analysis statements: one magnitude requires 2 states/direction and yields one J per direction/response; two magnitudes require 4; exact repeat is bit identical with a stated floor of 1e−8 N. No claim here rechecks those observations.

| Choice | Information and degrees of freedom | Added states for D directions | Scientific dependency |
|---|---|---:|---|
| 2 states/direction | One odd-response residual per response. Conditional on a fixed predictor, one squared residual can be computed, but there is no replicated sample variance or way to separate bias from dispersion. | 2D | Requires frozen predictor and magnitude rule; model bias, fit uncertainty, and deterministic ε variation remain mixed. |
| 4 states/direction | Two residuals at different magnitudes permit a small contrast and a magnitude-dependent discrepancy check. If treated as exchangeable independent samples with an estimated mean, only one variance df remains; fitting a two-parameter discrepancy trend consumes both observations. Those exchangeability assumptions are generally unsupported. | 4D | Requires frozen two-magnitude rule; magnitude dependence and shared calibration uncertainty cannot be ignored. |
| No jitter | No jitter-based noise or local-discrepancy estimate. Formal interpolation can still test the fixed response model. | 0 | σ0/ρ must remain explicitly externally assumed/provisional, rather than described as measured in R6. |

Do not multiply nominal df by pooling directions/responses. Directions differ in physical response and model error; responses from the same states and residuals sharing a calibration fit can be correlated. Pooling needs an explicit hierarchical/equivalence assumption and a frozen rule. Exact repeats, ε micro-jitter, grid-phase perturbations, time-window changes, and model residuals interrogate distinct mechanisms. They must not be folded into a common σ0 by naming them all “noise.”

Recommend no jitter in the first diagnostic R6 configuration if its purpose is model interpolation and the variance inputs remain honestly nominal. If the user specifically needs a local deterministic discrepancy diagnostic, prefer four states over two for a magnitude contrast, but it still cannot serve as standalone stochastic noise calibration. Separating jitter into a later round is defensible only if no R6 gate requires a jitter-derived σ0 or threshold. A later result cannot retroactively validate the earlier frozen variance model.

## L-1: ladder, identifiability, and separation of roles

Six positive magnitudes provide six odd responses per direction/response and nominal residual df = 6 − 2 = 4 for a two-coefficient fit. Actual state count is twelve per direction. Matrix rank is necessary but insufficient: report conditioning after the approved scaling, leverage, covariance/correlation of g and c, and the consequences of nested removal. A scaled condition number does not recover curvature information absent from the data. Rank handling and the minimum distinct retained magnitudes must be fixed for every nested fit/holdout.

A candidate compact ladder is {0.5, 0.8, 1.25, 2, 3.2, 5} mm. This is an **unexecuted engineering candidate**, not calibrated or approved. Its six distinct points and approximate logarithmic spacing are suited to studying a local linear-plus-cubic response. A preselected formal magnitude sqrt(2 × 3.2) mm is interior and separate from the six calibration points. Float32 distinctness and design diagnostics are still required.

A broader ladder incorporating a 15 mm endpoint increases the cubic-to-linear ratio, proportional to ε², and may aid curvature discrimination, but also increases omitted higher-order effects and geometric nonlocality. A separate upper-end comparison can be useful if its role is frozen as a sensitivity diagnostic, not an outcome-based choice between ladders. Stronger observed curvature is not automatically a more accurate derivative at zero. A compact ladder extending lower than 0.5 mm can improve locality but may be limited by Float32 state changes and response resolution; this requires evidence, not speculation.

The old seven-point/100× span rule may be unsuitable for this specific two-column local regression because a wide span can combine unresolved tiny perturbations with high-leverage/nonlocal upper points. That is an a priori identifiability/local-model argument; it must be tested through numerical/geometric diagnostics, not justified by R5 failing. Seven points can itself be valuable; the point count and the span are separate choices. Changing either old rule remains a user-approved contract change. Do not pick endpoints, exclusions, model, or thresholds from R5 force/results/analysis.

Freeze whether a calibration holdout is a leave-out internal diagnostic or a separately unused state. A point used for a model/tolerance choice is not available as untouched formal evidence. Preserve the required six-point regression and meaningful nested/holdout capability when budgeting; reducing states until they fit 5400 s is not a scientific design criterion.

## P-1: budget and a candidate configuration

Using only the prompt's estimates, 57 states cost 6195.9 s of solver time and 10413.9 s elapsed. A multiplicative 20% margin gives 7435.08 s and 12496.68 s, respectively. Integer second caps must be at least 7436 and 12497 if rounded upward. Both exceed the stated 5400/10800 s caps. Those limits and their enforcement semantics need current-HEAD verification by the parent.

Count all solver work charged by the contract, including baseline, calibration, formal, jitter, and any registered initialization/retry work. Kernel accounting additionally includes startup, reconstruction/transfer, compilation, evaluation, evidence packaging, and per-partition repeated overhead. A prior mean of 108.7 s/state is a planning estimate, not a wall-clock upper bound. A 20% margin is an engineering reserve, not a demonstrated completion probability.

Budget A (raise both caps) is the simplest candidate if allowed. Budget B (split kernels) requires a fixed state partition and unchanged criteria/source/dataset identity, verified state lineage, and aggregation rules; it does not solve a globally enforced solver-total cap and introduces repeated overhead. Budget C (fewer states) must derive from a still-adequate scientific design. Budget D (later jitter) is allowed only when the first round's decisions do not depend on its results. All of these are user decisions, not current authorizations.

One coherent **conditional candidate** is:

- N: numeric contract chosen on the separate reference/fixture evidence, with no numerical stop condition triggered. This review cannot choose or certify C5's bound.
- B-3: one-pass pilot WLS with frozen two-coefficient model A, model B as a separately frozen discrepancy diagnostic, and unscaled covariance explicitly labeled nominal.
- B-5: explicit user approval of provisional T2 as a diagnostic contract; no invented δ or #23 qualification claim. If the user requires δ-based accuracy qualification, that branch remains incomplete until δ is supplied.
- L-1: the six-point compact ladder above, subject to approval of the old-contract change and preregistered Float32/design validity checks; fixed internal nested/holdout rules.
- B-6: D0/D1/D2 plus one geometry-selected lobe, after permitted correlation/support auditing and frozen byte-generation rules. No replacement of D1.
- B-4: COV-A, all four registered directions × both responses.
- B-7: one fixed unused interior ± pair per direction, with frozen coefficients/covariance and tolerance rules, checking interpolation only.
- J-1: no jitter in this round; no claim that σ0/ρ have been measured by it.
- P-1: Budget A raising both limits with at least the specified 20% planning margin.

For that proposed inventory, **if one shared canonical baseline is required**, state count is 1 + 4 × (2 × 6 + 2 × 1) = 57. This is this review's explicit planning construction, not a verified decomposition of an existing table. If internal holdout needs extra independently run states, baseline accounting differs, more formal points are required, or 15 mm states are added, the count and budget must increase. Adding the specified jitter options to this construction yields 65 or 73 states before other additions; new elapsed predictions must include the actual additional overhead rather than blindly reuse the 57-state table.

This configuration is a candidate for the user's one decision. It cannot become an executable R6 registration merely by accepting this review: actual T2 values, formal thresholds, lobe parameters, numeric-rule evidence, current limits, and all changed-contract approvals must appear concretely in the packet first.

## Dependency structure and unresolved user choices

The stated DAG is a useful governance order:

    numeric contract → estimator/model → tolerance
      → ladder/jitter → direction inventory → coverage → formal

There are additional design dependencies to make explicit. The noise/covariance interpretation precedes standardized-error thresholds; tolerance must supply a rule usable for future directions rather than depend on observed g; ladder determines coefficient identifiability, nested/holdout validity, formal locations, and quantization checks; direction normalization determines the meaning of ε; inventory fixes the coverage denominator; formal count and jitter choice determine budget. N3 production scaling follows the approved ladder. Budget is a cross-cutting feasibility check on the complete planned state inventory, not a license to weaken statistical requirements after results.

Avoid an outcome-driven cycle: provisional design calculations may compare candidate ladders/directions before response data, but all acceptance rules and selections must be frozen together before calibration. The final configuration hash should bind these mutually dependent design choices.

The remaining genuine user tradeoffs are:

1. Provisional diagnostic T2 now versus a δ-based contract requiring a supplied accuracy target.
2. COV-A preserving every-direction scope versus an explicitly changed partial-space capability under COV-B.
3. Local compact ladder versus wider/15 mm curvature diagnostics and the corresponding old-contract change.
4. Nominal plug-in covariance as the registered uncertainty convention versus a separately authorized richer uncertainty design.
5. No jitter versus two/four extra states as deterministic discrepancy evidence, with no unsupported noise claim.
6. Raised total/kernel limits versus a scientifically adequate partition or a different prospective state inventory.
7. One interior formal pair versus multiple interior checks: the latter broadens sampled interpolation coverage at higher cost, while neither proves uniform interpolation accuracy.

No scientific PASS is claimed. The 17 historical numeric mismatches must remain historical unmet strict comparisons; no execution, registration, scope change, qualification-flag change, or roadmap update is authorized by this review.
