#!/usr/bin/env python3
"""T2-0b (#57): digitise the experimental Cl(h/c) curve (red markers) of Genua 2009, paper 1, Figure 6 (thesis PDF p. 9).

The figure is a 150 ppi raster inside the PDF; the page is rendered at 300 dpi with poppler's `pdftoppm` (local data preparation, not run on Kaggle).
Calibration: y from the tick marks left of the y axis (Cl 1.8 ... 0.8 in steps of 0.1, least squares), x from the visible markers at h/c 0.671 and 0.09.
Five red markers are free-standing (detected as red blobs after a morphological opening); the markers at h/c 0.179 and 0.134 are covered by black
symbols, so each is the mean of the two adjacent red line segments evaluated at the marker's x (each segment fitted to its red pixels away from the
markers); the half difference of the two evaluations is reported as that point's digitisation spread. Validation: the digitised values at h/c 0.224
and 0.09 must match the tabulated experimental Cl (1.286, 1.371; Genua Table 6) within 0.005, else the script fails.
The PDF is not in the repository (copyright); its SHA-256 is checked. Output: data/t20/zerihan_zhang_cl_genua2009_fig6.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
PDF_SHA256 = "f41cd300c32dc9db41484cb86c834a7b3b60596aff3478aef0f25e98b32e0d41"
URL = "https://repository.tudelft.nl/file/File_ec8400ef-f0a8-48d5-9c67-f266aa15a07b"
PAGE, DPI = 9, 300
HEIGHTS = (0.671, 0.448, 0.313, 0.224, 0.179, 0.134, 0.09)
HIDDEN = (0.179, 0.134)
TABULATED = {0.224: 1.286, 0.09: 1.371}
BOX = (300, 1040, 1250, 2200)            # Figure 6 plot region on the 300 dpi page [x0, y0, x1, y1]
TICKS_CL = np.round(np.arange(1.8, 0.75, -0.1), 1)


def render(pdf: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-f", str(PAGE), "-l", str(PAGE), "-png", str(pdf), f"{tmp}/p"], check=True)
        return np.asarray(Image.open(next(Path(tmp).glob("p*.png"))).convert("RGB")).astype(int)


def y_calibration(gray: np.ndarray) -> tuple[float, float, list]:
    """Cl = a + b * y_pixel from the tick marks: rows where the 9 pixels left of the axis column are dark, grouped, the 11 regularly spaced ones."""
    x0, y0, x1, y1 = BOX
    sub = gray[y0:y1, x0:x1] < 230
    axis = x0 + int(np.argmax(sub.sum(0)))
    rows = np.flatnonzero((gray[y0:y1, axis - 10:axis - 1] < 200).sum(1) >= 6) + y0
    groups = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)
    centres = np.array([g.mean() for g in groups])
    top = centres[0]
    step = np.median(np.diff(centres[:8]))
    ticks = [min(centres, key=lambda c: abs(c - (top + k * step))) for k in range(len(TICKS_CL))]
    assert max(abs(t - (top + k * step)) for k, t in enumerate(ticks)) < 3, "tick marks not on a regular grid"
    b, a = np.polyfit(ticks, TICKS_CL, 1)
    return a, b, [float(t) for t in ticks]


def red_mask(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r > 170) & (g < 110) & (b < 110)


def digitise(rgb: np.ndarray) -> dict:
    gray = rgb.mean(-1)
    a, b, ticks = y_calibration(gray)
    x0, y0, x1, y1 = BOX
    red = red_mask(rgb[y0:y1, x0:x1])
    lab, n = ndimage.label(ndimage.binary_opening(red, structure=np.ones((7, 7))))
    blobs = [(xs.mean() + x0, ys.mean() + y0) for ys, xs in (np.nonzero(lab == i) for i in range(1, n + 1))]
    blobs = sorted((p for p in blobs if p[1] > 1150), key=lambda p: p[0])   # the legend marker sits above y = 1150
    assert len(blobs) == 5, f"expected 5 free-standing red markers, found {len(blobs)}"
    visible = [h for h in HEIGHTS if h not in HIDDEN]
    xm = dict(zip(visible, (p[0] for p in blobs)))
    ym = dict(zip(visible, (p[1] for p in blobs)))
    sx = (xm[0.09] - xm[0.671]) / (0.09 - 0.671)
    x_of = lambda h: xm[0.671] + (h - 0.671) * sx
    x_residual = max(abs(x_of(h) - xm[h]) for h in visible)
    assert x_residual < 4, f"marker x positions not linear in h/c ({x_residual:.1f} px)"

    def segment(ha, hb, margin=12):
        """Red pixels strictly between the markers at ha and hb (margin px away from both), straight-line fit y(x)."""
        xa, xb = sorted((x_of(ha), x_of(hb)))
        ys, xs = np.nonzero(red)
        xs, ys = xs + x0, ys + y0
        sel = (xs > xa + margin) & (xs < xb - margin)
        lo, hi = sorted((ym.get(ha, 0), ym.get(hb, 0)))
        if lo and hi:
            sel &= (ys > lo - 30) & (ys < hi + 30)
        assert sel.sum() > 20, f"too few red pixels between h/c {ha} and {hb}"
        return np.polyfit(xs[sel], ys[sel], 1)

    pts = {}
    for h in visible:
        pts[h] = {"Cl": float(a + b * ym[h]), "method": "red marker centroid", "x_px": float(xm[h]), "y_px": float(ym[h])}
    seg = {(0.224, 0.179): segment(0.224, 0.179), (0.179, 0.134): segment(0.179, 0.134), (0.134, 0.09): segment(0.134, 0.09)}
    for h, (left, right) in {0.179: ((0.224, 0.179), (0.179, 0.134)), 0.134: ((0.179, 0.134), (0.134, 0.09))}.items():
        ya, yb = (np.polyval(seg[k], x_of(h)) for k in (left, right))
        pts[h] = {"Cl": float(a + b * (ya + yb) / 2), "spread_Cl": float(abs(b * (ya - yb)) / 2), "x_px": float(x_of(h)),
                  "method": "marker covered by black symbols: mean of the two adjacent red segments at the marker x"}
    for h, v in TABULATED.items():
        assert abs(pts[h]["Cl"] - v) < 0.005, f"digitised Cl at h/c {h} = {pts[h]['Cl']:.4f}, tabulated {v}"
    return {"points": {f"{h}": pts[h] for h in HEIGHTS}, "y_calibration": {"Cl_at_pixel_y": f"{a:.6f} + ({b:.8f}) * y", "tick_rows_px": ticks},
            "x_linearity_residual_px": x_residual, "validation_vs_tabulated": {f"{h}": {"tabulated": v, "digitised": round(pts[h]["Cl"], 4)} for h, v in TABULATED.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path, help="Genua 2009 thesis PDF (not in the repository)")
    ap.add_argument("--out", type=Path, default=ROOT / "data/t20/zerihan_zhang_cl_genua2009_fig6.json")
    a = ap.parse_args(argv)
    digest = hashlib.sha256(a.pdf.read_bytes()).hexdigest()
    assert digest == PDF_SHA256, f"PDF SHA-256 {digest} differs from the registered one"
    res = digitise(render(a.pdf))
    res = {"_provenance": f"Digitised from Genua 2009 (TU Delft MSc thesis, {URL}), paper 1 Figure 6 'Experimental' series (red), PDF page {PAGE} "
                          f"rendered at {DPI} dpi with pdftoppm; PDF sha256 {digest}. Script: scripts/t20b_digitize_genua_fig6.py. Secondary source: Genua re-plots "
                          "Zerihan & Zhang (Re_c 4.6e5, blunt-TE finite-span wing with end plates, moving belt); whether the plotted Cl is a balance (3D) or a "
                          "mid-span pressure-integrated value was not verified from the primary source. Cl = downforce coefficient.",
           "h_over_c": list(HEIGHTS), **res}
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({h: round(p["Cl"], 4) for h, p in res["points"].items()}))


if __name__ == "__main__":
    main()
