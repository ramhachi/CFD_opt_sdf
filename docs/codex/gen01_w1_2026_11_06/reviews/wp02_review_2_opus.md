# Opus source review 2 of WP2 (PR #84, 6881a64e), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Verdict INTEGRATE_AS_IS; GPU F1–F3 may run under four conditions. Decisions: `docs/force00_force_readout_gate_2026_11_01.md` Amendment 2 and `02_force00.md` Amendment 4.

# Source review round 2: WP2 FORCE-00 (feat/gen01-w1-02-force00, HEAD 6881a64e on afac79ed, Draft PR #84)

Read-only; the worktree was clean throughout. Probes ran on an APFS clone in the reviewer scratchpad (`wp02r2/probe/gate_probe.py`, `box_probe.jl`).

Re-run by me:
- Julia self-test: 116/116 PASS; the cylinder line is byte-identical to the record.
- `pytest test_force00_gate.py test_force00_boxes.py`: 96 passed.
- Job `.diff`: `cmp`-identical to a fresh `git diff --no-index -U0`.
- `git diff e3dcdf61 -- julia/CFDSDFWaterLily/src`: empty.
- `amendment3/SHA256SUMS`: 34/34 OK.

## Round-1 findings

**M1: CLOSED.** I ran the production path: `main()`, with the real references, provenance, registry and the committed U1. The 20 synthetic runs were built from the registered CSVs (legacy bytes verbatim, nds = cv = cur), and the registered σ is `None`.
- **Complete inputs:** exit 0, PASS, `adopted_readout R_cv`, `criteria.C5.status INCOMPLETE` (missing σ for `v18__camber_m19.7`), C1 PASS over 20 rows.
- **Missing inputs:** each case below exits 1 and writes nothing.
  - F3 k10 camber or F1 half omitted.
  - A registered FID-01 reference CSV deleted (`FileNotFoundError` from `registered_references`).
  - `nds` dropped from a U1 row: the `(FileNotFoundError, KeyError)` branch adds it to `missing`, and `write_gate` refuses (`force00_gate.py:507-508`).
- Only the σ branch (`:186`) maps to "absent" without blocking. That is correct for C5.
- **C4 at `:465`:** a relative shift of 0.15000000000000058 is PASS; 0.15·(1+3e-9) is HOLD.

**m1: CLOSED.**
- **Box registration:** `force00_boxes.py` derives one box per grid from the parent-only phase-0 Float32 μ₀ support. The scene with ground is preflighted separately. Margins are ≥ 2 / ≥ 5 (actual 15 / 21 cells), parent SHAs are recorded, and an existing file is refused before measurement (tested).
- **Job:** reads the registry (job:50-90). The environment variable is honoured only with `FORCE00_CPU_TEST=1` and `u isa Array`; both refusals are shown by probe.
- **Gate:** a shifted box in F3 k9 candidate or in F1 k3 is refused ("run differs from registered CV box"). A registry edited after U1 is refused on its SHA.

**m3: CLOSED.**
- **No default region:** `box` is mandatory, and `nothing` raises `ArgumentError`.
- **Exact face check:** `validate_force_box` checks `all(isone, view(μ₀, face…, axis))` on all 2D faces. The self-test's one-ulp perturbation is refused with the geometry unchanged.
- "One cell too close" is refused at three levels:
  - **Job reader:** a registry with 4-cell support clearance is refused, as are `body_clearance_cells: 4`, a changed parent SHA, and an upper bound beyond the inset.
  - **Validator, real v18 parent (flow_24, Float32, with ground):** the registered box is OK, and the fused target is refused. By x-lower clearance: 3 is OK, 2 is refused (SDF < 4), 1 is refused (enclosure). A bottom face at z = 3 is refused.
  - **Analytic sphere:** the same pattern.

**m2: CLOSED.**
- The summary records three path→SHA entries (job:92-97, 319). The gate requires them to equal U1 (`:286-287`); a `Force00.jl` SHA mismatch in F2 k15 is refused.
- U1 was regenerated: all 28 `source_sha256` entries equal the HEAD bytes. Editing `Force00.jl` afterwards makes the gate refuse ("uniform-pressure geometry/source SHA-256 mismatch").

**m5: CLOSED.**
- F3 references come from the FID-01 verified tables, SHA-checked against the table, `d_set.json` and the manifest. Nothing is hard-coded.
- The 8 F3 C1 rows carry `registered_csv_sha256` equal to FID-01 SHA256SUMS; 20 runs are required.
- A 1e-12 change to one legacy fx in F3 k7 camber (identities kept) gives C1 FAIL, status FAIL, NONE.

