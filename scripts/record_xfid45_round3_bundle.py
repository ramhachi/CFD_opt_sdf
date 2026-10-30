#!/usr/bin/env python3
"""Bind the finished solver-free evidence bundle without changing its criteria."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    reg = json.loads((OUT / "preregistration.json").read_text())
    result = json.loads((OUT / "result.json").read_text())
    independent = json.loads((OUT / "independent_result.json").read_text())
    assert len(result["cases"]) == len(independent["cases"]) == 40
    assert len(result["fidelity_pairs"]) == len(independent["fidelity_pairs"]) == 24
    assert result["qualification_flags"] == independent["qualification_flags"]
    assert result["qualification_flags"] == reg["qualification_flags"]
    assert not any(reg["qualification_flags"].values())
    bindings = {}
    for group in ("sources", "runtime_files", "inputs"):
        bindings[group] = {}
        for key, spec in reg[group].items():
            path = Path(spec["path"])
            if not path.is_absolute():
                path = ROOT / path
            current = digest(path)
            assert current == spec["sha256"], (group, key)
            bindings[group][key] = dict(spec, final_sha256=current, unchanged=True)
    protected = (
        "src",
        "docs/evidence/xfid45_surface_round2_2026_10_03",
        "docs/evidence/xfid01_geometry_preflight_2026_10_03",
    )
    unchanged = {}
    for path in protected:
        diff = subprocess.check_output(["git", "diff", "7351d41", "--", path], cwd=ROOT)
        assert not diff, path
        unchanged[path] = True
    for name in (
        "evaluation_resumed",
        "independent_r1",
        "independent_r2",
        "independent_r4",
        "independent_r8",
        "focused_final",
        "auxiliary_orientation",
    ):
        source = ROOT / "work" / f"xfid45_round3_{name}.log"
        assert source.is_file(), source
        (OUT / "validation" / f"{name}.log.gz").write_bytes(
            gzip.compress(source.read_bytes(), mtime=0)
        )
    manifest_path = OUT / "bundle_manifest.json"
    files = {
        str(p.relative_to(ROOT)): {
            "sha256": digest(p),
            "bytes": p.stat().st_size,
        }
        for p in sorted(OUT.rglob("*"))
        if p.is_file() and p != manifest_path
    }
    manifest = {
        "evidence_class": "immutable_registration_and_completed_solver_free_export_screen",
        "qualification_flags": reg["qualification_flags"],
        "registered_bindings": bindings,
        "protected_content_unchanged": unchanged,
        "report_documents": {
            name: digest(ROOT / name)
            for name in (
                "docs/issues/45_surface_round3_2026_10_03.md",
                "docs/phase_plan.md",
            )
        },
        "administrative_and_auxiliary_scripts": {
            str(p.relative_to(ROOT)): digest(p)
            for p in sorted((ROOT / "scripts").glob("*round3*.py"))
            if str(p.relative_to(ROOT))
            not in {s["path"] for s in reg["sources"].values()}
        },
        "files": files,
        "total_bytes": sum(v["bytes"] for v in files.values()),
        "coverage": independent["coverage"],
        "selected_r": independent["selected_r"],
        "scientific_registration_commit": "4a7b8dad21c778029fb719e3df90328deb2b9abc",
        "output_adapter_registration_commit": "3a32eee4a69b72bdafd6a5cb54c59ef7d1971c34",
        "independent_execution_partition_commit": "ee334b7",
        "numeric_limitation": independent["limitation"],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(f"Bound {len(files)} evidence files; {manifest['total_bytes']} bytes")


if __name__ == "__main__":
    main()
