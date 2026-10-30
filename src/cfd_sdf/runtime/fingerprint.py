"""Deterministic execution-backend identity for solver-neutral contracts.

A backend is identified by the identifiers that can change a numerical
result: solver revision, precision, grid, device and compiler.  The
fingerprint is a pure function of those identifiers, so two runs with the
same fingerprint are the same execution backend and can resume each other.
A changed GPU, solver commit or grid is a *different* backend identity and
must not silently resume another backend's checkpoints.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

RUNTIME_FINGERPRINT_SCHEMA_VERSION = 1
_SHA256_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


class FingerprintError(ValueError):
    """Fail-closed runtime-identity contract violation."""


class FingerprintMismatch(FingerprintError):
    """A resume target does not share the registered backend identity."""


def validate_sha256_hex(value: Any, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in _HEX_DIGITS for character in value)
    ):
        raise FingerprintError(f"{field_name} must be a 64-character lowercase hex sha256")
    return value


def _validate_label(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FingerprintError(f"{field_name} must be a non-empty string")
    return value


def _validate_mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FingerprintError(f"{field_name} must be a mapping")
    return value


def canonical_json_sha256(document: Mapping[str, Any]) -> str:
    """Hash a JSON-serializable mapping deterministically (sorted keys)."""

    try:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise FingerprintError(f"document is not canonically hashable: {error}") from error
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeFingerprint:
    """One execution-backend identity; identical fields imply identical hash."""

    platform: str
    backend: str
    solver_revision: str
    precision: str
    grid_identity: Mapping[str, Any]
    device: Mapping[str, Any] = field(default_factory=dict)
    compiler: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = RUNTIME_FINGERPRINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("platform", "backend", "solver_revision", "precision"):
            _validate_label(getattr(self, name), field_name=name)
        for name in ("grid_identity", "device", "compiler", "extra"):
            _validate_mapping(getattr(self, name), field_name=name)
        if int(self.schema_version) != RUNTIME_FINGERPRINT_SCHEMA_VERSION:
            raise FingerprintError(
                f"unsupported runtime fingerprint schema_version: {self.schema_version!r}"
            )
        canonical_json_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "platform": self.platform,
            "backend": self.backend,
            "solver_revision": self.solver_revision,
            "precision": self.precision,
            "grid_identity": dict(self.grid_identity),
            "device": dict(self.device),
            "compiler": dict(self.compiler),
            "extra": dict(self.extra),
        }

    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


def assert_resume_compatible(
    registered: RuntimeFingerprint,
    current: RuntimeFingerprint,
    *,
    ignored_fields: tuple[str, ...] = (),
) -> None:
    """Refuse a resume whose backend identity differs from the registration."""

    ignored = set(ignored_fields)
    unknown = sorted(ignored - set(registered.to_dict()))
    if unknown:
        raise FingerprintError(f"ignored_fields contains unknown fields: {unknown}")
    differences = sorted(
        key
        for key in registered.to_dict()
        if key not in ignored and registered.to_dict()[key] != current.to_dict()[key]
    )
    if differences:
        raise FingerprintMismatch(
            "resume target has a different backend identity: " + ", ".join(differences)
        )


__all__ = [
    "RUNTIME_FINGERPRINT_SCHEMA_VERSION",
    "FingerprintError",
    "FingerprintMismatch",
    "RuntimeFingerprint",
    "assert_resume_compatible",
    "canonical_json_sha256",
    "validate_sha256_hex",
]
