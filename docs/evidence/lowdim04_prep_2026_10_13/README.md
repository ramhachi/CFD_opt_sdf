# LOWDIM-04 preparation: exploratory solver-free scripts and outputs (2026-10-13)

**Not frozen, not reviewed, not a registered measurement.** These scratch scripts were kept so the numbers in
`docs/lowdim04_plan_2026_10_13.md` are reproducible. They read only retained, hash-pinned inputs and write nothing but stdout.
Run from the repository root with the project interpreter (`python -I docs/evidence/lowdim04_prep_2026_10_13/<script>.py`).

| Script | Output | What it shows |
| --- | --- | --- |
| `invariance_radius.py` | `invariance_radius.out` | min \|cell centre\| and cell counts within a radius, for the v17 baseline and the LOWDIM-03 parent |
| `rebuild_eight_states.py` | `rebuild_eight_states.out` | the eight recorded LOWDIM-04A perturbation states re-derived with `step01_states.perturb`; 8 of 8 phi Fortran SHA matches |
| `count_change_scan.py` | `count_change_scan.out` | first step (0.25 mm grid, either sign) at which the hard count changes along each retained direction. Note: the `proposal_downforce` row uses the LOWDIM-01 proposal file, not the LOWDIM-03 robust direction |

Not reproduced here: the continuum zero-set volume bounds, the LP previews and the curvature fits quoted from the adversarial reviews; they were
produced by reviewer subagents in scratch and are to be recomputed inside the frozen Stage A builder before any claim relies on them.
