# T2-0d pre-registration timing pilot (local, force-free, 2026-10-21)

Not evidence for any gate or label; disclosed in `docs/t20d_registration_2026_10_21.md` section 2. One xfine30 h/c 0.09, 0-deg case generated locally by
`scripts/t20c_case.py` (manifest `case_manifest.json`; local gmsh, so not Kaggle's mesh), run in the local OpenFOAM image (1 CPU, `--memory 3g`) by `run.sh`
(gmshToFoam, boundary fix, simpleFoam 400 iterations, then pimpleFoam with an adaptive step at Courant number 1, stopped after 113 steps) and `run2.sh`
(pimpleFoam at a fixed 1e-5 s and 2e-5 s, 100 steps each, 2 outer correctors). `prep.py` removed every function object from the steady controlDict before the
run, so no force or coefficient was computed. Logs are gzipped as written. Read: step counts, Courant numbers, time steps, timing, the last residual and continuity
lines. The host was shared and loaded (load average 48-102), so timings are ratios, not absolute costs.
