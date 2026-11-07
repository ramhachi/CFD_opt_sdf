"""Transcription fidelity is independent of OCR/physical geometry qualification."""
from pathlib import Path
import re

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/zz2003"


def test_coordinate_transcription_matches_primary_ocr_tokens():
    text = (ROOT / "docs/codex/gen01_w1_2026_11_06/reports/topo2d00_source_tables.txt").read_text()
    lines = {}
    for number, body in re.findall(r"^L(\d+): (.*)$", text, re.M):
        if number in lines:
            assert lines[number] == body, f"conflicting repeated OCR line {number}"
        lines[number] = body
    rows = [(int(n), re.findall(r"<td>([-+0-9.]+)</td>", body))
            for n, body in lines.items() if "<tr><td>" in body]
    for name, lo, hi, count in (
        ("single_element_table2.dat", 955, 998, 44),
        ("main_element_table3.dat", 1008, 1051, 44),
        ("flap_table4.dat", 1061, 1078, 18),
    ):
        # Ranges precede the indexed captions at L1000, L1053 and L1080.
        source_rows = [values for n, values in sorted(rows) if lo <= n <= hi]
        data_lines = [line for line in (DATA / name).read_text().splitlines()
                      if line.strip() and not line.startswith("#")]
        assert len(source_rows) == len(data_lines) == count
        assert [line.split("#", 1)[0].split() for line in data_lines] == source_rows
        assert all("# UNVERIFIED" in line for line in data_lines)


def test_main_source_is_distinct_from_the_sharpened_t20_variant():
    original = np.loadtxt(DATA / "single_element_table2.dat")
    sharpened = np.loadtxt(ROOT / "data/t20/tyrrell026s_genua2009.dat")
    np.testing.assert_allclose(np.max(np.abs(original - sharpened), axis=0),
                               [0, .0036, 0, .0037], rtol=0, atol=1e-14)
    assert np.isclose((original[-1, 3] - original[-1, 1]) * 223.4, 1.63082)
    assert sharpened[-1, 3] == sharpened[-1, 1]
    main = np.loadtxt(DATA / "main_element_table3.dat") * (380 / 223.4)
    np.testing.assert_allclose(np.max(np.abs(main - sharpened), axis=0),
        [.00023428827215754566, .003657206803939113,
         .00020590868397496465, .003827126230975829], rtol=1e-11, atol=1e-14)


def test_spline_resampling_interpolates_every_transcribed_table_coordinate():
    from cfd_gen.topo2d.geometry import build_scene
    scene = build_scene("E2_sharp", height_mm=100, dx_mm=223.4 / 120)
    for name, element, transform in zip(("main_element_table3.dat", "flap_table4.dat"),
                                        scene["elements"], scene["placement"]["transformations"]):
        rows = np.loadtxt(DATA / name) * 380
        for surface, columns in (("suction_mm", slice(0, 2)), ("pressure_mm", slice(2, 4))):
            dense = np.asarray(element[surface]) - transform["translation_mm"]
            distances = np.linalg.norm(rows[:, columns, None] - dense.T[None], axis=1)
            assert distances.min(axis=1).max() < 1e-10
