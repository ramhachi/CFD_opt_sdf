# LOWDIM-03 failed_attempt1: analyzer integrity check failed on complete kernel outputs

Both kernels completed (`COMPLETE`, `DONE`, no `ERROR.txt`; kernel a 7 states ~176 s each, kernel b 7 states ~409 s each; both fresh baselines byte-matched their registered historical CSV). The registered analyzer (`--check`, freeze `6009d6b0…`, source `e5386910`) stopped with `LOWDIM03_INCOMPLETE`:

`ValueError: summary device_roundtrip_sha256 differs from the fixed declaration` (`analyzer_check_output.json`).

## Cause (read-only diagnosis)
The analyzer (`scripts/analyze_lowdim03.py`, `check_kernel`, `canonical_metadata`) expects `device_roundtrip_sha256 == row["phi_c_order_sha256"]`. The unchanged Julia jobs report, in all 14 summaries, `device_roundtrip_sha256 == phi_fortran_sha256 == the registered phi Fortran-order SHA` (e.g. baseline `e3966d87…`, not the C-order `f6419547…`): the device read-back of the uploaded phi is hashed in Fortran order. So the measurement is internally consistent and the analyzer's fixed declaration is wrong; the synthetic test fixture mirrored the same wrong assumption (`tests/test_lowdim03_analyzer.py`), and no earlier analyzer (GRID-01, LOWDIM-01/02A) checked this field, so it was never exercised against a real summary before this run.

An in-memory run with only that expected value replaced (integrity only; the verdict was NOT read) reports `integrity.pass = true` with no other failure.

## Status under the registration
Integrity failure: no `--write`, no automatic repair, no resubmission. No LOWDIM-03 response/verdict has been computed or read. The decision on an analyzer amendment (replace the expected value by the registered Fortran-order SHA that the job emits; outcome-independent; re-analyse the SAME kept outputs, no new CFD) is the user's.
