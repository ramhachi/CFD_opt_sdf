# FD-08 v2 R6 pre-run parameter record

Recorded at `2026-10-06T12:52:56Z`, before any R6 T4 setup rehearsal or
calibration solver invocation.

- Frozen parameter file: `src/cfd_sdf/fd08_v2_gate_params.json`
- SHA-256: `c5f3fe1a3875c44d5fd0b87d48fd0bd0c06bdf22fb74581cb399e382dbac95ba`
- Classification: arbitrary-provisional diagnostic operating contract only.
- No parameter, tolerance, scenario, model, direction, or ladder value is
  changed by this record.
- The initial geometry-only preflight, created before this record, is retained
  as `preflight_initial_unbound.json` (SHA-256
  `e37cbf2511077cd947f8bc2c8a10c013ebdecd47d0bd13adb5d65d4268a24fba`). The
  updated preflight binds the parameter hash above.
- Earlier solver-free implementation and synthetic numerical checks are not
  R6 solver measurements. This record freezes the exact parameter bytes before
  the bounded T4 setup rehearsal and every R6 scientific run.

The rehearsal is an infrastructure check only. It may run one baseline step
and one signed P1 step; its forces are not retained or used for analysis.

The Kaggle CLI capability snapshot for this rehearsal is
`setup_budget_preflight.json` (SHA-256
`923c02249865a8d856c73b847f53591f3a51ce85e27f4becb2f4bcea5f1bde3d`): CLI
2.2.4, T4 timeout option available, 7,200-second requested allowance,
43,200-second documented CPU/GPU session maximum, and 22.55 hours of GPU quota
remaining. R6 and formal registrations require their own fresh quota snapshots.
