# Adversarial plan review brief (GEN-01 plan rev 0)

You are an independent adversarial reviewer. Your job is to find what is wrong, missing, over-claimed, under-specified or unrealistic in the plan, and to say so plainly. Do not be polite for its own sake; do not pad with praise. Every finding must be specific (quote or cite the section), say why it matters, and propose a concrete fix or a test that would settle it. Where you assert a fact from outside the plan, cite a source (paper, documentation page, or a file in the repository) and say whether you verified it or are recalling it.

Repository (read-only; write nothing; do not read .kicad_* files):
/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1

Read first:
1. docs/gen_system_plan_2026_11_01.md (the plan under review; Japanese; rev 0 commit as given in your prompt)
2. docs/evidence/gen01_plan_2026_11_01/research/*.md (four research reports the plan relies on, and their briefs) and gen_cost.py / gen_cost_output.txt
3. docs/STATE.md, and the 2026-10-16 entry of docs/phase_plan.md (search "PROC-01") for the project's evidence process
4. docs/roadmap_review_2026_10_24.md §4.5-4.7 and §6 (prior literature review and direction)
5. docs/t20_summary_for_m4_2026_10_22.md (the high-Re 2D RANS evaluator record), docs/stage_s_work_f_architecture_decision_2026_09_25.md and docs/problem_register_2026_09.md "P6" (the earlier body-fitted adjoint failures)

Context you must know: the project has so far optimised one analytic plate at Re 80 with a fixed-grid solver (WaterLily) and verified differences in laminar body-fitted OpenFOAM; every gradient route tried so far failed or was blocked (details in the plan §1.2). The user now wants a GENERIC whole-vehicle (FSAE car) optimiser: SDF representation of many components, hundreds to thousands of regularised node-based design variables, adjoint RANS gradients on body-fitted meshes, cloud compute, budget available. The plan proposes the architecture, the staged studies with pre-registered pass/fail rules, the budget and the risks. The project's process (PROC-01) requires pre-registration, freezing, written-once analysis, and fail-closed rules for every registered study.

You may use WebSearch/WebFetch to verify claims (e.g. Carter 1991's theorem, DAFoam v5 memory and Jacobian-free mode, SU2 v8.6 features, cloud prices, the Imperial Front Wing data, FSAE rules) — do so for the claims that matter most to your angle, and report what you found.

Output format (Markdown, English, at most ~2500 words):
- Verdict line: one of GO / GO_AFTER_FIXES / NO_GO, with one sentence of reason.
- Findings as a numbered list with ids prefixed by your angle letter (e.g. N1, N2 ...), each with: severity (P1 = must fix before any registration; P2 = fix in rev 1; P3 = note), the section cited, the problem, why it matters, the proposed fix or test, and your confidence.
- A short list of "things the plan gets right that must not be lost in revision".
- A list of claims you checked externally, with the result.
Report only in your final message. Write no files.
