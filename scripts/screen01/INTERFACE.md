# SCREEN-01 implementation interface (shared by the analyzer, the independent checker and the builder)

Authority: `docs/screen01_registration_2026_10_30.md` (rev. 1). Where this note and the registration disagree, the registration governs; report the disagreement.

## Files and owners
| File | Owner | May read |
| --- | --- | --- |
| `scripts/screen01/screen01_build.py`, `scripts/screen01/screen01_freeze.py`, `tests/screen01/test_screen01_build.py` | builder agent | everything in the repo |
| `scripts/screen01/analyze_screen01.py`, `tests/screen01/test_screen01_analyze.py`, `tests/screen01/synthetic.py` | analyzer agent | everything except `screen01_check.py` |
| `scripts/screen01/screen01_check.py`, `tests/screen01/test_screen01_check.py` | checker agent | the registration, this note, `screen01_pool.py` constants only; NOT `analyze_screen01.py`, NOT `screen01_pool.propose/fit9/d_optimal9/constrained_argmax` bodies |
`scripts/screen01/screen01_pool.py` and `screen01_oc.py` exist (P0 and OC); do not edit them unless a defect is found (then report, do not silently change). `propose` was corrected by the registrant on 2026-10-31 after the cross-check (registration §5.2 / §5.11.4-5; `docs/evidence/screen01_2026_10_30/crosscheck_reconciliation.md`) and `oc.json` regenerated.

Rule details the registration fixed after the cross-check are in registration §5.11; this note only fixes the shapes both implementations return.

## states.json (written by `screen01_build.py states`, read by the analyzer)
`{"schema": "screen01-states-v1", "parent": "v18__parent", "states": {name: {...}}}` with, per state:
- `role`: one of `parent`, `parent_repeat`, `axial`, `design`, `manual`, `ref`, `nc`, `random`, `proposal`
- `order`: int, the registered tie-break order within its role (axial: pitch+, pitch-, camber+, camber-, reflex+, reflex- i.e. mode order `pitch, camber, reflex`, + before -; design: freeze order from `design_check.json`; random: `rand3` sequence order; proposal: rank order from `rs.json`)
- `u`: `[u_pitch, u_camber, u_reflex]` normalised (`a_m = u_m A*_m`, A* = 3.1 deg, 19.7 mm, 29.3 mm) or `null` for parent / parent_repeat / nc; ref has its u
- `spec`: `{mode: amplitude}` as `fid01_designs` takes it (sorted keys), `null` for parent / nc
- `state_sha256`, `npz_sha256`, direction raw sha256 and step where applicable (as FID `states.json`)
The parent repeat is a distinct state name `v18__parent__repeat` with byte-identical state to the parent (role `parent_repeat`), so a kernel never carries two runs with the same (state, phase) key.

