"""Deterministic B0 evidence runner for generic STL geometry fixtures.

This runner deliberately exercises the native v2 problem preflight and
canonical geometry-mask path.  It is not an OpenFOAM or topology
qualification: its published result is limited to YAML/STL provenance and
role-mask construction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from .canonical_geometry_masks import (
    build_canonical_geometry_mask_snapshot,
    verify_canonical_geometry_mask_manifest,
)
from .problem_spec import (
    load_problem_spec,
    problem_spec_sha256,
    problem_spec_validation_summary,
    write_problem_spec_snapshot,
)


GENERIC_GEOMETRY_FIXTURE_PACK_KIND = "g4_b0_generic_geometry_fixture_pack"
GENERIC_GEOMETRY_FIXTURE_PACK_SCHEMA_VERSION = 1
GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_KIND = "g4_b0_generic_geometry_fixture_result_index"
GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_SCHEMA_VERSION = 1
DEFAULT_FIXTURE_PACK_PATH = Path("examples/g4_b0_generic_geometry_fixtures/fixture_pack.yaml")


@dataclass(frozen=True)
class GenericGeometryFixturePackResult:
    """Immutable result-index path and its parsed, deterministic contents."""

    index_path: Path
    records: tuple[Mapping[str, Any], ...]


def run_generic_geometry_fixture_pack(
    *,
    output_dir: str | Path,
    fixture_pack_path: str | Path = DEFAULT_FIXTURE_PACK_PATH,
    chunk_size: int = 65_536,
) -> GenericGeometryFixturePackResult:
    """Run the versioned fixture pack and publish one hash-bound result index.

    ``output_dir`` must not already contain a previous result.  Each accepted
    fixture is assembled in a private staging directory and moved into place
    only after preflight, role-report writing, snapshot construction, and
    manifest verification succeed.  Rejected fixtures never receive a result
    directory, which makes malformed input fail closed.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    pack_path = Path(fixture_pack_path)
    pack = _read_pack(pack_path)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("output_dir must be empty so the fixture result index is immutable")
    output.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    stage_root = output / ".staging"
    try:
        for fixture in pack["fixtures"]:
            record = _run_fixture(
                fixture=fixture,
                pack_path=pack_path,
                output=output,
                stage_root=stage_root,
                chunk_size=chunk_size,
            )
            records.append(record)
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)

    index = {
        "schema_version": GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_SCHEMA_VERSION,
        "kind": GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_KIND,
        "fixture_pack_sha256": _sha256_path(pack_path),
        "fixture_order": [item["id"] for item in pack["fixtures"]],
        "results": records,
    }
    index_path = output / "fixture_result_index.json"
    _write_json(index_path, index)
    return GenericGeometryFixturePackResult(index_path=index_path, records=tuple(records))


