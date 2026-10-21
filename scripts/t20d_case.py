#!/usr/bin/env python3
"""T2-0d (#57, registration docs/t20d_registration_2026_10_21.md section 3): the stage-2 runs of a solved S0 case.

S0 is the T2-0c steady case unchanged (scripts/t20c_case.py through the pinned generator; simpleFoam, SIMPLEC 0.9, 5000 iterations from uniform fields).
A stage-2 run copies the S0 case (mesh, dictionaries and S0's final fields; no mapping, no interpolation) and swaps its dictionaries:
- U, Udt2, Udt05, US1: pimpleFoam from the source's latest U, p, nuTilda, nut, phi moved to time 0; S0's schemes with `bounded` removed and `ddt backward`;
  PIMPLE 2 outer and 2 pressure correctors, no relaxation; fixed dt (DT) to END_TIME_S; forceCoeffs (S0's function objects) every step. The source is the S0 case,
  except for US1, whose source is the S1 run (a second start state).
- S1: simpleFoam continued from S0's latest time to S1_END_ITER with SIMPLE (consistent no), relaxation p 0.3, U 0.7, nuTilda 0.7; schemes unchanged.
The pinned T2-0a/T2-0c files are not modified.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

DT = {"U": 1e-5, "Udt2": 2e-5, "Udt05": 5e-6, "US1": 1e-5}                 # s
END_TIME_S = {"U": 0.1192, "Udt2": 0.1192, "Udt05": 0.0819, "US1": 0.1192}   # 16.0 T_c (Udt05: 11.0 T_c), T_c = 0.2234 / 30 s
T_TR_S = 0.0447                                                            # 6.0 T_c transient; the window is T_TR_S < t <= the end time
S1_END_ITER = 15000                      # S0 ends at 5000: 10000 relaxed iterations
FIELDS = ("U", "p", "nuTilda", "nut", "phi")
KINDS = (*DT, "S1")


def latest_time(case: Path) -> Path:
    """The S0 case's latest numeric time directory other than 0."""
    times = [p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"[0-9.eE+-]+", p.name) and float(p.name) > 0]
    if not times:
        raise FileNotFoundError(f"no solved time directory in {case}")
    return max(times, key=lambda p: float(p.name))


def _sub(pattern: str, repl: str, text: str, count: int = 1) -> str:
    out, n = re.subn(pattern, repl, text, flags=re.M)
    if n != count:
        raise ValueError(f"{pattern!r}: {n} matches, expected {count}")
    return out


def urans_dicts(s0: Path, dt: float, end_time: float) -> dict[str, str]:
    """controlDict, fvSchemes, fvSolution of a U run, derived from the S0 text so that everything else (function objects, gradients) stays S0's."""
    n_steps = round(end_time / dt)
    cd = (s0 / "system/controlDict").read_text()
    head = cd[:cd.index("application")]
    funcs = cd[cd.index("functions"):]
    control = head + f"""application pimpleFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {end_time};
deltaT {dt};
adjustTimeStep no;
writeControl timeStep;
writeInterval {n_steps};
purgeWrite 1;
writeFormat ascii;
writePrecision 8;
timePrecision 8;
runTimeModifiable false;

""" + funcs
    sch = (s0 / "system/fvSchemes").read_text()
    sch = _sub(r"^ddtSchemes \{ default steadyState; \}$", "ddtSchemes { default backward; }", sch)
    sch = sch.replace("bounded Gauss", "Gauss")
    sol = (s0 / "system/fvSolution").read_text()
    sol = sol[:sol.index("solvers")] + """solvers
{
    p { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }
    pFinal { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0; }
    "(U|nuTilda)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
    "(U|nuTilda)Final" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }
}
PIMPLE
{
    momentumPredictor yes;
    nOuterCorrectors 2;
    nCorrectors 2;
    nNonOrthogonalCorrectors 1;
}
relaxationFactors
{
    equations { ".*" 1; }
}
"""
    return {"system/controlDict": control, "system/fvSchemes": sch, "system/fvSolution": sol}


def relaxed_dicts(s0: Path, end_iter: int = S1_END_ITER) -> dict[str, str]:
    """controlDict and fvSolution of the S1 run (continuation of S0 with conservative SIMPLE relaxation). The copy carries no `uniform/time`, so the
    time index restarts at 0: the write interval is the number of S1 iterations (end_iter - the source iteration), which writes the final state."""
    start = int(float(latest_time(s0).name))
    if end_iter <= start:
        raise ValueError(f"S1 end {end_iter} not after the source iteration {start}")
    cd = (s0 / "system/controlDict").read_text()
    cd = _sub(r"^startFrom .*;$", "startFrom latestTime;", cd)
    cd = _sub(r"^endTime .*;$", f"endTime {end_iter};", cd)
    cd = _sub(r"^writeInterval .*;$", f"writeInterval {end_iter - start};", cd)
    sol = (s0 / "system/fvSolution").read_text()
    sol = _sub(r"^    consistent yes;$", "    consistent no;", sol)
    sol = _sub(r"^relaxationFactors\n\{\n(.*\n)*?\}\n", 'relaxationFactors\n{\n    fields { p 0.3; }\n    equations { "(U|nuTilda)" 0.7; }\n}\n', sol)
    return {"system/controlDict": cd, "system/fvSolution": sol}


def stage2_case(s0: Path, out: Path, kind: str, end=None) -> dict:
    """Copy the solved source case `s0` (S0; the S1 run for US1) into `out` as a `kind` run; returns the stage record (written into out/case_manifest.json under
    `stage2`). `end` (development smoke only) shortens the run: end time [s] for the URANS kinds, end iteration for S1."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    src = latest_time(s0)
    out.mkdir(parents=True)
    for d in ("constant", "system"):
        shutil.copytree(s0 / d, out / d)
    if kind == "S1":
        shutil.copytree(src, out / src.name, ignore=shutil.ignore_patterns("uniform", "yPlus"))
        end = end or S1_END_ITER
        files = relaxed_dicts(s0, end)
    else:
        (out / "0").mkdir()
        for f in FIELDS:
            if (src / f).is_file():
                shutil.copy2(src / f, out / "0" / f)
        end = end or END_TIME_S[kind]
        files = urans_dicts(s0, DT[kind], end)
    for rel, text in files.items():
        (out / rel).write_text(text)
    man = json.loads((s0 / "case_manifest.json").read_text())
    rec = {"kind": kind, "source_time": src.name, "dt_s": DT.get(kind), "end_time_s": end if kind in DT else None, "transient_s": T_TR_S if kind in DT else None,
           "end_iteration": end if kind == "S1" else None}
    man["stage2"] = rec
    (out / "case_manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--s0", type=Path, required=True, help="solved S0 case directory")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--kind", choices=KINDS, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(stage2_case(a.s0, a.out, a.kind)))


if __name__ == "__main__":
    main()
