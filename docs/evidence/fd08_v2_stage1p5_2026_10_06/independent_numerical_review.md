# Independent numerical pre-execution review

Evidence class: `solver_free_numeric_contract_design_unregistered`.

## Scope and disposition

I read only `/tmp/fd08-stage1p5-reviews/user_spec.md` and `/tmp/fd08-stage1p5-reviews/numeric_candidate_spec.md`. I did not read repository implementations, historical outputs, other reviews, force/results/analysis, or solver evidence, and did not run fixtures. Statements below are mathematical review of the proposal, not observations about an implementation. The historical count of 17 unmet comparisons is provided by the specification and has not been independently verified here.

**Corrections are necessary before freezing or evaluating the rule.** N1's principle is sound: calculate dimensionless diagnostics in fitting units and convert displayed dimensional outputs afterward. N2/N3 are useful conditioning experiments. However, the C5 propagation is presently incomplete, `gamma(32)` has no operationally defined perturbation, serialization is insufficiently specified, and convergence and threshold-margin acceptance are not fully executable contracts. These are specification gaps; they do not establish a primary/blind algorithm discrepancy or any stop-condition event in data.

C5 can become a useful **conditional engineering envelope**. Its proposed operation count does not establish a proved backward-error bound for NumPy/LAPACK SVD, coefficient extraction, or covariance computation. Finite synthetic tests cannot convert this assumption into a universal theorem. The specification already acknowledges part of this limitation and should retain it prominently.

## 1. Units, column scaling, and conditioning

The stated column scalings are correct for model A `[epsilon, epsilon^3]` and model B `[epsilon, epsilon*abs(epsilon)]`. If `X_new = X_mm D`, then

- `beta_new = D^{-1} beta_mm`;
- `C_new = D^{-1} C_mm D^{-T}`;
- reporting in mm uses `beta_mm = D beta_new`, `C_mm = D C_new D^T`.

For SI, `D_A=diag(1e-3,1e-9)` and `D_B=diag(1e-3,1e-6)`. For normalized epsilon, `D_A=diag(ref^{-1},ref^{-3})`, `D_B=diag(ref^{-1},ref^{-2})`. Predictions and slope-relative diagnostics are invariant in exact arithmetic. The proposed fixed full-ladder reference for every subset prevents the scaling itself from changing between nested fits; define `ref=max(abs(epsilon_i))` if signed epsilon is ever supplied, or explicitly require a positive magnitude ladder.

Report condition numbers for both the pilot and weighted matrices, for every distinct subset/model. `cond_2(X^T X)=cond_2(X)^2` in exact arithmetic; normal systems in a high-precision reference therefore need convergence checks even when a production SVD is comparatively stable. Condition numbers of dimensional column matrices depend on coordinate units and are useful for diagnosing a numerical implementation in those coordinates. They are not unit-invariant measures of physical identifiability. The relevant production comparison is propagated error after conversion to canonical units, together with semantic margins.

The normal-system reference is mathematically equivalent to full-rank OLS/WLS, subject to the stated one-pilot/one-WLS contract. Preregister positive finite `sigma0`, finite parameters, valid subset sizes, a full-column-rank design, and explicit handling of zero response/slope and singular input. A singular reference must not silently choose a pseudoinverse with a different model contract.

## 2. C5 factorization/solve perturbations need an explicit definition

Let `gk=gamma(k(n))`, `g32=gamma(32)`, and let `D_X,D_y` be nonnegative bounds for errors in the design and target supplied to a solve. The proposal's uniform entries `D_X,ij=gk*||X||_2`, `D_y,i=gk*||y||_2` are conservative elementwise consequences of an assumed normwise perturbation of that size. Their actual validity for the implementation remains an assumption. Ordinary nonnegative matrix products are meant below.

Define `U=abs(X)+D_X`, `v=abs(y)+D_y`. A complete envelope for forming the Gram matrix and right-hand side is

```
D_A,form = abs(X)^T D_X + D_X^T abs(X) + D_X^T D_X
           + gamma(n) U^T U
D_b,form = abs(X)^T D_y + D_X^T abs(y) + D_X^T D_y
           + gamma(n) U^T v
```

