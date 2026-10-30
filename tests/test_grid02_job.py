import difflib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts" / "waterlily_lowdim02_flow32_job.jl"
JOB = ROOT / "scripts" / "waterlily_grid02_job.jl"
CASE = ROOT / "scripts" / "grid02_case.jl"
MODULE = ROOT / "julia" / "CFDSDFWaterLily" / "src" / "V16W4Sensitivity.jl"
JULIA = shutil.which("julia")
VALIDATE = "    validate_grid02_case(case; canonical_design_origin_m=CANONICAL_ORIGIN_M,"


def test_job_differs_from_flow32_job_only_in_intended_lines():
    a, b = BASE.read_text().splitlines(), JOB.read_text().splitlines()
    changes = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            changes.append((i1 + 1, i2, a[i1:i2], b[j1:j2]))
    # (old first line, old last line) pairs; line numbers are of the flow_32 job
    assert [(c[0], c[1]) for c in changes] == [
        (1, 3), (29, 28), (30, 30), (61, 61), (141, 141), (320, 320), (347, 348), (366, 366)]
    by_start = {c[0]: c for c in changes}
    assert "GRID02_CASE" in " ".join(by_start[1][3]) and "flow_32" not in " ".join(by_start[1][3])
    assert by_start[29][3] == ['include(joinpath(@__DIR__, "grid02_case.jl"))']
    assert 'usage: waterlily_grid02_job.jl <phi_fortran.raw> <output_dir>' in by_start[30][3][0]
    assert by_start[61][3] == ["const EXPECTED_CASE_IDS = (grid02_case_id(),)"]
    assert by_start[141][3] == [VALIDATE] and by_start[320][3] == [VALIDATE]
    assert by_start[347][3] == [
        "    cases = (grid02_case(CANONICAL_ORIGIN_M, CANONICAL_DESIGN_SPACING_M),)"]
    assert "GRID-02 $(only(EXPECTED_CASE_IDS)) case returned" in by_start[366][3][0]
    text = JOB.read_text()
    assert "validate_w4_case" not in text and "w4_cases(" not in text
    assert 'W4_CANONICAL_ORIGIN_M' in text and '"flow_32"' not in text


needs_julia = pytest.mark.skipif(JULIA is None, reason="julia not installed")


def julia(code, env=None):
    import os
    return subprocess.run([JULIA, "--startup-file=no", "-e", code], capture_output=True,
                          text=True, env={**os.environ, **(env or {})})


@needs_julia
def test_sources_parse():
    for f in (JOB, CASE):
        r = julia("Meta.parseall(read(ARGS[1],String))".replace("ARGS[1]", f'"{f}"'))
        assert r.returncode == 0, r.stderr


PRELUDE = f'''
module W; include("{MODULE}"); end
using .W.V16W4Sensitivity
include("{CASE}")
const O = (-1.0, -0.8, -0.6); const H = 0.05
expect_error(f) = (try f(); false catch; true end) || error("expected raise")
'''


@needs_julia
def test_validation_builds_and_rejects():
    code = PRELUDE + '''
for (id, dims, nu, n) in (("flow_48", (300,144,108), 0.6, 48), ("flow_16", (100,48,36), 0.2, 16))
    ENV["GRID02_CASE"] = id
    c = grid02_case(O, H)
    @assert c.case_id == id && c.flow_dims == dims && c.solver_length == n
    @assert isapprox(c.solver_viscosity, nu; atol=1e-12)
    validate_grid02_case(c; canonical_design_origin_m=O, canonical_design_spacing_m=H)
    # shifted origin is carried through and validated against the same value
    S = (-0.9875, -0.7875, -0.6)
    cs = grid02_case(S, H)
    validate_grid02_case(cs; canonical_design_origin_m=S, canonical_design_spacing_m=H)
    expect_error(() -> validate_grid02_case(cs; canonical_design_origin_m=O, canonical_design_spacing_m=H))
    expect_error(() -> validate_grid02_case(c; canonical_design_origin_m=O, canonical_design_spacing_m=0.04))
    expect_error(() -> validate_grid02_case(c; canonical_design_origin_m=O, canonical_design_spacing_m=H,
        dims_table=Dict(id => (dims[1] + 1, dims[2], dims[3]))))
end
# case id: absent / invalid must raise
delete!(ENV, "GRID02_CASE"); expect_error(grid02_case_id)
for bad in ("flow_24", "flow_32", ""); ENV["GRID02_CASE"] = bad; expect_error(grid02_case_id); end
println("OK")
'''
    r = julia(code, env={"GRID02_CASE": ""})
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr
