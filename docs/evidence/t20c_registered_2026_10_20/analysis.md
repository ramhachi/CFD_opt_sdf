# T2-0c registered verdict: **T20C_MORPH_NO_GO**

Scope: 2D single-element section (Tyrrell 026), Re_c 4.6e5, moving ground, OpenFOAM v2512 SA wall functions; morph at fine30 against xfine30. Thresholds were set after T2-0a and T2-0b were visible (registration section 2).

Next action (registration section 6, row 5): steady RANS does not settle at that (mesh, h, alpha): an unsteady/solver-convergence study there; no mesh-dependence or morph conclusion

| gate @ h/c | result | detail |
|---|---|---|
| G6m @ 0.224 | PASS | `{"sigma_eff": 0.00043264683140551645, "consistency": {"a": 0.1317600038599993, "b": 0.13020947738, "allowed": 0.03294000096499983, "noise_3rss": 0.0037841142920742167, "margin": -0.9529287664063272, "unresolved": false, "pass": true}, "dCl_pm0.25": 0.06588000192999965, "resolved": true}` |
| G6m @ 0.134 | FAIL | `{"sigma_eff": 0.0021478240721434835, "consistency": {"a": 0.06260984890000021, "b": 0.06307128950999996, "allowed": 0.01878578826488909, "noise_3rss": 0.01878578826488909, "margin": -0.9754367182524786, "unresolved": true, "pass": false}, "dCl_pm0.25": 0.031304924450000104, "resolved": true}` |
| G3bm @ 0.224 | PASS | `{"xfine30": {"a": 0.13020947738, "b": 0.12024572606999995, "allowed": 0.032552369345, "noise_3rss": 0.0014427586847463897, "margin": -0.6939162490938477, "unresolved": false, "pass": true}, "sign_ok": true}` |
| G3bm @ 0.134 | FAIL | `{"reason": "M:sa-wf_h0.134_xfine30_da0 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.25 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.5 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+1 (UNSTEADY)", "bad_inputs": {"M:sa-wf_h0.134_xfine30_da0": "UNSTEADY", "M:sa-wf_h0.134_xfine30_morph-da+0.25": "UNSTEADY", "M:sa-wf_h0.134_xfine30_morph-da+0.5": "UNSTEADY", "M:sa-wf_h0.134_xfine30_morph-da+1": "UNSTEADY"}}` |
| G3bm @ 0.09 | FAIL | `{"reason": "M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY), M:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+1 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-1 (UNSTEADY)", "bad_inputs": {"M:sa-wf_h0.09_fine30_morph-da+1": "UNSTEADY", "M:sa-wf_h0.09_xfine30_morph-da-1": "UNSTEADY", "M:sa-wf_h0.09_xfine30_morph-da-0.5": "SOLVER_FAIL", "M:sa-wf_h0.09_xfine30_morph-da-0.25": "SOLVER_FAIL", "M:sa-wf_h0.09_xfine30_da0": "SOLVER_FAIL", "M:sa-wf_h0.09_xfine30_morph-da+0.25": "SOLVER` |
| G7m_fine30 @ 0.224 | PASS | `{"a": 0.13020947738, "b": 0.12378218459500001, "allowed": 0.032552369345, "noise_3rss": 0.022104898602735984, "margin": -0.8025553004488993, "unresolved": false, "pass": true, "undetectable_bias": 0.032552369345, "dM_minus_dR_in_remesh_sigma_d": 0.8730426621542808}` |
| G7m_fine30 @ 0.134 | PASS | `{"a": 0.06307128950999996, "b": 0.07793983025499984, "allowed": 0.02582761894233536, "noise_3rss": 0.02582761894233536, "margin": -0.42431624153211805, "unresolved": false, "pass": true, "undetectable_bias": 0.02582761894233536, "dM_minus_dR_in_remesh_sigma_d": -1.7545682321347265}` |
| G7m_fine30 @ 0.09 | FAIL | `{"reason": "M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY), R:sa-wf_h0.09_fine30_da+1 (UNSTEADY)", "bad_inputs": {"M:sa-wf_h0.09_fine30_morph-da+1": "UNSTEADY", "R:sa-wf_h0.09_fine30_da+1": "UNSTEADY"}}` |
| G7m_xfine30 @ 0.224 | PASS | `{"a": 0.12024572606999995, "b": 0.12364639470000005, "allowed": 0.030911598675000013, "noise_3rss": 0.008743550097260194, "margin": -0.889987293580179, "unresolved": false, "pass": true, "undetectable_bias": 0.030911598675000013, "dM_minus_dR_in_remesh_sigma_d": -1.176376943532275}` |
| G7m_xfine30 @ 0.134 | FAIL | `{"reason": "M:sa-wf_h0.134_xfine30_da0 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.25 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.5 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+1 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+0.25 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+0.5 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+1 (UNSTEADY), R:sa-wf_h0.134_xfine30_da0 (UNSTEADY)", "bad_inputs": {"M:sa-wf_h0.134_xfine30_da0": "UNSTEADY", "M:sa-wf_h0.134_xfine30_morph-da+0.25": "UNSTEADY", "M:sa-wf_h0.134_xfine30_morph-da+0.5": "UNSTEADY", "M:sa-wf_h0.134_xfine30_morph-da+1": "UNSTEADY", "R:sa-wf_h0.134_xfine30_da0": "UNSTEADY", "R:sa-wf_h0.134_xfine30_da+0.25": "UNSTEADY", "R:sa-wf_h0.134_xfine30_da+0.5": "UNSTEADY",` |
| G7m_xfine30 @ 0.09 | FAIL | `{"reason": "M:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+1 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-1 (UNSTEADY), R:sa-wf_h0.09_xfine30_da+0.25 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da+0.5 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da+1 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-0.25 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-0.5 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-1 (UNSTEADY), R:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL)", "bad_inputs": {"M:sa-wf_h0.09_xfine30_morph-da-1": ` |
| G8m @ 0.224 | PASS | `{"1.0": {"a": 0.13020947738, "b": 0.1280237204600001, "allowed": 0.032552369345, "noise_3rss": 0.0012979404942165492, "margin": -0.9328541373798457, "unresolved": false, "pass": true}, "0.25": {"a": 0.1317600038599993, "b": 0.12684297999999927, "allowed": 0.03294000096499983, "noise_3rss": 0.005191761976866197, "margin": -0.8507278774756386, "unresolved": false, "pass": true}}` |
| G8m @ 0.134 | FAIL | `{"1.0": {"a": 0.06307128950999996, "b": 0.085619760865, "allowed": 0.02140494021625, "noise_3rss": 0.00644347221643045, "margin": 0.053423701593985636, "unresolved": false, "pass": false}, "0.25": {"a": 0.06260984890000021, "b": 0.08358980264000015, "allowed": 0.0257738888657218, "noise_3rss": 0.0257738888657218, "margin": -0.1859996817204248, "unresolved": true, "pass": false}}` |
| G8m @ 0.09 | FAIL | `{"reason": "M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY), M:sa-wf_h0.09_fine30_morphB2-da+1 (UNSTEADY)", "bad_inputs": {"M:sa-wf_h0.09_fine30_morph-da+1": "UNSTEADY", "M:sa-wf_h0.09_fine30_morphB2-da+1": "UNSTEADY"}}` |

## Labels (never change the verdict)

