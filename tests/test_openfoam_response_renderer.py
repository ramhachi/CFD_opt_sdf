from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from cfd_sdf.openfoam_response_renderer import render_openfoam_force_response_files
from cfd_sdf.solver_case_manifest import SolverFlowCasePlan


PRIMAL_BLOCK = '''primalSolvers
{
    op1
    {
        type incompressible;
        note "quoted braces } { stay";
    }
}
'''
OLD_ADJOINT = '''adjointManagers
{
    oldManager
    {
        // misleading braces { }
        oldSolver { active false; }
    }
}
'''
OPTIMISATION_BLOCK = '''optimisation
{
    designVariables { type density; }
    updateMethod { type mma; }
}
'''
OTHER_SOURCE = '''otherSource
{
    type scalarSemiImplicitSource;
    names (keepThis);
}
'''


def _optimisation_text(adjoint: str = OLD_ADJOINT) -> str:
    return (
        "FoamFile\n{\n    object optimisationDict;\n}\n"
        "// outside comment with braces { ignored }\n"
        + PRIMAL_BLOCK
        + adjoint
        + OPTIMISATION_BLOCK
    )


def _fv_options_text(top_source: str | None = None) -> str:
    if top_source is None:
        top_source = '''topologySource
{
    type topOSource;
    // names (fakeInComment);
    names (U Uaas1 Uadownforce);
    selectionMode all;
}
'''
    return "FoamFile\n{\n    object fvOptions;\n}\n" + top_source + OTHER_SOURCE


def _write_case(
    tmp_path: Path,
    *,
    optimisation: str | None = None,
    fv_options: str | None = None,
) -> Path:
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "system/optimisationDict").write_text(
        _optimisation_text() if optimisation is None else optimisation,
        encoding="utf-8",
        newline="\n",
    )
    (case / "system/fvOptions").write_text(
        _fv_options_text() if fv_options is None else fv_options,
        encoding="utf-8",
        newline="\n",
    )
    return case


def _response(response_id: str, direction=(1.0, 0.0, 0.0)) -> dict:
    return {
        "response_id": response_id,
        "openfoam_objective_type": "porousDirectionalForce",
        "direction": direction,
        "Aref": 1.2,
        "UInf": 30.0,
    }


def _plan(*response_ids: str) -> SolverFlowCasePlan:
    ids = response_ids or ("drag",)
    return SolverFlowCasePlan(
        flow_case_id="straight",
        case_directory_name="flow_straight",
        requested={"response_ids": ids},
        generated={"responses": tuple(_response(response_id) for response_id in ids)},
        supported_response_ids=tuple(ids),
        unsupported=(),
    )


def _replace_plan(plan: SolverFlowCasePlan, **updates) -> SolverFlowCasePlan:
    values = {
        "flow_case_id": plan.flow_case_id,
        "case_directory_name": plan.case_directory_name,
        "requested": deepcopy(plan.requested),
        "generated": deepcopy(plan.generated),
        "supported_response_ids": plan.supported_response_ids,
        "unsupported": plan.unsupported,
    }
    values.update(updates)
    return SolverFlowCasePlan(**values)


