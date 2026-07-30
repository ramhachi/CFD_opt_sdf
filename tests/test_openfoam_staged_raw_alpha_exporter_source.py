from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "openfoam_extensions" / "porousDirectionalForce"


def test_staged_raw_alpha_exporter_is_explicit_serial_and_fail_closed() -> None:
    source = (EXTENSION / "stagedRawAlphaGradientExporter.C").read_text(encoding="utf-8")
    header = (EXTENSION / "stagedRawAlphaGradientExporter.H").read_text(encoding="utf-8")

    assert 'TypeName("stagedRawAlphaGradientExporter")' in header
    assert "gradientVariable != \"staged_raw_alpha\"" in source
    assert 'derivativeMeaning != "dJ=sum_i g_alpha[i]*d(alpha_i)"' in source
    assert 'internalChain != "alpha->alphaTilda->beta->response"' in source
    assert "newtonConversionFactor" in source
    assert "newtonConversionFormula" in source
    assert "newtonConversionUnits" in source
    assert "sourcePath" in source and "sourceSha256" in source
    assert "runTime_.timeName()" in source
    assert "Pstream::parRun()" in source
    assert "No native field or metadata artifact was written" in source


def test_exporter_does_not_relabel_legacy_sensitivity_fields() -> None:
    source = (EXTENSION / "stagedRawAlphaGradientExporter.C").read_text(encoding="utf-8")
    readme = (EXTENSION / "README.md").read_text(encoding="utf-8")

    assert "topologySens" not in source
    assert "dJ/dbeta" in readme
    assert "cannot be relabelled" in readme


def test_exporter_is_in_the_extension_build_source_list() -> None:
    make_files = (EXTENSION / "Make" / "files").read_text(encoding="utf-8")
    assert "stagedRawAlphaGradientExporter.C" in make_files
