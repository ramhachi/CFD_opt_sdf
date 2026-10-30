# SCREEN-01 implementation interface (shared by the analyzer, the independent checker and the builder)

Authority: `docs/screen01_registration_2026_10_30.md` (rev. 1). Where this note and the registration disagree, the registration governs; report the disagreement.

## Files and owners
| File | Owner | May read |
| --- | --- | --- |
| `scripts/screen01/screen01_build.py`, `scripts/screen01/screen01_freeze.py`, `tests/screen01/test_screen01_build.py` | builder agent | everything in the repo |
| `scripts/screen01/analyze_screen01.py`, `tests/screen01/test_screen01_analyze.py`, `tests/screen01/synthetic.py` | analyzer agent | everything except `screen01_check.py` |
| `scripts/screen01/screen01_check.py`, `tests/screen01/test_screen01_check.py` | checker agent | the registration, this note, `screen01_pool.py` constants only; NOT `analyze_screen01.py`, NOT `screen01_pool.propose/fit9/d_optimal9/constrained_argmax` bodies |
`scripts/screen01/screen01_pool.py` and `screen01_oc.py` exist (P0 and OC); do not edit them unless a defect is found (then report, do not silently change).

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
  "gating": [ {"name": str, "u": [3], "target_index": int, "y_pred": float, "z_pred": float, "admissible": bool} ... ]   # every stage: the rs.json gating record, in gated order (at stage rs the analyzer gates first, then cross-checks before writing rs.json)
}
```
`null` = non-finite force; `ok = false` = harness verify failed / per-state cap exceeded / run not finished. Phases: g1 and g2 use 11, 12; f32 uses 13-16 and the replay 11; f48 uses 13, 14.
Both implementations apply §5.1 DATA_LOSS themselves (ok false, null, or `|F - F_parent,k| > 0.25 |F_parent,k|` for either response, against the parent of the same stage and phase).

## Comparable output (both return this dict; the analyzer compares before writing)
`compare_keys(stage)` — strings/bools/None exact; floats `abs(a-b) <= 1e-9 * max(1, |a|, |b|)`; lists elementwise.
- stage `rs`: `data_loss` (sorted list of `state@stage@phase`), `fit.downforce.coef` (9 floats, column order `[u_p, u_c, u_r, u_p^2, u_c^2, u_r^2, u_p u_c, u_p u_r, u_c u_r]`), `fit.drag.coef`, `fit.rank`, `fit.cond`, `fit.residual_sd.{downforce,drag}`, `rs_fit_poor`, `rs_not_fit`, `u_star_1`, `y_star_1`, `pool_limited_pre`, `targets[tau].u_star`, `targets[tau].y_pred`, `targets[tau].z_pred` for tau in {1, 1.5, 2}; `gated` (list of `[target_index, u rounded to 6 decimals]` in the order the §5.2 rule gates them, regenerated independently from the fit: Sobol cloud seeds `20261032 + target index`, filter, ordering, round-robin, rounds of 4, the stopping rule, the 36 cap; the admissibility outcomes are taken from `T["gating"]`), `stop_after` (number of gated points), `proposals` (indices into `gated`, in proposal order).
- stage `finalist`: `data_loss`, `candidates` ({name: {"delta_bar": {downforce, drag}, "P": int, "se_eff": {downforce, drag}, "feasible": bool}}), `finalist` (name or None), `futility` (None | `NO_FEASIBLE_CANDIDATE` | `GAIN_BELOW_MIN_AT_SELECTION`), `search_complete`, `pool_limited`, `r_best`, `K_opt`, `K_rand`, `proposals_from_gating` (the proposal names that the §5.2 selection rule yields from `gating`).
- stage `main`: everything of `finalist` plus `outcome`, `cause` (list), `G`, `D` (decision and label), `R3` (label + the secondary labels), `NC` (G1 and F: z and label), `determinism` (g1k11, f32a), `generation_drift`, `controls` (OPT_VS_RANDOM, OPT_VS_MANUAL, RANDOM_FEASIBLE_GAIN, K_MISMATCH), `selection_bias` (b_K central/upper, g_XV,exp central/pessimistic, XV_MARGIN labels), `confirmation` per finalist (delta_bar, sigma_d, se_eff, P for downforce/drag on f32 and f48).
The checker exposes `check(T: dict) -> dict` returning exactly these keys for `T["stage"]`, plus `compare(a: dict, b: dict, stage) -> list[str]` (list of discrepancy paths; empty = agree) — or the analyzer owns `compare`; the checker's `check` is the contract.

## Constants
Re-read from FID and M2 analysis files by SHA-256 (registration §6) in the analyzer; the checker may hard-code the §6 table values (independence of code, not of constants).

## rs.json fields used by the builder (`screen01_build.py campaign g2 --rs rs.json`; top-level keys, everything else is ignored)
- `proposals`: list in rank order (<= 4) of `{"name": str, "u": [u_pitch, u_camber, u_reflex]}`. The state is `spec = dict(sorted(screen01_pool.u_to_spec(u).items()))` (amplitudes rounded to 1e-3) and `name` **must equal `fid01_designs.name(spec)` with the keys in sorted order** (registration §3.2: `v18__camber_..._pitch_..._reflex_...`); the builder refuses otherwise. NOTE: `screen01_pool.propose()` currently names points `D.name(u_to_spec(u))`, i.e. in pitch-camber-reflex key order, which is not the registered name; the analyzer must write sorted names in `proposals` and `gating` (and exclude already-evaluated names by their sorted names).
- `gating`: the gating record, list of `{"name": str, "admissible": bool, "phi_fortran_sha256": str, ...}` (further keys, e.g. `u`, `target_index`, `y_pred`, `z_pred` or the gate row, are carried into freeze 2.1 as the proposal's `gating_row`). Every proposal name must appear with `admissible: true` and `phi_fortran_sha256` = the gate row's `phi_fortran_sha256` (the gated harness bytes); the builder refuses unless the built state reproduces that SHA and the runner regeneration reproduces it again.
- No proposal (`proposals == []`) means no g2 kernel: `campaign g2` writes nothing.
- Outputs: `states_g2.json` (schema as `states.json`, role `proposal`, `order` = rank index, `u = spec_to_u(spec)`, `rs_json_sha256`), the proposals' direction raws in `inputs/`, and `docs/harness/screen01_g2_campaign.json` (campaign `screen01_g2`, kernel `g2`: a separate campaign, because the harness binds the campaign file's SHA-256 into the frozen `screen01` runs and `verify`).

## finalist.json fields used by the builder (`screen01_build.py campaign f --finalist finalist.json`; top-level keys)
- `finalist`: state name (a G1 axial / design state or a proposal; `null` = no finalist, nothing is built) and `r_best`: state name of a random-control state, or `null` (its runs are dropped).
- Outputs: `docs/harness/screen01_f_campaign.json` (f32a, f32b, smoke kernel f32smk) and `docs/harness/screen01_f48_campaign.json` (f48k13, f48k14, smoke kernel f48smk). The state rows come from `states.json` (+ `states_g2.json` when it exists).

## Other builder facts the analyzer may rely on
- Run (table) names are `<state>__k<phase>` (e.g. `v18__parent__k11`, `v18__parent__repeat__k13`); a kernel holds one run per (state, phase). Kernels: `g1k11` (phase 11, the repeat last), `g1k12`, `g2` (screen01_g2; phases 11, 12), `f48k13`, `f48k14`, `f32a` (13, 14, parent replay at 11, the repeat at 13 last), `f32b` (15, 16). Smoke-only kernels `f32smk`, `f48smk` (parent at phase 20) carry no registered force.
- `states.json`: `order` is 0-based within the role; `parent_repeat` has `u = null`, `spec = null`; `parent_record` holds the UNC-01 parent record (extra key).