def test_one_force_response_maps_to_solver_field_and_objective(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    artifacts = render_openfoam_force_response_files(
        _plan("rotated_force"), case, adjoint_iterations=17
    )

    optimisation = artifacts.optimisation_dict.read_text(encoding="utf-8")
    fv_options = artifacts.fv_options.read_text(encoding="utf-8")
    assert "resp_rotated_force" in optimisation
    assert "isConstraint false;" in optimisation
    assert "type porousDirectionalForce;" in optimisation
    assert "direction (1 0 0);" in optimisation
    assert "Aref 1.2;" in optimisation
    assert "UInf 30;" in optimisation
    assert "nIters 17;" in optimisation
    assert '"pa.*" 5e-7;' in optimisation
    assert '"Ua.*" 5e-7;' in optimisation
    assert "names (U Uaresp_rotated_force);" in fv_options
    assert artifacts.response_ids == ("rotated_force",)


def test_two_force_responses_preserve_requested_order(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    artifacts = render_openfoam_force_response_files(_plan("drag", "side_force"), case)

    optimisation = artifacts.optimisation_dict.read_text(encoding="utf-8")
    assert optimisation.index("resp_drag") < optimisation.index("resp_side_force")
    assert "names (U Uaresp_drag Uaresp_side_force);" in artifacts.fv_options.read_text(
        encoding="utf-8"
    )
    metadata = json.loads(artifacts.metadata_json.read_text(encoding="utf-8"))
    assert [item["response_id"] for item in metadata["response_mappings"]] == [
        "drag",
        "side_force",
    ]
    assert metadata["response_mappings"][1]["adjoint_velocity_field"] == "Uaresp_side_force"


def test_non_target_blocks_and_comment_braces_are_byte_preserved(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    render_openfoam_force_response_files(_plan(), case)

    optimisation = (case / "system/optimisationDict").read_text(encoding="utf-8")
    fv_options = (case / "system/fvOptions").read_text(encoding="utf-8")
    assert PRIMAL_BLOCK in optimisation
    assert OPTIMISATION_BLOCK in optimisation
    assert "// outside comment with braces { ignored }\n" in optimisation
    assert OTHER_SOURCE in fv_options
    assert "names (keepThis);" in fv_options


def test_non_target_crlf_template_bytes_are_preserved(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    optimisation_path = case / "system/optimisationDict"
    fv_path = case / "system/fvOptions"
    optimisation_path.write_bytes(_optimisation_text().replace("\n", "\r\n").encode("utf-8"))
    fv_path.write_bytes(_fv_options_text().replace("\n", "\r\n").encode("utf-8"))

    render_openfoam_force_response_files(_plan(), case)

    optimisation = optimisation_path.read_bytes()
    fv_options = fv_path.read_bytes()
    assert PRIMAL_BLOCK.replace("\n", "\r\n").encode("utf-8") in optimisation
    assert OPTIMISATION_BLOCK.replace("\n", "\r\n").encode("utf-8") in optimisation
    assert OTHER_SOURCE.replace("\n", "\r\n").encode("utf-8") in fv_options


def test_metadata_pre_post_hashes_match_readback(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    optimisation_before = (case / "system/optimisationDict").read_bytes()
    fv_before = (case / "system/fvOptions").read_bytes()
    artifacts = render_openfoam_force_response_files(_plan(), case)
    metadata = json.loads(artifacts.metadata_json.read_text(encoding="utf-8"))

    records = metadata["source_files"]
    assert records["system/optimisationDict"]["pre_sha256"] == hashlib.sha256(
        optimisation_before
    ).hexdigest()
    assert records["system/fvOptions"]["pre_sha256"] == hashlib.sha256(fv_before).hexdigest()
    for relative, record in records.items():
        digest = hashlib.sha256((case / relative).read_bytes()).hexdigest()
        assert digest == record["post_sha256"]
        assert artifacts.file_sha256[relative] == digest


def test_unsupported_plan_and_missing_sources_are_rejected(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    unsupported = _replace_plan(_plan(), unsupported=("unsupported_response_kind:pitch:moment",))
    with pytest.raises(ValueError, match="unsupported features"):
        render_openfoam_force_response_files(unsupported, case)

    missing = tmp_path / "missing"
    missing.mkdir()
    with pytest.raises(FileNotFoundError, match="optimisationDict and system/fvOptions"):
        render_openfoam_force_response_files(_plan(), missing)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda plan: plan.generated.update(responses=()), "non-empty sequence"),
        (
            lambda plan: plan.generated["responses"][0].update(response_id="bad/path"),
            "Unsafe response_id",
        ),
        (
            lambda plan: plan.generated.update(
                responses=(plan.generated["responses"][0], plan.generated["responses"][0])
            ),
            "Duplicate generated response_id",
        ),
        (
            lambda plan: plan.generated["responses"][0].update(openfoam_objective_type="moment"),
            "must use porousDirectionalForce",
        ),
        (
            lambda plan: plan.generated["responses"][0].update(direction=[1.0, 0.0]),
            "finite vector3",
        ),
        (lambda plan: plan.generated["responses"][0].update(Aref=0), "Aref must be positive"),
        (lambda plan: plan.generated["responses"][0].update(UInf=float("nan")), "UInf must be finite"),
    ],
)
def test_invalid_response_contracts_are_rejected(tmp_path: Path, mutation, message: str) -> None:
    case = _write_case(tmp_path)
    plan = _plan()
    mutation(plan)

    with pytest.raises(ValueError, match=message):
        render_openfoam_force_response_files(plan, case)


@pytest.mark.parametrize("iterations", [0, -1, 1.5, True])
def test_invalid_adjoint_iterations_are_rejected(tmp_path: Path, iterations) -> None:
    case = _write_case(tmp_path)
    with pytest.raises(ValueError, match="positive integer"):
        render_openfoam_force_response_files(_plan(), case, adjoint_iterations=iterations)


def test_existing_metadata_requires_explicit_overwrite(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    first = render_openfoam_force_response_files(_plan(), case)
    with pytest.raises(FileExistsError, match="overwrite=True"):
        render_openfoam_force_response_files(_plan(), case)

    second = render_openfoam_force_response_files(
        _plan("drag", "side_force"), case, adjoint_iterations=5, overwrite=True
    )
    assert first.metadata_json == second.metadata_json
    assert second.response_ids == ("drag", "side_force")


@pytest.mark.parametrize(
    ("optimisation", "fv_options", "message"),
    [
        (_optimisation_text(adjoint=""), None, "top-level adjointManagers block, found 0"),
        (
            _optimisation_text(adjoint=OLD_ADJOINT + OLD_ADJOINT),
            None,
            "top-level adjointManagers block, found 2",
        ),
        (None, _fv_options_text(top_source=OTHER_SOURCE), "topOSource block, found 0"),
        (
            None,
            _fv_options_text() + _fv_options_text().split("FoamFile", 1)[1].split("}", 1)[1],
            "topOSource block, found 2",
        ),
        (
            None,
            _fv_options_text(
                top_source="topologySource\n{\n type topOSource;\n selectionMode all;\n}\n"
            ),
            "names statement in topOSource, found 0",
        ),
        (
            None,
            _fv_options_text(
                top_source=(
                    "topologySource\n{\n type topOSource;\n names (U);\n names (V);\n}\n"
                )
            ),
            "names statement in topOSource, found 2",
        ),
        (
            _optimisation_text() + "broken\n{\n",
            None,
            "Unbalanced opening brace",
        ),
    ],
)
def test_malformed_missing_and_ambiguous_blocks_fail_before_any_write(
    tmp_path: Path,
    optimisation: str | None,
    fv_options: str | None,
    message: str,
) -> None:
    case = _write_case(tmp_path, optimisation=optimisation, fv_options=fv_options)
    optimisation_before = (case / "system/optimisationDict").read_bytes()
    fv_before = (case / "system/fvOptions").read_bytes()

    with pytest.raises(ValueError, match=message):
        render_openfoam_force_response_files(_plan(), case)
    assert (case / "system/optimisationDict").read_bytes() == optimisation_before
    assert (case / "system/fvOptions").read_bytes() == fv_before
    assert not (case / "generated_openfoam_responses.json").exists()
