"""Strict codec for a staged OpenFOAM ``0.orig/alpha`` scalar field.

The codec intentionally has a very narrow responsibility.  It neither stages
cases nor applies a design-to-CFD transfer; it only makes a supplied native
``float64`` alpha vector observable in a single OpenFOAM field file.  A write
is accepted only when the resulting file can be parsed back as exactly the
same finite vector and byte-stable array hash.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

import numpy as np


_FOAMFILE_START = re.compile(r"\A\s*FoamFile\s*\{")
_HEADER_CLASS = re.compile(r"\bclass\s+([^;\s]+)\s*;")
_HEADER_OBJECT = re.compile(r"\bobject\s+([^;\s]+)\s*;")
_INTERNAL_FIELD = re.compile(
    r"\binternalField\s+(?:"
    r"uniform\s+(?P<uniform>[^;]+)"
    r"|nonuniform\s+List<scalar>\s+(?P<count>[0-9]+)\s*\(\s*(?P<values>.*?)\s*\)"
    r")\s*;",
    flags=re.DOTALL,
)
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", flags=re.DOTALL)


@dataclass(frozen=True)
class OpenFOAMAlphaField:
    """A verified nonuniform scalar ``alpha`` internal field."""

    path: Path
    values: np.ndarray
    cell_count: int
    value_sha256: str


@dataclass(frozen=True)
class _InternalFieldMatch:
    start: int
    end: int
    kind: str
    values: np.ndarray | None


def read_openfoam_alpha_field(path: Path) -> OpenFOAMAlphaField:
    """Read one strict nonuniform ``0.orig/alpha`` field.

    Uniform fields are deliberately not accepted here: a caller using this
    function is verifying the cellwise state that will be passed to OpenFOAM.
    """

    path = _require_alpha_path(path)
    text = _read_posix_text(path)
    _validate_alpha_header(text, path)
    field = _find_single_internal_field(text, path)
    if field.kind != "nonuniform" or field.values is None:
        raise ValueError(f"alpha field must have one nonuniform List<scalar> internalField: {path}")
    values = field.values
    values.setflags(write=False)
    return OpenFOAMAlphaField(
        path=path,
        values=values,
        cell_count=int(values.size),
        value_sha256=openfoam_alpha_values_sha256(values),
    )


def write_and_verify_openfoam_alpha_field(path: Path, values: np.ndarray) -> OpenFOAMAlphaField:
    """Write and immediately read back a finite native-``float64`` alpha vector.

    The pre-existing field is used only as a boundary-field-preserving
    template.  It must still be a valid alpha ``volScalarField`` with exactly
    one well-formed internal field declaration.  Output is always POSIX LF so
    a case prepared on Windows remains runnable by Docker/WSL bash.
    """

    path = _require_alpha_path(path)
    expected = _require_float64_vector(values, "alpha values")
    text = _read_posix_text(path)
    _validate_alpha_header(text, path)
    field = _find_single_internal_field(text, path)
    # Parsing the template before replacement prevents an ambiguous or
    # malformed existing declaration from being silently hidden by a write.
    if field.kind == "nonuniform" and field.values is None:  # defensive invariant
        raise AssertionError("nonuniform alpha parser returned no values")

    replacement = _render_nonuniform_internal_field(expected)
    rendered = text[: field.start] + replacement + text[field.end :]
    # ``write_bytes`` avoids platform newline translation.
    path.write_bytes(rendered.encode("utf-8"))

    observed = read_openfoam_alpha_field(path)
    expected_hash = openfoam_alpha_values_sha256(expected)
    if observed.cell_count != expected.size:
        raise ValueError(f"alpha readback count mismatch in {path}")
    if observed.value_sha256 != expected_hash or not np.array_equal(observed.values, expected):
        raise ValueError(f"alpha readback values/hash mismatch in {path}")
    return observed


def openfoam_alpha_values_sha256(values: np.ndarray) -> str:
    """Hash the canonical little-endian float64 vector representation."""

    vector = _require_float64_vector(values, "alpha values")
    canonical = np.asarray(vector, dtype="<f8")
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _require_alpha_path(path: Path) -> Path:
    path = Path(path)
    if path.name != "alpha" or path.parent.name != "0.orig":
        raise ValueError(f"OpenFOAM alpha codec only accepts a 0.orig/alpha path: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"OpenFOAM alpha field is missing: {path}")
    return path


def _read_posix_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"OpenFOAM alpha field must be UTF-8 text: {path}") from error
    # CRLF input is accepted as a template, but all codec output is LF.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _validate_alpha_header(text: str, path: Path) -> None:
    match = _FOAMFILE_START.match(_mask_comments(text))
    if match is None:
        raise ValueError(f"alpha field has no valid leading FoamFile header: {path}")
    end = _matching_brace(_mask_comments(text), match.end() - 1)
    if end is None:
        raise ValueError(f"alpha field FoamFile header is not closed: {path}")
    header = _mask_comments(text[match.end() : end])
    classes = _HEADER_CLASS.findall(header)
    objects = _HEADER_OBJECT.findall(header)
    if classes != ["volScalarField"] or objects != ["alpha"]:
        raise ValueError(f"alpha field has an unexpected FoamFile class/object header: {path}")


def _find_single_internal_field(text: str, path: Path) -> _InternalFieldMatch:
    masked = _mask_comments(text)
    matches = list(_INTERNAL_FIELD.finditer(masked))
    # Count the declaration keyword separately.  A malformed second
    # declaration must not be preserved merely because the strict list regex
    # cannot parse it.
    declarations = re.findall(r"\binternalField\b", masked)
    if len(declarations) != 1 or len(matches) != 1:
        raise ValueError(f"alpha field must contain exactly one internalField declaration: {path}")
    match = matches[0]
    if match.group("uniform") is not None:
        uniform = _parse_scalar_tokens(match.group("uniform"), path, "uniform alpha")
        if uniform.size != 1:
            raise ValueError(f"uniform alpha must contain exactly one scalar in {path}")
        return _InternalFieldMatch(match.start(), match.end(), "uniform", None)
    count = int(match.group("count"))
    values = _parse_scalar_tokens(text[match.start("values") : match.end("values")], path, "nonuniform alpha")
    if values.size != count:
        raise ValueError(f"nonuniform alpha count does not match its values in {path}")
    return _InternalFieldMatch(match.start(), match.end(), "nonuniform", values)


def _parse_scalar_tokens(text: str, path: Path, label: str) -> np.ndarray:
    tokens = text.split()
    if not tokens:
        raise ValueError(f"{label} has no values in {path}")
    try:
        values = np.asarray([float(token) for token in tokens], dtype=np.float64)
    except ValueError as error:
        raise ValueError(f"{label} contains a non-scalar token in {path}") from error
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} contains a non-finite value in {path}")
    return values


def _require_float64_vector(values: np.ndarray, label: str) -> np.ndarray:
    if not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float64) or values.ndim != 1:
        raise ValueError(f"{label} must be a one-dimensional native float64 numpy array")
    if values.size == 0:
        raise ValueError(f"{label} must not be empty")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} contains a non-finite value")
    return np.ascontiguousarray(values)


def _render_nonuniform_internal_field(values: np.ndarray) -> str:
    return "internalField nonuniform List<scalar>\n" + str(values.size) + "\n(\n" + "\n".join(
        f"{value:.17g}" for value in values
    ) + "\n)\n;"


def _mask_comments(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return _COMMENTS.sub(replace, text)


def _matching_brace(text: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                return None
    return None


__all__ = [
    "OpenFOAMAlphaField",
    "openfoam_alpha_values_sha256",
    "read_openfoam_alpha_field",
    "write_and_verify_openfoam_alpha_field",
]
