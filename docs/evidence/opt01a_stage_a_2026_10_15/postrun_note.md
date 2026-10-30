# OPT-01 v1 Stage A post-run note (2026-10-15)

Verdict `LOCAL_FEASIBLE_CONE_FOUND` (analysis `opt01a_analysis.json`; integrity pass; parent byte-identical to the retained LOWDIM-04B
0.3125 mm CSVs on both grids). The post-run review recomputed all 16 secants (relative difference 6.6e-12) and the cone solutions
(independent SLSQP, t* main 0.1710, robust 0.1226) and confirmed FOUND.

**Caveat placed next to the verdict.** Every basis direction has at least one secant probe that fails the crossing-slope rule, which is
report-only for probes (Amendment 2, F1): D0− 284, D1− 40, D1+ 153, D2− 3, D2+ 206, P1+ 212 failing nodes, all on the baseline |φ| < 1e-6
tie nodes (a node-set coincidence; the mechanism is not demonstrated). At those nodes the zero set can move by up to an edge length for a
1.25 mm probe, so the secants may include sub-cell zero-set jumps. FOUND is a statement about the linear cone model of these secants; it is
not a smooth-response measurement and not a gain forecast. The even parts are large (eta_even 3.24 and 3.00 for flow_24 downforce D0 and
P1, 5.81 for flow_32 drag D0) and all downforce even parts are negative; the main cone's flow_32 drag prediction is exactly at zero (active).