The last terms must cover dot products of the **perturbed operands**, not just the original `abs(X)` and `abs(y)`. The original formula omits these extra terms. The gamma(n) expressions assume the ordinary floating-point model, no overflow/underflow invalidating it, and an appropriate implementation of the products.

One explicit *conditional* interpretation of the requested gamma32 factor/solve allowance is:

```
abs(F_beta) <= g32 * (abs(A) + D_A,form)
abs(f_beta) <= g32 * (abs(b) + D_b,form)
(A + Delta_A,form + F_beta) beta_hat
    = b + Delta_b,form + f_beta

D_A,beta = D_A,form + g32*(abs(A)+D_A,form)
D_b,beta = D_b,form + g32*(abs(b)+D_b,form)
```

Here `A=X^T X`, `b=X^T y` are exact reference quantities. Do not merely write “add gamma32” to a matrix: gamma32 is dimensionless and must multiply a dimensionally appropriate envelope. With `C=A^{-1}` and `E_beta=abs(C) D_A,beta`, the conditional coefficient bound is

```
B_beta = (I-E_beta)^{-1} abs(C)
         (D_b,beta + D_A,beta abs(beta)),  if rho(E_beta)<1.
```

For covariance, define its own algorithmic assumption. If its columns are exact solutions of nearby systems with `abs(F_C,j)<=g32*(abs(A)+D_A,form)` and an exactly represented basis right-hand side, then

```
D_A,C = D_A,form + g32*(abs(A)+D_A,form)
E_C = abs(C) D_A,C
B_C = (I-E_C)^{-1} abs(C) D_A,C abs(C).
```

The same nonnegative envelope can cover independently perturbed column solves; a single common perturbation need not be assumed. If the covariance algorithm has a right-hand-side perturbation `D_I`, use

```
B_C = (I-E_C)^{-1} abs(C) (D_I + D_A,C abs(C)).
```

A covariance built from SVD singular vectors/values or a coefficient computed through `lstsq` does not automatically satisfy the componentwise normal-system backward assumptions just written. A normal-equation solve does not automatically do so either: factorization growth and componentwise factor magnitudes matter. Either justify a backend-specific error bound or label these as explicitly assumed envelopes and test them as such. Do not describe `32` as a certified LAPACK operation count. If an explicit inverse is followed by a floating-point `C_hat*b_hat` multiplication, account for that multiplication and the inverse error, rather than assuming it is exactly the backward-stable solve above.

For `rho(E)<1`, `(I-E)^{-1}` is nonnegative and the proposed perturbation argument is valid. Evaluate the bound at reference precision, require convergence for the bound itself and its validity tests, and mark `rho(E)>=1` or an unresolvable near-one boundary **unavailable**, not infinite/PASS. Large usable bounds can still render semantic margins inconclusive.

## 3. Pilot predictions and weights are missing cross terms and arithmetic

A complete prediction bound, when both the stored design and coefficients can be perturbed, is

```
B_pilot = abs(X) B_beta + D_X abs(beta) + D_X B_beta
          + gamma(p)*(abs(X)+D_X)*(abs(beta)+B_beta).
```

The original expression omits `D_X B_beta` and rounding on perturbed dot-product operands. The same issue applies to holdout/predictive means. If a row is freshly formed for prediction, freeze a separate row-construction error rather than assuming it equals a training row's error.

Write `q_i=sigma0^2+(rho*pilot_i)^2`. The exact sensitivity term in the proposal is valid:

```
D_q,sensitivity,i = rho^2*(2*abs(pilot_i)*B_pilot,i+B_pilot,i^2).
```

It must also include the arithmetic used to construct q. For the explicitly fixed route `sigma0*sigma0 + (rho*pilot)*(rho*pilot)` with a reused computed product and correctly rounded binary64 operations, a conservative allowance is

```
D_q,i = D_q,sensitivity,i
        + gamma(4)*(q_i+D_q,sensitivity,i).
ell_i = D_q,i/q_i.
```

Other computational routes need their own preregistered allowance. This formula assumes the input parameters themselves are exact binary64 reference values and that no overflow/underflow occurs. If parameters are converted before fitting, propagate that conversion too.

