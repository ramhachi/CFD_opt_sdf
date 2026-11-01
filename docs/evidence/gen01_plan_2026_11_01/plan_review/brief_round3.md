# Adversarial plan review, round 3 (GEN-01 plan rev 3: WaterLily main line)

You are an independent adversarial reviewer. Find what is wrong, missing, over-claimed, under-specified or unrealistic, and say so plainly. Every finding must cite the section, say why it matters, and propose a concrete fix or test. Cite sources for external facts and say whether you verified them.

Repository (read-only; write nothing; do not read .kicad_* files):
/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1

Context. The user rebuilt this research line on WaterLily.jl (Julia, GPU, uniform Cartesian grid, BDIM immersed boundary, implicit LES, ~134 B/cell, Kaggle T4) because OpenFOAM/DAFoam were too heavy. The user's stated reason for using an SDF is topology freedom: a front wing whose number of elements is not fixed in advance. Plan revisions 0-2 of this document proposed a body-fitted RANS + discrete adjoint main line; the user rejected it on 2026-11-01 (it abandoned the GPU/fixed-grid premise, DAFoam's adjoint needs TB-scale RAM, cloud cost was beyond a research budget; realistic hardware is one machine with ~128 GB RAM plus a GPU). Rev 3 puts WaterLily back as the main line: an SDF scene of morphable analytic components (union by min), topology events (vanish/merge/seed/knock-out) judged by paired same-phase tests, gradient-free or reduced-basis FD optimisation (WaterLily's AD is blocked: tangents grow exponentially, GRAD-03 #23), OpenFOAM primal (no adjoint) only as a verifier at the same Re (unsteady laminar, few pairs) and at FSAE Re (RANS, the transfer test TR-01), and RE-01 (#78) as the other transfer gate.

Read first:
1. docs/gen_system_plan_2026_11_01.md (rev 3, Japanese; commit and SHA-256 in your prompt)
2. docs/evidence/gen01_plan_2026_11_01/gen_cost_wl.py and gen_cost_wl_output.txt (GPU-hour cost model); gen_cost_local.py (the single-machine OpenFOAM model) for comparison
3. docs/evidence/gen01_plan_2026_11_01/plan_review/*.md (the five earlier reviews and two adoption records of the rejected body-fitted line; reuse what still applies)
4. docs/re01_plan_2026_11_01.md (RE-01: Re ladder on the v18 plate, Stage-0 charter, unsteady statistics contract), docs/STATE.md, the 2026-10-16 PROC-01 entry in docs/phase_plan.md (search "PROC-01"), docs/roadmap_review_2026_10_24.md §4.5-4.6 and §6.3
5. docs/evidence/screen01_2026_10_30/README.md (the only working proposer so far: 3-mode response surface, +4 %), docs/evidence/fid01_2026_10_21/analysis.md (retention of fixed-grid differences in body-fitted OpenFOAM at Re 80), scripts/v18_plate.py (the analytic plate SDF the plan generalises into components), docs/width_rule_decision_2026_10_20.md (the one-cell occupancy artefact, "R0")

Output (Markdown, English, at most ~2200 words): verdict line (GO / GO_AFTER_FIXES / NO_GO) with one sentence; numbered findings with ids prefixed by your angle letter, each with severity (P1 must fix before any registration; P2 fix in rev 3.1; P3 note), section, problem, why it matters, fix or test, confidence; a short list of what the plan gets right; claims checked externally. Report only in your final message. Write no files.