```json
{
 "noise": {
  "R:med30:0.224": {
   "fit_cubic": 0.002605766462893233,
   "fit_quadratic": 0.0022821764566427556,
   "iter": 0.00028013500000001473,
   "eff": 0.002605766462893233,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.0059039274763927,
   "d": {
    "1.0": 0.12990440079499987,
    "0.5": 0.1306999600000005,
    "0.25": 0.13148646000000008
   },
   "smallest_resolved_incidence_deg": 0.05673572642109322,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "R:med30:0.134": {
   "fit_cubic": 0.005426532574251772,
   "fit_quadratic": 0.004821029537321327,
   "iter": 0.00021934250002849138,
   "eff": 0.005426532574251772,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.012294983154819177,
   "d": {
    "1.0": 0.06837944776499971,
    "0.5": 0.06517646499999974,
    "0.25": 0.06544502254000051
   },
   "smallest_resolved_incidence_deg": 0.22446147823657475,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "R:med30:0.09": {
   "fit_cubic": 0.003521453676330929,
   "fit_quadratic": 0.004539832328550067,
   "iter": 0.0004611184726248024,
   "eff": 0.003521453676330929,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.007978614896075632,
   "d": {
    "1.0": 0.055484701575000184,
    "0.5": 0.04960904652000009,
    "0.25": 0.03389297632000021
   },
   "smallest_resolved_incidence_deg": 0.17951209637864143,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "R:fine30:0.224": {
   "fit_cubic": 0.010411363636526899,
   "fit_quadratic": 0.01151834570577575,
   "iter": 0.00011764000000002992,
   "eff": 0.010411363636526899,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.023589196006520836,
   "d": {
    "1.0": 0.12378218459500001,
    "0.5": 0.15456878618000025,
    "0.25": 0.1150105899999998
   },
   "smallest_resolved_incidence_deg": 0.23790001292591756,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "R:fine30:0.134": {
   "fit_cubic": 0.011984311347466133,
   "fit_quadratic": 0.013317499602776707,
   "iter": 0.0003562510933743158,
   "eff": 0.011984311347466133,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.02715304923043258,
   "d": {
    "1.0": 0.07793983025499984,
    "0.5": 0.06817623614000001,
    "0.25": 0.009912736920000054
   },
   "smallest_resolved_incidence_deg": 0.4349092264593725,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "R:fine30:0.09": "not computable: R:sa-wf_h0.09_fine30_da+1 (UNSTEADY)",
  "R:xfine30:0.224": {
   "fit_cubic": 0.004088206356070027,
   "fit_quadratic": 0.005151716266678876,
   "iter": 1.1951438381634261e-05,
   "eff": 0.004088206356070027,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.009262715664843548,
   "d": {
    "1.0": 0.12364639470000005,
    "0.5": 0.13324087185,
    "0.25": 0.13850576980000007
   },
   "smallest_resolved_incidence_deg": 0.09351824432183176,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "R:xfine30:0.134": "not computable: R:sa-wf_h0.134_xfine30_da+0.25 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+0.5 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+1 (UNSTEADY), R:sa-wf_h0.134_xfine30_da0 (UNSTEADY)",
  "R:xfine30:0.09": "not computable: R:sa-wf_h0.09_xfine30_da+0.25 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da+0.5 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da+1 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-0.25 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-0.5 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-1 (UNSTEADY), R:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL)",
  "M:med30:0.224": {
   "fit_cubic": 0.00015239925854331908,
   "fit_quadratic": 0.00034758560069357125,
   "iter": 0.00027762000000008946,
   "eff": 0.00027762000000008946,
   "nonlinear": true,
   "chi2_90_upper_fit": 0.0003452934799447691,
   "d": {
    "1.0": 0.12805688749999988,
    "0.5": 0.1291053249999996,
    "0.25": 0.1286615000000011
   },
   "smallest_resolved_incidence_deg": 0.006131868060375051,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "M:med30:0.134": {
   "fit_cubic": 0.00039556241526573393,
   "fit_quadratic": 0.0016513916997233445,
   "iter": 0.00022419250002787567,
   "eff": 0.00039556241526573393,
   "nonlinear": true,
   "chi2_90_upper_fit": 0.0008962322009174288,
   "d": {
    "1.0": 0.052870157500000126,
    "0.5": 0.04840660928999996,
    "0.25": 0.047421349999998696
   },
   "smallest_resolved_incidence_deg": 0.02116164425777842,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "M:med30:0.09": {
   "fit_cubic": 0.0015245605195415427,
   "fit_quadratic": 0.0018352917136116491,
   "iter": 0.000591098128274893,
   "eff": 0.0015245605195415427,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.0034542215769984915,
   "d": {
    "1.0": 0.049700127945000006,
    "0.5": 0.054846403440000024,
    "0.25": 0.04912774570000078
   },
   "smallest_resolved_incidence_deg": 0.08676251963697924,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "M:fine30:0.224": {
   "fit_cubic": 0.00043264683140551645,
   "fit_quadratic": 0.0004530131821536946,
   "iter": 0.00014184958550125126,
   "eff": 0.00043264683140551645,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.000980254966008413,
   "d": {
    "1.0": 0.13020947738,
    "0.5": 0.13068243618999986,
    "0.25": 0.1317600038599993
   },
   "smallest_resolved_incidence_deg": 0.009398010482843815,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "M:fine30:0.134": {
   "fit_cubic": 0.0021478240721434835,
   "fit_quadratic": 0.001869794692977645,
   "iter": 0.0003562510933743158,
   "eff": 0.0021478240721434835,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.004866359949964993,
   "d": {
    "1.0": 0.06307128950999996,
    "0.5": 0.06396543760999984,
    "0.25": 0.06260984890000021
   },
   "smallest_resolved_incidence_deg": 0.09631900524041546,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "M:fine30:0.09": "not computable: M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY)",
  "M:xfine30:0.224": {
   "fit_cubic": 0.0005247703961729004,
   "fit_quadratic": 0.0005956275710029156,
   "iter": 1.3688393733288583e-05,
   "eff": 0.0005247703961729004,
   "nonlinear": false,
   "chi2_90_upper_fit": 0.001188980825750083,
   "d": {
    "1.0": 0.12024572606999995,
    "0.5": 0.12190438175999962,
    "0.25": 0.11975973170000032
   },
   "smallest_resolved_incidence_deg": 0.012343680489194094,
   "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"
  },
  "M:xfine30:0.134": "not computable: M:sa-wf_h0.134_xfine30_da0 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.25 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.5 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+1 (UNSTEADY)",
  "M:xfine30:0.09": "not computable: M:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+1 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-1 (UNSTEADY)",
  "pooled_noise_reduction_R_over_M": 8.231650045131992,
  "per_pair_ratio_R_over_M": {
   "med30:0.224": 9.38609056585402,
   "med30:0.134": 13.718524219765154,
   "med30:0.09": 2.309815603377871,
   "fine30:0.224": 24.06434736319243,
   "fine30:0.134": 5.579745335243422,
   "xfine30:0.224": 7.790466813457694
  }
 },
 "SURVIVES_2SIGMA": {
  "G6m@0.224": true,
  "G6m@0.134": false,
  "G3bm@0.224": true,
  "G3bm@0.134": false,
  "G3bm@0.09": false,
  "G7m_fine30@0.224": true,
  "G7m_fine30@0.134": true,
  "G7m_fine30@0.09": false,
  "G7m_xfine30@0.224": true,
  "G7m_xfine30@0.134": false,
  "G7m_xfine30@0.09": false,
  "G8m@0.224": true,
  "G8m@0.134": false,
  "G8m@0.09": false
 },
 "G6M_009": "not computable: M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY)",
 "remeshed_rules": {
  "G6R:med30:0.224": {
   "pass": false,
   "consistency": {
    "a": 0.13148646000000008,
    "b": 0.12990440079499987,
    "allowed": 0.03287161500000002,
    "noise_3rss": 0.02279114834149745,
    "margin": -0.9518715705023861,
    "unresolved": true,
    "pass": false
   },
   "resolved": true
  },
  "G6R:med30:0.134": {
   "pass": false,
   "consistency": {
    "a": 0.06544502254000051,
    "b": 0.06837944776499971,
    "allowed": 0.04746277559440967,
    "noise_3rss": 0.04746277559440967,
    "margin": -0.9381741756934917,
    "unresolved": true,
    "pass": false
   },
   "resolved": false
  },
  "G6R:med30:0.09": {
   "pass": false,
   "consistency": {
    "a": 0.03389297632000021,
    "b": 0.055484701575000184,
    "allowed": 0.030800140479917668,
    "noise_3rss": 0.030800140479917668,
    "margin": -0.29897315666211893,
    "unresolved": true,
    "pass": false
   },
   "resolved": false
  },
  "G6R:fine30:0.224": {
   "pass": false,
   "consistency": {
    "a": 0.1150105899999998,
    "b": 0.12378218459500001,
    "allowed": 0.09106224078649496,
    "noise_3rss": 0.09106224078649496,
    "margin": -0.9036747336849953,
    "unresolved": true,
    "pass": false
   },
   "resolved": false
  },
  "G6R:fine30:0.134": {
   "pass": false,
   "consistency": {
    "a": 0.009912736920000054,
    "b": 0.07793983025499984,
    "allowed": 0.10481991443988553,
    "noise_3rss": 0.10481991443988553,
    "margin": -0.3510098372193054,
    "unresolved": true,
    "pass": false
   },
   "resolved": false
  },
  "G6R:fine30:0.09": "not computable: R:sa-wf_h0.09_fine30_da+1 (UNSTEADY)",
  "G6R:xfine30:0.224": {
   "pass": false,
   "consistency": {
    "a": 0.13850576980000007,
    "b": 0.12364639470000005,
    "allowed": 0.03575720189766769,
    "noise_3rss": 0.03575720189766769,
    "margin": -0.5844368599499046,
    "unresolved": true,
    "pass": false
   },
   "resolved": true
  },
  "G6R:xfine30:0.134": "not computable: R:sa-wf_h0.134_xfine30_da+0.25 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+0.5 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+1 (UNSTEADY), R:sa-wf_h0.134_xfine30_da0 (UNSTEADY)",
  "G6R:xfine30:0.09": "not computable: R:sa-wf_h0.09_xfine30_da+0.25 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da+0.5 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da+1 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-0.25 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-0.5 (SOLVER_FAIL), R:sa-wf_h0.09_xfine30_da-1 (UNSTEADY), R:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL)",
  "G3bR:med30-fine30:0.224": {
   "a": 0.12990440079499987,
   "b": 0.12378218459500001,
   "allowed": 0.03247610019874997,
   "noise_3rss": 0.022767066177707254,
   "margin": -0.8114854874035795,
   "unresolved": true,
   "pass": false,
   "sign_ok": true
  },
  "G3bR:med30-fine30:0.134": {
   "a": 0.06837944776499971,
   "b": 0.07793983025499984,
   "allowed": 0.027907335668886327,
   "noise_3rss": 0.027907335668886327,
   "margin": -0.6574240334716392,
   "unresolved": true,
   "pass": false
  },
  "G3bR:med30-fine30:0.09": "not computable: R:sa-wf_h0.09_fine30_da+1 (UNSTEADY)",
  "G3bR:fine30-xfine30:0.224": {
   "a": 0.12378218459500001,
   "b": 0.12364639470000005,
   "allowed": 0.030945546148750003,
   "noise_3rss": 0.023727508464188286,
   "margin": -0.9956119729040411,
   "unresolved": true,
   "pass": false,
   "sign_ok": true
  },
  "G3bR:fine30-xfine30:0.134": "not computable: R:sa-wf_h0.134_xfine30_da+0.25 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+0.5 (UNSTEADY), R:sa-wf_h0.134_xfine30_da+1 (UNSTEADY), R:sa-wf_h0.134_xfine30_da0 (UNSTEADY)",
  "G3bR:fine30-xfine30:0.09": "not computable: R:sa-wf_h0.09_fine30_da+1 (UNSTEADY)"
 },
 "BLEND": {
  "0.224": {
   "d_linear": 0.12916577063,
   "d_smoothstep": 0.13020947738,
   "abs_diff_in_G3bm_bands": 0.03206238965091787
  },
  "0.134": "not computable: KeyError: 'xfine30'",
  "0.09": "not computable: M:sa-wf_h0.09_fine30_morphLin-da+1 (UNSTEADY)"
 },
 "MED30": {
  "full": false,
  "attached": false,
  "gates": {
   "G6m@0.224": {
    "value": true,
    "detail": {
     "sigma_eff": 0.00027762000000008946,
     "consistency": {
      "a": 0.1286615000000011,
      "b": 0.12805688749999988,
      "allowed": 0.032165375000000274,
      "noise_3rss": 0.0024281832975712103,
      "margin": -0.9812030016749003,
      "unresolved": false,
      "pass": true
     },
     "dCl_pm0.25": 0.06433075000000055,
     "resolved": true
    }
   },
   "G6m@0.134": {
    "value": true,
    "detail": {
     "sigma_eff": 0.00039556241526573393,
     "consistency": {
      "a": 0.047421349999998696,
      "b": 0.052870157500000126,
      "allowed": 0.013217539375000031,
      "noise_3rss": 0.0034597581222349716,
      "margin": -0.5877593139380063,
      "unresolved": false,
      "pass": true
     },
     "dCl_pm0.25": 0.023710674999999348,
     "resolved": true
    }
   },
   "G3bm@0.224": {
    "value": true,
    "detail": {
     "fine30": {
      "a": 0.12805688749999988,
      "b": 0.13020947738,
      "allowed": 0.032552369345,
      "noise_3rss": 0.001090482761470246,
      "margin": -0.9338730198964535,
      "unresolved": false,
      "pass": true
     },
     "xfine30": {
      "a": 0.12805688749999988,
      "b": 0.12024572606999995,
      "allowed": 0.03201422187499997,
      "noise_3rss": 0.0012593870528744553,
      "margin": -0.7560096428237819,
      "unresolved": false,
      "pass": true
     },
     "sign_ok": true
    }
   },
   "G3bm@0.134": {
    "value": false,
    "detail": {
     "reason": "M:sa-wf_h0.134_xfine30_da0 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.25 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+0.5 (UNSTEADY), M:sa-wf_h0.134_xfine30_morph-da+1 (UNSTEADY)",
     "bad_inputs": {
      "M:sa-wf_h0.134_xfine30_da0": "UNSTEADY",
      "M:sa-wf_h0.134_xfine30_morph-da+0.25": "UNSTEADY",
      "M:sa-wf_h0.134_xfine30_morph-da+0.5": "UNSTEADY",
      "M:sa-wf_h0.134_xfine30_morph-da+1": "UNSTEADY"
     }
    }
   },
   "G3bm@0.09": {
    "value": false,
    "detail": {
     "reason": "M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY), M:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da+1 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.25 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-0.5 (SOLVER_FAIL), M:sa-wf_h0.09_xfine30_morph-da-1 (UNSTEADY)",
     "bad_inputs": {
      "M:sa-wf_h0.09_fine30_morph-da+1": "UNSTEADY",
      "M:sa-wf_h0.09_xfine30_morph-da-1": "UNSTEADY",
      "M:sa-wf_h0.09_xfine30_morph-da-0.5": "SOLVER_FAIL",
      "M:sa-wf_h0.09_xfine30_morph-da-0.25": "SOLVER_FAIL",
      "M:sa-wf_h0.09_xfine30_da0": "SOLVER_FAIL",
      "M:sa-wf_h0.09_xfine30_morph-da+0.25": "SOLVER_FAIL",
      "M:sa-wf_h0.09_xfine30_morph-da+0.5": "SOLVER_FAIL",
      "M:sa-wf_h0.09_xfine30_morph-da+1": "SOLVER_FAIL"
     }
    }
   },
   "G7m_med30@0.224": {
    "value": true,
    "detail": {
     "a": 0.12805688749999988,
     "b": 0.12990440079499987,
     "allowed": 0.03247610019874997,
     "noise_3rss": 0.005558948889486772,
     "margin": -0.9431116025725557,
     "unresolved": false,
     "pass": true,
     "undetectable_bias": 0.03247610019874997,
     "dM_minus_dR_in_remesh_sigma_d": -1.002690914807682
    }
   },
   "G7m_med30@0.134": {
    "value": true,
    "detail": {
     "a": 0.052870157500000126,
     "b": 0.06837944776499971,
     "allowed": 0.017094861941249928,
     "noise_3rss": 0.01154195669360438,
     "margin": -0.09275135895800096,
     "unresolved": false,
     "pass": true,
     "undetectable_bias": 0.017094861941249928,
     "dM_minus_dR_in_remesh_sigma_d": -4.041890163824859
    }
   },
   "G7m_med30@0.09": {
    "value": true,
    "detail": {
     "a": 0.049700127945000006,
     "b": 0.055484701575000184,
     "allowed": 0.013871175393750046,
     "noise_3rss": 0.008140156231627392,
     "margin": -0.5829788416772135,
     "unresolved": false,
     "pass": true,
     "undetectable_bias": 0.013871175393750046,
     "dM_minus_dR_in_remesh_sigma_d": -2.32308110002332
    }
   },
   "G8m@0.224": {
    "value": true,
    "detail": {
     "1.0": {
      "a": 0.12805688749999988,
      "b": 0.12739771423500001,
      "allowed": 0.03201422187499997,
      "noise_3rss": 0.0008328600000002682,
      "margin": -0.9794099863625104,
      "unresolved": false,
      "pass": true
     },
     "0.25": {
      "a": 0.1286615000000011,
      "b": 0.12955307999999954,
      "allowed": 0.032388269999999886,
      "noise_3rss": 0.0033314400000010727,
      "margin": -0.9724721326579514,
      "unresolved": false,
      "pass": true
     }
    }
   },
   "G8m@0.134": {
    "value": false,
    "detail": {
     "1.0": {
      "a": 0.052870157500000126,
      "b": 0.06632107207500026,
      "allowed": 0.016580268018750066,
      "noise_3rss": 0.0011866872457972017,
      "margin": -0.1887396174905645,
      "unresolved": false,
      "pass": true
     },
     "0.25": {
      "a": 0.047421349999998696,
      "b": 0.06641294030000022,
      "allowed": 0.016603235075000056,
      "noise_3rss": 0.004746748983188807,
      "margin": 0.14384878695102513,
      "unresolved": false,
      "pass": false
     }
    }
   },
   "G8m@0.09": {
    "value": false,
    "detail": {
     "1.0": {
      "a": 0.049700127945000006,
      "b": 0.04903729365999998,
      "allowed": 0.012425031986250001,
      "noise_3rss": 0.004573681558624627,
      "margin": -0.9466533135903762,
      "unresolved": false,
      "pass": true
     },
     "0.25": {
      "a": 0.04912774570000078,
      "b": 0.043696340559999935,
      "allowed": 0.018294726234498508,
      "noise_3rss": 0.018294726234498508,
      "margin": -0.703116347827124,
      "unresolved": true,
      "pass": false
     }
    }
   }
  }
 },
 "series": {
  "Cl": {
   "0.671": "not computable: ValueError: remeshed sigma missing for [('fine30', 0.09), ('xfine30', 0.134), ('xfine30', 0.09)]",
   "0.448": "not computable: ValueError: remeshed sigma missing for [('fine30', 0.09), ('xfine30', 0.134), ('xfine30', 0.09)]",
   "0.313": "not computable: ValueError: remeshed sigma missing for [('fine30', 0.09), ('xfine30', 0.134), ('xfine30', 0.09)]",
   "0.224": {
    "values": {
     "med30": 1.34487500659,
     "fine30": 1.30828086883,
     "xfine30": 1.2714218219
    },
    "e2": -0.03659413775999987,
    "e3": -0.03685904693000008,
    "R": 1.0072391149570896,
    "noise": 0.029447783315148815,
    "label": "DIVERGENT",
    "coa30": 1.3602358150599998
   },
   "0.179": "not computable: ValueError: remeshed sigma missing for [('fine30', 0.09), ('xfine30', 0.134), ('xfine30', 0.09)]",
   "0.134": "not computable: R:sa-wf_h0.134_xfine30_da0 (UNSTEADY)",
   "0.09": "not computable: R:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL)"
  },
  "d_M": {
   "0.224": {
    "values": {
     "med30": 0.12805688749999988,
     "fine30": 0.13020947738,
     "xfine30": 0.12024572606999995
    },
    "e2": 0.002152589880000111,
    "e3": -0.009963751310000046,
    "R": -4.628727191637421,
    "noise": 0.001360245932799942,
    "label": "DIVERGENT"
   },
   "0.134": "not computable: M:sa-wf_h0.134_xfine30_morph-da+1 (UNSTEADY)",
   "0.09": "not computable: M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY)"
  },
  "d_R": {
   "0.224": {
    "values": {
     "med30": 0.12990440079499987,
     "fine30": 0.12378218459500001,
     "xfine30": 0.12364639470000005
    },
    "e2": -0.006122216199999864,
    "e3": -0.0001357898949999603,
    "R": 0.02217985947637121,
    "noise": 0.02237050951425166,
    "label": "NOT_RESOLVED"
   },
   "0.134": "not computable: R:sa-wf_h0.134_xfine30_da+1 (UNSTEADY)",
   "0.09": "not computable: R:sa-wf_h0.09_fine30_da+1 (UNSTEADY)"
  },
  "G2_by_level": {
   "coa30": {
    "mean_abs_e_nominal": 0.04392886483587542,
    "e_h": {
     "0.671": 0.04553633476510943,
     "0.448": 0.05353877560973408,
     "0.313": 0.05745409465231499,
     "0.224": 0.058051992641835026,
     "0.179": 0.005112072618299823,
     "0.134": -0.033574970850126284,
     "0.09": -0.05423381271370831
    },
    "peak_h": 0.179,
    "G2d_E": 0.36640301791169033,
    "peak_margin": -0.02268898821415033,
    "rise_breaks_after_h": [
     0.179
    ],
    "peak_ok": false,
    "G2d_pass": false
   },
   "med30": {
    "mean_abs_e_nominal": 0.04235815669937627,
    "e_h": {
     "0.671": 0.05042072927045904,
     "0.448": 0.055534506129111705,
     "0.313": 0.05734522151726895,
     "0.224": 0.04610367174752317,
     "0.179": 0.03725344198988112,
     "0.134": 0.007678621340690528,
     "0.09": -0.04217090490069941
    },
    "peak_h": 0.179,
    "G2d_E": 0.28832311751441925,
    "peak_margin": -0.009076697355000496,
    "rise_breaks_after_h": [
     0.179
    ],
    "peak_ok": false,
    "G2d_pass": true,
    "mean_abs_e_plus_0p15deg": 0.05454742070308505,
    "G2_pass": false,
    "peak_noise": 0.015348551926332483,
    "peak_margin_in_noise": -0.5913715768474689
   },
   "fine30": "not computable: R:sa-wf_h0.09_fine30_da+1 (UNSTEADY)",
   "xfine30": "not computable: R:sa-wf_h0.09_xfine30_da0 (SOLVER_FAIL), R:sa-wf_h0.134_xfine30_da0 (UNSTEADY)"
  },
  "level_stats": {
   "coa30": {
    "n_layers": [
     10,
     11,
     7,
     8
    ],
    "cells": [
     7349,
     9503
    ],
    "max_non_orthogonality": 63.170768,
    "yplus_airfoil_avg": [
     29.666109,
     30.412637
    ],
    "median_cost_to_plateau_min": 0.16133397586419546
   },
   "med30": {
    "n_layers": [
     7
    ],
    "cells": [
     13722,
     15919
    ],
    "max_non_orthogonality": 43.868342,
    "yplus_airfoil_avg": [
     30.951998,
     32.410412
    ],
    "median_cost_to_plateau_min": 0.26234184520832493
   },
   "fine30": {
    "n_layers": [
     4
    ],
    "cells": [
     25298,
     28022
    ],
    "max_non_orthogonality": 45.915118,
    "yplus_airfoil_avg": [
     31.398968,
     32.838458
    ],
    "median_cost_to_plateau_min": 0.5769322345397353
   },
   "xfine30": {
    "n_layers": [
     2
    ],
    "cells": [
     50303,
     52741
    ],
    "max_non_orthogonality": 46.098168,
    "yplus_airfoil_avg": [
     31.348203,
     32.646424
    ],
    "median_cost_to_plateau_min": 1.9645666177994943
   }
  },
  "PEAK": "not computable (an input case of fine30 or xfine30 is not valid)"
 },
 "replication": {
  "vs_T20B": {
   "cases": 41,
   "identical_mesh_sha": 36,
   "max_rel_dCl": 2.983578728965597e-06,
   "label": "NOT_BITWISE",
   "cpu_models": {
    "R:docs/evidence/t20c_registered_2026_10_20/kernel_remesh_run1/t20c": "Intel(R) Xeon(R) CPU @ 2.20GHz",
    "M:docs/evidence/t20c_registered_2026_10_20/kernel_morph_run1/t20c": "AMD EPYC 7B12",
    "S:docs/evidence/t20c_registered_2026_10_20/kernel_shape_run1/t20c": "Intel(R) Xeon(R) CPU @ 2.20GHz"
   }
  },
  "cross_kernel": {
   "cases": 14,
   "identical_mesh_sha": 12,
   "identical_Cl": 14,
   "label": "CROSS_KERNEL_DIFFERENT",
   "cpu_models": {
    "R:docs/evidence/t20c_registered_2026_10_20/kernel_remesh_run1/t20c": "Intel(R) Xeon(R) CPU @ 2.20GHz",
    "M:docs/evidence/t20c_registered_2026_10_20/kernel_morph_run1/t20c": "AMD EPYC 7B12",
    "S:docs/evidence/t20c_registered_2026_10_20/kernel_shape_run1/t20c": "Intel(R) Xeon(R) CPU @ 2.20GHz"
   },
   "note": "a difference with a different CPU model is reported, not a defect"
  }
 },
 "shapes": {
  "camber:0.224": {
   "med30": {
    "dCl": {
     "0.25": 0.026767329999999312,
     "0.5": 0.05383438000000029
    },
    "d_per_mm": {
     "0.25": 0.053534659999998624,
     "0.5": 0.05383438000000029
    },
    "sigma_eff_incidence_scan": 0.00027762000000008946,
    "fit5_quadratic_sigma": 6.707316237982774e-05,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.053534659999998624,
     "b": 0.05383438000000029,
     "allowed": 0.013458595000000073,
     "noise_3rss": 0.002633734572048685,
     "margin": -0.9777302162668787,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": {
    "dCl": {
     "0.25": 0.022956353349999903,
     "0.5": 0.046087056900000034
    },
    "d_per_mm": {
     "0.25": 0.045912706699999806,
     "0.5": 0.046087056900000034
    },
    "sigma_eff_incidence_scan": 0.00043264683140551645,
    "fit5_quadratic_sigma": 5.326238638779219e-05,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.045912706699999806,
     "b": 0.046087056900000034,
     "allowed": 0.011521764225000009,
     "noise_3rss": 0.004104448229088899,
     "margin": -0.9848677514488691,
     "unresolved": false,
     "pass": true
    }
   },
   "med30_vs_fine30": {
    "a": 0.05383438000000029,
    "b": 0.046087056900000034,
    "allowed": 0.013458595000000073,
    "noise_3rss": 0.002180965522940492,
    "margin": -0.42435870163265804,
    "unresolved": false,
    "pass": true
   },
   "morph_vs_remesh_fine30": {
    "a": 0.046087056900000034,
    "b": 0.0539679099999999,
    "allowed": 0.04420979720547197,
    "noise_3rss": 0.04420979720547197,
    "margin": -0.8217396686220395,
    "unresolved": false,
    "pass": true
   }
  },
  "camber:0.134": {
   "med30": {
    "dCl": {
     "0.25": 0.009774667980000595,
     "0.5": 0.01782033428999963
    },
    "d_per_mm": {
     "0.25": 0.01954933596000119,
     "0.5": 0.01782033428999963
    },
    "sigma_eff_incidence_scan": 0.00039556241526573393,
    "fit5_quadratic_sigma": 0.000386965301836623,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.01954933596000119,
     "b": 0.01782033428999963,
     "allowed": 0.004887333990000298,
     "noise_3rss": 0.003752634566991233,
     "margin": -0.646228051215821,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": {
    "dCl": {
     "0.25": 0.009330021440000058,
     "0.5": 0.0183420944299999
    },
    "d_per_mm": {
     "0.25": 0.018660042880000116,
     "0.5": 0.0183420944299999
    },
    "sigma_eff_incidence_scan": 0.0021478240721434835,
    "fit5_quadratic_sigma": 7.158904324491719e-05,
    "expected_sign_ok": true,
    "resolved": false,
    "linearity": {
     "a": 0.018660042880000116,
     "b": 0.0183420944299999,
     "allowed": 0.020376048243933645,
     "noise_3rss": 0.020376048243933645,
     "margin": -0.9843959708872952,
     "unresolved": false,
     "pass": true
    }
   },
   "med30_vs_fine30": {
    "a": 0.01782033428999963,
    "b": 0.0183420944299999,
    "allowed": 0.009265695961259347,
    "noise_3rss": 0.009265695961259347,
    "margin": -0.9436890502147065,
    "unresolved": false,
    "pass": true
   },
   "morph_vs_remesh_fine30": {
    "a": 0.0183420944299999,
    "b": 0.04086322772000006,
    "allowed": 0.05165523788467072,
    "noise_3rss": 0.05165523788467072,
    "margin": -0.5640106557967558,
    "unresolved": false,
    "pass": true
   }
  },
  "camber:0.09": {
   "med30": {
    "dCl": {
     "0.25": 0.007997544679999802,
     "0.5": 0.015290398209999667
    },
    "d_per_mm": {
     "0.25": 0.015995089359999604,
     "0.5": 0.015290398209999667
    },
    "sigma_eff_incidence_scan": 0.0015245605195415427,
    "fit5_quadratic_sigma": 0.00015978453694033058,
    "expected_sign_ok": true,
    "resolved": false,
    "linearity": {
     "a": 0.015995089359999604,
     "b": 0.015290398209999667,
     "allowed": 0.014463251017562753,
     "noise_3rss": 0.014463251017562753,
     "margin": -0.9512771264811605,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": "not computable: M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY)",
   "med30_vs_fine30": "not computable",
   "morph_vs_remesh_fine30": "not computable"
  },
  "flap:0.224": {
   "med30": {
    "dCl": {
     "0.25": 0.04082525999999986,
     "0.5": 0.08213483500000018
    },
    "d_per_mm": {
     "0.25": 0.08165051999999973,
     "0.5": 0.08213483500000018
    },
    "sigma_eff_incidence_scan": 0.00027762000000008946,
    "fit5_quadratic_sigma": 0.00010846954295566325,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.08165051999999973,
     "b": 0.08213483500000018,
     "allowed": 0.020533708750000046,
     "noise_3rss": 0.002633734572048685,
     "margin": -0.9764136617550663,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": {
    "dCl": {
     "0.25": 0.03691470500000005,
     "0.5": 0.07408539248000046
    },
    "d_per_mm": {
     "0.25": 0.0738294100000001,
     "0.5": 0.07408539248000046
    },
    "sigma_eff_incidence_scan": 0.00043264683140551645,
    "fit5_quadratic_sigma": 0.00018629231961977548,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.0738294100000001,
     "b": 0.07408539248000046,
     "allowed": 0.018521348120000114,
     "noise_3rss": 0.004104448229088899,
     "margin": -0.9861790578989258,
     "unresolved": false,
     "pass": true
    }
   },
   "med30_vs_fine30": {
    "a": 0.08213483500000018,
    "b": 0.07408539248000046,
    "allowed": 0.020533708750000046,
    "noise_3rss": 0.002180965522940492,
    "margin": -0.6079888627036404,
    "unresolved": false,
    "pass": true
   },
   "morph_vs_remesh_fine30": {
    "a": 0.07408539248000046,
    "b": 0.052770931609999794,
    "allowed": 0.04420979720547197,
    "noise_3rss": 0.04420979720547197,
    "margin": -0.5178792435772016,
    "unresolved": false,
    "pass": true
   }
  },
  "flap:0.134": {
   "med30": {
    "dCl": {
     "0.25": 0.026926036589999924,
     "0.5": 0.051862578840000007
    },
    "d_per_mm": {
     "0.25": 0.05385207317999985,
     "0.5": 0.051862578840000007
    },
    "sigma_eff_incidence_scan": 0.00039556241526573393,
    "fit5_quadratic_sigma": 0.00047517557900402034,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.05385207317999985,
     "b": 0.051862578840000007,
     "allowed": 0.013463018294999962,
     "noise_3rss": 0.003752634566991233,
     "margin": -0.8522252368372164,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": {
    "dCl": {
     "0.25": 0.027588176859999924,
     "0.5": 0.0548069818000001
    },
    "d_per_mm": {
     "0.25": 0.05517635371999985,
     "0.5": 0.0548069818000001
    },
    "sigma_eff_incidence_scan": 0.0021478240721434835,
    "fit5_quadratic_sigma": 0.00014638870745833633,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.05517635371999985,
     "b": 0.0548069818000001,
     "allowed": 0.020376048243933645,
     "noise_3rss": 0.020376048243933645,
     "margin": -0.9818722494382727,
     "unresolved": false,
     "pass": true
    }
   },
   "med30_vs_fine30": {
    "a": 0.051862578840000007,
    "b": 0.0548069818000001,
    "allowed": 0.013701745450000025,
    "noise_3rss": 0.009265695961259347,
    "margin": -0.785107454320713,
    "unresolved": false,
    "pass": true
   },
   "morph_vs_remesh_fine30": {
    "a": 0.0548069818000001,
    "b": 0.05338234566000044,
    "allowed": 0.05165523788467072,
    "noise_3rss": 0.05165523788467072,
    "margin": -0.9724202965983739,
    "unresolved": false,
    "pass": true
   }
  },
  "flap:0.09": {
   "med30": {
    "dCl": {
     "0.25": 0.028109870000000203,
     "0.5": 0.057260246500000056
    },
    "d_per_mm": {
     "0.25": 0.05621974000000041,
     "0.5": 0.057260246500000056
    },
    "sigma_eff_incidence_scan": 0.0015245605195415427,
    "fit5_quadratic_sigma": 0.00033875873980684847,
    "expected_sign_ok": true,
    "resolved": true,
    "linearity": {
     "a": 0.05621974000000041,
     "b": 0.057260246500000056,
     "allowed": 0.014463251017562753,
     "noise_3rss": 0.014463251017562753,
     "margin": -0.9280586018498773,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": "not computable: M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY)",
   "med30_vs_fine30": "not computable",
   "morph_vs_remesh_fine30": "not computable"
  },
  "heave:0.224": {
   "med30": {
    "dCl": {
     "0.25": -0.003660044999999945,
     "0.5": -0.0074225155799994
    },
    "d_per_mm": {
     "0.25": -0.00732008999999989,
     "0.5": -0.0074225155799994
    },
    "sigma_eff_incidence_scan": 0.00027762000000008946,
    "fit5_quadratic_sigma": 2.533088233631025e-05,
    "expected_sign_ok": null,
    "resolved": true,
    "linearity": {
     "a": -0.00732008999999989,
     "b": -0.0074225155799994,
     "allowed": 0.002633734572048685,
     "noise_3rss": 0.002633734572048685,
     "margin": -0.961110135741645,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": {
    "dCl": {
     "0.25": -0.003099540400000045,
     "0.5": -0.006387905669999805
    },
    "d_per_mm": {
     "0.25": -0.00619908080000009,
     "0.5": -0.006387905669999805
    },
    "sigma_eff_incidence_scan": 0.00043264683140551645,
    "fit5_quadratic_sigma": 4.250788489893621e-05,
    "expected_sign_ok": null,
    "resolved": true,
    "linearity": {
     "a": -0.00619908080000009,
     "b": -0.006387905669999805,
     "allowed": 0.004104448229088899,
     "noise_3rss": 0.004104448229088899,
     "margin": -0.9539950659722097,
     "unresolved": false,
     "pass": true
    }
   },
   "med30_vs_fine30": {
    "a": -0.0074225155799994,
    "b": -0.006387905669999805,
    "allowed": 0.002180965522940492,
    "noise_3rss": 0.002180965522940492,
    "margin": -0.5256184019797434,
    "unresolved": false,
    "pass": true
   },
   "morph_vs_remesh_fine30": {
    "a": -0.006387905669999805,
    "b": 0.007841176049999676,
    "allowed": 0.04420979720547197,
    "noise_3rss": 0.04420979720547197,
    "margin": -0.6781464150611777,
    "unresolved": false,
    "pass": true
   }
  },
  "heave:0.134": {
   "med30": {
    "dCl": {
     "0.25": 0.002393878579999509,
     "0.5": 0.0051961815399999
    },
    "d_per_mm": {
     "0.25": 0.004787757159999018,
     "0.5": 0.0051961815399999
    },
    "sigma_eff_incidence_scan": 0.00039556241526573393,
    "fit5_quadratic_sigma": 0.00011081653894914207,
    "expected_sign_ok": null,
    "resolved": false,
    "linearity": {
     "a": 0.004787757159999018,
     "b": 0.0051961815399999,
     "allowed": 0.003752634566991233,
     "noise_3rss": 0.003752634566991233,
     "margin": -0.8911632953569613,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": {
    "dCl": {
     "0.25": 0.002120655099999702,
     "0.5": 0.0034936252499999654
    },
    "d_per_mm": {
     "0.25": 0.004241310199999404,
     "0.5": 0.0034936252499999654
    },
    "sigma_eff_incidence_scan": 0.0021478240721434835,
    "fit5_quadratic_sigma": 0.00017197033312692432,
    "expected_sign_ok": null,
    "resolved": false,
    "linearity": {
     "a": 0.004241310199999404,
     "b": 0.0034936252499999654,
     "allowed": 0.020376048243933645,
     "noise_3rss": 0.020376048243933645,
     "margin": -0.9633056939673256,
     "unresolved": false,
     "pass": true
    }
   },
   "med30_vs_fine30": {
    "a": 0.0051961815399999,
    "b": 0.0034936252499999654,
    "allowed": 0.009265695961259347,
    "noise_3rss": 0.009265695961259347,
    "margin": -0.8162516558800909,
    "unresolved": false,
    "pass": true
   },
   "morph_vs_remesh_fine30": {
    "a": 0.0034936252499999654,
    "b": 0.006829577310000001,
    "allowed": 0.05165523788467072,
    "noise_3rss": 0.05165523788467072,
    "margin": -0.9354189004521065,
    "unresolved": false,
    "pass": true
   }
  },
  "heave:0.09": {
   "med30": {
    "dCl": {
     "0.25": 0.0040031874999999495,
     "0.5": 0.009427072500000078
    },
    "d_per_mm": {
     "0.25": 0.008006374999999899,
     "0.5": 0.009427072500000078
    },
    "sigma_eff_incidence_scan": 0.0015245605195415427,
    "fit5_quadratic_sigma": 0.0003782912946082981,
    "expected_sign_ok": null,
    "resolved": false,
    "linearity": {
     "a": 0.008006374999999899,
     "b": 0.009427072500000078,
     "allowed": 0.014463251017562753,
     "noise_3rss": 0.014463251017562753,
     "margin": -0.9017719115657314,
     "unresolved": false,
     "pass": true
    }
   },
   "fine30": "not computable: M:sa-wf_h0.09_fine30_morph-da+1 (UNSTEADY)",
   "med30_vs_fine30": "not computable",
   "morph_vs_remesh_fine30": "not computable"
  },
  "label": "SHAPE_NOT_RESOLVED",
  "holds": {
   "resolved": false,
   "linear": false,
   "mesh": false,
   "remesh": false
  }
 },
 "UNSTEADY_cases": {
  "R:sa-wf_h0.134_xfine30_da+0.25": {
   "tail_rel_std": 0.013882608241898072,
   "tail_min": 1.36140444,
   "tail_max": 1.41402363
  },
  "R:sa-wf_h0.134_xfine30_da0": {
   "tail_rel_std": 0.007392271815241626,
   "tail_min": 1.31199414,
   "tail_max": 1.34011186
  },
  "R:sa-wf_h0.134_xfine30_da+0.5": {
   "tail_rel_std": 0.012910590420793164,
   "tail_min": 1.37359987,
   "tail_max": 1.42376594
  },
  "R:sa-wf_h0.134_xfine30_da+1": {
   "tail_rel_std": 0.019492255898540353,
   "tail_min": 1.44375135,
   "tail_max": 1.52555111
  },
  "R:sa-wf_h0.09_xfine30_da-1": {
   "tail_rel_std": 0.020344087169045004,
   "tail_min": 1.20087323,
   "tail_max": 1.27166034
  },
  "R:sa-wf_h0.09_fine30_da+1": {
   "tail_rel_std": 0.0188143320965531,
   "tail_min": 1.35938383,
   "tail_max": 1.43294215
  },
  "M:sa-wf_h0.134_xfine30_da0": {
   "tail_rel_std": 0.007392271815241626,
   "tail_min": 1.31199414,
   "tail_max": 1.34011186
  },
  "M:sa-wf_h0.134_xfine30_morph-da+0.25": {
   "tail_rel_std": 0.010834021609999214,
   "tail_min": 1.34015153,
   "tail_max": 1.38355644
  },
  "M:sa-wf_h0.134_xfine30_morph-da+0.5": {
   "tail_rel_std": 0.013126457531247488,
   "tail_min": 1.37311634,
   "tail_max": 1.42169064
  },
  "M:sa-wf_h0.134_xfine30_morph-da+1": {
   "tail_rel_std": 0.019261231553397925,
   "tail_min": 1.42077671,
   "tail_max": 1.49976084
  },
  "M:sa-wf_h0.09_xfine30_morph-da-1": {
   "tail_rel_std": 0.020433554916886913,
   "tail_min": 1.19108461,
   "tail_max": 1.26033596
  },
  "M:sa-wf_h0.09_fine30_morph-da+1": {
   "tail_rel_std": 0.01910006260005358,
   "tail_min": 1.3540533,
   "tail_max": 1.42733544
  },
  "M:sa-wf_h0.09_fine30_morphB2-da+1": {
   "tail_rel_std": 0.014995119702675976,
   "tail_min": 1.35144346,
   "tail_max": 1.40893536
  },
  "M:sa-wf_h0.09_fine30_morphLin-da+1": {
   "tail_rel_std": 0.018906627936429946,
   "tail_min": 1.354568,
   "tail_max": 1.42588107
  }
 }
}
```

