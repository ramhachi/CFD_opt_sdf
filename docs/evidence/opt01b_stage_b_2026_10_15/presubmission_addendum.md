# OPT-01 v1 Stage B pre-submission addendum (written and committed before submission, 2026-10-15)

Not part of the frozen registration (the freeze and prerun note are unchanged); committed before the kernels are pushed so that it is
timestamped foreknowledge. The pre-run review pointed out that the Stage A diagonal-curvature hindcast (linear term plus the sum over the four
basis directions of `(w_i f / 1.25 mm)^2 * even_i`, the LOWDIM-04B formula, not a registered model) already estimates the **flow_24 downforce**
change along the robust direction at about **+1.5e-5 N at 0.3125 mm** (linear part +3.0e-5 N), about −8e-7 N at 0.625 mm and negative beyond.
Against the strict 3e-5 N floor this makes the smallest step a toss-up and **REJECT the more likely outcome**; flow_32 is estimated positive.
Either ACCEPT or REJECT closes #30 (E5). An ACCEPT at 0.3125 mm with a flow_24 gain below about 2σ of the nominal floor (about 6e-5 N) is
reported as not noise-resolved; the selected gain is biased upward in any case.
