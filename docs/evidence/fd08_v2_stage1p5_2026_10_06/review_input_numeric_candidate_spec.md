# Stage 1.5 numerical comparison specification — pre-execution

Evidence class: `solver_free_numeric_contract_design_unregistered`.
Historical Stage 1 strict numeric condition: **unmet 17**. This document does not change its comparison or verdict.
All numerical experiment outputs must be absent when this specification and the seeds are frozen.

## Arithmetic and reference

- N1: fit in mm; form dimensionless diagnostics in native fitting units; convert only displayed g/SE to N/m.
- N2: fit in m; model A columns change by diag(1e-3,1e-9), model B by diag(1e-3,1e-6); form dimensionless diagnostics in SI fitting units. Transform beta and covariance back to mm only for forward-error reporting.
- N3: x=epsilon_mm/epsilon_ref_mm, epsilon_ref=max(full input ladder), fixed for every nested/holdout subset. Model A columns scale by diag(1/ref,1/ref^3), B by diag(1/ref,1/ref^2). This is a conditioning experiment, not a production choice while the ladder is undecided.
- Reference: standard-library Decimal, precision 80; exact conversion of the binary64 inputs and parameters via Decimal.from_float/as_integer_ratio. Solve the full-rank two-column OLS and WLS normal systems and inverse at arbitrary precision; all pilots, diagnostics, subset fits, covariance and thresholds remain Decimal. Repeat at precision120 as convergence check. This is a reference written after reading primary, **not a third independent implementation**. No package installation is necessary.
- Same mathematical contract: OLS pilot on the exact subset, w=1/(sigma0^2+(rho*S_pilot)^2), one WLS, nominal covariance, sign drops1..3, stability drops1..nested_drop, internal one-point holdouts, all input points.
- Primary and the frozen Stage1 blind implementation may be re-executed unchanged on new synthetic inputs. Preserve their source hashes. Do not change any Stage1 input/output/artifact.

## Rules fixed before evaluation

Let u=2^-53 (unit roundoff), gamma(k)=k*u/(1-k*u), n=subset point count, p=2.
The operation envelope k(n)=8*n+32 is an **engineering backward-error assumption**:
8 vector operations per observation plus 32 scalar/two-column factorization and conversion operations.
It is chosen from the computation path, not from measured mismatches. LAPACK/SVD internal operation count is not certified by this expression.
We test the envelope against the arbitrary-precision reference; successful finite-fixture checks are not a universal error theorem.

### C1: pure relative

abs(a-b) <= 1e-9*max(abs(a),abs(b)); atol=0; both0 agree.
Diagnostic comparison only for near-zero differences; historical C1 remains unmet17.

### C2: mixed, input-scaled absolute part

abs(a-b) <= 1e-9*max(abs(a),abs(b)) + gamma(k(n))*scale.
Scales are fixed by dimensions, not by the historical17:

- beta_j: ||S||2/||X_mm[:,j]||2 (N/mm for g; N/mm^3 or N/mm^2 for curvature).
- g/SE: first-coefficient scale, with the same display-unit conversion if needed.
- covariance_ij: sqrt(C_ii*C_jj), in the covariance's fitting units.
- predictions, holdout absolute errors: max(||S||inf,sigma0).
- relative SE, nested shifts, model difference: dimensionless scale1.

Report C2 separately; do not silently turn it into historical C1.

### C3: ULP

Absolute bit-distance of finite IEEE754 binary64 numbers, diagnostic allowance8 ULP.
Sign, zero and finite/nonfinite classification reported separately. The allowance is a diagnostic engineering choice, not a bound for the full fitting algorithm.
The ULP of a final near-zero difference measures the difference's exponent, not the rounding of its operands; it cannot explain cancellation in two nearly equal slopes.

### C4: semantic

Require identical availability/finite status, nonzero slope signs, each of six item's threshold side, internal holdout sides, and three-valued verdict.
Record signed margins for SE/nested/model/holdout/magnitude thresholds in their own units.
Margin differences must lie inside their propagated C5 envelopes; a threshold within an error envelope is explicitly numerically ambiguous, never rescued by tolerance.
Any actual verdict or item-side change between arithmetic variants triggers stop(c), even if the margin is tiny.

### C5: operand and fit-error propagation

For full/subset/model fits, use a conditional matrix-perturbation envelope. For a design X and target y:

1. dx_ij=gamma(k(n))*||X||2, dy_i=gamma(k(n))*||y||2 describes normwise backward error conservatively elementwise. Include design construction/unit conversion in this envelope.
2. A=X^T X, b=X^T y, C=A^-1, beta=C*b at high precision for this bound.
3. dA=abs(X)^T*dx+dx^T*abs(X)+dx^T*dx+gamma(n)*abs(X)^T*abs(X).
4. db=abs(X)^T*dy+dx^T*abs(y)+dx^T*dy+gamma(n)*abs(X)^T*abs(y).
5. E=abs(C)*dA. If spectral_radius(E)>=1, bound is unavailable (ill-conditioned envelope), never PASS by an infinite bound.
6. B_beta=(I-E)^-1*abs(C)*(db+dA*abs(beta)); B_C=(I-E)^-1*abs(C)*dA*abs(C).
   Add gamma(32) inverse/solve backward perturbation to dA/db before forming E. This explicitly includes covariance inversion arithmetic.

Apply this first to OLS. Pilot prediction error at each point:
B_pilot=abs(X)*B_beta + dx*abs(beta) + gamma(p)*abs(X)*abs(beta).
Pilot-dependent variance uncertainty: dv_i=rho^2*(2*abs(pilot_i)*B_pilot_i+B_pilot_i^2).
Let l_i=dv_i/(sigma0^2+(rho*pilot_i)^2). If l_i>=1, the bound is unavailable.
For sqrt(W), eta_w_i=1/sqrt(1-l_i)-1; this bounds both upward and downward weight errors.
For WLS Xw=sqrt(W)*X,yw=sqrt(W)*y, add rowwise abs(Xw)*eta_w to dx and abs(yw)*eta_w to dy, and repeat steps2..6. Thus the coefficient includes pilot/weight sensitivity and matrix conditioning, not just the final subtraction.
Report cond2(X),cond2(Xw), envelope spectral radius and the resulting coefficient/error bounds. These norms are unit dependent; forward errors are also shown in canonical mm units.

For r=abs(a-b)/abs(b), let operand error bounds be Aerr,Berr. For observed/calculated r versus high-precision r, use:

d=abs(b), t=abs(a-b), D=d-Berr; if D<=0, bound is unavailable.

B_r=(Aerr+Berr)/D + t*Berr/(d*D) + gamma(3)*(abs(a)+abs(b))/D.

This gives the requested form C*u*(abs(a)+abs(b))/abs(b), with C explicitly determined from B_beta/u and the subtraction/division path rather than fitted to17. For relativeSE use the same quotient propagation without cancellation in its numerator.
For two binary64 implementations, add their forward envelopes (plus saved decimal12 serialization bounds when comparing archived JSON). Do not compare a final r's ULP to operand-error budgets.
For a max of nested shifts, take the max of constituent bounds (max is Lipschitz in infinity norm). For abs holdout error, use the prediction error bound plus subtraction rounding. For prediction, propagate B_beta; for predictive variance use abs(x)^T*B_C*abs(x) plus prediction's rho term and dot-product rounding; use the exact square-root perturbation denominator. For max(3sigma,tol_hold*abs(prediction)), use max of the two propagated bounds. Covariance and SE use B_C and square-root propagation.

C5+semantic agreement is the candidate future rule; C1/C2/C3 remain explicit diagnostics.
If C5 under its stated assumptions is exceeded by an unseen fixture and no computational/input-precision cause explains it, stop(b) without changing formulas. Invalid bounds are explained separately and cannot be used to authorize production.

## Pre-fixed fixtures and execution order

- Unseen base_seed=46150000. Generator=PCG64. seed=base_seed+1000*scenario_number+ladder_count.
- Scenario numbers1,2,3,4,6,7,9,10,11,12,13,15,16,17,18,19,20,22,24,27 from the unchanged Stage1 synthetic scenario definitions, each ladder6/8. This covers exact linear/cubic, absolute noise, waviness, misspecified curvature and weak response. 40 unseen series; no results used to choose the numbers.
- Additional conditioning-only d15,d16,d17,d18,d22,d24 on geomspace(.5,15,7), six unseen series; same k at5mm, seed formula uses count7.
- Noise first, relative deviation second, per point; consume both standard normals. Generate once, serialize float12 before evaluation, and supply identical saved binary64 values to every implementation and reference.
- Exact-zero six/eight-point series may be used only as predeclared algorithm edge tests, not as noise samples.
- Historical20 are evaluated only after freezing the rules and unseen seeds. Their future-rule classifications are consequences; historical17 are not relabeled PASS.
- Convergence check: Decimal80 vs120 on the same inputs; report all errors, require verdict/item-side agreement and stability of the reference to1e-60 in input-scaled norm. A failed precision check stops reference use; no automatic precision escalation after results.

## Stop before decision design

(a) Essential primary/blind algorithm mismatch against the reference affecting threshold side/verdict.
(b) Unexplained violation of pre-fixed C5/semantic rule on unseen seeds.
(c) Verdict or three-valued item-side changes between arithmetic candidates.
When any stop condition is true, do not create B-3..B-7, budget, ladder or direction-design proposals; report only the numerical evidence and stop at Issue46.
Historical17 preservation, root cause, future canonical arithmetic, future comparison rule are separate report fields.