If `ell_i>=1`, the weight bound is unavailable. For `s_i=sqrt(w_i)=1/sqrt(q_i)`, the exact input-variance perturbation is bounded relatively by `1/sqrt(1-ell_i)-1`. The production reciprocal and square-root operations must be included. For either a correctly rounded reciprocal-plus-square-root route or square-root-plus-reciprocal route, a conservative combined relative envelope is

```
eta_i = (1+gamma(2))/sqrt(1-ell_i) - 1.
```

Then, before adding the separate solve envelope, a complete bound for the floating-point row construction is, for example,

```
D_Xw,row,i = s_i*D_X,row,i + eta_i*s_i*(abs(X_i)+D_X,row,i)
             + u*s_i*(1+eta_i)*(abs(X_i)+D_X,row,i)
D_yw,row,i = s_i*D_y,row,i + eta_i*s_i*(abs(y_i)+D_y,row,i)
             + u*s_i*(1+eta_i)*(abs(y_i)+D_y,row,i).
```

Do not add an unweighted `D_X` to a weighted matrix without the row scale. Freeze whether the normwise solve envelope is formed directly for exact `Xw,yw` and then added to these row-construction envelopes. This avoids ambiguous units and makes double-counting explicit. Reapply the corrected Gram/solve/inverse formulas to the weighted inputs. Weight error depends on the **subset's** pilot as already specified.

## 4. Quotients, covariance, predictions, and threshold margins

For reference operands `a,b`, let `abs(a_hat-a)<=Aerr`, `abs(b_hat-b)<=Berr`, `d=abs(b)`, `t=abs(a-b)`, `D=d-Berr`. If `D<=0`, the relative diagnostic is unavailable. A conservative cancellation-aware bound for a rounded subtraction and division is

```
B_r = (Aerr+Berr)/D + t*Berr/(d*D)
      + gamma(3)*(abs(a)+Aerr+abs(b)+Berr)/D.
```

The proposal's first two terms are sound when `a,b,t,d` are reference quantities. Its last term should include perturbed operand magnitudes. Explicitly freeze which quantities are reference values; do not interchange reference and observed denominator bounds without a new derivation. Gamma3 is conservative for this short path under the ordinary rounding model. This expression has the requested `C*u*(abs(a)+abs(b))/abs(b)` interpretation where denominators are safely separated from zero, with C obtained from the fitted operand-error envelopes and denominator gap. C is not a universal constant and can become large or unavailable when conditioning/weak slope is unfavorable.

For relative SE, use a quotient bound directly. With reference `s=SE>=0`, `d=abs(g)`, `D=d-B_g>0`,

```
B_SErelative = B_SE/D + s*B_g/(d*D)
               + u*(s+B_SE)/D.
```

For an exact square root of reference `v>=0` with perturbation `B_v`, a safe absolute envelope is

```
L=max(0,v-B_v); H=v+B_v
B_sqrt = max(sqrt(H)-sqrt(v), sqrt(v)-sqrt(L)) + u*sqrt(H).
```

Use this for `SE=sqrt(C_11)` and predictive sigma, with a validity condition that the computed argument is nonnegative. If a definitely positive variance is required, require `v-B_v>0`. The identity `abs(delta sqrt(v))=abs(delta v)/(sqrt(v+delta v)+sqrt(v))` explains the square-root denominator; an unspecified “exact denominator” is not an executable rule. Zero needs the interval formula above.

For a predictive mean `mu=x^T beta`, use the corrected prediction bound from section 3. For the common proposed predictive variance `v_pred=x^T C x + sigma0^2+(rho*mu)^2`, the covariance part needs more than `abs(x)^T B_C abs(x)` if the row can be perturbed. Let `U=abs(x)`, `H=D_x`. Its exact perturbation is bounded by

```
H^T abs(C) U + U^T abs(C) H + H^T abs(C) H
+ (U+H)^T B_C (U+H).
```

Add the rounding envelope for the fixed quadratic evaluation, the rho/mean variance sensitivity, and variance-assembly arithmetic. If the intended predictive variance differs from this formula, state its exact formula and derive its bound before freezing. No error-term list is adequate without defining the expression and operation route.