**m4: CLOSED (descriptive by decision).**
- **Summation-by-parts test:** linear p compared with ∂ᵢp·Σ(1−μ₀), atol 1e-12, 2D and 3D, Float32 and Float64. This is an independent discrete identity, not a tautology.
- **Self-written D16 / Re100 cylinder:** spread 0.046 %; CV is 12.48–12.53 % above cur. This independently reproduces the round-1 probe (12.823 / 12.829 / 12.826).
- It only prints. CV sign and term regressions are guarded by the affine and quadratic analytic tests.

**m6, n6, n5, n2: CLOSED.**
- Timing and VRAM non-comparability are stated as summary flags with a scope string.
- The header, usage and DONE text name FORCE-00; the `W4_JOB_DONE` filename is kept.
- The sphere radius has a single source, `Simulation.jl`, read by `force00_uniform_inputs.py:74`.
- `gpu_name == "Tesla T4"`, per Amendment 1 §5.

**n3: CLOSED** (C4 tolerance). **n4: CLOSED**; the decoy test also asserts the refused write. **n7:** unchanged; the gate's relative thresholds govern. **n8: OPEN by nature.** GPU compile is unverified, now including `all(isone, view(CuArray))`; all new kernels run in the preflight, before warm-up.

## Regressions: none

- **`Force00.jl` vs afac79ed:** only the region/box handling changed, plus the μ₀ face check. `_force00_nds`, the nds sums, the CV face and storage terms, the signs, `Δt[end-1]` / `u⁰` and the `flow.f` restore are unchanged.
- **Job:** only the box source, the summary fields and the texts changed. The solver, cadence, window, legacy columns and R_cur duplication are untouched.
- **flow_16 regression:** registered = projected = `cut -f1-13` of the extended CSV = `c48e92cb…`; both final-array and cur-token flags are true.

## Report honesty: accurate

- 116 assertions: reproduced.
- 104 placements, repeat run byte-identical (`fc76ee6d…`).
- Closure: 9.0983e-13.
- Focused tests: 100 = 86 + 10 + 2 + 2; I ran 96 of them.
- **Full suite:** 3580 / 74 / 0. The JUnit has 3654 cases, of which 98 are FORCE-00 tests (86 + 10 + 2). Base e3dcdf61 has none, so 3482 + 98 = 3580.
- One assertion was added after the suite launch; this is disclosed, and the focused run covers it.
- The 52-file inventory equals `git diff --stat afac79ed`.

## New findings

- **N1 (minor, operational).** `force00_source_sha256()` runs only when the summary is built, after the full solve (job:319).
  - If the bundle lacks the dispatcher (which is read even for direct flow_32 launches), the job dies after hours with no summary.
  - Fix: compute the SHAs before warm-up.
  - Low risk if the kernel clones a pinned commit, as `build_lowdim02a_kernel.py` does.
  - Any job edit requires re-running U1 (~2 min).
- **N2 (note).** There is no FORCE-00 Kaggle kernel builder or freeze yet. It must pin the commit carrying `Force00.jl`, the job, the dispatcher, `force00_boxes.json` and `genesis.json`, and watch the new `FORCE00_…_DONE` marker. This is out of WP2 scope but a precondition for F1–F3.
- **N3 (note).** The spec-compliant "largest" box places faces 2 cells from the inlet, the sides, the top and the convective exit, and exactly 4.0 cells above the ground (zero slack, passing by exact Float32 arithmetic). The cylinder boxes stay ≥ 50 cells from their exit, so this configuration is not exercised on CPU. If R_cv reaches HOLD or FAIL_PHASE, suspect exit-face sensitivity first.
- **N4 (note).** The 5-cell margin is enforced by the generator, the job reader and the gate's registry equality. `validate_force_box` itself accepts a face 3 cells from the support, consistent with Amendment 1; do not credit the validator with the 5-cell rule.

## Verdict

**INTEGRATE_AS_IS.** Every round-1 required item is closed:
- M1, with production-path evidence;
- m1 / m3, with refusals shown at the job reader, the validator and the gate;
- m2, with U1 regenerated at HEAD;
- m5, from evidence;
- m4 / n4, m6 and n2 / n5 / n6.

The read-out mathematics, the registered job semantics and `src/` are unchanged, and the records are accurate. N1 is cheap pre-launch hardening, not a blocker.

**GPU: yes.** The job variant may run F1–F3 on the Kaggle T4 as is, provided that:
- the kernel pins the commit carrying the registry and the dispatcher (N1 / N2);
- flow_24 is launched through `waterlily_force00_dispatch.jl`;
- a short single-phase smoke run comes first;
- any edit to `Force00.jl`, the job, the dispatcher or the registry (N1 included) is followed by a U1 re-run before the gate.
