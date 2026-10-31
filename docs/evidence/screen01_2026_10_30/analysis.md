# SCREEN-01 analysis: SCREEN01_GAIN

cause: []

| item | value |
| --- | --- |
| finalist | "v18__camber_m29.55_pitch_p0.155_reflex_p16.115" |
| futility | null |
| search_complete | true |
| pool_limited | false |
| r_best | "v18__camber_m28.656_pitch_m0.68_reflex_p2.727" |
| K_opt | 19 |
| K_rand | 19 |
| g1_controls | {"NC_g1": {"label": "CONSISTENT", "z": 0.48039721441320915}, "determinism_g1k11": {"judged": true, "max_abs_diff": {"downforce": 0.0, "drag": 0.0}, "nondeterminism": false}, "invalid_at_step_2": false} |
| G | {"GAIN_RESOLVED_ABOVE_MIN": true, "decision": "PASS"} |
| D | {"decision": "PASS", "label": "PASS_RESOLVED"} |
| R3 | {"G48_ABOVE_MIN": true, "G48_MARGIN": 0.0031729290613620037, "R3_DRAG_SAME_SIGN": true, "R3_E2_EXCEEDED": false, "R3_RATIO_IN_BAND": true, "label": "R3_CONFIRMED"} |
| NC | {"f32": {"label": "CONSISTENT", "z": 0.05235997377511001}, "g1": {"label": "CONSISTENT", "z": 0.48039721441320915}} |
| determinism | {"f32a": {"judged": true, "max_abs_diff": {"downforce": 0.0, "drag": 0.0}, "nondeterminism": false}, "g1k11": {"judged": true, "max_abs_diff": {"downforce": 0.0, "drag": 0.0}, "nondeterminism": false}} |
| generation_drift | {"drift": false, "max_abs_diff": {"downforce": 0.0, "drag": 0.0}} |
| controls | {"K_MISMATCH": false, "OPT_VS_MANUAL": "OPT_BEATS_MANUAL", "OPT_VS_RANDOM": "OPT_BEATS_RANDOM", "RANDOM_FEASIBLE_GAIN": false} |
| selection_bias | {"XV_MARGIN": {"central": "XV_MARGIN_ADEQUATE", "pessimistic": "XV_MARGIN_ADEQUATE"}, "b_K": {"central": 0.0010347541280097462, "upper": 0.0026697259050362117}, "g_XV_exp": {"central": 0.02400236872435667, "pessimistic": 0.01738113623200366}} |

determinism NOT_JUDGED (repeat absent or not ok): none
rs_fit_label: RS_FIT_POOR
G1 chain controls invalid_at_step_2: False