For internal holdout absolute error `h=abs(y-mu)`, use

```
B_h = B_y+B_mu + u*(abs(y)+B_y+abs(mu)+B_mu).
```

For threshold `T=max(3*sigma_pred, tol_hold*abs(mu))`, propagate each branch, then `B_T=max(B_branch1,B_branch2)`; max is 1-Lipschitz in infinity norm even if the selected branch changes. Include constant-multiplication rounding. The holdout signed margin is `m_hold=T-h` with bound `B_T+B_h` plus rounding of a computed subtraction, if margins are actually computed in binary64.

Freeze every other signed margin and its bound explicitly, for example:

- `m_se=tol_se-SE/abs(g)`: quotient envelope plus subtraction rounding;
- `m_nested=tol_nested-max(r_subset)`: max of constituent envelopes plus subtraction rounding;
- `m_model=tol_model-r_model`: corresponding quotient envelope plus subtraction rounding;
- `m_mag=abs(g)-k_mag*SE`: `B_g+abs(k_mag)*B_SE`, product rounding, and subtraction rounding;
- slope sign margin is `g` itself; a certified nonzero sign requires `abs(g)>B_g`.

Parameters can be treated as exact input binary64 values. If their displayed decimal interpretations instead define the mathematical contract, include parameter-representation error. Freeze `<` versus `<=`, exact-zero handling, ties, undefined denominators, aggregation of holdout sides, and unavailable-value status.

To certify agreement with the reference, require its margin interval to lie strictly on the prescribed side of the threshold. A margin intersecting zero is **numerically ambiguous**, even if both implementations happen to report the same side. For two implementations, add their individual forward envelopes; for margin comparison, add their margin envelopes. Do not confuse a small observed margin difference with a certified threshold side. Bound-unavailable, numerically-ambiguous, explained-forward-error failure, unexplained failure, and actual side/verdict disagreement need separate output states. The predeclared actual-disagreement stop rule remains binding regardless of a tiny margin.

## 5. Twelve-significant-digit serialization

“float12” must specify **12 significant decimal digits**, not 12 digits after the decimal point; decimal round-to-nearest mode; literal syntax; correctly rounded binary64 parsing; and treatment of zero, subnormals, infinity, and NaN. Define the exact formatting route/version in the freeze record.

For a finite nonzero x, `e=floor(log10(abs(x)))` and decimal spacing `h=10^(e-11)`, round-to-nearest 12-significant-digit formatting to an exact decimal z satisfies

```
abs(z-x) <= h/2 <= 5e-12*abs(x).
```

For correctly rounded binary64 parsing and normal-range values,

```
B_ser(x) = h/2 + u*(abs(x)+h/2)
         <= [5e-12 + u*(1+5e-12)]*abs(x).
```

The bound covers carry into the next decimal decade. Zero is exact. A safe bound including subnormal parse rounding is obtained by adding `2^-1075` to the absolute expression; evaluate that constant at high precision, not binary64. Exclude overflow or define it as an unavailable/nonfinite state. Compute the decade robustly from exact decimal/rational magnitude, rather than a float log10 that may misclassify a power-of-ten boundary.

If fixture inputs are formatted, parsed **once**, and those identical binary64 values define every implementation/reference input, there is no input-serialization difference between them. The reference must use exact binary64 conversion of those saved parsed values. Comparing against the pre-serialization generated model is a separate experiment requiring input-sensitivity propagation.

Archived output comparisons require the appropriate `B_ser` for each serialized field. Comparing two serialized final r fields adds `B_ser(r_A)+B_ser(r_B)` to their forward envelopes; comparing serialized slopes first requires propagation through the quotient. Do not attach a slope serialization allowance directly to a dimensionless diagnostic. A 12-significant-digit output can lose about 5e-12 relative information, far above binary64 unit roundoff; it can change a threshold side near the boundary. Semantic decisions must be made from unrounded computations and preserved as such, or explicitly carry serialization uncertainty.

## 6. High-precision convergence must precede binary64 conversion

