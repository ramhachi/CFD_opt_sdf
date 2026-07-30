# Localized G2 finite-difference qualification contract

Date: 2026-07-30

## Decision

The localized G2 finite-difference (FD) independent variable is the canonical
x-fastest `float64` `rho_raw` vector on the local design grid.  It is never a
coarse OpenFOAM `alpha` vector and it is never a reconstructed density field.
The declared chain is exact:

```text
rho_raw -> active-normalised cone filter -> tanh Heaviside projection -> E -> alpha
```

The input direction is finite, nonzero, active-only, exactly zero on fixed,
root, and forbidden masks, and has `max(abs(d)) == 1`.  Perturbations are made
without clipping.  The default experiment is one-sided (`+h`); central FD may
be selected only if every `+/-` member of the fixed ladder is raw-feasible.
The ladder is always predeclared as `h, h/2, h/4`.

Preparation accepts only:

- a verified, published localized schema-v2 reference bundle;
- a `success` topology report bound to that exact bundle, project, state, and
  projected-density hash;
- a verified alpha-reference binding bound to that reference state and the
  actual parsed CFD grid; and
- a compiled OpenFOAM template staged through the strict localized alpha
  stager.

For every prepared perturbation the discrete predicate
`rho_projected >= 0.5` must be byte-identical to the reference predicate.
Any changed predicate, infeasible raw step, mismatched provenance, or partial
case-staging failure rejects preparation and publishes no output directory.
The resulting directory is atomically published and says only `not_run`; it is
not an OpenFOAM execution, an FD result, or native-v2 qualification.

## Prepare/run boundary

`prepare-localized-g2-openfoam-fd-direction` is the immutable-input boundary.
It neither launches OpenFOAM nor contains solver output.  The separate
`run-localized-g2-openfoam-fd-direction` command accepts only that prepared
directory, verifies every staged alpha-case manifest and its recorded hashes,
then copies each case into a new atomically published run-evidence directory.
It refuses an existing output path and never mutates the prepared directory.

The run phase explicitly requires `--execute`.  It runs at least two fresh
reference primals, then one fresh named adjoint copied from the first exact
reference-alpha baseline, then the prepared `+h,+h/2,+h/4` ladder (and the
negative ladder only for an already prepared central experiment).  It records
commands, runner identity, case input/output tree hashes, convergence/final
time/response provenance, and failures.  A run report is still not a
validation: it leaves `validation_status: not_run`, selects no FD step, and
makes no numerical acceptance claim.

## Immutable numerical protocol for the later run/validate phases

At least `n0 >= 2` independently executed baseline cases are required.  Let
`Jbar0` be their mean and `sJ` their sample standard deviation.  For ladder
responses `Jk`, define:

```text
Jscale  = max(rms(J0), max_k |Jk - Jbar0|)
sigmaJ  = max(sJ, 1e-12 * Jscale)
sigmaD,k = sigmaJ * sqrt(1 + 1/n0) / hk
SNRk = |Jk - Jbar0| / (sigmaJ * sqrt(1 + 1/n0)) >= 10
```

For adjacent steps `hc=2hk`, the stability metric is:

```text
sigmaDelta = sigmaJ * sqrt(1/hk^2 + 1/hc^2 + (1/hc - 1/hk)^2/n0)
Mstab = |Dk - Dc| / (0.05 * max(|Dk|, |Dc|) + 2 * sigmaDelta) <= 1
```

Select the smallest of `h/2` and `h/4` satisfying its own and its
coarse-neighbour SNR/stability gates.  If none does, report
`fd_ladder_unqualified`.  The final comparison additionally requires both
derivatives to have magnitude at least `5*sigmaD`, equal nonzero signs,
relative error at most `0.10`, and absolute error at most `5*sigmaD`.

## Rationale and evidence

`sol_localized_fd_contract` selected the raw-density chain, no-clipping
feasibility, immutable input bindings, and discrete-topology stability rule.
`sol_localized_fd_noise_thresholds` selected the baseline-repeat, noise,
SNR, stability, and final comparison formulas above.  The implementation
records these formulas in each preparation report; execute/validate remain
separate work so no prepared artifact can be mistaken for numerical evidence.

## Limitations

Predicate stability checks only the declared discrete voxel topology at 0.5.
It does not prove continuous manufacturability, solver convergence, response
provenance, adjoint correctness, or native-v2 readiness.