def _run_fixture(
    *,
    fixture: Mapping[str, str],
    pack_path: Path,
    output: Path,
    stage_root: Path,
    chunk_size: int,
) -> dict[str, Any]:
    fixture_id = fixture["id"]
    family = fixture["family"]
    expectation = fixture["expectation"]
    project_path = (pack_path.parent / fixture["project"]).resolve()
    input_sha256 = _fixture_input_sha256(project_path)
    stage = stage_root / fixture_id
    try:
        spec = load_problem_spec(project_path)
        if expectation == "reject":
            # Parsing alone intentionally does not validate every STL.  Run
            # the normal generic mask path to prove malformed assets fail
            # before publication.
            build_canonical_geometry_mask_snapshot(spec, output_dir=stage, chunk_size=chunk_size)
        else:
            stage.mkdir(parents=True, exist_ok=False)
            role_report = problem_spec_validation_summary(spec)
            _write_json(stage / "problem_spec_validation.json", role_report)
            snapshot_path = write_problem_spec_snapshot(spec, stage / "problem_spec_snapshot.json")
            artifacts = build_canonical_geometry_mask_snapshot(spec, output_dir=stage, chunk_size=chunk_size)
            verified = verify_canonical_geometry_mask_manifest(artifacts.geometry_manifest_path, spec)
            result_identity = _sha256_json(
                {
                    "fixture_id": fixture_id,
                    "family": family,
                    "input_sha256": input_sha256,
                    "problem_spec_sha256": problem_spec_sha256(spec),
                    "role_report_sha256": _sha256_path(stage / "problem_spec_validation.json"),
                    "problem_spec_snapshot_sha256": _sha256_path(snapshot_path),
                    "canonical_snapshot_sha256": _sha256_path(artifacts.snapshot_path),
                    "geometry_manifest_sha256": _sha256_path(artifacts.geometry_manifest_path),
                    "mask_true_counts": dict(verified.mask_true_counts),
                }
            )
            _write_json(
                stage / "fixture_result.json",
                {
                    "schema_version": 1,
                    "kind": "g4_b0_generic_geometry_fixture_result",
                    "fixture_id": fixture_id,
                    "family": family,
                    "input_sha256": input_sha256,
                    "result_identity": result_identity,
                    "status": "passed",
                },
            )
            destination = output / fixture_id
            if destination.exists():
                raise ValueError(f"fixture output already exists: {fixture_id}")
            stage.replace(destination)
            return {
                "id": fixture_id,
                "family": family,
                "input_sha256": input_sha256,
                "status": "passed",
                "reason": "preflight_snapshot_role_report_and_hash_bound_publication_succeeded",
                "result_identity": result_identity,
            }
    except (OSError, ValueError, yaml.YAMLError) as exc:
        if expectation != "reject":
            raise RuntimeError(f"valid fixture {fixture_id!r} was rejected: {exc}") from exc
        return {
            "id": fixture_id,
            "family": family,
            "input_sha256": input_sha256,
            "status": "rejected",
            "reason": str(exc),
            "result_identity": None,
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    raise RuntimeError(f"invalid fixture {fixture_id!r} unexpectedly passed generic preflight")


def _read_pack(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to read generic geometry fixture pack: {path}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("generic geometry fixture pack must be a mapping")
    if raw.get("schema_version") != GENERIC_GEOMETRY_FIXTURE_PACK_SCHEMA_VERSION:
        raise ValueError("Unsupported generic geometry fixture pack schema_version")
    if raw.get("kind") != GENERIC_GEOMETRY_FIXTURE_PACK_KIND:
        raise ValueError("Invalid generic geometry fixture pack kind")
    fixtures = raw.get("fixtures")
    if not isinstance(fixtures, Sequence) or isinstance(fixtures, (str, bytes)) or not fixtures:
        raise ValueError("generic geometry fixture pack fixtures must be a non-empty sequence")
    parsed: list[dict[str, str]] = []
    expected_ids = {"sphere", "box", "plate", "multi_component", "invalid_stl"}
    for item in fixtures:
        if not isinstance(item, Mapping) or set(item) != {"id", "family", "project", "expectation"}:
            raise ValueError("each generic geometry fixture entry must contain id, family, project, expectation")
        parsed_item = {key: item[key] for key in ("id", "family", "project", "expectation")}
        if not all(isinstance(value, str) and value for value in parsed_item.values()):
            raise ValueError("generic geometry fixture entry values must be non-empty strings")
        if parsed_item["expectation"] not in {"pass", "reject"}:
            raise ValueError("generic geometry fixture expectation must be pass or reject")
        project = Path(parsed_item["project"])
        if project.is_absolute() or project.drive or ".." in project.parts or project.suffix not in {".yaml", ".yml"}:
            raise ValueError("generic geometry fixture project must be a safe relative YAML path")
        parsed.append(parsed_item)
    ids = [item["id"] for item in parsed]
    if len(set(ids)) != len(ids) or set(ids) != expected_ids:
        raise ValueError("generic geometry fixture pack must declare each required family exactly once")
    if [item["id"] for item in parsed] != ["sphere", "box", "plate", "multi_component", "invalid_stl"]:
        raise ValueError("generic geometry fixture pack order is fixed for deterministic replay")
    if [item["expectation"] for item in parsed].count("reject") != 1:
        raise ValueError("generic geometry fixture pack must declare exactly one rejected fixture")
    return {"fixtures": parsed}


def _fixture_input_sha256(project_path: Path) -> str:
    spec = load_problem_spec(project_path)
    sources = {
        "project.yaml": _sha256_path(project_path),
        **{
            region.file.as_posix(): _sha256_path((project_path.parent / region.file).resolve())
            for region in sorted(spec.geometry_regions, key=lambda item: item.id)
        },
    }
    return _sha256_json(sources)


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


__all__ = [
    "DEFAULT_FIXTURE_PACK_PATH",
    "GENERIC_GEOMETRY_FIXTURE_PACK_KIND",
    "GENERIC_GEOMETRY_FIXTURE_PACK_SCHEMA_VERSION",
    "GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_KIND",
    "GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_SCHEMA_VERSION",
    "GenericGeometryFixturePackResult",
    "run_generic_geometry_fixture_pack",
]