## Normalised force input `T` (built by the analyzer from harness-verified tables; the checker consumes exactly this)
```
T = {
  "schema": "screen01-T-v1",
  "stage": "rs" | "finalist" | "main",
  "roles": {state: {"role": str, "order": int, "u": [3 floats] | null}},   # from states.json (+ proposals from rs.json from stage finalist on)
  "runs": {                                   # every run the harness tables list for the stage's kernels; a lost kernel contributes nothing
     "g1":  {state: {phase(int as str): {"downforce": float|null, "drag": float|null, "ok": bool}}},
     "g2":  {...},                            # present from stage "finalist"
     "f32": {...}, "f48": {...}               # present at stage "main"
  },
  "lost_kernels": [kernel ids declared lost with --lost],
  "gating": [ {"name": str, "u": [3], "target_index": int, "y_pred": float, "z_pred": float, "admissible": bool} ... ]   # every stage: the rs.json gating record, in gated order (at stage rs the analyzer gates first, then cross-checks before writing rs.json); `target_index` is the 0-based index of the OWNING target (§5.2: the list that queued the point first); every name appears at most once
}
```
`null` = non-finite force; `ok = false` = harness verify failed / per-state cap exceeded / run not finished. Phases: g1 and g2 use 11, 12; f32 uses 13-16 and the replay 11; f48 uses 13, 14.
Both implementations apply §5.1 DATA_LOSS themselves, uniformly to every run of every role, the parent repeat included (§5.11.1: ok false, null, or `|F - F_parent,k| > 0.25 |F_parent,k|` for either response, against the parent's finite ok run of the same group and phase). Determinism and drift are judged on the raw runs, not on the DATA_LOSS-filtered ones (§5.11.10).

## Comparable output (both return this dict; the analyzer compares before writing)
`compare_keys(stage)` — strings/bools/None exact; floats `abs(a-b) <= 1e-9 * max(1, |a|, |b|)`; lists elementwise.
- stage `rs`: `data_loss` (sorted list of `state@stage@phase`), `fit.downforce.coef` (9 floats, column order `[u_p, u_c, u_r, u_p^2, u_c^2, u_r^2, u_p u_c, u_p u_r, u_c u_r]`; `null` on `RS_NOT_FIT`), `fit.drag.coef`, `fit.rank`, `fit.cond` (`null` when rank < 9), `fit.residual_sd.{downforce,drag}` (`null` when n <= 9 or not fit), `rs_fit_poor` (bool; `null` when the residual SD is undefined, §5.11.3), `rs_not_fit`, `u_star_1`, `y_star_1`, `pool_limited_pre`, `targets[tau].u_star`, `targets[tau].y_pred`, `targets[tau].z_pred` for the keys `"1"`, `"1.5"`, `"2"` (`f"{tau:g}"`; `compare` folds `1`, `1.0`, `"1.0"` onto the same key; reported for every target with a feasible grid point, also when `y_pred <= 0`); `gated` (list of `[target_index, u rounded to 6 decimals]` in the order the §5.2 rule gates them, regenerated independently from the fit: u*_tau first, Sobol cloud seeds `20261032 + 0-based target index`, filter, ordering, per-list name dedup and freeze-1 name exclusion, round-robin into one queue with cross-list name dedup, targets with `y_pred <= 0` contribute nothing, rounds of 4, the stopping rule over targets with a queued point, the 36 cap; the admissibility outcomes are taken from `T["gating"]`), `stop_after` (number of gated points), `proposals` (indices into `gated`, in proposal order).
- stage `finalist`: `data_loss`, `candidates` ({name: {"delta_bar": {downforce, drag}, "P": int, "se_eff": {downforce, drag}, "feasible": bool}} for every registered C_opt member; a member without a paired phase has `P: 0`, `null` estimates and `feasible: false`), `finalist` (name or None), `futility` (None | `NO_FEASIBLE_CANDIDATE` | `GAIN_BELOW_MIN_AT_SELECTION`), `search_complete`, `pool_limited`, `r_best` (name or None), `K_opt` (= 6 + 9 + number of proposals), `K_rand`, `proposals_from_gating` (the proposal names that the §5.2 selection rule yields from `gating`).
- stage `main`: everything of `finalist` plus the blocks below. A block is `null` when its data do not exist (§5.11.12, §5.11.16); inside a block a label that cannot be computed is `null`, never a default.
  - `outcome`: `SCREEN01_GAIN | SCREEN01_NO_GAIN | SCREEN01_INCONCLUSIVE | SCREEN01_INCOMPLETE | SCREEN01_INVALID`; `cause`: list of strings, `[]` for GAIN. Spellings and order: step 1 `DATA_G1`; step 2 `NC_G1`, `NONDETERMINISM_G1K11` (all that apply); step 3 INCOMPLETE `DATA_G1`, `DATA_REFINE`, `DATA_G2` (all that apply, stage order, §5.11.7), step 3 NO_GAIN `NO_FEASIBLE_CANDIDATE` | `GAIN_BELOW_MIN_AT_SELECTION`; step 4 `BUDGET` | `DATA_F` (one, §5.11.15); step 5 `NC_F`, `NONDETERMINISM_F32A`; step 6 `GAIN_BELOW_MIN`, `DRAG_VIOLATION`, `GRID_SIGN_SPLIT` (all that apply, that order); step 7 `G_UNRESOLVED`, `R3_UNRESOLVED` (all that apply).
  - `G`: `{"decision": "PASS"|"UNRESOLVED"|"FAIL", "GAIN_RESOLVED_ABOVE_MIN": bool}` or `null` (no finalist or |Φ_s| < 3).
  - `D`: `{"decision": "PASS"|"VIOLATION", "label": "PASS_RESOLVED"|"PASS_UNRESOLVED"|"VIOLATION_UNRESOLVED"|"VIOLATION_RESOLVED"}` or `null` (as G).
  - `R3`: `{"label": "R3_CONFIRMED"|"R3_SIGN_SPLIT"|"R3_UNRESOLVED", "R3_RATIO_IN_BAND": bool|null, "G48_ABOVE_MIN": bool, "G48_MARGIN": float (N), "R3_E2_EXCEEDED": bool|null, "R3_DRAG_SAME_SIGN": bool|null}` or `null` (no finalist or no paired flow_48 phase); the three paired labels are `null` when Φ_48 and the finalist's flow_32 phases within {13, 14} have no common phase (§5.11.11).
  - `NC`: `{"g1": {"z": float|null, "label": "CONSISTENT"|"NOT_CONSISTENT"|null}, "f32": {...}}` (`null` = no paired NC phase at that stage).
  - `determinism`: `{"g1k11": {"max_abs_diff": {"downforce": float, "drag": float}|null, "nondeterminism": bool, "judged": bool}, "f32a": {...}}`; the repeat absent or not ok → `judged: false`, `max_abs_diff: null`, `nondeterminism: false` (NOT_JUDGED); a non-finite repeat force against a finite ok parent run → `judged: true`, `max_abs_diff: null`, `nondeterminism: true` (§5.11.10).
  - `generation_drift`: `{"max_abs_diff": {"downforce": float, "drag": float}|null, "drift": bool}` (`null` and `false` when either phase-11 parent run is invalid).
  - `controls`: `{"OPT_VS_RANDOM": "OPT_BEATS_RANDOM"|"RANDOM_BEATS_OPT"|"OPT_RANDOM_UNRESOLVED"|"RANDOM_NO_FEASIBLE"|null, "OPT_VS_MANUAL": "OPT_BEATS_MANUAL"|"MANUAL_BEATS_OPT"|"OPT_MANUAL_UNRESOLVED"|"MANUAL_NONE"|null, "RANDOM_FEASIBLE_GAIN": bool, "K_MISMATCH": bool}`; the two comparison labels are `null` without a finalist (§5.11.13).
  - `selection_bias`: `{"b_K": {"central": float, "upper": float}, "g_XV_exp": {"central": float, "pessimistic": float}, "XV_MARGIN": {"central": "XV_MARGIN_ADEQUATE"|"XV_MARGIN_THIN", "pessimistic": ...}}` or `null` (as G).
  - `confirmation`: `{"f32": {"P": int, "delta_bar": {"downforce": float, "drag": float}, "sigma_d": {... float|null}, "se_eff": {...}}|null, "f48": {...}|null}` for the finalist (`null` = no paired phase on that grid).
The checker exposes `check(T: dict) -> dict` returning exactly these keys for `T["stage"]`, plus `compare(a: dict, b: dict, stage) -> list[str]` (list of discrepancy paths; empty = agree) — or the analyzer owns `compare`; the checker's `check` is the contract.

## Constants
Re-read from FID and M2 analysis files by SHA-256 (registration §6) in the analyzer; the checker may hard-code the §6 table values (independence of code, not of constants).

## rs.json fields used by the builder (`screen01_build.py campaign g2 --rs rs.json`; top-level keys, everything else is ignored)
- `proposals`: list in rank order (<= 4) of `{"name": str, "u": [u_pitch, u_camber, u_reflex]}`. The state is `spec = dict(sorted(screen01_pool.u_to_spec(u).items()))` (amplitudes rounded to 1e-3) and `name` **must equal `fid01_designs.name(spec)` with the keys in sorted order** (registration §3.2: `v18__camber_..._pitch_..._reflex_...`); the builder refuses otherwise. `screen01_pool.u_to_spec` returns sorted keys, so the names `propose()` gives its gated points and proposals are the registered names; the analyzer writes them unchanged and excludes the freeze-1 states by these names.
- `gating`: the gating record, list of `{"name": str, "admissible": bool, "phi_fortran_sha256": str, ...}` (further keys, e.g. `u`, `target_index`, `y_pred`, `z_pred` or the gate row, are carried into freeze 2.1 as the proposal's `gating_row`). Every proposal name must appear with `admissible: true` and `phi_fortran_sha256` = the gate row's `phi_fortran_sha256` (the gated harness bytes); the builder refuses unless the built state reproduces that SHA and the runner regeneration reproduces it again.
- No proposal (`proposals == []`) means no g2 kernel: `campaign g2` writes nothing.
- Outputs: `states_g2.json` (schema as `states.json`, role `proposal`, `order` = rank index, `u = spec_to_u(spec)`, `rs_json_sha256`), the proposals' direction raws in `inputs/`, and `docs/harness/screen01_g2_campaign.json` (campaign `screen01_g2`, kernel `g2`: a separate campaign, because the harness binds the campaign file's SHA-256 into the frozen `screen01` runs and `verify`).

## finalist.json fields used by the builder (`screen01_build.py campaign f --finalist finalist.json`; top-level keys)
- `finalist`: state name (a G1 axial / design state or a proposal; `null` = no finalist, nothing is built) and `r_best`: state name of a random-control state, or `null` (its runs are dropped).
- Outputs: `docs/harness/screen01_f_campaign.json` (f32a, f32b, smoke kernel f32smk) and `docs/harness/screen01_f48_campaign.json` (f48k13, f48k14, smoke kernel f48smk). The state rows come from `states.json` (+ `states_g2.json` when it exists).

## Other builder facts the analyzer may rely on
- Run (table) names are `<state>__k<phase>` (e.g. `v18__parent__k11`, `v18__parent__repeat__k13`); a kernel holds one run per (state, phase). Kernels: `g1k11` (phase 11, the repeat last), `g1k12`, `g2` (screen01_g2; phases 11, 12), `f48k13`, `f48k14`, `f32a` (13, 14, parent replay at 11, the repeat at 13 last), `f32b` (15, 16). Smoke-only kernels `f32smk`, `f48smk` (parent at phase 20) carry no registered force.
- `states.json`: `order` is 0-based within the role; `parent_repeat` has `u = null`, `spec = null`; `parent_record` holds the UNC-01 parent record (extra key).
