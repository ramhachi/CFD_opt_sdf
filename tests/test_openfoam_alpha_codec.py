from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.openfoam_alpha_codec import (
    openfoam_alpha_values_sha256,
    read_openfoam_alpha_field,
    write_and_verify_openfoam_alpha_field,
)


def _alpha_path(tmp_path: Path, internal_field: str = "internalField uniform 0;") -> Path:
    path = tmp_path / "0.orig" / "alpha"
    path.parent.mkdir()
    path.write_text(
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class volScalarField;\n    object alpha;\n}\n\n"
        "dimensions [0 0 0 0 0 0 0];\n"
        + internal_field
        + "\n\nboundaryField\n{\n    outlet { type zeroGradient; }\n}\n",
        encoding="utf-8",
    )
    return path


def test_writes_posix_nonuniform_alpha_and_exactly_reads_it_back(tmp_path: Path) -> None:
    path = _alpha_path(tmp_path)
    expected = np.array([0.0, 0.125, 1.0, -0.0], dtype=np.float64)

    observed = write_and_verify_openfoam_alpha_field(path, expected)

    assert observed.cell_count == 4
    assert np.array_equal(observed.values, expected)
    assert observed.value_sha256 == openfoam_alpha_values_sha256(expected)
    assert read_openfoam_alpha_field(path).value_sha256 == observed.value_sha256
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.count(b"internalField") == 1
    assert b"internalField nonuniform List<scalar>\n4\n(" in raw
    assert b"boundaryField" in raw


@pytest.mark.parametrize(
    ("internal_field", "message"),
    [
        ("internalField nonuniform List<scalar> 2\n(\n0\n);", "count does not match"),
        ("internalField nonuniform List<scalar> 1\n(\nnan\n);", "non-finite"),
        ("internalField uniform 0;\ninternalField uniform 1;", "exactly one"),
        ("internalField uniform 0;\ninternalField malformed;", "exactly one"),
    ],
)
def test_read_refuses_malformed_or_ambiguous_internal_field(tmp_path: Path, internal_field: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        read_openfoam_alpha_field(_alpha_path(tmp_path, internal_field))


@pytest.mark.parametrize(
    ("field_text", "message"),
    [
        ("not-a-field", "FoamFile"),
        (
            "FoamFile\n{\n class volVectorField;\n object alpha;\n}\ninternalField uniform 0;\n",
            "class/object",
        ),
        (
            "FoamFile\n{\n class volScalarField;\n object beta;\n}\ninternalField uniform 0;\n",
            "class/object",
        ),
    ],
)
def test_write_refuses_invalid_foamfile_header(tmp_path: Path, field_text: str, message: str) -> None:
    path = tmp_path / "0.orig" / "alpha"
    path.parent.mkdir()
    path.write_text(field_text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        write_and_verify_openfoam_alpha_field(path, np.array([0.5], dtype=np.float64))


def test_refuses_non_float64_nan_and_non_alpha_path(tmp_path: Path) -> None:
    path = _alpha_path(tmp_path)
    with pytest.raises(ValueError, match="float64"):
        write_and_verify_openfoam_alpha_field(path, np.array([0.5], dtype=np.float32))
    with pytest.raises(ValueError, match="non-finite"):
        write_and_verify_openfoam_alpha_field(path, np.array([np.nan], dtype=np.float64))
    other = tmp_path / "0.orig" / "beta"
    other.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="0.orig/alpha"):
        read_openfoam_alpha_field(other)
