"""Build an append-only successor criteria round from terminal diagnostics."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping


MUTABLE_FIELDS = {
    "criteria_round",
    "criteria_sha256",
    "registered_at_utc",
    "registered_source_commit",
    "source_commit",
    "source_tree_commit",
    "source_input_sha256",
    "inputs",
    "supersedes",
    "kernel_id",
    "kernel_title",
}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
KERNEL_TERMINAL = re.compile(r'^(.+)/(\d+) has status "KernelWorkerStatus\.(ERROR|COMPLETE)"$')
QUALIFICATION_FLAGS = {
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology",
}
KAGGLE_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
KAGGLE_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class SupersessionError(ValueError):
    """The proposed successor changes evidence or its measurement contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(Path(path).read_bytes())


def canonical_sha256(criteria: dict) -> str:
    value = {key: item for key, item in criteria.items() if key != "criteria_sha256"}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(encoded)


def git_source_reader(repository: Path) -> Callable[[str, str], bytes]:
    repository = Path(repository).resolve()

    def read(commit: str, path: str) -> bytes:
        completed = subprocess.run(
            ["git", "-C", str(repository), "show", f"{commit}:{path}"],
            check=True,
            capture_output=True,
        )
        return completed.stdout

    return read


def _load_immutable(path: Path) -> tuple[dict, str]:
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise SupersessionError(f"immutable evidence and sidecar are required: {path}")
    digest = file_sha256(path)
    if sidecar.read_text().strip() != digest:
        raise SupersessionError(f"evidence sidecar mismatch: {path}")
    try:
        value = json.loads(path.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SupersessionError(f"invalid JSON evidence: {path}") from exc
    if not isinstance(value, dict):
        raise SupersessionError(f"JSON evidence must be an object: {path}")
    return value, digest


def _check_flag_state(criteria: dict) -> None:
    def visit(value: object, parent: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                is_flag = key.endswith("_qualified") or key in QUALIFICATION_FLAGS
                if is_flag and not isinstance(child, dict) and child is not False:
                    raise SupersessionError(f"qualification flag must remain false: {parent}{key}")
                if is_flag and key.endswith("_qualified") and not isinstance(child, bool):
                    raise SupersessionError(f"qualification flag must be boolean: {parent}{key}")
                # A topology-policy contract may itself be a mapping, not a flag.
                visit(child, f"{parent}{key}.")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{parent}[{index}].")

    visit(criteria)


def _kernel_slug_is_valid(criteria: dict, *, allow_legacy_overlength: bool = False) -> None:
    kernel_id = criteria.get("kernel_id")
    title = criteria.get("kernel_title")
    dataset_id = criteria.get("input_dataset_id")
    if not all(isinstance(value, str) and value for value in (kernel_id, title, dataset_id)):
        raise SupersessionError("kernel and dataset identities are required")
    owner, separator, slug = kernel_id.partition("/")
    dataset_owner, dataset_separator, dataset_slug = dataset_id.partition("/")
    if (not separator or not dataset_separator or not KAGGLE_OWNER.fullmatch(owner)
            or not KAGGLE_OWNER.fullmatch(dataset_owner) or owner != dataset_owner
            or not KAGGLE_SLUG.fullmatch(slug) or (len(slug) > 40 and not allow_legacy_overlength)
            or not KAGGLE_SLUG.fullmatch(dataset_slug) or slug == dataset_slug):
        raise SupersessionError("kernel ID must be a valid unique slug separate from its dataset ID")
    if not isinstance(title, str):
        raise SupersessionError("kernel title must be text")
    title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if title_slug != slug:
        raise SupersessionError("kernel slug does not match the title-derived slug")


def _check_terminal(criteria: dict, criteria_path: Path, criteria_file_sha: str,
                    diagnostic: dict, diagnostic_path: Path) -> dict:
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise SupersessionError("predecessor is not an immutable preregistered round")
    if criteria.get("formal_measurement_started") is not False:
        raise SupersessionError("predecessor criteria already records formal measurement")
    if criteria.get("criteria_sha256") != canonical_sha256(criteria):
        raise SupersessionError("predecessor canonical criteria hash mismatch")
    _check_flag_state(criteria)
    supplied_criteria_path = criteria_path.as_posix()
    absolute_criteria_path = criteria_path.resolve().as_posix()
    observed_path = diagnostic.get("criteria_path")
    if observed_path:
        observed_parts = Path(observed_path).parts
        supplied_parts = criteria_path.parts
        absolute_parts = criteria_path.resolve().parts
        path_matches = observed_path in {supplied_criteria_path, absolute_criteria_path}
        path_matches |= (not Path(observed_path).is_absolute() and
                         (supplied_parts[-len(observed_parts):] == observed_parts or
                          absolute_parts[-len(observed_parts):] == observed_parts))
        if not path_matches:
            raise SupersessionError("terminal diagnostic names a different predecessor criteria")
    if diagnostic.get("criteria_sha256") != criteria_file_sha:
        raise SupersessionError("terminal diagnostic is not bound to the exact predecessor file hash")
    if diagnostic.get("kernel_id") != criteria.get("kernel_id"):
        raise SupersessionError("terminal diagnostic kernel identity differs from predecessor")
    dataset_id = criteria.get("input_dataset_id")
    dataset_version = diagnostic.get("dataset_version")
    dataset_files = criteria.get("input_dataset_files")
    if (diagnostic.get("dataset_id") != dataset_id or not isinstance(dataset_version, int)
            or isinstance(dataset_version, bool) or dataset_version < 1 or not isinstance(dataset_files, dict)):
        raise SupersessionError("terminal diagnostic lacks the exact registered dataset identity and inventory")
    version = diagnostic.get("kernel_version")
    terminal = diagnostic.get("terminal_status")
    match = KERNEL_TERMINAL.fullmatch(terminal or "")
    if (not isinstance(version, int) or isinstance(version, bool) or version < 1 or not match
            or match.group(1) != criteria["kernel_id"] or int(match.group(2)) != version):
        raise SupersessionError("diagnostic does not carry the exact terminal kernel state")
    if diagnostic.get("host_verification_passed") is not False:
        raise SupersessionError("supersession requires a terminal diagnostic that failed host verification")
    if diagnostic.get("measurement_thresholds_changed", False) is not False:
        raise SupersessionError("terminal diagnostic reports changed measurement thresholds")
    return {
        "criteria_path": observed_path or criteria_path.name,
        "criteria_file_sha256": criteria_file_sha,
        "criteria_canonical_sha256": criteria["criteria_sha256"],
        "diagnostic_path": diagnostic_path.name,
        "diagnostic_file_sha256": file_sha256(diagnostic_path),
        "kernel_id": match.group(1),
        "kernel_version": version,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "dataset_input_inventory_sha256": sha256(json.dumps(
            dataset_files, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
        "terminal_status": terminal,
        "host_verification_passed": False,
        "failure_stage": diagnostic.get("failure_stage", diagnostic.get("runner_execution_state", {}).get("stage")),
        "host_verifier_error": diagnostic.get("host_verifier_error"),
        "solver_started": diagnostic.get("solver_started", diagnostic.get("runner_execution_state", {}).get("solver_started")),
        "solver_step_invoked": diagnostic.get("solver_step_invoked", diagnostic.get("julia_progress_markers", {}).get("solver_step_invoked", [])),
        "solver_step_returned": diagnostic.get("solver_step_returned", diagnostic.get("julia_progress_markers", {}).get("solver_step_returned", [])),
        "measurement_thresholds_changed": False,
        "successor_identity": {
            "kernel_id": match.group(1),
            "kernel_version": {
                "status": "pending_at_registration",
                "must_be_greater_than_predecessor": version,
            },
            "dataset": {
                "id": dataset_id,
                "version": dataset_version,
                "input_inventory_sha256": sha256(json.dumps(
                    dataset_files, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
                "status": "exact_registered_version_and_inventory",
            },
        },
    }


def verify_successor_submission(successor: dict, *, kernel_id: str, kernel_version: int,
                                dataset_id: str, dataset_version: int,
                                dataset_files: Mapping[str, str]) -> None:
    """Check a completed versioned submission against its preregistered identity."""
    binding = successor.get("supersedes", {}).get("successor_identity", {})
    previous_version = binding.get("kernel_version", {}).get("must_be_greater_than_predecessor")
    if (kernel_id != binding.get("kernel_id") or not isinstance(kernel_version, int)
            or isinstance(kernel_version, bool) or not isinstance(previous_version, int)
            or kernel_version <= previous_version):
        raise SupersessionError("submitted kernel identity or version differs from its registration")
    expected_dataset = binding.get("dataset", {})
    inventory_sha = sha256(json.dumps(
        dict(dataset_files), sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    if (dataset_id != expected_dataset.get("id") or dataset_version != expected_dataset.get("version")
            or inventory_sha != expected_dataset.get("input_inventory_sha256")):
        raise SupersessionError("submitted dataset version or exact input inventory differs from registration")


def _validate_successor_identity(predecessor: dict, successor: dict) -> None:
    binding = successor.get("supersedes")
    if not isinstance(binding, dict):
        raise SupersessionError("successor must bind the exact predecessor diagnostic")
    legacy_binding = {
        "kernel3_diagnostic_path", "kernel3_diagnostic_sha256",
    } <= binding.keys()
    if legacy_binding:
        # Existing immutable rounds use this earlier, campaign-specific schema.
        if (binding.get("criteria_canonical_sha256") != predecessor.get("criteria_sha256")
                or binding.get("kernel_id") != predecessor.get("kernel_id")
                or not isinstance(binding.get("kernel_version"), int)
                or binding.get("kernel_version", 0) < 1
                or not HEX_SHA256.fullmatch(binding.get("criteria_file_sha256", ""))):
            raise SupersessionError("legacy supersession binding does not match its predecessor")
        return

    diagnostic = KERNEL_TERMINAL.fullmatch(binding.get("terminal_status", ""))
    version = binding.get("kernel_version")
    dataset_id = predecessor.get("input_dataset_id")
    dataset_version = binding.get("dataset_version")
    inventory_sha = sha256(json.dumps(
        predecessor.get("input_dataset_files"), sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode())
    expected_identity = {
        "kernel_id": successor.get("kernel_id"),
        "kernel_version": {
            "status": "pending_at_registration",
            "must_be_greater_than_predecessor": version,
        },
        "dataset": {
            "id": dataset_id,
            "version": dataset_version,
            "input_inventory_sha256": inventory_sha,
            "status": "exact_registered_version_and_inventory",
        },
    }
    if (not HEX_SHA256.fullmatch(binding.get("criteria_file_sha256", ""))
            or binding.get("criteria_canonical_sha256") != predecessor.get("criteria_sha256")
            or binding.get("kernel_id") != predecessor.get("kernel_id")
            or not isinstance(version, int) or isinstance(version, bool) or version < 1
            or not diagnostic or diagnostic.group(1) != predecessor.get("kernel_id")
            or int(diagnostic.group(2)) != version
            or binding.get("dataset_id") != dataset_id
            or binding.get("dataset_input_inventory_sha256") != inventory_sha
            or binding.get("host_verification_passed") is not False
            or binding.get("successor_identity") != expected_identity):
        raise SupersessionError("successor kernel/dataset identity binding is inconsistent")


def validate_successor(predecessor: dict, successor: dict,
                       allowed_source_changes: Mapping[str, Mapping[str, str]]) -> None:
    if (predecessor.get("criteria_sha256") != canonical_sha256(predecessor)
            or not isinstance(predecessor.get("criteria_round"), int)
            or isinstance(predecessor.get("criteria_round"), bool)
            or predecessor["criteria_round"] < 1):
        raise SupersessionError("predecessor canonical hash or round identity is invalid")
    if (not isinstance(successor.get("criteria_round"), int)
            or isinstance(successor.get("criteria_round"), bool)
            or successor.get("criteria_round") != predecessor["criteria_round"] + 1):
        raise SupersessionError("successor round must increment exactly once")
    _check_flag_state(predecessor)
    for field in predecessor.keys() | successor.keys():
        if field not in MUTABLE_FIELDS and successor.get(field) != predecessor.get(field):
            raise SupersessionError(f"successor changed immutable measurement contract field: {field}")
    old_inputs, new_inputs = predecessor.get("inputs"), successor.get("inputs")
    if not isinstance(old_inputs, dict) or not isinstance(new_inputs, dict) or old_inputs.keys() != new_inputs.keys():
        raise SupersessionError("successor input inventory changed")
    changed = set()
    for name, old in old_inputs.items():
        new = new_inputs[name]
        if not isinstance(old, dict) or not isinstance(new, dict):
            raise SupersessionError(f"invalid input entry: {name}")
        if old == new:
            continue
        if old.get("location") != "source_repo" or new.get("location") != "source_repo":
            raise SupersessionError(f"non-source measurement input changed: {name}")
        if set(old) != set(new) or any(old[key] != new[key] for key in old if key != "sha256"):
            raise SupersessionError(f"source input path or metadata changed: {name}")
        if not HEX_SHA256.fullmatch(new.get("sha256", "")):
            raise SupersessionError(f"invalid successor source hash: {name}")
        changed.add(name)
    if changed != set(allowed_source_changes):
        raise SupersessionError("allowed source changes must exactly match changed source input hashes")
    for name in changed:
        approved = allowed_source_changes[name]
        old, new = old_inputs[name], new_inputs[name]
        if approved.get("path") != old.get("path") or not approved.get("reason", "").strip():
            raise SupersessionError(f"source change needs its exact registered path and a diagnostic reason: {name}")
    expected_source_hashes = {
        name: item["sha256"] for name, item in new_inputs.items()
        if item.get("location") == "source_repo"
    }
    if successor.get("source_input_sha256") != expected_source_hashes:
        raise SupersessionError("source_input_sha256 does not match the successor source inventory")
    if successor.get("input_dataset_id") != predecessor.get("input_dataset_id"):
        raise SupersessionError("successor changed the measurement dataset identity")
    if predecessor.get("kernel_id") != predecessor.get("input_dataset_id"):
        if (successor.get("kernel_id"), successor.get("kernel_title")) != (
                predecessor.get("kernel_id"), predecessor.get("kernel_title")):
            raise SupersessionError("kernel identity changed without a predecessor ID collision")
    elif successor.get("kernel_id") == successor.get("input_dataset_id"):
        raise SupersessionError("successor must repair a predecessor kernel/dataset ID collision")
    if successor.get("immutable") is not True or successor.get("registered_before_computation") is not True:
        raise SupersessionError("successor must be immutable and registered before computation")
    if successor.get("status") != "registered_not_run" or successor.get("formal_measurement_started") is not False:
        raise SupersessionError("successor must be an unrun round")
    if successor.get("source_commit") != successor.get("registered_source_commit"):
        raise SupersessionError("successor source commit is not registered consistently")
    _check_flag_state(successor)
    _kernel_slug_is_valid(
        successor, allow_legacy_overlength=successor.get("kernel_id") == predecessor.get("kernel_id"))
    _validate_successor_identity(predecessor, successor)
    if successor.get("criteria_sha256") != canonical_sha256(successor):
        raise SupersessionError("successor canonical criteria hash mismatch")


def build_successor(
    predecessor_path: Path,
    terminal_diagnostic_path: Path,
    *,
    source_commit: str,
    source_reader: Callable[[str, str], bytes],
    allowed_source_changes: Mapping[str, Mapping[str, str]],
    registered_at_utc: str,
    kernel_id: str | None = None,
    kernel_title: str | None = None,
) -> dict:
    predecessor_path, terminal_diagnostic_path = Path(predecessor_path), Path(terminal_diagnostic_path)
    predecessor, predecessor_file_sha = _load_immutable(predecessor_path)
    diagnostic, _ = _load_immutable(terminal_diagnostic_path)
    binding = _check_terminal(predecessor, predecessor_path, predecessor_file_sha, diagnostic, terminal_diagnostic_path)
    if not GIT_COMMIT.fullmatch(source_commit):
        raise SupersessionError("successor source commit must be a full Git SHA")
    try:
        parsed_time = datetime.fromisoformat(registered_at_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupersessionError("registration timestamp must be ISO-8601") from exc
    if parsed_time.tzinfo is None:
        raise SupersessionError("registration timestamp must include a timezone")

    successor = copy.deepcopy(predecessor)
    old_kernel_id = predecessor.get("kernel_id")
    old_title = predecessor.get("kernel_title")
    if kernel_id is not None or kernel_title is not None:
        if predecessor.get("kernel_id") != predecessor.get("input_dataset_id"):
            raise SupersessionError("kernel identity can only be repaired when predecessor kernel and dataset IDs collide")
        if not kernel_id or not kernel_title:
            raise SupersessionError("a repaired kernel identity requires both ID and title")
        successor["kernel_id"], successor["kernel_title"] = kernel_id, kernel_title
    else:
        successor["kernel_id"], successor["kernel_title"] = old_kernel_id, old_title

    old_inputs = predecessor.get("inputs")
    if not isinstance(old_inputs, dict):
        raise SupersessionError("predecessor has no immutable input inventory")
    if set(allowed_source_changes) - old_inputs.keys():
        raise SupersessionError("source-change allowlist names an unregistered input")
    new_hashes = {}
    for name, entry in old_inputs.items():
        if entry.get("location") != "source_repo":
            continue
        approved = allowed_source_changes.get(name)
        if approved is not None and approved.get("path") != entry.get("path"):
            raise SupersessionError(f"allowlisted path differs from the exact predecessor input: {name}")
        try:
            observed = sha256(source_reader(source_commit, entry["path"]))
        except Exception as exc:
            raise SupersessionError(f"cannot read source snapshot for {name}: {exc}") from exc
        if approved is None and observed != entry.get("sha256"):
            raise SupersessionError(f"unallowlisted source input changed: {name}")
        if approved is not None and observed == entry.get("sha256"):
            raise SupersessionError(f"allowlisted source input has no actual change: {name}")
        successor["inputs"][name]["sha256"] = observed
        new_hashes[name] = observed

    successor["criteria_round"] = predecessor["criteria_round"] + 1
    successor["registered_at_utc"] = registered_at_utc
    successor["registered_source_commit"] = source_commit
    successor["source_commit"] = source_commit
    if "source_tree_commit" in successor:
        successor["source_tree_commit"] = source_commit
    successor["source_input_sha256"] = new_hashes
    successor["supersedes"] = binding
    binding["successor_identity"]["kernel_id"] = successor["kernel_id"]
    successor["criteria_sha256"] = canonical_sha256(successor)
    validate_successor(predecessor, successor, allowed_source_changes)
    return successor


def write_successor(successor: dict, output_path: Path) -> str:
    output_path = Path(output_path)
    sidecar = output_path.with_suffix(output_path.suffix + ".sha256")
    if output_path.exists() or sidecar.exists():
        raise SupersessionError("successor target already exists; immutable rounds are append-only")
    payload = json.dumps(successor, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    digest = sha256(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as stream:
        stream.write(payload)
    with sidecar.open("x", encoding="utf-8") as stream:
        stream.write(digest + "\n")
    return digest
