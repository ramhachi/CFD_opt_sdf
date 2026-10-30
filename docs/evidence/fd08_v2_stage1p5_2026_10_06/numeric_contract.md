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
- pilot predictions: max(||S||inf,sigma0); weights: abs(reference weight).
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

### C5: operand and conditional fit-error propagation (corrected before execution)

This is a conditional engineering envelope, **not a certified LAPACK/SVD theorem**. IEEE754 binary64 normal-range operations, no overflow/underflow, full column rank, exact input binary64 parameters, and the following componentwise backward-error assumptions are required. Finite fixture checks test these assumptions only on the frozen suite.

For every subset/model/native basis, calculate exact-reference X,y,A=X^T X,b=X^T y,C=A^-1,beta=C*b in Decimal. Let k(n)=8n+32, gk=gamma(k(n)), g32=gamma(32), p=2. Initial assumed solve/construction envelopes have every entry DX_ij=gk*||X||2, Dy_i=gk*||y||2; their elementwise form conservatively covers the stated normwise perturbation assumption.

Let U=abs(X)+DX and v=abs(y)+Dy; all bound matrix products are ordinary nonnegative products:

```
DAform=abs(X)^T DX+DX^T abs(X)+DX^T DX+gamma(n)*U^T U
Dbform=abs(X)^T Dy+DX^T abs(y)+DX^T Dy+gamma(n)*U^T v
DA=DAform+g32*(abs(A)+DAform)
Db=Dbform+g32*(abs(b)+Dbform)
E=abs(C)*DA
Bbeta=(I-E)^-1 abs(C)*(Db+DA*abs(beta))
BC=(I-E)^-1 abs(C)*DA*abs(C)
```

Require spectral_radius(E)<1. The coefficient assumption is that its computed value solves a system with the DA/Db perturbations above. The separate covariance assumption bounds each inverse column by DA with exact basis RHS; it does not assume a single common perturbation for all columns. A backend is not automatically guaranteed to satisfy either assumption. Explicit inverse arithmetic is covered by the separately assumed column bound, and a coefficient path using an explicit inverse would additionally require its matrix-vector product allowance. The binary64 variants use lstsq rather than such an inverse-product coefficient path. Unavailable radius, negative diagonal variance or failure of PSD (negative off-diagonal covariance is valid), rank loss, nonfinite arithmetic, or weight/denominator gaps are recorded explicitly; an infinite bound never passes.

OLS pilot:

```
Bpilot=abs(X)*Bbeta+DX*abs(beta)+DX*Bbeta
       +gamma(p)*(abs(X)+DX)*(abs(beta)+Bbeta)
q=sigma0^2+(rho*pilot)^2
Dqsens=rho^2*(2*abs(pilot)*Bpilot+Bpilot^2)
Dq=Dqsens+gamma(4)*(q+Dqsens)
ell=Dq/q
eta=(1+gamma(2))/sqrt(1-ell)-1
```

Require ell<1. gamma4 covers reused-product square/add variance arithmetic; gamma2 covers reciprocal-plus-sqrt. For exact s=sqrt(W), Xw=sX,yw=sy:

```
DXw_row=s*DX_row+eta*s*(abs(X_row)+DX_row)
        +u*s*(1+eta)*(abs(X_row)+DX_row)
Dyw_row=s*Dy_row+eta*s*(abs(y_row)+Dy_row)
        +u*s*(1+eta)*(abs(y_row)+Dy_row)
```

Then add the direct WLS solve envelope gk*||Xw||2 to every DXw entry and gk*||yw||2 to every Dyw entry. This intentionally conservative addition counts construction and solve separately. Reapply corrected DA/Db/Bbeta/BC formulas. Report native cond2(X),cond2(Xw), radius, maximum ell, beta/covariance envelopes and validity. Canonical mm coefficient/covariance reporting uses gamma(4) per computed mapping diagonal (unit division/power/multiplication), with both diagonals propagated for covariance; an additional gamma(2) conservatively covers legacy display multiply/divide reconstruction of reported mm slope/SE in comparisons. It propagates the diagonal conversion multiplication(s); N1's exact unit mapping requires no multiplication allowance. Display g/SE in N/m adds u times the converted perturbed magnitude. The frozen blind forms ratios from displayed slopes, so its ratio operand budgets include that extra display multiplication before subtraction; its fitting errors use the N1 basis.

For reference operands a,b with errors Ea,Eb, d=abs(b), t=abs(a-b), D=d-Eb>0:

```
Br=(Ea+Eb)/D+t*Eb/(d*D)
   +gamma(3)*(abs(a)+Ea+abs(b)+Eb)/D
B_SErelative=ESE/D+SE*Eg/(d*D)+u*(SE+ESE)/D
```

Br is used for each nested/model difference. It has the requested C*u*(abs(a)+abs(b))/abs(b) interpretation with C determined by conditional fit error/conditioning and the denominator gap, never fitted to the historical17. The maximum nested-shift error is the maximum constituent envelope. For v>=0 with absolute variance error Bv, define L=max(0,v-Bv),H=v+Bv:

```
Bsqrt=max(sqrt(H)-sqrt(v),sqrt(v)-sqrt(L))+u*sqrt(H)
```

Use this for SE and predictive sigma. Reject negative computed variance; if the mathematical variance interval includes zero, report its positivity as ambiguous.

For a freshly formed holdout row x, use Hx_j=gk*||x||2 as its fixed construction allowance, plus conversion if relevant, and the same corrected dot-product prediction bound Bmu. For vfit=x^T C x with Ux=abs(x):

