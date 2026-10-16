# T2-0a result tables (descriptive; EXPLORATORY_COMMITTED, no verdict)

Cl = downforce coefficient, Cd drag, per unit span, reference chord. Ours = mean over the last 20 % of iterations (kernel `forces.Cl.tail_mean`).
Genua = his Med30 case with the same turbulence-model family (sa-wf: Med30SA full sweep; sst-wf: Med30KWS, h/c 0.224 and 0.09 only). diff = (ours - Genua)/Genua.

## sa-wf

| h/c | mesh | status | Cl ours | Cl Genua | diff % | Cl exp | diff vs exp % | Cd ours | Cd Genua | diff % | iters | plateau | res.conv | wall min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.671 | med30 | COMPLETED | 0.948 | 0.895 | 5.9 | - | - | 0.0213 | 0.0330 | -35.4 | 5000 | True | False | 6.0 |
| 0.448 | med30 | COMPLETED | 1.065 | 0.993 | 7.3 | - | - | 0.0238 | 0.0360 | -33.9 | 5000 | True | False | 5.8 |
| 0.224 | med30 | COMPLETED | 1.345 | 1.255 | 7.2 | 1.286 | 4.6 | 0.0333 | 0.0470 | -29.2 | 5000 | True | False | 5.5 |
| 0.134 | med30 | COMPLETED | 1.396 | 1.409 | -0.9 | - | - | 0.0480 | 0.0620 | -22.6 | 5000 | True | False | 5.4 |
| 0.09 | med30 | COMPLETED | 1.312 | 1.381 | -5.0 | 1.371 | -4.3 | 0.0617 | 0.0750 | -17.7 | 5000 | True | False | 5.1 |

## sst-lm

| h/c | mesh | status | Cl ours | Cl Genua | diff % | Cl exp | diff vs exp % | Cd ours | Cd Genua | diff % | iters | plateau | res.conv | wall min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.224 | wr2 | COMPLETED | 1.332 | - | - | 1.286 | 3.6 | 0.0234 | - | - | 2000 | False | False | 140.5 |
| 0.134 | wr2 | COMPLETED | 1.509 | - | - | - | - | 0.0401 | - | - | 2000 | False | False | 141.8 |
| 0.09 | wr2 | COMPLETED | 1.386 | - | - | 1.371 | 1.1 | 0.0621 | - | - | 2000 | False | False | 141.7 |

## sst-wf

| h/c | mesh | status | Cl ours | Cl Genua | diff % | Cl exp | diff vs exp % | Cd ours | Cd Genua | diff % | iters | plateau | res.conv | wall min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.671 | med30 | COMPLETED | 0.968 | - | - | - | - | 0.0181 | - | - | 5000 | True | False | 6.2 |
| 0.448 | med30 | COMPLETED | 1.092 | - | - | - | - | 0.0201 | - | - | 5000 | True | False | 6.4 |
| 0.224 | med30 | COMPLETED | 1.405 | 1.306 | 7.6 | 1.286 | 9.3 | 0.0282 | - | - | 5000 | True | False | 5.7 |
| 0.134 | med30 | COMPLETED | 1.435 | - | - | - | - | 0.0453 | - | - | 5000 | True | False | 5.8 |
| 0.09 | med30 | COMPLETED | 1.221 | 1.779 | -31.4 | 1.371 | -11.0 | 0.0637 | - | - | 5000 | True | False | 5.7 |

## Cl peak location (h/c at the largest Cl among the heights run; Genua and the experiment place it at 0.134)

- sa-wf: 0.134  (heights run: [0.671, 0.448, 0.224, 0.134, 0.09])
- sst-lm: 0.134  (heights run: [0.224, 0.134, 0.09])
- sst-wf: 0.134  (heights run: [0.671, 0.448, 0.224, 0.134, 0.09])

## Mesh and timing

| case | cells | max non-orth | max skew | max AR | checkMesh failed counts | solver wall min | total wall min | peak RSS MB |
|---|---|---|---|---|---|---|---|---|
| sa-wf_h0.09_med30 | 13722 | 41.637644 | 0.64883743 | 6.7223694 | [] | 5.0 | 5.1 | 75 |
| sa-wf_h0.134_med30 | 14151 | 38.62036 | 0.64883743 | 6.7223694 | [] | 5.3 | 5.4 | 76 |
| sa-wf_h0.224_med30 | 14773 | 43.868342 | 0.64883743 | 6.7223694 | [] | 5.4 | 5.5 | 76 |
| sa-wf_h0.448_med30 | 15546 | 40.271237 | 0.64883743 | 6.7223702 | [] | 5.7 | 5.8 | 79 |
| sa-wf_h0.671_med30 | 15919 | 37.868413 | 0.64883743 | 6.7223702 | [] | 5.9 | 6.0 | 79 |
| sst-lm_h0.09_wr2 | 129592 | 48.793354 | 0.73474783 | 69.353549 | [] | 25.8 | 141.7 | 320 |
| sst-lm_h0.134_wr2 | 130138 | 53.316974 | 0.73474783 | 69.353549 | [] | 25.1 | 141.8 | 321 |
| sst-lm_h0.224_wr2 | 131302 | 53.241433 | 0.73474783 | 69.353549 | [] | 24.6 | 140.5 | 324 |
| sst-wf_h0.09_med30 | 13722 | 41.637644 | 0.64883743 | 6.7223694 | [] | 5.6 | 5.7 | 74 |
| sst-wf_h0.134_med30 | 14151 | 38.62036 | 0.64883743 | 6.7223694 | [] | 5.7 | 5.8 | 77 |
| sst-wf_h0.224_med30 | 14773 | 43.868342 | 0.64883743 | 6.7223694 | [] | 5.6 | 5.7 | 77 |
| sst-wf_h0.448_med30 | 15546 | 40.271237 | 0.64883743 | 6.7223702 | [] | 6.3 | 6.4 | 78 |
| sst-wf_h0.671_med30 | 15919 | 37.868413 | 0.64883743 | 6.7223702 | [] | 6.1 | 6.2 | 80 |

