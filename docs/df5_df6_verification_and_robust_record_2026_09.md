# DF5/DF6 record — verification algebra and robust three-field support (2026-09-21)

Status: DF5 implementable part and DF6 pre-work delivered. DF5's own acceptance
(three qualified grids per required pair) and DF6's promotion remain gated on
the registered OpenFOAM campaigns, exactly as the architecture plan requires.

## DF5 — independent required-pair verification

`src/cfd_sdf/independent_verification.py` + CLI `cfd-sdf verify-required-pairs`:

- combined uncertainty is `sqrt(numerical^2 + extraction^2)` (rule id recorded);
  the pair uses the larger candidate-specific value;
- a missing mesh/residual/stationarity gate yields `gate_failed` and suppresses
  the conclusion while keeping every candidate row explicit;
- a candidate with `extraction_status: not_measured` (or not measured yet)
  yields `unresolved_extraction_not_measured`; an unmeasured sensitivity is
  never treated as zero;
- reference measurements declaring `used_in_optimization: true` are rejected
  (Stage V independence);
- improvements smaller than the combined uncertainty are `unresolved`, wrong
  directions beyond it are `regressed`.

Current standing evidence (recorded, not re-judged):

- the registered fixed-domain anchor still misses the downforce grid bound
  (finest drift 0.01291 against the registered 0.005; wake-refinement family
  0.0147), so no required pair can currently reach `improved` on numerical
  grounds alone;
- extraction sensitivity of optimizer-generated candidates is `not_measured`
  (DF0/P18 record), which by the rule above forces `unresolved` regardless of
  the measured improvement.

## DF6 — robust three-field support (pre-work, not promoted)

`src/cfd_sdf/robust_fields.py`:

- one filter/interpolation owner: the three fields share the parent
  `DesignTransform` filter and RAMP stack and differ only in the projection
  threshold (`eta_dilated < eta_intermediate < eta_eroded`);
- the volume constraint definition uses the **dilated** field (Trillet,
  Duysinx & Fernández 2021, arXiv:2101.08605);
- worst-case objective selection by sense; exact chain gradient per field
  (FD-verified in tests);
- `same_topology` performs the a posteriori consistency check (inclusions and
  component counts) and states the caveat that it is a necessary condition,
  not a proof;
- `parameter_report` records the declared parameters, the analytic-relation
  literature, and the three-fold primal/adjoint cost.

DF6 promotion still requires DF5 to pass, and the robust backend must be
compared against the current one under the same KKT/feasibility definition.