The proposed 80/120 check is useful only when every compared result remains Decimal. Independently execute both precisions from the same exact binary64 inputs, using separate local contexts. Compare all coefficients, covariance entries, predictions, SEs, diagnostics, signed margins, validity tests, and C5 bound quantities **before any float conversion, JSON rounding, or printed truncation**. Conversion to binary64 first can hide disagreement and cannot substantiate 1e-60 stability.

For each scalar/vector field f, freeze an explicit positive, dimensionally consistent scale `s_f` and require

```
max_i abs(f_80,i-f_120,i)/s_f <= 1e-60.
```

Use a prescribed absolute rule for any field whose natural input scale is zero. The present phrase “input-scaled norm” leaves these scales undefined, particularly for covariance, dimensionless quantities, zero response, and bound spectral-radius margins. Require exact agreement of finite/availability statuses and item/verdict sides computed at each precision. Preserve decimal strings for audit.

Agreement at two precisions is an empirical convergence check, not a rigorous error certificate: both calculations can share an implementation or arithmetic error. A reference margin within its unresolved precision uncertainty must remain indeterminate. If the work requires rigorous sign certification, use validated interval arithmetic or a separately justified Decimal error bound; do not call the two-precision difference a proved error bound. No reference use after the specified failed precision check is sound. The predeclared no-escalation rule should remain unchanged after evaluation.

## 7. Unseen-seed freeze and validation protocol

The proposed seed formula distinguishes scenario/count combinations in the listed range; changing ladder count to 7 distinguishes the conditioning-only set from the count6/count8 set. However, the claim that these seeds are disjoint from Stage1 needs an explicit historical seed inventory comparison performed before fixture generation. This review did not inspect that inventory.

Freeze a manifest containing the rules, all concrete seed values, scenario-definition/source hashes, ladder arrays or exact construction route, all parameters, PCG64 and normal-transform/library versions, draw order, serialization route, missing-value/zero conventions, and thresholds. “Unchanged Stage1 scenario definitions” and “same k at5mm” need exact definitions/hashes; k is ambiguous because the rule also uses k(n) for an operation count. A source hash of each unchanged implementation should be recorded before execution. Hashing only prose and seeds does not freeze the fixture generator or evaluator.

Generate all saved fixtures only after this manifest is finalized, then parse the saved values once. Supply those values to all paths. Process the full unseen suite under the frozen rule before any historical future-rule classification can influence design. Exact-zero edge tests must have a stated number/ladder/expected mathematical status, and remain separately reported. The rule must prescribe how unavailable C5 envelopes and convergence failures affect the validation summary; they cannot count as explained successes.

New random seeds protect against direct fitting to those realized draws. These fixtures still share preselected scenarios, distributions, finite ladder sizes, and software paths; they are not independent physical validation, unseen-model generalization, or a proof of a universal error bound. No solver execution or R5 data is needed to test this numerical contract.

## Final recommendation to the parent

Revise the mathematical specification before any freeze: complete and dimension the gamma32 perturbation assumptions; retain perturbed-operand/cross terms; include weight and row-construction arithmetic; state every predictive/threshold formula; fix 12-significant-digit serialization and separate common-input from output rounding; define Decimal convergence scales and compare before conversion; freeze the full generator/evaluator manifest and failure taxonomy.

After those revisions, C5 plus certified semantic margins is a reasonable candidate **conditional validation rule**. N1 is the justified current arithmetic recommendation; N3 remains an experiment pending a ladder contract. This review cannot declare a numerical PASS, explained historical root cause, stop(a/b/c) event, or production qualification. No fixtures or solver were run, and no historical result was relabeled.

## Addendum: review of revised pre-execution specification

I read only the revised specification at `/Users/sota/.codex/worktrees/issue46-fd08v2-stage1p5-contract/CFD2026_09/docs/evidence/fd08_v2_stage1p5_2026_10_06/numeric_contract.md`, in addition to the two originally authorized specification files. No code, results, or fixtures were inspected or evaluated.

