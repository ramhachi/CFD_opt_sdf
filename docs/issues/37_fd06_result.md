# FD-06 (#37) result: v17 / flow_24 / normal_floor = 0.25, round 1

**Verdict: fail-closed under the registered contract (T10/T11), with a large improvement over FD-05.** The single
registered Kaggle kernel completed all 33 fresh primal runs. 2 of 6 direction/response combinations passed the
unchanged 5% plateau gate; the other 4 missed it by 1.4–3.7 percentage points (5.2–8.7% deviation). No threshold,
epsilon or criterion was changed and no retry was run. Strict host verification failed closed on the missing `DONE`
marker (the runner raises, and so writes no `DONE`, whenever any gate is false — as in FD-05).

## What changed relative to FD-05

Only the body normal: `n = g / max(|g|, 0.25)` instead of `g / |g|` (`NormalFloorWaterLilyBody`, a new file;
`WaterLilyBody.jl` is untouched). 0.25 is the repository's registered flat-gradient threshold, fixed before any force
response under a floor was run. Canonical state (v17), flow_24, directions, the 30 perturbation identities, the ε
ladder, run order, windows and all gates/thresholds are FD-05's verbatim; the registrar asserts this mechanically.
Also fixed: the runner's `outcome.json` now carries the canonical criteria hash the host verifier compares (the FD-05
T12 mismatch); T12 passed here. Design basis: [`37_fd06_normal_floor_probe.md`](37_fd06_normal_floor_probe.md).

## Registered run identity

- Criteria: round 1, file SHA-256 `a058280b9c70e78fa2d4345f4ea9e93e8c625f76c689b2bc7e7ebfc3d7922c2d`
  (canonical `797350ea82bc…`), source commit `dd26cabd48c44d38ffd35abb02ef600606377468`.
- Dataset `ramhachi888/cfd-opt-sdf-v17-nfloor-directional-fd-oracle` v1: 38 remote files, exact path set, SHA-256 and
  size (inventory SHA-256 `79df30392707ff273727a680ca2d7b8032e96b063365e702496bdc36778832b2`).
- Kernel `ramhachi888/cfd-opt-sdf-v17-nfloor-fd-oracle` v1, submitted once, `KernelWorkerStatus.ERROR` after all solver
  calls (aggregate wall about 3.6e3 s). Local Julia CPU prestep reached immediately before the first `sim_step!` for all 33 runs.

## N-based results

Baseline A/B/C are bit-identical: drag `0.32326693 N`, downforce `0.33098380 N` (noise span 0, floor 1e-8 N).
The floor moved the baseline by −0.00305 N drag (−0.93%) and −0.00005 N downforce relative to the W4/FD-05 value
(0.32631744 / 0.33102903 N); this is the expected primal change, not a gate.

Pair signal `R(+ε) − R(−ε)` in N for ε = 0.5, 1, 2.5, 5, 10 mm (all resolved, signs stable):

| Direction | Response | Pair signals (N) | Reference slope (N/m) | Max plateau deviation | Gate |
| --- | --- | --- | ---: | ---: | --- |
| D0 | drag | −0.000111, −0.000213, −0.000601, −0.001373, −0.002739 | −0.111 | 8.14% | FAIL |
| D1 | drag | −0.000060, −0.000126, −0.000336, −0.000676, −0.001284 | −0.063 | 6.40% | FAIL |
| D2 | drag | −0.000173, −0.000341, −0.000850, −0.001709, −0.003370 | −0.170 | 1.40% | PASS |
| D0 | downforce | +0.000777, +0.001567, +0.003782, +0.007376, +0.012391 | +0.777 | 2.64% | PASS |
| D1 | downforce | −0.000099, −0.000211, −0.000556, −0.001008, −0.001798 | −0.106 | 6.46% | FAIL |
| D2 | downforce | −0.000104, −0.000189, −0.000479, −0.000976, −0.001882 | −0.096 | 8.72% | FAIL |

FD-05 (same contract, raw normal) had 83–150% deviations (D0 drag 114%, D1 drag 97%, D2 drag 150%, D0 downforce 12.5%,
D1 downforce 84%, D2 downforce 139%). The pair signals now scale with ε instead of staying flat, and the centered slopes agree within
a few percent across ε = 0.5–2.5 mm.

## Evidence

- Strict host verification at the registered commit (worktree at `dd26cab`): failed closed with
  `FD Kaggle output has no DONE marker`; append-only record
  [`…normalfloor_kernel1_diagnostic_2026_09.json`](../evidence/sdf_directional_fd_v17_flow24_normalfloor_kernel1_diagnostic_2026_09.json)
  (SHA-256 `1ad408b6c5b76b1945228b6c029d775940d6f218a1ef99d7981250b08d5ed9f0`).
- Diagnostic-only independent recomputation from the raw CSVs
  ([`scripts/recompute_fd_directional_from_raw.py`](../../scripts/recompute_fd_directional_from_raw.py)): matches the runner's
  `outcome.json` (plateau verdicts, deviations, reference slopes); 0 output-manifest hash mismatches; all 33 summaries carry
  `normal_floor = 0.25`. Record
  [`…normalfloor_kernel1_host_recomputed_metrics_2026_10.json`](../evidence/sdf_directional_fd_v17_flow24_normalfloor_kernel1_host_recomputed_metrics_2026_10.json)
  (SHA-256 `f2ea1da62c38d3bc60a4c68eb4a55b0f3270e968cec00e2bc1b68b2a64ec671b`). It does not replace strict verification.
- Dataset verification and CPU prestep evidence are alongside the criteria in `docs/evidence/`.

## What this supports and does not support

**Supported (evidence-scoped)**
- The eps-independent +/− offset of FD-05 is gone with the floor: pair signals are ε-proportional, and plateau deviations
  fell from 83–150% to 1.4–8.7% on the same directions, perturbations and ε.
- Two combinations (D2 drag, D0 downforce) meet the registered 5% gate.

**Not supported**
- The FD oracle is **not** qualified (4 of 6 combinations miss the registered gate); no gradient, reverse-mode, optimizer,
  topology or shape-update qualification. All flags remain false.
- Why the remaining deviations are 5–9%. Candidates, none verified: the floor changes the normal only where |g| < 0.25 but
  the remaining derivative drift with ε (e.g. D0 drag slope −0.111, −0.106, −0.120, −0.137 N/m for ε = 0.5…5 mm) could be a
  genuine even nonlinearity, another kink in the BDIM/force path, or a floor too small to cover all sensitive samples.
- Physical force accuracy or grid convergence.

## Follow-ups (need a decision; nothing registered)

- Do **not** retry FD-06 or edit its criteria; any change (for example a different floor, a smoother normal, or re-examining
  the plateau ε selection) is a new contract round with its own preregistration, chosen before its responses are seen.
- Solver-free diagnostics first: compare the remaining derivative drift with the normal-census sample sets per ε.