## Cases

| kernel | case | class | Cl | Cd | Cl raw tail rel std | Cl block rel std | iters to plateau | cost min | capped wall min | cells | layers | max non-orth | morph area ratio | s per cell-iter (x1e6) | RSS MB | y+ airfoil min/avg/max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R | sa-wf_h0.09_coa30_da0 | VALID | 1.2958 | 0.0681 | 6.37e-05 | 1.71e-16 | 105 | 0.1 | 3.1 | 7349 | 7 | 49.437042 | --- | 4.85 | 65 | 2.5/30.0/65.5 |
| R | sa-wf_h0.09_fine30_da+0.25 | VALID | 1.3144 | 0.0633 | 1.30e-04 | 8.12e-05 | 99 | 0.4 | 10.3 | 25581 | 4 | 41.153817 | --- | 4.75 | 93 | 3.1/32.3/68.0 |
| R | sa-wf_h0.09_fine30_da+0.5 | VALID | 1.3367 | 0.0661 | 1.13e-04 | 6.29e-05 | 146 | 0.5 | 10.1 | 25469 | 4 | 43.878974 | --- | 4.64 | 95 | 3.2/32.3/68.3 |
| R | sa-wf_h0.09_fine30_da+1 | UNSTEADY | 1.3966 | 0.0730 | 1.88e-02 | 3.18e-03 | 5001 | 10.7 | 10.7 | 25619 | 4 | 45.164321 | --- | 4.94 | 92 | 2.2/32.3/69.1 |
| R | sa-wf_h0.09_fine30_da-0.25 | VALID | 1.3094 | 0.0586 | 1.44e-04 | 9.35e-05 | 126 | 0.4 | 10.3 | 25431 | 4 | 34.978605 | --- | 4.76 | 93 | 2.3/32.4/67.6 |
| R | sa-wf_h0.09_fine30_da-0.5 | VALID | 1.2779 | 0.0557 | 5.80e-05 | 4.13e-05 | 131 | 0.4 | 10.2 | 25395 | 4 | 42.779008 | --- | 4.72 | 93 | 3.4/32.4/67.1 |
| R | sa-wf_h0.09_fine30_da-1 | VALID | 1.2333 | 0.0515 | 1.83e-04 | 1.13e-04 | 76 | 0.3 | 10.2 | 25299 | 4 | 40.22487 | --- | 4.77 | 94 | 2.9/32.3/66.2 |
| R | sa-wf_h0.09_fine30_da0 | VALID | 1.3055 | 0.0608 | 5.87e-05 | 3.91e-05 | 73 | 0.3 | 9.8 | 25298 | 4 | 36.800861 | --- | 4.54 | 93 | 3.4/32.4/67.7 |
| R | sa-wf_h0.09_med30_da+0.25 | VALID | 1.3220 | 0.0647 | 1.10e-04 | 2.14e-09 | 127 | 0.2 | 5.6 | 13761 | 7 | 35.999862 | --- | 4.77 | 76 | 2.8/31.8/67.3 |
| R | sa-wf_h0.09_med30_da+0.5 | VALID | 1.3404 | 0.0671 | 3.44e-04 | 2.12e-04 | 68 | 0.2 | 5.7 | 13828 | 7 | 39.160998 | --- | 4.87 | 75 | 3.0/31.8/67.6 |
| R | sa-wf_h0.09_med30_da+1 | VALID | 1.3637 | 0.0729 | 9.49e-05 | 3.26e-16 | 131 | 0.3 | 5.8 | 13809 | 7 | 39.541342 | --- | 4.94 | 76 | 2.9/31.7/68.0 |
| R | sa-wf_h0.09_med30_da-0.25 | VALID | 1.3050 | 0.0597 | 1.43e-04 | 1.70e-16 | 217 | 0.4 | 5.9 | 13671 | 7 | 35.877935 | --- | 5.03 | 75 | 1.9/31.8/67.0 |
| R | sa-wf_h0.09_med30_da-0.5 | VALID | 1.2908 | 0.0574 | 1.61e-04 | 8.50e-05 | 61 | 0.2 | 5.8 | 13660 | 7 | 38.945663 | --- | 4.99 | 76 | 3.6/31.8/66.5 |
| R | sa-wf_h0.09_med30_da-1 | VALID | 1.2527 | 0.0530 | 2.32e-04 | 1.61e-04 | 113 | 0.2 | 5.9 | 13566 | 7 | 40.607922 | --- | 5.08 | 75 | 2.6/31.7/65.8 |
| R | sa-wf_h0.09_med30_da0 | VALID | 1.3123 | 0.0617 | 9.71e-05 | 3.38e-16 | 63 | 0.2 | 5.8 | 13722 | 7 | 41.637644 | --- | 4.94 | 76 | 2.0/31.8/67.1 |
| R | sa-wf_h0.09_xfine30_da+0.25 | SOLVER_FAIL | 1.4001 | 0.0685 | 3.86e-02 | 7.22e-03 | 15001 | - | 61.5 | 49682 | 2 | 36.850877 | --- | 4.93 | 136 | 2.2/32.5/69.1 |
| R | sa-wf_h0.09_xfine30_da+0.5 | SOLVER_FAIL | 1.4054 | 0.0726 | 4.54e-02 | 8.53e-03 | 15001 | - | 61.4 | 49588 | 2 | 39.016637 | --- | 4.92 | 132 | 1.8/32.7/69.4 |
| R | sa-wf_h0.09_xfine30_da+1 | SOLVER_FAIL | 1.4904 | 0.0790 | 5.21e-02 | 9.07e-03 | 15001 | - | 63.4 | 49840 | 2 | 40.050861 | --- | 5.06 | 132 | 2.6/32.6/70.5 |
| R | sa-wf_h0.09_xfine30_da-0.25 | SOLVER_FAIL | 1.3295 | 0.0617 | 3.36e-02 | 7.20e-03 | 15001 | - | 62.5 | 49577 | 2 | 37.329448 | --- | 5.02 | 130 | 2.5/32.6/68.2 |
| R | sa-wf_h0.09_xfine30_da-0.5 | SOLVER_FAIL | 1.3225 | 0.0589 | 2.72e-02 | 5.75e-03 | 15001 | - | 63.1 | 49621 | 2 | 42.075538 | --- | 5.06 | 131 | 1.9/32.7/67.9 |
| R | sa-wf_h0.09_xfine30_da-1 | UNSTEADY | 1.2365 | 0.0540 | 2.03e-02 | 4.29e-03 | 5001 | 20.7 | 20.7 | 49271 | 2 | 43.687759 | --- | 4.97 | 131 | 2.4/32.5/66.5 |
| R | sa-wf_h0.09_xfine30_da0 | SOLVER_FAIL | 1.3366 | 0.0649 | 3.61e-02 | 6.82e-03 | 15001 | - | 62.3 | 49699 | 2 | 40.293849 | --- | 4.99 | 136 | 2.1/32.6/68.5 |
| R | sa-wf_h0.134_coa30_da0 | VALID | 1.3389 | 0.0529 | 4.24e-05 | 0.00e+00 | 234 | 0.2 | 3.4 | 7767 | 8 | 42.625798 | --- | 5.07 | 66 | 4.4/30.3/62.5 |
| R | sa-wf_h0.134_fine30_da+0.25 | VALID | 1.3859 | 0.0492 | 1.97e-04 | 1.46e-04 | 182 | 0.6 | 10.5 | 26051 | 4 | 37.667232 | --- | 4.73 | 95 | 2.0/32.8/65.0 |
| R | sa-wf_h0.134_fine30_da+0.5 | VALID | 1.4150 | 0.0508 | 2.87e-05 | 1.40e-05 | 187 | 0.6 | 10.5 | 26059 | 4 | 41.614925 | --- | 4.74 | 95 | 3.1/32.8/65.6 |
| R | sa-wf_h0.134_fine30_da+1 | VALID | 1.4372 | 0.0555 | 1.45e-04 | 1.24e-04 | 170 | 0.5 | 10.2 | 26098 | 4 | 37.733562 | --- | 4.60 | 94 | 2.5/32.6/65.9 |
| R | sa-wf_h0.134_fine30_da-0.25 | VALID | 1.3810 | 0.0447 | 4.01e-05 | 1.39e-05 | 200 | 0.6 | 10.4 | 25904 | 4 | 34.993118 | --- | 4.71 | 92 | 3.3/33.0/64.9 |
| R | sa-wf_h0.134_fine30_da-0.5 | VALID | 1.3469 | 0.0432 | 1.21e-04 | 6.98e-09 | 258 | 0.7 | 10.7 | 25953 | 4 | 43.630159 | --- | 4.84 | 96 | 1.8/32.9/64.4 |
| R | sa-wf_h0.134_fine30_da-1 | VALID | 1.2813 | 0.0401 | 1.08e-04 | 1.73e-16 | 238 | 0.7 | 10.5 | 25878 | 4 | 33.485361 | --- | 4.77 | 95 | 2.9/32.9/63.4 |
| R | sa-wf_h0.134_fine30_da0 | VALID | 1.4003 | 0.0462 | 2.54e-04 | 1.90e-04 | 186 | 0.6 | 10.5 | 26074 | 4 | 44.877668 | --- | 4.75 | 94 | 1.6/32.8/65.2 |
| R | sa-wf_h0.134_med30_da+0.25 | VALID | 1.4045 | 0.0495 | 1.54e-04 | 1.58e-16 | 127 | 0.3 | 5.9 | 14212 | 7 | 36.61511 | --- | 4.84 | 76 | 2.7/32.1/64.7 |
| R | sa-wf_h0.134_med30_da+0.5 | VALID | 1.4274 | 0.0518 | 1.45e-04 | 0.00e+00 | 129 | 0.3 | 5.7 | 14265 | 7 | 48.740071 | --- | 4.72 | 77 | 1.9/32.2/65.0 |
| R | sa-wf_h0.134_med30_da+1 | VALID | 1.4487 | 0.0567 | 1.18e-04 | 5.02e-05 | 125 | 0.3 | 5.8 | 14284 | 7 | 38.502214 | --- | 4.79 | 76 | 2.8/32.1/65.2 |
| R | sa-wf_h0.134_med30_da-0.25 | VALID | 1.3718 | 0.0463 | 1.46e-04 | 4.64e-05 | 123 | 0.3 | 5.9 | 14075 | 7 | 43.633958 | --- | 4.96 | 77 | 2.0/32.2/64.0 |
| R | sa-wf_h0.134_med30_da-0.5 | VALID | 1.3622 | 0.0447 | 1.58e-04 | 1.63e-16 | 125 | 0.3 | 5.8 | 14126 | 7 | 41.487483 | --- | 4.85 | 78 | 2.0/32.4/63.9 |
| R | sa-wf_h0.134_med30_da-1 | VALID | 1.3119 | 0.0413 | 1.67e-04 | 1.69e-16 | 121 | 0.3 | 6.0 | 14112 | 7 | 39.167408 | --- | 4.97 | 76 | 3.0/32.3/63.0 |
| R | sa-wf_h0.134_med30_da0 | VALID | 1.3960 | 0.0480 | 1.40e-04 | 4.15e-05 | 121 | 0.3 | 6.0 | 14151 | 7 | 38.62036 | --- | 4.95 | 76 | 2.2/32.3/64.5 |
| R | sa-wf_h0.134_xfine30_da+0.25 | UNSTEADY | 1.3883 | 0.0503 | 1.39e-02 | 2.93e-03 | 5000 | 21.4 | 21.4 | 50297 | 2 | 37.28144 | --- | 5.04 | 136 | 1.9/32.8/65.5 |
| R | sa-wf_h0.134_xfine30_da+0.5 | UNSTEADY | 1.3989 | 0.0527 | 1.29e-02 | 2.88e-03 | 5001 | 20.8 | 20.9 | 50463 | 2 | 34.658823 | --- | 4.88 | 135 | 2.2/32.7/65.7 |
| R | sa-wf_h0.134_xfine30_da+1 | UNSTEADY | 1.4842 | 0.0576 | 1.95e-02 | 4.19e-03 | 5001 | 21.2 | 21.2 | 50483 | 2 | 47.60624 | --- | 4.97 | 132 | 2.2/32.9/66.8 |
| R | sa-wf_h0.134_xfine30_da-0.25 | VALID | 1.2803 | 0.0450 | 9.08e-06 | 6.92e-06 | 370 | 1.8 | 20.1 | 50237 | 2 | 42.256115 | --- | 4.72 | 135 | 2.0/32.6/64.2 |
| R | sa-wf_h0.134_xfine30_da-0.5 | VALID | 1.2671 | 0.0431 | 4.90e-03 | 6.98e-04 | 5001 | 21.2 | 21.2 | 50310 | 2 | 36.914331 | --- | 4.99 | 136 | 2.1/32.7/64.0 |
| R | sa-wf_h0.134_xfine30_da-1 | VALID | 1.2209 | 0.0397 | 5.51e-06 | 4.98e-09 | 375 | 1.8 | 20.5 | 50044 | 2 | 36.971239 | --- | 4.83 | 131 | 2.1/32.7/63.2 |
| R | sa-wf_h0.134_xfine30_da0 | UNSTEADY | 1.3262 | 0.0474 | 7.39e-03 | 1.43e-03 | 5001 | 21.6 | 21.6 | 50303 | 2 | 40.539013 | --- | 5.08 | 137 | 2.0/32.6/64.9 |
| R | sa-wf_h0.179_coa30_da0 | VALID | 1.3684 | 0.0441 | 7.04e-05 | 6.15e-07 | 118 | 0.2 | 3.6 | 8318 | 10 | 63.170768 | --- | 4.99 | 66 | 2.5/30.3/60.4 |
| R | sa-wf_h0.179_fine30_da0 | VALID | 1.3492 | 0.0377 | 3.49e-05 | 5.99e-06 | 224 | 0.6 | 10.6 | 26425 | 4 | 45.915118 | --- | 4.71 | 97 | 2.1/32.8/62.3 |
| R | sa-wf_h0.179_med30_da0 | VALID | 1.4122 | 0.0389 | 1.77e-04 | 0.00e+00 | 131 | 0.3 | 6.0 | 14536 | 7 | 40.777795 | --- | 4.83 | 76 | 2.8/32.4/62.4 |
| R | sa-wf_h0.179_xfine30_da0 | VALID | 1.3098 | 0.0370 | 6.50e-06 | 6.50e-10 | 446 | 2.1 | 20.3 | 50802 | 2 | 45.825788 | --- | 4.72 | 133 | 1.7/32.6/62.4 |
| R | sa-wf_h0.224_coa30_da0 | VALID | 1.3602 | 0.0389 | 1.57e-04 | 1.40e-10 | 120 | 0.2 | 4.1 | 8660 | 11 | 43.186814 | --- | 5.55 | 67 | 1.0/30.3/59.9 |
| R | sa-wf_h0.224_fine30_da+0.25 | VALID | 1.3389 | 0.0331 | 8.79e-05 | 1.66e-16 | 246 | 0.7 | 10.9 | 26826 | 4 | 38.001059 | --- | 4.77 | 93 | 3.1/32.6/64.2 |
| R | sa-wf_h0.224_fine30_da+0.5 | VALID | 1.3935 | 0.0343 | 3.52e-05 | 0.00e+00 | 244 | 0.7 | 10.5 | 26913 | 4 | 53.723773 | --- | 4.61 | 97 | 1.6/32.8/65.8 |
| R | sa-wf_h0.224_fine30_da+1 | VALID | 1.4209 | 0.0372 | 8.16e-05 | 9.75e-08 | 254 | 0.7 | 10.8 | 26863 | 4 | 39.619638 | --- | 4.74 | 95 | 2.3/32.6/67.2 |
| R | sa-wf_h0.224_fine30_da-0.25 | VALID | 1.2814 | 0.0309 | 8.53e-05 | 0.00e+00 | 254 | 0.7 | 10.9 | 26838 | 4 | 49.954551 | --- | 4.77 | 96 | 1.6/32.8/62.3 |
| R | sa-wf_h0.224_fine30_da-0.5 | VALID | 1.2389 | 0.0299 | 6.69e-05 | 3.07e-09 | 242 | 0.7 | 10.4 | 26684 | 4 | 40.472827 | --- | 4.59 | 95 | 1.3/32.8/61.2 |
| R | sa-wf_h0.224_fine30_da-1 | VALID | 1.1734 | 0.0283 | 6.18e-05 | 0.00e+00 | 224 | 0.7 | 11.1 | 26707 | 4 | 38.988645 | --- | 4.91 | 96 | 2.3/32.7/58.7 |
| R | sa-wf_h0.224_fine30_da0 | VALID | 1.3083 | 0.0318 | 6.05e-05 | 8.19e-06 | 246 | 0.7 | 11.1 | 26916 | 4 | 36.32678 | --- | 4.88 | 98 | 1.9/32.8/63.5 |
| R | sa-wf_h0.224_med30_da+0.25 | VALID | 1.3800 | 0.0344 | 1.94e-04 | 0.00e+00 | 135 | 0.3 | 5.9 | 14781 | 7 | 40.207722 | --- | 4.65 | 79 | 2.2/32.0/64.3 |
| R | sa-wf_h0.224_med30_da+0.5 | VALID | 1.4047 | 0.0354 | 1.99e-04 | 1.58e-16 | 139 | 0.3 | 5.9 | 14731 | 7 | 35.345403 | --- | 4.71 | 79 | 2.7/32.2/65.3 |
| R | sa-wf_h0.224_med30_da+1 | VALID | 1.4581 | 0.0383 | 1.59e-04 | 5.66e-08 | 143 | 0.3 | 6.0 | 14758 | 7 | 38.636402 | --- | 4.81 | 78 | 2.5/32.0/67.0 |
| R | sa-wf_h0.224_med30_da-0.25 | VALID | 1.3142 | 0.0323 | 1.96e-04 | 0.00e+00 | 129 | 0.3 | 6.1 | 14740 | 7 | 42.885905 | --- | 4.84 | 76 | 1.2/32.2/62.0 |
| R | sa-wf_h0.224_med30_da-0.5 | VALID | 1.2740 | 0.0311 | 1.87e-04 | 1.74e-16 | 127 | 0.3 | 5.9 | 14734 | 7 | 38.253672 | --- | 4.71 | 78 | 3.0/32.3/60.9 |
| R | sa-wf_h0.224_med30_da-1 | VALID | 1.1983 | 0.0293 | 2.09e-04 | 0.00e+00 | 129 | 0.3 | 5.8 | 14693 | 7 | 38.198188 | --- | 4.63 | 78 | 5.1/32.3/58.5 |
| R | sa-wf_h0.224_med30_da0 | VALID | 1.3449 | 0.0333 | 1.88e-04 | 2.85e-10 | 135 | 0.3 | 6.0 | 14773 | 7 | 43.868342 | --- | 4.79 | 77 | 1.7/32.2/63.2 |
| R | sa-wf_h0.224_xfine30_da+0.25 | VALID | 1.3091 | 0.0324 | 6.10e-06 | 4.49e-08 | 415 | 2.1 | 21.4 | 51221 | 2 | 40.558477 | --- | 4.94 | 134 | 1.9/32.6/64.8 |
| R | sa-wf_h0.224_xfine30_da+0.5 | VALID | 1.3315 | 0.0335 | 8.82e-06 | 2.02e-09 | 392 | 1.9 | 21.1 | 51289 | 2 | 44.21628 | --- | 4.87 | 135 | 1.8/32.5/65.7 |
| R | sa-wf_h0.224_xfine30_da+1 | VALID | 1.3821 | 0.0362 | 4.42e-06 | 3.64e-09 | 448 | 2.2 | 21.0 | 51423 | 2 | 36.378929 | --- | 4.82 | 135 | 2.1/32.5/67.6 |
| R | sa-wf_h0.224_xfine30_da-0.25 | VALID | 1.2399 | 0.0301 | 6.41e-06 | 1.75e-07 | 389 | 2.0 | 21.7 | 51156 | 2 | 36.439599 | --- | 5.00 | 133 | 1.7/32.6/62.4 |
| R | sa-wf_h0.224_xfine30_da-0.5 | VALID | 1.1983 | 0.0292 | 1.80e-06 | 1.15e-08 | 384 | 1.9 | 20.5 | 51218 | 2 | 35.3914 | --- | 4.73 | 135 | 1.8/32.5/61.0 |
| R | sa-wf_h0.224_xfine30_da-1 | VALID | 1.1348 | 0.0274 | 1.29e-06 | 6.49e-09 | 371 | 1.9 | 21.3 | 51120 | 2 | 41.814141 | --- | 4.91 | 133 | 1.9/32.6/59.1 |
| R | sa-wf_h0.224_xfine30_da0 | VALID | 1.2714 | 0.0313 | 9.40e-06 | 4.13e-08 | 409 | 2.0 | 21.6 | 51287 | 2 | 39.896462 | --- | 4.97 | 134 | 1.9/32.6/63.5 |
| R | sa-wf_h0.313_coa30_da0 | VALID | 1.2108 | 0.0323 | 1.77e-04 | 0.00e+00 | 102 | 0.2 | 3.9 | 8983 | 11 | 42.460543 | --- | 5.09 | 69 | 7.8/30.4/59.2 |
| R | sa-wf_h0.313_fine30_da0 | VALID | 1.1945 | 0.0262 | 6.98e-05 | 1.86e-16 | 214 | 0.6 | 11.1 | 27352 | 4 | 34.157243 | --- | 4.77 | 97 | 4.7/32.5/63.0 |
| R | sa-wf_h0.313_med30_da0 | VALID | 1.2106 | 0.0273 | 2.03e-04 | 1.77e-09 | 127 | 0.3 | 6.2 | 15164 | 7 | 36.165318 | --- | 4.82 | 77 | 7.2/32.0/62.7 |
| R | sa-wf_h0.313_xfine30_da0 | VALID | 1.1605 | 0.0253 | 1.68e-06 | 1.13e-09 | 358 | 1.9 | 22.1 | 51736 | 2 | 38.228164 | --- | 5.04 | 134 | 2.9/32.3/63.6 |
| R | sa-wf_h0.448_coa30_da0 | VALID | 1.0630 | 0.0279 | 2.04e-04 | 0.00e+00 | 90 | 0.2 | 4.0 | 9276 | 11 | 46.855094 | --- | 4.99 | 69 | 10.8/30.1/57.8 |
| R | sa-wf_h0.448_fine30_da0 | VALID | 1.0473 | 0.0227 | 4.88e-05 | 2.12e-16 | 180 | 0.6 | 11.2 | 27681 | 4 | 39.201552 | --- | 4.76 | 96 | 7.8/32.0/61.5 |
| R | sa-wf_h0.448_med30_da0 | VALID | 1.0651 | 0.0238 | 1.94e-04 | 0.00e+00 | 115 | 0.3 | 6.4 | 15546 | 7 | 40.271237 | --- | 4.81 | 78 | 10.1/31.5/61.3 |
| R | sa-wf_h0.448_xfine30_da0 | VALID | 1.0273 | 0.0217 | 7.81e-07 | 2.16e-16 | 305 | 1.6 | 21.5 | 52316 | 2 | 37.753085 | --- | 4.85 | 136 | 6.0/31.8/62.1 |
| R | sa-wf_h0.671_coa30_da0 | VALID | 0.9438 | 0.0255 | 1.92e-04 | 0.00e+00 | 80 | 0.1 | 4.0 | 9503 | 11 | 37.620714 | --- | 4.95 | 69 | 12.7/29.7/56.3 |
| R | sa-wf_h0.671_fine30_da0 | VALID | 0.9366 | 0.0203 | 1.42e-05 | 9.67e-11 | 160 | 0.5 | 11.3 | 28022 | 4 | 34.983242 | --- | 4.76 | 97 | 8.3/31.4/60.2 |
| R | sa-wf_h0.671_med30_da0 | VALID | 0.9482 | 0.0213 | 1.65e-04 | 1.17e-16 | 103 | 0.3 | 6.6 | 15919 | 7 | 37.868413 | --- | 4.85 | 79 | 10.6/31.0/59.9 |
| R | sa-wf_h0.671_xfine30_da0 | VALID | 0.9211 | 0.0195 | 1.74e-07 | 0.00e+00 | 279 | 1.5 | 21.9 | 52741 | 2 | 46.098168 | --- | 4.91 | 140 | 7.8/31.3/60.8 |
| M | sa-wf_h0.09_fine30_da0 | VALID | 1.3055 | 0.0608 | 5.87e-05 | 3.91e-05 | 73 | 0.1 | 5.5 | 25298 | 4 | 36.800861 | --- | 2.60 | 92 | 3.4/32.4/67.7 |
| M | sa-wf_h0.09_fine30_morph-da+0.25 | VALID | 1.3169 | 0.0632 | 8.26e-05 | 5.91e-05 | 87 | 0.2 | 5.9 | 25298 | 4 | 36.769955 | 0.989-1.027 | 2.74 | 94 | 3.6/32.3/68.0 |
| M | sa-wf_h0.09_fine30_morph-da+0.5 | VALID | 1.3305 | 0.0658 | 9.43e-05 | 7.35e-05 | 88 | 0.2 | 5.7 | 25298 | 4 | 36.739025 | 0.979-1.053 | 2.62 | 95 | 2.0/32.3/68.3 |
| M | sa-wf_h0.09_fine30_morph-da+1 | UNSTEADY | 1.3910 | 0.0729 | 1.91e-02 | 3.35e-03 | 5001 | 6.0 | 6.0 | 25298 | 4 | 36.677713 | 0.958-1.107 | 2.81 | 95 | 2.6/32.4/69.3 |
| M | sa-wf_h0.09_fine30_morph-da-0.25 | VALID | 1.2963 | 0.0584 | 1.48e-04 | 8.29e-05 | 126 | 0.3 | 5.9 | 25298 | 4 | 36.831634 | 0.973-1.011 | 2.74 | 94 | 2.8/32.4/67.4 |
| M | sa-wf_h0.09_fine30_morph-da-0.5 | VALID | 1.2784 | 0.0560 | 7.03e-05 | 4.48e-05 | 72 | 0.2 | 5.9 | 25298 | 4 | 36.862851 | 0.947-1.021 | 2.73 | 96 | 2.5/32.4/67.0 |
| M | sa-wf_h0.09_fine30_morph-da-1 | VALID | 1.2461 | 0.0520 | 1.72e-04 | 1.12e-04 | 148 | 0.3 | 5.8 | 25298 | 4 | 36.92514 | 0.894-1.043 | 2.69 | 94 | 3.9/32.4/66.2 |
| M | sa-wf_h0.09_fine30_morphB2-da+0.25 | VALID | 1.3227 | 0.0634 | 1.28e-04 | 7.05e-05 | 144 | 0.3 | 6.0 | 25469 | 4 | 43.739833 | 0.974-1.010 | 2.76 | 95 | 2.3/32.3/68.0 |
| M | sa-wf_h0.09_fine30_morphB2-da+1 | UNSTEADY | 1.3805 | 0.0727 | 1.50e-02 | 2.75e-03 | 5001 | 5.8 | 5.8 | 25469 | 4 | 44.152924 | 0.979-1.052 | 2.67 | 95 | 4.1/32.4/69.0 |
| M | sa-wf_h0.09_fine30_morphB2-da-0.25 | VALID | 1.2920 | 0.0585 | 3.93e-05 | 2.01e-05 | 140 | 0.3 | 5.8 | 25469 | 4 | 43.459668 | 0.923-1.031 | 2.66 | 94 | 2.9/32.4/67.3 |
| M | sa-wf_h0.09_fine30_morphB2-da-1 | VALID | 1.2496 | 0.0521 | 1.65e-04 | 1.26e-04 | 160 | 0.3 | 5.8 | 25469 | 4 | 43.029689 | 0.846-1.063 | 2.69 | 95 | 1.5/32.4/66.3 |
| M | sa-wf_h0.09_fine30_morphLin-da+1 | UNSTEADY | 1.3906 | 0.0730 | 1.89e-02 | 3.34e-03 | 5001 | 5.9 | 6.0 | 25298 | 4 | 36.148874 | 0.939-1.075 | 2.77 | 95 | 2.4/32.2/69.1 |
| M | sa-wf_h0.09_fine30_morphLin-da-1 | VALID | 1.2458 | 0.0519 | 1.75e-04 | 1.19e-04 | 144 | 0.3 | 5.8 | 25298 | 4 | 37.463489 | 0.926-1.060 | 2.70 | 96 | 3.9/32.4/66.3 |
| M | sa-wf_h0.09_med30_da0 | VALID | 1.3123 | 0.0617 | 9.71e-05 | 3.38e-16 | 63 | 0.1 | 3.3 | 13722 | 7 | 41.637644 | --- | 2.82 | 76 | 2.0/31.8/67.1 |
| M | sa-wf_h0.09_med30_morph-da+0.25 | VALID | 1.3222 | 0.0643 | 4.23e-04 | 3.34e-04 | 70 | 0.1 | 3.2 | 13722 | 7 | 41.637651 | 0.982-1.040 | 2.75 | 75 | 2.6/31.7/67.3 |
| M | sa-wf_h0.09_med30_morph-da+0.5 | VALID | 1.3360 | 0.0670 | 1.18e-04 | 4.68e-05 | 65 | 0.1 | 3.3 | 13722 | 7 | 41.637657 | 0.964-1.080 | 2.78 | 76 | 2.7/31.7/67.6 |
| M | sa-wf_h0.09_med30_morph-da+1 | VALID | 1.3525 | 0.0728 | 4.37e-04 | 3.59e-04 | 70 | 0.1 | 3.3 | 13722 | 7 | 41.637668 | 0.930-1.160 | 2.78 | 75 | 2.3/31.7/68.0 |
| M | sa-wf_h0.09_med30_morph-da-0.25 | VALID | 1.2976 | 0.0592 | 1.26e-04 | 0.00e+00 | 62 | 0.1 | 3.2 | 13722 | 7 | 41.637638 | 0.960-1.018 | 2.76 | 76 | 2.4/31.8/66.8 |
| M | sa-wf_h0.09_med30_morph-da-0.5 | VALID | 1.2812 | 0.0568 | 1.26e-04 | 3.95e-05 | 63 | 0.1 | 3.3 | 13722 | 7 | 41.637632 | 0.921-1.036 | 2.79 | 75 | 3.2/31.8/66.4 |
| M | sa-wf_h0.09_med30_morph-da-1 | VALID | 1.2531 | 0.0527 | 1.38e-04 | 4.88e-05 | 121 | 0.1 | 3.2 | 13722 | 7 | 41.637618 | 0.843-1.073 | 2.70 | 76 | 2.8/31.8/65.8 |
| M | sa-wf_h0.09_med30_morphB2-da+0.25 | VALID | 1.3300 | 0.0646 | 4.42e-04 | 3.28e-04 | 68 | 0.1 | 2.6 | 13828 | 7 | 39.16296 | 0.962-1.018 | 2.15 | 76 | 2.8/31.9/67.4 |
| M | sa-wf_h0.09_med30_morphB2-da+1 | VALID | 1.3570 | 0.0722 | 5.22e-04 | 4.35e-04 | 74 | 0.1 | 2.4 | 13828 | 7 | 39.157136 | 0.965-1.076 | 2.00 | 75 | 2.6/31.7/68.0 |
| M | sa-wf_h0.09_med30_morphB2-da-0.25 | VALID | 1.3082 | 0.0600 | 5.02e-04 | 4.02e-04 | 67 | 0.1 | 3.2 | 13828 | 7 | 39.166905 | 0.886-1.054 | 2.66 | 76 | 2.3/31.9/66.9 |
| M | sa-wf_h0.09_med30_morphB2-da-1 | VALID | 1.2590 | 0.0533 | 1.73e-04 | 1.15e-04 | 121 | 0.2 | 3.3 | 13828 | 7 | 39.172958 | 0.774-1.110 | 2.76 | 75 | 3.7/31.9/65.9 |
| M | sa-wf_h0.09_xfine30_da0 | SOLVER_FAIL | 1.3366 | 0.0649 | 3.61e-02 | 6.82e-03 | 15001 | - | 39.7 | 49699 | 2 | 40.293849 | --- | 3.19 | 136 | 2.1/32.6/68.5 |
| M | sa-wf_h0.09_xfine30_morph-da+0.25 | SOLVER_FAIL | 1.3616 | 0.0681 | 3.97e-02 | 6.97e-03 | 15001 | - | 38.8 | 49699 | 2 | 40.192073 | 0.991-1.024 | 3.10 | 135 | 2.1/32.7/68.9 |
| M | sa-wf_h0.09_xfine30_morph-da+0.5 | SOLVER_FAIL | 1.3856 | 0.0714 | 4.31e-02 | 6.90e-03 | 15001 | - | 38.4 | 49699 | 2 | 40.090813 | 0.982-1.048 | 3.07 | 135 | 2.0/32.7/69.3 |
| M | sa-wf_h0.09_xfine30_morph-da+1 | SOLVER_FAIL | 1.4440 | 0.0791 | 5.35e-02 | 7.27e-03 | 15001 | - | 38.2 | 49699 | 2 | 39.891833 | 0.964-1.097 | 3.06 | 136 | 2.4/32.6/70.2 |
| M | sa-wf_h0.09_xfine30_morph-da-0.25 | SOLVER_FAIL | 1.3114 | 0.0619 | 3.20e-02 | 6.41e-03 | 15001 | - | 38.8 | 49699 | 2 | 40.395792 | 0.976-1.009 | 3.11 | 134 | 1.8/32.4/67.8 |
| M | sa-wf_h0.09_xfine30_morph-da-0.5 | SOLVER_FAIL | 1.2844 | 0.0590 | 2.82e-02 | 5.90e-03 | 15001 | - | 38.2 | 49699 | 2 | 40.499798 | 0.952-1.018 | 3.05 | 134 | 2.3/32.4/67.4 |
| M | sa-wf_h0.09_xfine30_morph-da-1 | UNSTEADY | 1.2258 | 0.0535 | 2.04e-02 | 4.36e-03 | 5001 | 13.5 | 13.6 | 49699 | 2 | 40.709191 | 0.904-1.037 | 3.22 | 139 | 1.9/32.4/66.4 |
| M | sa-wf_h0.134_fine30_da0 | VALID | 1.4003 | 0.0462 | 2.54e-04 | 1.90e-04 | 186 | 0.3 | 6.2 | 26074 | 4 | 44.877668 | --- | 2.85 | 95 | 1.6/32.8/65.2 |
| M | sa-wf_h0.134_fine30_morph-da+0.25 | VALID | 1.4145 | 0.0481 | 4.95e-05 | 2.20e-05 | 186 | 0.3 | 6.2 | 26074 | 4 | 44.877671 | 0.992-1.021 | 2.81 | 94 | 2.0/32.8/65.4 |
| M | sa-wf_h0.134_fine30_morph-da+0.5 | VALID | 1.4318 | 0.0503 | 4.92e-05 | 1.77e-05 | 184 | 0.3 | 6.2 | 26074 | 4 | 44.877674 | 0.985-1.042 | 2.80 | 93 | 2.7/32.7/65.7 |
| M | sa-wf_h0.134_fine30_morph-da+1 | VALID | 1.4502 | 0.0547 | 2.09e-04 | 1.63e-04 | 166 | 0.3 | 6.3 | 26074 | 4 | 44.87768 | 0.970-1.085 | 2.83 | 94 | 2.8/32.6/66.0 |
| M | sa-wf_h0.134_fine30_morph-da-0.25 | VALID | 1.3832 | 0.0444 | 5.41e-05 | 3.77e-05 | 192 | 0.4 | 6.3 | 26074 | 4 | 44.877665 | 0.979-1.008 | 2.83 | 94 | 2.6/32.9/64.9 |
| M | sa-wf_h0.134_fine30_morph-da-0.5 | VALID | 1.3678 | 0.0427 | 1.36e-04 | 0.00e+00 | 242 | 0.4 | 6.3 | 26074 | 4 | 44.877662 | 0.958-1.015 | 2.86 | 94 | 2.6/32.9/64.6 |
| M | sa-wf_h0.134_fine30_morph-da-1 | VALID | 1.3241 | 0.0396 | 1.45e-04 | 0.00e+00 | 234 | 0.4 | 6.4 | 26074 | 4 | 44.877655 | 0.915-1.031 | 2.88 | 94 | 2.5/33.0/63.9 |
| M | sa-wf_h0.134_fine30_morphB2-da+0.25 | VALID | 1.3940 | 0.0487 | 1.99e-04 | 1.55e-04 | 188 | 0.3 | 6.2 | 26059 | 4 | 41.619552 | 0.979-1.008 | 2.79 | 96 | 2.4/32.8/65.3 |
| M | sa-wf_h0.134_fine30_morphB2-da+1 | VALID | 1.4488 | 0.0551 | 1.51e-04 | 1.13e-04 | 186 | 0.3 | 6.2 | 26059 | 4 | 41.605893 | 0.984-1.041 | 2.80 | 95 | 1.8/32.7/66.0 |
| M | sa-wf_h0.134_fine30_morphB2-da-0.25 | VALID | 1.3523 | 0.0451 | 1.68e-04 | 1.12e-04 | 192 | 0.4 | 6.3 | 26059 | 4 | 41.628879 | 0.938-1.024 | 2.82 | 96 | 3.1/32.9/64.6 |
| M | sa-wf_h0.134_fine30_morphB2-da-1 | VALID | 1.2775 | 0.0402 | 8.84e-05 | 8.63e-05 | 197 | 0.4 | 6.1 | 26059 | 4 | 41.643354 | 0.877-1.049 | 2.76 | 94 | 2.3/32.9/63.4 |
| M | sa-wf_h0.134_fine30_morphLin-da+1 | VALID | 1.4505 | 0.0547 | 1.33e-04 | 1.13e-04 | 160 | 0.3 | 6.2 | 26074 | 4 | 44.886016 | 0.949-1.060 | 2.78 | 95 | 2.8/32.6/66.0 |
| M | sa-wf_h0.134_fine30_morphLin-da-1 | VALID | 1.3236 | 0.0396 | 3.82e-05 | 2.37e-05 | 198 | 0.3 | 6.0 | 26074 | 4 | 44.868506 | 0.940-1.051 | 2.70 | 94 | 2.3/33.0/63.9 |
| M | sa-wf_h0.134_med30_da0 | VALID | 1.3960 | 0.0480 | 1.40e-04 | 4.15e-05 | 121 | 0.1 | 3.4 | 14151 | 7 | 38.62036 | --- | 2.85 | 75 | 2.2/32.3/64.5 |
| M | sa-wf_h0.134_med30_morph-da+0.25 | VALID | 1.4070 | 0.0499 | 1.33e-04 | 1.58e-16 | 123 | 0.2 | 3.3 | 14151 | 7 | 38.58729 | 0.990-1.026 | 2.74 | 76 | 3.3/32.2/64.7 |
| M | sa-wf_h0.134_med30_morph-da+0.5 | VALID | 1.4177 | 0.0519 | 1.58e-04 | 3.13e-16 | 127 | 0.2 | 3.2 | 14151 | 7 | 38.554326 | 0.980-1.052 | 2.66 | 76 | 2.5/32.1/64.8 |
| M | sa-wf_h0.134_med30_morph-da+1 | VALID | 1.4364 | 0.0564 | 1.17e-04 | 1.55e-16 | 127 | 0.2 | 3.4 | 14151 | 7 | 38.488542 | 0.959-1.105 | 2.83 | 75 | 2.1/32.0/65.1 |
| M | sa-wf_h0.134_med30_morph-da-0.25 | VALID | 1.3833 | 0.0462 | 1.50e-04 | 1.61e-16 | 123 | 0.2 | 3.4 | 14151 | 7 | 38.65356 | 0.974-1.010 | 2.83 | 75 | 2.0/32.3/64.2 |
| M | sa-wf_h0.134_med30_morph-da-0.5 | VALID | 1.3693 | 0.0445 | 1.33e-04 | 2.20e-10 | 123 | 0.2 | 3.4 | 14151 | 7 | 38.68673 | 0.948-1.021 | 2.82 | 75 | 2.1/32.4/64.0 |
| M | sa-wf_h0.134_med30_morph-da-1 | VALID | 1.3307 | 0.0412 | 1.27e-04 | 0.00e+00 | 135 | 0.2 | 3.4 | 14151 | 7 | 38.753384 | 0.896-1.042 | 2.77 | 75 | 2.7/32.4/63.4 |
| M | sa-wf_h0.134_med30_morphB2-da+0.25 | VALID | 1.4131 | 0.0498 | 1.52e-04 | 1.57e-16 | 127 | 0.2 | 3.4 | 14265 | 7 | 48.6948 | 0.975-1.010 | 2.78 | 76 | 2.5/32.2/64.8 |
| M | sa-wf_h0.134_med30_morphB2-da+1 | VALID | 1.4522 | 0.0564 | 1.03e-04 | 0.00e+00 | 131 | 0.2 | 3.2 | 14265 | 7 | 48.8292 | 0.980-1.050 | 2.65 | 76 | 3.2/32.1/65.3 |
| M | sa-wf_h0.134_med30_morphB2-da-0.25 | VALID | 1.3799 | 0.0459 | 1.53e-04 | 4.29e-05 | 123 | 0.2 | 3.4 | 14265 | 7 | 48.603908 | 0.925-1.031 | 2.77 | 76 | 1.9/32.3/64.2 |
| M | sa-wf_h0.134_med30_morphB2-da-1 | VALID | 1.3195 | 0.0408 | 1.53e-04 | 2.26e-09 | 119 | 0.2 | 3.3 | 14265 | 7 | 48.464508 | 0.850-1.062 | 2.71 | 76 | 3.2/32.4/63.2 |
| M | sa-wf_h0.134_xfine30_da0 | UNSTEADY | 1.3262 | 0.0474 | 7.39e-03 | 1.43e-03 | 5001 | 13.2 | 13.2 | 50303 | 2 | 40.539013 | --- | 3.14 | 135 | 2.0/32.6/64.9 |
| M | sa-wf_h0.134_xfine30_morph-da+0.25 | UNSTEADY | 1.3617 | 0.0499 | 1.08e-02 | 2.23e-03 | 5001 | 13.5 | 13.5 | 50303 | 2 | 40.453682 | 0.993-1.020 | 3.16 | 132 | 2.0/32.7/65.3 |
| M | sa-wf_h0.134_xfine30_morph-da+0.5 | UNSTEADY | 1.3972 | 0.0526 | 1.31e-02 | 3.71e-03 | 5001 | 13.7 | 13.7 | 50303 | 2 | 40.368609 | 0.986-1.040 | 3.22 | 133 | 2.0/32.7/65.8 |
| M | sa-wf_h0.134_xfine30_morph-da+1 | UNSTEADY | 1.4605 | 0.0584 | 1.93e-02 | 4.17e-03 | 5001 | 13.8 | 13.8 | 50303 | 2 | 40.200831 | 0.972-1.080 | 3.24 | 135 | 2.1/32.7/66.6 |
| M | sa-wf_h0.134_xfine30_morph-da-0.25 | VALID | 1.2814 | 0.0448 | 2.40e-05 | 1.98e-05 | 367 | 1.1 | 12.5 | 50303 | 2 | 40.62432 | 0.980-1.007 | 2.92 | 134 | 1.7/32.6/64.3 |
| M | sa-wf_h0.134_xfine30_morph-da-0.5 | VALID | 1.2602 | 0.0430 | 6.90e-06 | 5.64e-07 | 372 | 1.1 | 12.9 | 50303 | 2 | 40.711121 | 0.960-1.014 | 3.03 | 133 | 2.1/32.6/63.9 |
| M | sa-wf_h0.134_xfine30_morph-da-1 | VALID | 1.2170 | 0.0395 | 4.83e-06 | 9.67e-07 | 391 | 1.2 | 12.9 | 50303 | 2 | 40.885354 | 0.921-1.029 | 3.01 | 133 | 1.8/32.6/63.2 |
| M | sa-wf_h0.224_fine30_da0 | VALID | 1.3083 | 0.0318 | 6.05e-05 | 8.19e-06 | 246 | 0.4 | 6.8 | 26916 | 4 | 36.32678 | --- | 3.00 | 97 | 1.9/32.8/63.5 |
| M | sa-wf_h0.224_fine30_morph-da+0.25 | VALID | 1.3409 | 0.0329 | 1.06e-04 | 3.83e-08 | 252 | 0.4 | 6.6 | 26916 | 4 | 36.327915 | 0.995-1.016 | 2.87 | 97 | 1.9/32.7/64.6 |
| M | sa-wf_h0.224_fine30_morph-da+0.5 | VALID | 1.3722 | 0.0340 | 9.73e-05 | 4.41e-08 | 256 | 0.5 | 6.6 | 26916 | 4 | 36.329046 | 0.989-1.031 | 2.89 | 98 | 2.4/32.6/65.5 |
| M | sa-wf_h0.224_fine30_morph-da+1 | VALID | 1.4300 | 0.0366 | 9.31e-05 | 1.44e-10 | 262 | 0.5 | 6.5 | 26916 | 4 | 36.33127 | 0.979-1.063 | 2.86 | 100 | 1.9/32.6/67.5 |
| M | sa-wf_h0.224_fine30_morph-da-0.25 | VALID | 1.2750 | 0.0308 | 6.03e-05 | 0.00e+00 | 241 | 0.4 | 6.7 | 26916 | 4 | 36.34026 | 0.984-1.005 | 2.93 | 96 | 2.7/32.8/62.4 |
| M | sa-wf_h0.224_fine30_morph-da-0.5 | VALID | 1.2415 | 0.0299 | 6.98e-05 | 6.80e-08 | 234 | 0.4 | 6.5 | 26916 | 4 | 36.538532 | 0.969-1.011 | 2.85 | 96 | 2.4/32.9/61.2 |
| M | sa-wf_h0.224_fine30_morph-da-1 | VALID | 1.1696 | 0.0281 | 6.94e-05 | 1.61e-07 | 221 | 0.4 | 6.7 | 26916 | 4 | 36.934123 | 0.938-1.022 | 2.92 | 98 | 1.7/32.9/58.7 |
| M | sa-wf_h0.224_fine30_morphB2-da+0.25 | VALID | 1.3635 | 0.0331 | 8.82e-05 | 0.00e+00 | 252 | 0.4 | 6.5 | 26913 | 4 | 53.723772 | 0.985-1.005 | 2.84 | 97 | 1.8/32.9/64.7 |
| M | sa-wf_h0.224_fine30_morphB2-da+1 | VALID | 1.4486 | 0.0369 | 4.33e-05 | 1.53e-16 | 246 | 0.4 | 6.5 | 26913 | 4 | 53.723776 | 0.989-1.031 | 2.84 | 98 | 2.2/32.7/67.8 |
| M | sa-wf_h0.224_fine30_morphB2-da-0.25 | VALID | 1.3000 | 0.0309 | 7.41e-05 | 0.00e+00 | 244 | 0.4 | 6.5 | 26913 | 4 | 53.723769 | 0.954-1.016 | 2.83 | 96 | 0.9/32.9/62.5 |
| M | sa-wf_h0.224_fine30_morphB2-da-1 | VALID | 1.1926 | 0.0281 | 7.58e-05 | 3.39e-10 | 232 | 0.4 | 6.6 | 26913 | 4 | 53.723765 | 0.908-1.033 | 2.86 | 96 | 1.3/33.0/59.1 |
| M | sa-wf_h0.224_fine30_morphLin-da+1 | VALID | 1.4286 | 0.0366 | 1.10e-04 | 4.01e-08 | 264 | 0.5 | 6.7 | 26916 | 4 | 36.449744 | 0.961-1.046 | 2.91 | 98 | 1.9/32.5/67.5 |
| M | sa-wf_h0.224_fine30_morphLin-da-1 | VALID | 1.1703 | 0.0281 | 7.31e-05 | 2.42e-07 | 221 | 0.4 | 6.6 | 26916 | 4 | 36.897903 | 0.955-1.038 | 2.90 | 97 | 1.6/32.9/58.8 |
| M | sa-wf_h0.224_med30_da0 | VALID | 1.3449 | 0.0333 | 1.88e-04 | 2.85e-10 | 135 | 0.1 | 3.4 | 14773 | 7 | 43.868342 | --- | 2.74 | 77 | 1.7/32.2/63.2 |
| M | sa-wf_h0.224_med30_morph-da+0.25 | VALID | 1.3759 | 0.0344 | 1.79e-04 | 0.00e+00 | 137 | 0.2 | 3.4 | 14773 | 7 | 43.862308 | 0.994-1.017 | 2.71 | 76 | 2.0/32.1/64.2 |
| M | sa-wf_h0.224_med30_morph-da+0.5 | VALID | 1.4057 | 0.0356 | 1.98e-04 | 3.16e-16 | 139 | 0.2 | 3.5 | 14773 | 7 | 43.856266 | 0.987-1.035 | 2.74 | 76 | 2.5/32.0/65.2 |
| M | sa-wf_h0.224_med30_morph-da+1 | VALID | 1.4582 | 0.0383 | 1.59e-04 | 0.00e+00 | 141 | 0.2 | 3.2 | 14773 | 7 | 43.844271 | 0.975-1.070 | 2.57 | 77 | 2.3/31.9/67.0 |
| M | sa-wf_h0.224_med30_morph-da-0.25 | VALID | 1.3116 | 0.0322 | 1.94e-04 | 0.00e+00 | 133 | 0.2 | 3.2 | 14773 | 7 | 43.874347 | 0.983-1.006 | 2.56 | 76 | 1.6/32.2/62.1 |
| M | sa-wf_h0.224_med30_morph-da-0.5 | VALID | 1.2766 | 0.0311 | 1.99e-04 | 1.74e-16 | 133 | 0.2 | 3.4 | 14773 | 7 | 43.880429 | 0.965-1.013 | 2.71 | 78 | 2.8/32.3/60.9 |
| M | sa-wf_h0.224_med30_morph-da-1 | VALID | 1.2021 | 0.0292 | 1.98e-04 | 0.00e+00 | 129 | 0.2 | 3.4 | 14773 | 7 | 43.892555 | 0.931-1.026 | 2.67 | 77 | 5.0/32.4/58.5 |
| M | sa-wf_h0.224_med30_morphB2-da+0.25 | VALID | 1.3747 | 0.0342 | 1.91e-04 | 1.62e-16 | 137 | 0.2 | 3.2 | 14731 | 7 | 35.349298 | 0.983-1.006 | 2.56 | 78 | 2.2/32.2/64.3 |
| M | sa-wf_h0.224_med30_morphB2-da+1 | VALID | 1.4557 | 0.0381 | 1.78e-04 | 1.53e-16 | 143 | 0.2 | 3.4 | 14731 | 7 | 35.337921 | 0.987-1.035 | 2.69 | 79 | 2.5/32.0/67.1 |
| M | sa-wf_h0.224_med30_morphB2-da-0.25 | VALID | 1.3099 | 0.0320 | 2.08e-04 | 0.00e+00 | 135 | 0.2 | 3.3 | 14731 | 7 | 35.357473 | 0.948-1.019 | 2.66 | 79 | 1.7/32.3/62.2 |
| M | sa-wf_h0.224_med30_morphB2-da-1 | VALID | 1.2009 | 0.0291 | 2.12e-04 | 5.23e-10 | 131 | 0.2 | 3.4 | 14731 | 7 | 35.370575 | 0.895-1.038 | 2.69 | 78 | 5.1/32.5/58.6 |
| M | sa-wf_h0.224_xfine30_da0 | VALID | 1.2714 | 0.0313 | 9.40e-06 | 4.13e-08 | 409 | 1.2 | 13.6 | 51287 | 2 | 39.896462 | --- | 3.17 | 136 | 1.9/32.6/63.5 |
| M | sa-wf_h0.224_xfine30_morph-da+0.25 | VALID | 1.3000 | 0.0325 | 1.05e-05 | 5.55e-09 | 413 | 1.3 | 13.3 | 51287 | 2 | 39.974733 | 0.995-1.015 | 3.06 | 134 | 1.9/32.6/64.6 |
| M | sa-wf_h0.224_xfine30_morph-da+0.5 | VALID | 1.3288 | 0.0337 | 7.84e-06 | 7.37e-09 | 420 | 1.3 | 13.4 | 51287 | 2 | 40.05304 | 0.990-1.030 | 3.07 | 134 | 2.0/32.5/65.6 |
| M | sa-wf_h0.224_xfine30_morph-da+1 | VALID | 1.3782 | 0.0365 | 8.43e-06 | 9.74e-09 | 424 | 1.3 | 13.4 | 51287 | 2 | 40.208442 | 0.980-1.059 | 3.09 | 135 | 1.9/32.5/67.5 |
| M | sa-wf_h0.224_xfine30_morph-da-0.25 | VALID | 1.2401 | 0.0303 | 7.84e-06 | 4.39e-07 | 399 | 1.3 | 13.6 | 51287 | 2 | 39.818458 | 0.985-1.005 | 3.13 | 135 | 1.7/32.6/62.4 |
| M | sa-wf_h0.224_xfine30_morph-da-0.5 | VALID | 1.2069 | 0.0293 | 6.13e-06 | 8.38e-09 | 386 | 1.2 | 13.6 | 51287 | 2 | 39.739472 | 0.970-1.010 | 3.12 | 137 | 1.7/32.6/61.3 |
| M | sa-wf_h0.224_xfine30_morph-da-1 | VALID | 1.1377 | 0.0275 | 2.80e-07 | 3.46e-09 | 377 | 1.2 | 13.2 | 51287 | 2 | 39.581737 | 0.941-1.020 | 3.04 | 135 | 1.8/32.7/59.0 |
| S | sa-wf_h0.09_fine30_camber+0.5mm | VALID | 1.3286 | 0.0629 | 1.22e-04 | 7.61e-05 | 132 | 0.4 | 10.7 | 25427 | 4 | 37.883103 | --- | 4.94 | 93 | 1.8/32.4/67.8 |
| S | sa-wf_h0.09_fine30_camber-0.5mm | VALID | 1.3052 | 0.0587 | 2.02e-04 | 1.38e-04 | 122 | 0.5 | 10.7 | 25410 | 4 | 33.899859 | --- | 4.95 | 96 | 3.0/32.4/67.8 |
| S | sa-wf_h0.09_fine30_da0 | VALID | 1.3055 | 0.0608 | 5.87e-05 | 3.91e-05 | 73 | 0.2 | 10.0 | 25298 | 4 | 36.800861 | --- | 4.70 | 93 | 3.4/32.4/67.7 |
| S | sa-wf_h0.09_fine30_flap+0.5mm | VALID | 1.3570 | 0.0634 | 5.39e-05 | 3.55e-05 | 106 | 0.4 | 10.3 | 25478 | 4 | 33.957818 | --- | 4.74 | 96 | 2.3/32.4/68.2 |
| S | sa-wf_h0.09_fine30_flap-0.5mm | VALID | 1.2823 | 0.0590 | 2.83e-05 | 1.47e-05 | 88 | 0.4 | 10.5 | 25351 | 4 | 33.957818 | --- | 4.87 | 94 | 2.8/32.3/67.5 |
| S | sa-wf_h0.09_fine30_heave+0.5mm | VALID | 1.3173 | 0.0595 | 1.65e-04 | 1.22e-04 | 85 | 0.4 | 10.6 | 25516 | 4 | 42.594955 | --- | 4.88 | 95 | 2.4/32.4/67.6 |
| S | sa-wf_h0.09_fine30_heave-0.5mm | VALID | 1.3069 | 0.0616 | 1.31e-04 | 7.96e-05 | 138 | 0.5 | 10.5 | 25380 | 4 | 33.380595 | --- | 4.87 | 95 | 3.8/32.3/67.9 |
| S | sa-wf_h0.09_fine30_morph-camber+0.25mm | VALID | 1.3084 | 0.0617 | 4.10e-05 | 2.42e-05 | 85 | 0.4 | 10.4 | 25298 | 4 | 36.91353 | 0.993-1.009 | 4.83 | 93 | 3.0/32.3/67.6 |
| S | sa-wf_h0.09_fine30_morph-camber+0.5mm | VALID | 1.3124 | 0.0626 | 4.37e-05 | 3.07e-05 | 88 | 0.4 | 10.3 | 25298 | 4 | 37.027201 | 0.986-1.018 | 4.79 | 93 | 2.8/32.3/67.5 |
| S | sa-wf_h0.09_fine30_morph-camber-0.25mm | VALID | 1.3023 | 0.0599 | 1.64e-04 | 1.29e-04 | 71 | 0.3 | 10.3 | 25298 | 4 | 36.689036 | 0.991-1.007 | 4.79 | 91 | 3.3/32.4/67.8 |
| S | sa-wf_h0.09_fine30_morph-camber-0.5mm | VALID | 1.2968 | 0.0590 | 1.73e-04 | 1.16e-04 | 71 | 0.3 | 10.4 | 25298 | 4 | 36.578063 | 0.982-1.014 | 4.85 | 94 | 2.9/32.4/67.8 |
| S | sa-wf_h0.09_fine30_morph-flap+0.25mm | VALID | 1.3192 | 0.0619 | 5.96e-05 | 4.16e-05 | 72 | 0.4 | 10.8 | 25298 | 4 | 36.800861 | 0.997-1.009 | 5.04 | 93 | 3.4/32.4/67.8 |
| S | sa-wf_h0.09_fine30_morph-flap+0.5mm | VALID | 1.3338 | 0.0631 | 6.66e-05 | 4.50e-05 | 71 | 0.3 | 10.9 | 25298 | 4 | 36.800861 | 0.993-1.018 | 5.08 | 93 | 3.4/32.4/68.0 |
| S | sa-wf_h0.09_fine30_morph-flap-0.25mm | VALID | 1.2916 | 0.0597 | 1.58e-04 | 1.22e-04 | 74 | 0.3 | 10.8 | 25298 | 4 | 36.800861 | 0.991-1.003 | 5.03 | 95 | 3.4/32.3/67.6 |
| S | sa-wf_h0.09_fine30_morph-flap-0.5mm | VALID | 1.2758 | 0.0586 | 1.59e-04 | 1.23e-04 | 87 | 0.4 | 10.3 | 25298 | 4 | 36.800861 | 0.982-1.007 | 4.80 | 94 | 3.4/32.3/67.4 |
| S | sa-wf_h0.09_fine30_morph-heave+0.25mm | VALID | 1.3085 | 0.0604 | 6.83e-05 | 5.21e-05 | 71 | 0.4 | 10.7 | 25298 | 4 | 36.837107 | 0.998-1.027 | 4.98 | 93 | 3.3/32.4/67.6 |
| S | sa-wf_h0.09_fine30_morph-heave+0.5mm | VALID | 1.3106 | 0.0599 | 1.33e-04 | 8.29e-05 | 71 | 0.4 | 10.3 | 25298 | 4 | 36.87338 | 0.996-1.054 | 4.75 | 95 | 2.7/32.4/67.5 |
| S | sa-wf_h0.09_fine30_morph-heave-0.25mm | VALID | 1.3022 | 0.0612 | 7.13e-05 | 5.38e-05 | 85 | 0.4 | 10.7 | 25298 | 4 | 36.764643 | 0.973-1.002 | 4.97 | 93 | 2.9/32.3/67.8 |
| S | sa-wf_h0.09_fine30_morph-heave-0.5mm | VALID | 1.2999 | 0.0617 | 3.61e-05 | 1.98e-05 | 86 | 0.4 | 10.8 | 25298 | 4 | 36.728454 | 0.946-1.004 | 5.01 | 93 | 2.8/32.3/67.8 |
| S | sa-wf_h0.09_med30_da0 | VALID | 1.3123 | 0.0617 | 9.71e-05 | 3.38e-16 | 63 | 0.1 | 6.2 | 13722 | 7 | 41.637644 | --- | 5.37 | 75 | 2.0/31.8/67.1 |
| S | sa-wf_h0.09_med30_morph-camber+0.25mm | VALID | 1.3160 | 0.0626 | 1.18e-04 | 0.00e+00 | 287 | 0.5 | 6.1 | 13722 | 7 | 41.63764 | 0.985-1.015 | 5.25 | 76 | 2.3/31.7/67.0 |
| S | sa-wf_h0.09_med30_morph-camber+0.5mm | VALID | 1.3188 | 0.0636 | 1.81e-04 | 1.31e-04 | 67 | 0.2 | 6.1 | 13722 | 7 | 41.637636 | 0.971-1.030 | 5.19 | 76 | 2.7/31.7/67.0 |
| S | sa-wf_h0.09_med30_morph-camber-0.25mm | VALID | 1.3080 | 0.0608 | 1.37e-04 | 4.78e-05 | 61 | 0.2 | 6.1 | 13722 | 7 | 41.637649 | 0.985-1.015 | 5.25 | 76 | 2.1/31.8/67.1 |
| S | sa-wf_h0.09_med30_morph-camber-0.5mm | VALID | 1.3035 | 0.0599 | 1.43e-04 | 4.97e-05 | 58 | 0.2 | 6.1 | 13722 | 7 | 41.637653 | 0.970-1.030 | 5.23 | 76 | 2.5/31.8/67.2 |
| S | sa-wf_h0.09_med30_morph-flap+0.25mm | VALID | 1.3257 | 0.0628 | 8.72e-05 | 1.67e-16 | 64 | 0.2 | 6.0 | 13722 | 7 | 41.637644 | 0.996-1.010 | 5.13 | 76 | 2.0/31.8/67.2 |
| S | sa-wf_h0.09_med30_morph-flap+0.5mm | VALID | 1.3396 | 0.0640 | 1.13e-04 | 1.08e-07 | 66 | 0.2 | 6.2 | 13722 | 7 | 41.637644 | 0.992-1.020 | 5.26 | 75 | 2.0/31.8/67.3 |
| S | sa-wf_h0.09_med30_morph-flap-0.25mm | VALID | 1.2975 | 0.0606 | 1.23e-04 | 1.71e-16 | 64 | 0.2 | 6.1 | 13722 | 7 | 41.637644 | 0.990-1.004 | 5.25 | 76 | 2.0/31.7/66.9 |
| S | sa-wf_h0.09_med30_morph-flap-0.5mm | VALID | 1.2823 | 0.0595 | 1.24e-04 | 0.00e+00 | 66 | 0.2 | 6.2 | 13722 | 7 | 41.637644 | 0.980-1.008 | 5.26 | 75 | 2.0/31.7/66.8 |
| S | sa-wf_h0.09_med30_morph-heave+0.25mm | VALID | 1.3138 | 0.0612 | 1.11e-04 | 1.69e-16 | 62 | 0.2 | 5.6 | 13722 | 7 | 41.637638 | 0.998-1.055 | 4.78 | 76 | 2.1/31.8/67.0 |
| S | sa-wf_h0.09_med30_morph-heave+0.5mm | VALID | 1.3161 | 0.0608 | 1.45e-04 | 0.00e+00 | 62 | 0.2 | 4.3 | 13722 | 7 | 41.637631 | 0.996-1.110 | 3.69 | 74 | 2.5/31.8/66.9 |
| S | sa-wf_h0.09_med30_morph-heave-0.25mm | VALID | 1.3098 | 0.0622 | 1.28e-04 | 0.00e+00 | 64 | 0.2 | 5.9 | 13722 | 7 | 41.637651 | 0.945-1.002 | 5.01 | 76 | 2.4/31.7/67.1 |
| S | sa-wf_h0.09_med30_morph-heave-0.5mm | VALID | 1.3067 | 0.0627 | 9.88e-05 | 1.70e-16 | 66 | 0.2 | 6.2 | 13722 | 7 | 41.637658 | 0.890-1.004 | 5.28 | 76 | 2.9/31.7/67.2 |
| S | sa-wf_h0.134_fine30_camber+0.5mm | VALID | 1.3787 | 0.0484 | 3.83e-05 | 3.09e-05 | 179 | 0.6 | 11.0 | 26092 | 4 | 39.999359 | --- | 4.96 | 96 | 3.8/32.9/64.9 |
| S | sa-wf_h0.134_fine30_camber-0.5mm | VALID | 1.3378 | 0.0455 | 1.65e-04 | 1.17e-04 | 188 | 0.6 | 11.0 | 26017 | 4 | 42.400101 | --- | 4.98 | 95 | 2.0/32.6/64.5 |
| S | sa-wf_h0.134_fine30_da0 | VALID | 1.4003 | 0.0462 | 2.54e-04 | 1.90e-04 | 186 | 0.5 | 11.1 | 26074 | 4 | 44.877668 | --- | 5.07 | 95 | 1.6/32.8/65.2 |
| S | sa-wf_h0.134_fine30_flap+0.5mm | VALID | 1.3946 | 0.0488 | 5.27e-05 | 2.20e-05 | 176 | 0.6 | 10.9 | 26109 | 4 | 37.113317 | --- | 4.89 | 96 | 2.8/32.8/65.0 |
| S | sa-wf_h0.134_fine30_flap-0.5mm | VALID | 1.3412 | 0.0452 | 3.15e-05 | 1.60e-05 | 200 | 0.6 | 10.4 | 25990 | 4 | 36.421073 | --- | 4.72 | 97 | 2.2/32.7/64.6 |
| S | sa-wf_h0.134_fine30_heave+0.5mm | VALID | 1.3524 | 0.0464 | 1.38e-04 | 9.77e-05 | 190 | 0.6 | 11.1 | 26102 | 4 | 35.840419 | --- | 5.01 | 95 | 2.6/32.7/64.5 |
| S | sa-wf_h0.134_fine30_heave-0.5mm | VALID | 1.3456 | 0.0477 | 1.63e-04 | 1.12e-04 | 174 | 0.6 | 10.9 | 26029 | 4 | 39.38743 | --- | 4.94 | 97 | 2.1/32.7/64.7 |
| S | sa-wf_h0.134_fine30_morph-camber+0.25mm | VALID | 1.4047 | 0.0470 | 2.58e-04 | 2.03e-04 | 180 | 0.6 | 11.1 | 26074 | 4 | 44.746161 | 0.995-1.007 | 5.00 | 95 | 2.2/32.8/65.2 |
| S | sa-wf_h0.134_fine30_morph-camber+0.5mm | VALID | 1.4084 | 0.0478 | 4.81e-05 | 2.47e-05 | 182 | 0.6 | 10.9 | 26074 | 4 | 44.614084 | 0.991-1.014 | 4.93 | 93 | 3.0/32.8/65.2 |
| S | sa-wf_h0.134_fine30_morph-camber-0.25mm | VALID | 1.3954 | 0.0455 | 2.59e-04 | 1.91e-04 | 190 | 0.6 | 11.2 | 26074 | 4 | 45.008608 | 0.993-1.005 | 5.04 | 94 | 2.6/32.8/65.2 |
| S | sa-wf_h0.134_fine30_morph-camber-0.5mm | VALID | 1.3900 | 0.0447 | 5.79e-05 | 2.81e-05 | 196 | 0.6 | 11.1 | 26074 | 4 | 45.138983 | 0.986-1.009 | 5.02 | 94 | 3.2/32.9/65.1 |
| S | sa-wf_h0.134_fine30_morph-flap+0.25mm | VALID | 1.4140 | 0.0472 | 5.45e-05 | 2.67e-05 | 190 | 0.6 | 10.6 | 26074 | 4 | 44.877668 | 0.997-1.007 | 4.80 | 94 | 2.0/32.9/65.3 |
| S | sa-wf_h0.134_fine30_morph-flap+0.5mm | VALID | 1.4268 | 0.0481 | 2.54e-04 | 1.86e-04 | 182 | 0.6 | 11.2 | 26074 | 4 | 44.877668 | 0.993-1.015 | 5.03 | 94 | 2.2/32.9/65.4 |
| S | sa-wf_h0.134_fine30_morph-flap-0.25mm | VALID | 1.3864 | 0.0453 | 5.11e-05 | 2.60e-05 | 190 | 0.6 | 11.1 | 26074 | 4 | 44.877668 | 0.993-1.003 | 4.99 | 95 | 2.1/32.8/65.1 |
| S | sa-wf_h0.134_fine30_morph-flap-0.5mm | VALID | 1.3720 | 0.0444 | 5.11e-05 | 2.54e-05 | 190 | 0.6 | 11.1 | 26074 | 4 | 44.877668 | 0.985-1.007 | 5.02 | 94 | 2.7/32.8/65.0 |
| S | sa-wf_h0.134_fine30_morph-heave+0.25mm | VALID | 1.4013 | 0.0460 | 2.48e-04 | 1.80e-04 | 184 | 0.6 | 11.2 | 26074 | 4 | 44.877663 | 0.998-1.016 | 5.05 | 94 | 2.0/32.8/65.1 |
| S | sa-wf_h0.134_fine30_morph-heave+0.5mm | VALID | 1.4015 | 0.0457 | 2.43e-04 | 1.60e-04 | 186 | 0.6 | 11.3 | 26074 | 4 | 44.877657 | 0.997-1.031 | 5.09 | 95 | 2.6/32.8/65.0 |
| S | sa-wf_h0.134_fine30_morph-heave-0.25mm | VALID | 1.3991 | 0.0465 | 2.60e-04 | 1.90e-04 | 186 | 0.6 | 11.1 | 26074 | 4 | 44.877674 | 0.984-1.002 | 5.00 | 92 | 2.0/32.8/65.2 |
| S | sa-wf_h0.134_fine30_morph-heave-0.5mm | VALID | 1.3980 | 0.0468 | 2.45e-04 | 1.75e-04 | 184 | 0.6 | 11.4 | 26074 | 4 | 44.87768 | 0.969-1.003 | 5.13 | 96 | 2.3/32.8/65.3 |
| S | sa-wf_h0.134_med30_da0 | VALID | 1.3960 | 0.0480 | 1.40e-04 | 4.15e-05 | 121 | 0.2 | 6.2 | 14151 | 7 | 38.62036 | --- | 5.24 | 75 | 2.2/32.3/64.5 |
| S | sa-wf_h0.134_med30_morph-camber+0.25mm | VALID | 1.4007 | 0.0487 | 1.28e-04 | 4.55e-05 | 121 | 0.3 | 6.1 | 14151 | 7 | 38.613939 | 0.993-1.009 | 5.10 | 76 | 2.2/32.3/64.5 |
| S | sa-wf_h0.134_med30_morph-camber+0.5mm | VALID | 1.4042 | 0.0495 | 1.37e-04 | 5.10e-05 | 123 | 0.3 | 6.3 | 14151 | 7 | 38.607472 | 0.986-1.018 | 5.22 | 76 | 3.0/32.2/64.5 |
| S | sa-wf_h0.134_med30_morph-camber-0.25mm | VALID | 1.3909 | 0.0473 | 1.59e-04 | 1.60e-16 | 123 | 0.3 | 6.3 | 14151 | 7 | 38.626782 | 0.991-1.007 | 5.21 | 75 | 2.8/32.3/64.4 |
| S | sa-wf_h0.134_med30_morph-camber-0.5mm | VALID | 1.3864 | 0.0466 | 1.58e-04 | 0.00e+00 | 123 | 0.3 | 6.3 | 14151 | 7 | 38.633204 | 0.982-1.014 | 5.23 | 75 | 3.2/32.3/64.4 |
| S | sa-wf_h0.134_med30_morph-flap+0.25mm | VALID | 1.4091 | 0.0489 | 1.22e-04 | 4.63e-05 | 119 | 0.3 | 5.8 | 14151 | 7 | 38.609613 | 0.997-1.009 | 4.76 | 76 | 2.0/32.3/64.6 |
| S | sa-wf_h0.134_med30_morph-flap+0.5mm | VALID | 1.4213 | 0.0498 | 1.23e-04 | 4.85e-05 | 121 | 0.3 | 5.9 | 14151 | 7 | 38.598868 | 0.993-1.018 | 4.93 | 77 | 2.3/32.3/64.7 |
| S | sa-wf_h0.134_med30_morph-flap-0.25mm | VALID | 1.3822 | 0.0471 | 1.47e-04 | 4.00e-05 | 119 | 0.3 | 6.4 | 14151 | 7 | 38.631107 | 0.991-1.003 | 5.28 | 76 | 2.5/32.3/64.4 |
| S | sa-wf_h0.134_med30_morph-flap-0.5mm | VALID | 1.3695 | 0.0462 | 1.39e-04 | 3.30e-05 | 121 | 0.3 | 6.2 | 14151 | 7 | 38.641858 | 0.982-1.007 | 5.14 | 76 | 3.0/32.2/64.3 |
| S | sa-wf_h0.134_med30_morph-heave+0.25mm | VALID | 1.3973 | 0.0477 | 1.45e-04 | 0.00e+00 | 123 | 0.3 | 6.4 | 14151 | 7 | 38.610232 | 0.998-1.024 | 5.35 | 76 | 2.5/32.3/64.4 |
| S | sa-wf_h0.134_med30_morph-heave+0.5mm | VALID | 1.3985 | 0.0474 | 1.40e-04 | 1.59e-16 | 123 | 0.3 | 6.4 | 14151 | 7 | 38.600107 | 0.996-1.048 | 5.33 | 75 | 2.9/32.3/64.3 |
| S | sa-wf_h0.134_med30_morph-heave-0.25mm | VALID | 1.3949 | 0.0483 | 1.27e-04 | 3.18e-05 | 121 | 0.3 | 6.4 | 14151 | 7 | 38.630489 | 0.976-1.002 | 5.30 | 75 | 2.0/32.3/64.5 |
| S | sa-wf_h0.134_med30_morph-heave-0.5mm | VALID | 1.3933 | 0.0486 | 1.30e-04 | 4.91e-05 | 123 | 0.3 | 6.3 | 14151 | 7 | 38.640621 | 0.952-1.004 | 5.24 | 76 | 2.3/32.2/64.6 |
| S | sa-wf_h0.224_fine30_camber+0.5mm | VALID | 1.3328 | 0.0329 | 8.85e-05 | 1.67e-16 | 244 | 0.7 | 11.7 | 26725 | 4 | 35.230847 | --- | 5.14 | 97 | 2.2/32.8/62.9 |
| S | sa-wf_h0.224_fine30_camber-0.5mm | VALID | 1.2788 | 0.0311 | 9.45e-05 | 1.74e-16 | 252 | 0.8 | 11.7 | 26735 | 4 | 33.362212 | --- | 5.17 | 96 | 1.7/32.6/63.5 |
| S | sa-wf_h0.224_fine30_da0 | VALID | 1.3083 | 0.0318 | 6.05e-05 | 8.19e-06 | 246 | 0.6 | 11.7 | 26916 | 4 | 36.32678 | --- | 5.19 | 97 | 1.9/32.8/63.5 |
| S | sa-wf_h0.224_fine30_flap+0.5mm | VALID | 1.3458 | 0.0333 | 2.30e-05 | 1.31e-06 | 230 | 0.7 | 10.7 | 26671 | 4 | 42.519588 | --- | 4.72 | 98 | 1.9/32.8/64.0 |
| S | sa-wf_h0.224_fine30_flap-0.5mm | VALID | 1.2930 | 0.0309 | 8.32e-05 | 4.78e-10 | 252 | 0.8 | 11.5 | 26827 | 4 | 40.4343 | --- | 5.04 | 98 | 1.7/32.8/63.0 |
| S | sa-wf_h0.224_fine30_heave+0.5mm | VALID | 1.3272 | 0.0319 | 1.01e-04 | 1.33e-09 | 259 | 0.8 | 11.7 | 26814 | 4 | 33.352496 | --- | 5.14 | 94 | 2.6/32.8/63.7 |
| S | sa-wf_h0.224_fine30_heave-0.5mm | VALID | 1.3193 | 0.0323 | 7.12e-05 | 0.00e+00 | 242 | 0.7 | 11.5 | 26761 | 4 | 37.750139 | --- | 5.07 | 94 | 3.0/32.7/63.3 |
| S | sa-wf_h0.224_fine30_morph-camber+0.25mm | VALID | 1.3196 | 0.0323 | 7.99e-05 | 0.00e+00 | 248 | 0.8 | 11.4 | 26916 | 4 | 36.471424 | 0.997-1.004 | 4.97 | 97 | 2.1/32.8/63.2 |
| S | sa-wf_h0.224_fine30_morph-camber+0.5mm | VALID | 1.3307 | 0.0327 | 8.12e-05 | 1.73e-07 | 250 | 0.7 | 11.3 | 26916 | 4 | 36.616427 | 0.994-1.009 | 4.94 | 96 | 2.2/32.8/62.8 |
| S | sa-wf_h0.224_fine30_morph-camber-0.25mm | VALID | 1.2967 | 0.0314 | 5.14e-05 | 2.98e-08 | 248 | 0.8 | 11.4 | 26916 | 4 | 36.182509 | 0.996-1.003 | 5.00 | 97 | 1.7/32.8/63.9 |
| S | sa-wf_h0.224_fine30_morph-camber-0.5mm | VALID | 1.2846 | 0.0310 | 7.69e-05 | 4.11e-08 | 247 | 0.8 | 11.8 | 26916 | 4 | 36.061247 | 0.991-1.006 | 5.13 | 97 | 2.8/32.7/64.2 |
| S | sa-wf_h0.224_fine30_morph-flap+0.25mm | VALID | 1.3268 | 0.0324 | 9.86e-05 | 0.00e+00 | 250 | 0.8 | 12.1 | 26916 | 4 | 36.32678 | 0.996-1.005 | 5.30 | 97 | 2.0/32.8/63.8 |
| S | sa-wf_h0.224_fine30_morph-flap+0.5mm | VALID | 1.3444 | 0.0330 | 3.85e-05 | 1.49e-05 | 240 | 0.8 | 11.8 | 26916 | 4 | 36.32678 | 0.993-1.011 | 5.14 | 98 | 2.4/32.8/64.0 |
| S | sa-wf_h0.224_fine30_morph-flap-0.25mm | VALID | 1.2899 | 0.0313 | 1.06e-04 | 0.00e+00 | 248 | 0.8 | 12.2 | 26916 | 4 | 36.32678 | 0.995-1.004 | 5.34 | 96 | 2.0/32.8/63.3 |
| S | sa-wf_h0.224_fine30_morph-flap-0.5mm | VALID | 1.2703 | 0.0307 | 6.96e-05 | 1.75e-16 | 244 | 0.8 | 12.1 | 26916 | 4 | 36.32678 | 0.989-1.007 | 5.30 | 97 | 2.7/32.8/63.0 |
| S | sa-wf_h0.224_fine30_morph-heave+0.25mm | VALID | 1.3068 | 0.0317 | 6.06e-05 | 8.00e-06 | 248 | 0.8 | 11.9 | 26916 | 4 | 36.325007 | 0.999-1.009 | 5.22 | 97 | 1.8/32.8/63.5 |
| S | sa-wf_h0.224_fine30_morph-heave+0.5mm | VALID | 1.3053 | 0.0316 | 5.96e-05 | 7.86e-06 | 248 | 0.8 | 11.8 | 26916 | 4 | 36.481748 | 0.997-1.017 | 5.15 | 97 | 1.7/32.8/63.5 |
| S | sa-wf_h0.224_fine30_morph-heave-0.25mm | VALID | 1.3099 | 0.0320 | 4.95e-05 | 8.27e-06 | 248 | 0.8 | 11.5 | 26916 | 4 | 36.328552 | 0.991-1.001 | 5.04 | 96 | 2.1/32.8/63.5 |
| S | sa-wf_h0.224_fine30_morph-heave-0.5mm | VALID | 1.3117 | 0.0321 | 1.05e-04 | 0.00e+00 | 252 | 0.8 | 11.8 | 26916 | 4 | 36.330324 | 0.983-1.003 | 5.18 | 97 | 2.1/32.8/63.5 |
| S | sa-wf_h0.224_med30_da0 | VALID | 1.3449 | 0.0333 | 1.88e-04 | 2.85e-10 | 135 | 0.2 | 6.1 | 14773 | 7 | 43.868342 | --- | 4.95 | 77 | 1.7/32.2/63.2 |
| S | sa-wf_h0.224_med30_morph-camber+0.25mm | VALID | 1.3580 | 0.0337 | 1.83e-04 | 0.00e+00 | 135 | 0.3 | 6.1 | 14773 | 7 | 43.969196 | 0.997-1.005 | 4.85 | 77 | 2.6/32.2/62.9 |
| S | sa-wf_h0.224_med30_morph-camber+0.5mm | VALID | 1.3709 | 0.0341 | 1.84e-04 | 1.62e-16 | 135 | 0.3 | 6.3 | 14773 | 7 | 44.070783 | 0.993-1.011 | 5.02 | 75 | 2.0/32.2/62.5 |
| S | sa-wf_h0.224_med30_morph-camber-0.25mm | VALID | 1.3313 | 0.0329 | 1.91e-04 | 0.00e+00 | 137 | 0.3 | 6.2 | 14773 | 7 | 43.768198 | 0.995-1.003 | 4.90 | 78 | 2.1/32.2/63.5 |
| S | sa-wf_h0.224_med30_morph-camber-0.5mm | VALID | 1.3171 | 0.0325 | 2.20e-04 | 1.69e-16 | 137 | 0.3 | 6.3 | 14773 | 7 | 43.668775 | 0.989-1.007 | 5.03 | 77 | 1.5/32.1/63.8 |
| S | sa-wf_h0.224_med30_morph-flap+0.25mm | VALID | 1.3650 | 0.0339 | 1.84e-04 | 1.63e-16 | 135 | 0.3 | 6.2 | 14773 | 7 | 43.868342 | 0.997-1.007 | 4.90 | 76 | 2.8/32.2/63.5 |
| S | sa-wf_h0.224_med30_morph-flap+0.5mm | VALID | 1.3848 | 0.0345 | 1.77e-04 | 0.00e+00 | 137 | 0.3 | 6.1 | 14773 | 7 | 43.868342 | 0.993-1.014 | 4.82 | 77 | 1.7/32.2/63.7 |
| S | sa-wf_h0.224_med30_morph-flap-0.25mm | VALID | 1.3242 | 0.0327 | 1.90e-04 | 0.00e+00 | 135 | 0.3 | 6.3 | 14773 | 7 | 43.868342 | 0.993-1.003 | 4.98 | 76 | 1.8/32.1/62.9 |
| S | sa-wf_h0.224_med30_morph-flap-0.5mm | VALID | 1.3027 | 0.0321 | 2.04e-04 | 0.00e+00 | 135 | 0.3 | 6.4 | 14773 | 7 | 43.868342 | 0.986-1.007 | 5.09 | 77 | 1.1/32.1/62.6 |
| S | sa-wf_h0.224_med30_morph-heave+0.25mm | VALID | 1.3430 | 0.0332 | 1.89e-04 | 3.31e-16 | 135 | 0.3 | 6.0 | 14773 | 7 | 43.87491 | 0.999-1.011 | 4.79 | 76 | 1.9/32.2/63.2 |
| S | sa-wf_h0.224_med30_morph-heave+0.5mm | VALID | 1.3411 | 0.0330 | 1.82e-04 | 3.02e-10 | 135 | 0.3 | 6.3 | 14773 | 7 | 43.88148 | 0.997-1.021 | 5.00 | 76 | 2.1/32.2/63.2 |
| S | sa-wf_h0.224_med30_morph-heave-0.25mm | VALID | 1.3467 | 0.0334 | 1.89e-04 | 0.00e+00 | 135 | 0.3 | 6.3 | 14773 | 7 | 43.861774 | 0.989-1.001 | 5.01 | 76 | 1.5/32.2/63.2 |
| S | sa-wf_h0.224_med30_morph-heave-0.5mm | VALID | 1.3485 | 0.0335 | 1.87e-04 | 3.29e-16 | 135 | 0.3 | 6.4 | 14773 | 7 | 43.855208 | 0.979-1.003 | 5.07 | 76 | 1.7/32.2/63.2 |
