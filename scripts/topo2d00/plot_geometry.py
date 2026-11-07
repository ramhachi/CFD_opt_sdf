#!/usr/bin/env python3
"""Plot the generated polygon series; source OCR remains image-unverified."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cfd_gen.topo2d.geometry import GeometryError, validate_scene  # noqa: E402


def plot_geometry(output, *, dx_mm=None):
    directory = ROOT / "docs/harness/topo2d00_scenes"
    def load(configuration):
        scene = json.loads((directory / f"{configuration}.json").read_text())
        if validate_scene(scene) != scene["gates"]:
            raise GeometryError("plot scene has stale geometric gates")
        if dx_mm is not None and scene["dx_mm"] != dx_mm:
            raise GeometryError("declared plot spacing differs from scene")
        return scene
    scenes = [load(c) for c in ("E1", "E2", "E3")]
    figure, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, constrained_layout=True)
    colors = ["#1f5b99", "#b65a16", "#367a4a"]
    for ax, scene in zip(axes, scenes):
        raw = load(scene["configuration"] + "_sharp")
        ratios = []
        for e, original, color in zip(scene["elements"], raw["elements"], colors):
            polygon = np.array(e["polygon_mm"] + e["polygon_mm"][:1])
            ax.fill(polygon[:, 0], polygon[:, 1], color=color, alpha=0.22)
            ax.plot(polygon[:, 0], polygon[:, 1], color=color, lw=1.4, label=e["name"])
            original_polygon = np.array(original["polygon_mm"] + original["polygon_mm"][:1])
            ax.plot(original_polygon[:, 0], original_polygon[:, 1], color="#444444", ls="--", lw=0.75)
            original_surface = np.array(original["suction_mm"])
            arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(original_surface, axis=0), axis=1))]
            cap = np.array(e["suction_mm"])[arc <= .02 * e["nominal_chord_mm"]]
            ax.plot(cap[:, 0], cap[:, 1], color=color, lw=2.6)
            ratios.append(f"{e['name']}: {e['thickening']['max_thickness_ratio']:.2f}x")
        ax.axhline(0, color="#222222", lw=1.3)
        ax.set_aspect("equal", adjustable="box")
        ax.set_ylim(-8, 235)
        ax.set_ylabel("z [mm]")
        gap_text = ", ".join(f"{g['distance_mm']:.2f}" for g in scene["gates"]["pair_gaps_mm"]
                             if g["elements"][0:1] != ["main"] or g["elements"][-1] != "flap2")
        ax.set_title(f"{scene['configuration']}   h={scene['height_mm']:g} mm   maximum normal-thickness ratios: " + ", ".join(ratios), fontsize=10, loc="left")
        ax.text(0.99, 0.06, f"floor = 4 dx = {scene['t_min_mm']:.3f} mm; "
                + (f"adjacent Euclidean gaps: {gap_text} mm" if gap_text else "single element"),
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8)
        ax.grid(alpha=0.15)
        ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=3)
    axes[-1].set_xlabel("x [mm]; flow to the right; moving ground at z=0")
    axes[-1].set_xlim(-20, 405)
    figure.suptitle("TOPO-2D-00: deterministic source-derived polygon series\n"
                    "Solid: thickened; dashed: original finite-TE arm (*_sharp). "
                    "LE cap retained through 2% chord in surface arc; segments 0.1-1 mm, adjacent ratio <= 3.\n"
                    "4 dx normal-thickness gate applies from original maximum-thickness station aft; "
                    "cap/ramp excluded. Source OCR: UNVERIFIED.", fontsize=10)
    figure.savefig(output, dpi=180, metadata={"Software": "TOPO-2D-00 geometry"})
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dx-mm", type=float)
    args = parser.parse_args()
    plot_geometry(args.output, dx_mm=args.dx_mm)
