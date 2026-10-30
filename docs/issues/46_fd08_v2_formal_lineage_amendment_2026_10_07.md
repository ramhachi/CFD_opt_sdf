# FD-08 v2 Formal Preregistration Lineage Amendment

This is a user-authorized post-R6 preregistration infrastructure amendment,
made before any formal criteria registration or formal observation. It does
not alter the RCFG-1 scientific contract or qualify FD-08 by itself.

## Original frozen design and failures

The pre-R6 registrar is `scripts/register_fd08_v2_formal.py`, SHA-256
`7882195db39b01a3178c9ef1b8bc8c014ba1a579c81c768cf8fdb7df22b5c92c`.
R6 criteria bound this SHA before measurement. At `read_r6_parent`, line 101
initialized `raw_states = {}` and line 106 called `raw_states.add(raw)`.
The exception was exactly `AttributeError: 'dict' object has no attribute 'add'`.
The intended collection is a set of 49 distinct calibration phi byte arrays;
the correction is solely `raw_states = set()` at that location.

The failure evidence is
`docs/evidence/fd08_v2_formal_2026_10_06/formal_retry2_registration_failure.json`,
SHA-256 `5aee6ab0bfc57afc45bdefa7f1ab7a1255989d71d7aa1703a136642bd8ce8d05`.
It records no formal criteria, preflight, dataset staging/upload, solver run,
force observation, or verdict. The failed attempt remains unchanged.

The subsequent solver-free investigation found that the original registrar
copies R6's source commit into the top-level formal `source_commit` while
hashing the current source files. After changing the registrar, the runner
would checkout the old R6 commit and reject the new registrar hash. The
original formal dataset also reused the R6 dataset ID. The prior investigation
stopped without edits or commits when these exceeded its one-line mandate.

## Approved implementation scope

The present user instruction authorizes the dict/set correction, execution
source binding, preserved calibration binding, amendment provenance, distinct
formal criteria/round/dataset identities, minimal packaging, and solver-free
tests/dry-run hooks. No R6 registrar, runner, analyzer, criteria, dataset, raw
result, terminal verification, or verdict is changed. The existing shared
runner is reused byte-for-byte; only a new formal kernel metadata template is
added (K2, a dedicated private kernel slug).

The formal top-level `source_commit` is explicitly supplied at registration
and must identify the clean pushed integration HEAD. Every `source_inputs`
file is checked against that commit's Git tree before registration. The
runner checks out this amended execution commit and repeats the file-SHA
checks. R6's commit remains solely in `calibration_binding.source_commit`.
Neither source files nor this document embed their eventual merge commit;
criteria are created after the merge, so there is no circular identity.

New identities are:

- criteria: `FD08-V2-FORMAL-AMEND1-2026-10-07`;
- round/evidence: `fd08_v2_formal_2026_10_07_amend1`;
- private dataset: `ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend1`;
- private kernel: `ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend1`.

The kernel staging directory contains byte-identical copies of the registered
shared runner and the new formal metadata template. The R6 dataset is never
updated. Registration checks both criteria/preflight and their sidecars before
writing, constructs the entire payload before writing, and refuses overwrite.
Dry-run performs the same construction without writing those artifacts.

## Immutable R6 parent

| Identity | Value |
| --- | --- |
| source | `f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9` |
| criteria SHA-256 | `90e9e40ffebffc96891af12bdc7942a0a038d877fe6e7bffe7a88574679e1837` |
| result SHA-256 | `b5d55b77f750f447fd486a600f9e52a66a3f6c2610c5dba5ce6792018cc647be` |
| terminal verification SHA-256 | `dd0b1c9bd3643adc0d36fcb70d38ac19d4f223d880b840f03a30b8106422f06f` |
| disposition | R6 PASS, 8/8 series, one analyzer run |

The frozen full-six-point Model A coefficients and nominal covariances are
copied from this result without refitting or reanalysis. All 49 parent phi
byte arrays are validated before testing the new formal arrays for collisions.

## Unchanged scientific contract

D0/D1/D2/P1, L6, J1, COV-A, N1, C4/C5, T2, and RCFG-1 remain fixed.
Intervals are exactly `{0,2,4}` and epsilon is `sqrt(e_i*e_(i+1))`, giving
`0.6294627058970836`, `1.5811388300841898`, `3.971641173621408` mm.
Inventory is baseline 1 plus four directions times three epsilon times two
signs: exactly 25 states and 24 comparisons over drag/downforce. Model A only,
no formal refit, no model switch, no jitter or direction exclusion.

For `x=(epsilon_mm,epsilon_mm^3)`, `S_pred=x.T beta` and
`sigma_pred^2=sigma0_n^2+(rho*S_pred)^2+x.T C x`. Observation is the host
raw-history reconstruction `(R_plus-R_minus)/2` in N. Finite/integrity,
nonzero same sign, both magnitudes at least `5*sigma0_n`, and absolute error
at most `max(3*sigma_pred,tol_hold*abs(S_pred))` are unchanged. T2 remains
sigma0=3e-6 N, rho=.05, tol_hold=.15, k_mag=5, with all other T2 parameters
unchanged and arbitrary-provisional. All 24 PASS is formal PASS; any FAIL is
formal FAIL; otherwise any UNRESOLVED is formal UNRESOLVED. Solver/kernel
caps remain 3300/5600 s, planning caps rather than runtime guarantees.

The pre-amendment canonical scientific representation is captured from the
original registrar and unchanged campaign/parameter sources. Equivalence,
actual canonical geometry/Float32 inventory, fresh-checkout runner verification,
and two independent reviews must pass before immutable registration. Full
pytest must introduce zero failures relative to the pinned 37-ID baseline.

## Interpretation and stop policy

Formal runs under a **post-R6 Formal Preregistration Lineage Amendment**;
the amended source is not bit-identical to the original pre-R6 registrar.
Lineage and original/failure/amended/document/review hashes are bound explicitly
in criteria. Formal FAIL/UNRESOLVED is terminal and is never scientifically
retried. Infrastructure attempts retain their own identities and artifacts.

Even PASS qualifies only diagnostic directional response/interior interpolation
for frozen Candidate C / canonical v17 / flow_24 / these four directions and
registered points. It does not qualify arbitrary directions, full-field
gradients, exact epsilon-to-zero derivatives, physical truth, high-Re validity,
grid independence, OpenFOAM equivalence, reverse AD, optimizer, or topology.
R5 FAIL, historical Stage 1 strict mismatches (17), and Stage 1.5 evidence remain
unchanged. Six qualification flags remain false before formal PASS; subsequent
flag transition requires the authority check in the user instruction.