```
Bvfit=Hx^T abs(C) Ux+Ux^T abs(C) Hx+Hx^T abs(C) Hx
      +(Ux+Hx)^T BC (Ux+Hx)
      +gamma(2*p+1)*(Ux+Hx)^T*(abs(C)+BC)*(Ux+Hx)
Dqpred=rho^2*(2*abs(mu)*Bmu+Bmu^2)
        +gamma(4)*(sigma0^2+(rho*mu)^2
                    +rho^2*(2*abs(mu)*Bmu+Bmu^2))
Bvpred=Bvfit+Dqpred+gamma(2)*(abs(vfit)+Bvfit+qpred+Dqpred)
Bh=Bmu+u*(abs(y)+abs(mu)+Bmu)
BT=max(3*Bsigma+u*3*(sigma+Bsigma),
       tol_hold*Bmu+u*tol_hold*(abs(mu)+Bmu))
```

The input observation y is an exact shared binary64 value, so By=0. Variance construction is fixed as sigma0^2+(rho*mu)^2+x^T C x; gamma(2p+1) conservatively covers the two matrix/vector products in the quadratic. Propagate absolute holdout error Bh and threshold BT separately.

Margins:

- m_se=tol_se-relativeSE, m_nested=tol_nested-maxShift, m_model=tol_model-modelDifference. Budget Bmetric+u*(abs(tol)+abs(metric)+Bmetric).
- m_hold=limit-abs(y-mu). Budget BT+Bh+u*(abs(limit)+BT+abs(error)+Bh).
- Sign margin for every full/nested slope is g; require abs(g)>Bg to certify a nonzero sign.
- Magnitude uses **the actual gate** count(abs(S_i)>=k_mag*sigma0)>=4. Point margin abs(S_i)-k_mag*sigma0 has budget u*abs(k_mag*sigma0)+u*(abs(S_i)+abs(k_mag*sigma0)*(1+u)). This is not g>=k*SE. Exact ties obey >= as in the specification.
- For magnitude aggregation Lcount=#{m_i-B_i>0}, Ucount=#{m_i+B_i>=0}. The >=4 aggregate is certified PASS if Lcount>=4, certified FAIL if Ucount<4, otherwise ambiguous; individual ambiguous points are reported even if the aggregate is certified.
- SE/nested/model/holdout pass uses <=; undefined ratios have null, zero slopes fail sign, missing items are three-valued unavailable, n<4 is UNRESOLVED, otherwise computable first-five failure precedes magnitude-only UNRESOLVED.

For a certified side the reference margin interval must lie strictly on one side of zero; a zero-intersecting interval is `numerically_ambiguous` even when calculated sides agree. Actual variant item-side/verdict disagreement triggers stop(c) regardless of ambiguity. C4 compares all sides, signs, finite/availability states, and signed margins. For pair comparisons add forward envelopes and margin envelopes, plus archived-output serialization allowances below.

C5 plus semantic agreement **and certified margins** is the recommended candidate future independent rule, conditional on the backward assumptions. C1/C2/C3 remain diagnostics. An unavailable envelope or ambiguous margin is reported separately and cannot authorize production. An unexplained unseen forward/semantic violation triggers stop(b), without tuning; an explicitly explained unavailable/ambiguity is not silently counted as PASS.

#### Serialization and convergence

`float12` is Python format(value,'.12g') (12 significant decimal digits, round to nearest), converted to a JSON number and parsed once by the frozen Python runtime into binary64. The exact saved/parsed binary64 inputs are the common mathematical inputs; generator-to-saved rounding is not an inter-implementation error. NaN/Infinity are forbidden (allow_nan=False), zero is exact, overflow/nonfinite is unavailable.

For finite nonzero x use e=floor(log10(abs(x))) determined with exact Decimal magnitude, h=10^(e-11). Archived output budget is Bser=h/2+u*(abs(x)+h/2)+2^-1075 computed in Decimal; this covers decimal rounding and binary64 parsing including subnormal absolute rounding. Inverse-decade uncertainty from already archived decimals is conservatively covered by the equivalent scale-free upper bound [5e-12+u*(1+5e-12)]*abs(x)+2^-1075, multiplied by 1/(1-5e-12-u*(1+5e-12)) if only the saved value is available. Add Bser of each **final compared field**, not slope-unit bounds to a dimensionless field. New live values are compared before output formatting.

Independently calculate reference and C5 bounds at80 and120 Decimal digits from identical binary64 values; compare raw Decimal leaves and validity/semantic states before float conversion. Per-field convergence scale: coefficient/g/SE use ||S||2/||X_mm[:,j]||2 (display conversion as applicable), covariance_ij use sqrt(Cii*Cjj), prediction/pilot/holdout/error/limit use max(||S||inf,sigma0), native coefficients/SE use the inverse native-to-mm diagonal times their canonical coefficient scale; weights use abs(reference weight), dimensionless diagnostics/radius/ell use1, native norm/condition/bound diagnostics use max(abs(reference value),1) in their own reported units; zero natural scales use sigma0 with the coefficient/column conversion where applicable. Require abs(f80-f120)<=1e-60*scale and exact availability/item/verdict/radius-validity agreement. Preserve maximum convergence errors as decimal strings. Two-precision agreement is empirical convergence, not validated interval arithmetic or a proved reference error bound. No automatic precision escalation follows a failed check.


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

Implementation audit: reference/compared canonical fields use the scales above. C5 bounds use abs(bound120) for positive envelopes (zero floors at1e-300 in their own units), and max(abs(value),1) for radius/ell diagnostics. This stricter relative bound convergence rule is fixed before evaluation. Coefficient input-scale computation uses the exact subset; covariance cross scales use sqrt(Cii*Cjj). Reference native fields are audited by focused unit-invariance tests; fixture reference comparison uses canonical common fields.
