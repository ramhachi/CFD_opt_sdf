# Draft: data request for Zhou, Overmars & Westerweel (2026), Exp. Fluids 67(6):75

Status: draft for the user to send (DATA-G, GEN-01 plan §7). Not sent. The paper states its data are available on request (research report C §2). Fill in the bracketed parts before sending.

---

Subject: Data request — Tyrrell 026 wing in ground effect, Exp. Fluids 67:75 (2026)

Dear Dr Zhou, Dr Overmars and Prof. Westerweel,

I am [name], [role] with the Formula SAE team at [Tokyo Metropolitan University / institution], where we develop an open research code for aerodynamic shape optimisation of ground-effect wings and full Formula Student vehicles (repository: https://github.com/ramhachi/CFD_opt_sdf). Our work uses pre-registered, frozen evaluation protocols, and we are assembling the validation data for the ground-effect wing section.

Your 2026 Experiments in Fluids paper on the Tyrrell 026 profile (span 550 mm, chord 110.8 mm, H/C 0.054–1.40, accelerating start and steady phase, PIV-based force reconstruction) is, as far as we can find, the only recent primary dataset on this section with resolved flow fields. Zerihan & Zhang's 2000 data, which we currently use, are described by their authors as suitable for qualitative trends only.

Would you be willing to share the following, under whatever terms you consider appropriate (we would cite the paper and your data statement in every use, and we can agree not to redistribute)?

1. The steady-phase time-averaged lift and drag (or the reconstructed force histories) versus H/C, with the averaging windows used.
2. The time-averaged velocity fields (PIV) at the steady phase for a subset of H/C values — ideally H/C ≈ 0.15 (your optimum), 0.22 and one value below 0.1.
3. Any estimate of the force uncertainty (run-to-run repeatability or the impulse-reconstruction uncertainty), and the free-stream turbulence intensity and Reynolds number of the facility.

Our intended use is a validation rung for a 2D RANS/URANS evaluator at low ride heights (trend of force with H/C, onset height of the force reduction, and the frequency of the shedding you report near 5 Hz). We would not use the data to tune a model; our protocol registers the comparison rule before the data are read.

Thank you for considering this request.

Kind regards,
[name]
[affiliation, email]