**Disposition:** The revised DA/Db, pilot, variance/weight arithmetic, WLS row scaling, cancellation quotient, predictive variance, square-root and serialization formulas address the substantive omissions identified above. They are mathematically coherent as conservative **conditional** envelopes under their stated componentwise backward-error assumptions and normal-range arithmetic. The covariance column assumption is now explicit: each column may solve a differently perturbed matrix with exactly represented basis RHS; the nonnegative common envelope still bounds each column. It does not require one common perturbed inverse and does not certify the actual backend. The negative/unavailable/rank-loss classification and explicit numerical-ambiguity status substantially improve the contract.

The actual revised magnitude gate is `count(abs(S_i)>=k_mag*sigma0)>=4`. This supersedes the illustrative `abs(g)-k*SE` margin in my original review. With exact shared binary64 S, k and sigma0 as mathematical inputs, the revised point-margin bound correctly covers a rounded threshold multiplication and margin subtraction. It should not inherit slope/SE fitting error. The stated >= tie rule is explicit.

Four short clarifications remain appropriate before freeze:

1. **“Negative covariance” must mean a negative variance/diagonal entry or violation of positive-semidefiniteness, not a negative off-diagonal entry.** Inverse Gram matrices for positively correlated design columns commonly have a valid negative C12. A negative covariance off-diagonal must not trigger invalid status. Negative computed square-root arguments remain invalid. Define whether the PSD diagnostic itself is exact-reference or computed and how an uncertain PSD result is classified.
2. **Native coefficient convergence scales need the same coordinate transformation as the coefficients.** If `X_native=X_mm D`, use `scale_beta_native,j=scale_beta_mm,j/abs(D_jj)`; use canonical mm scales after transforming outputs back. N3's normalized beta has units of force, not N/mm, so `||S||/||X_mm[:,j]||` cannot directly scale it. The same applies to native coefficient-error bounds if those are tested against field-specific scales. The covariance scale `sqrt(Cii*Cjj)` already has native covariance units. Make the zero-response fallback explicit, for example `sigma0/||X_mm[:,j]||` before the coordinate mapping, rather than an unconverted sigma0. Separate binding of the relative-SE quotient must be explicit: `d=abs(g)`, `D=d-Eg` in its formula.
3. **Magnitude count uncertainty needs an aggregation policy.** One useful policy is `Lcount=count(m_i-B_i>0)`, `Ucount=count(m_i+B_i>=0)`. Under the specification's strict-margin certification convention, `Lcount>=4` certifies passing the >=4 count, `Ucount<4` certifies failing, and the remaining case is ambiguous. Individual point margins may be ambiguous while the count remains certified. A stricter rule requiring every point to be certified is also conservative, but should be named explicitly; do not silently switch policies after results. Actual item/verdict disagreement remains stop(c) under either policy.
4. **State parameter preconditions:** finite positive sigma0, nonnegative tolerance/k_mag parameters used as bounds, and finite rho. This makes the nonnegative BT/magnitude envelopes and exact-zero fixture reference well defined. Missing/invalid parameters must produce a declared invalid/unavailable state, rather than an apparently successful comparison.

Serialization now separates common saved input values from output rounding. The 12-significant-digit bound, subnormal parse term, and saved-value-only inflation factor are mathematically sound under correctly rounded formatting/parsing. Two successive parsing/JSON-roundtrip operations are harmless only if the frozen JSON route round-trips the first parsed binary64 number exactly. Preserve that route in the freeze manifest. Compute the decimal decade from exact magnitude (e.g. an exact Decimal exponent) rather than a rounded logarithm at a boundary.

Decimal80/120 checks now precede float conversion and include validity/semantic/bound quantities. This resolves the major convergence-order issue. The stated stability test remains empirical rather than a validated reference interval, as the revised text correctly says. Convergence scales for signed margins and native coefficient/bound fields should be concretely bound to the corresponding units, as above. Identical computed threshold sides at two precisions do not prove a side for an unresolved near-zero margin; the explicitly ambiguous status must remain applicable.

The revised specification continues to leave the complete generator/runtime/source/seed-disjointness manifest to the freeze artifact. That manifest is still required before evaluation; this review has not inspected or confirmed it. Finite fixture success cannot establish the LAPACK assumptions universally, independent physical/noise validation, or production qualification. No actual stop-condition event is asserted by this addendum.
