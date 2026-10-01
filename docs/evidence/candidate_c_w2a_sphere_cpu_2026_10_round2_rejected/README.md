# Rejected W2a-C Round 2 pre-execution registration

This directory preserves the exact Round 2 criteria, source manifest, runner,
Julia job, and initialization-only preflight before any numerical measurement.
Round 2 criteria SHA-256 is
`1185b98aa69d1765b6fe6829305e5842a2e81a5fd2c22c76ddfd4a478c8b51ec`; source
manifest SHA-256 is
`d7f935eb56da31c5d0e50711c344f924fe3122e6ab26794e24d4414458502d4d`.

Parent source review found an implementation mismatch in G5. The criteria
registered `abs(mean_drag(40-50)-mean_drag(50-60))/abs(mean_drag(40-60))`, but
Round 2 computed the numerator from `mean_drag(40-50)-mean_drag(40-60)`. For
equal-duration halves with means 98.5 and 101.5 and full mean 100, that code
would report 0.015 instead of the registered 0.03 and could falsely pass the
2% limit. No solver measurement occurred. Round 3 corrects the implementation,
adds fail-closed zero/non-finite denominator handling, and independently
recomputes the registered window means from raw CSV before applying gates.
Round 2 files remain unchanged as an append-only rejected snapshot.
