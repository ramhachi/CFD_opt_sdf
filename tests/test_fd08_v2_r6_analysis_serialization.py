"""Regression coverage for exact C5 diagnostics in the R6 analysis artifact."""

from decimal import Decimal
import importlib.util
import json
from pathlib import Path

import numpy as np

from cfd_sdf.fd08_v2_gate import load_params


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fd08_v2_r6_analysis_serialization",
    ROOT / "scripts/analyze_fd08_v2_r6.py",
)
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)
FORWARD_SPEC = importlib.util.spec_from_file_location(
    "fd08_v2_r6_forward_error_serialization",
    ROOT / "scripts/fd08_v2_forward_error.py",
)
forward = importlib.util.module_from_spec(FORWARD_SPEC)
FORWARD_SPEC.loader.exec_module(forward)


def _leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


def test_c5_decimal_diagnostics_serialize_at_exact_decimal_precision():
    epsilon = np.geomspace(0.3, 5, 8)
    response = (-0.104 - 0.00104 * epsilon**2) * epsilon / 1000
    response[3] += 2e-6
    envelope = forward.bound_series(epsilon, response, load_params(), decimal_output=True)
    diagnostics = envelope["diagnostics"]
    assert any(isinstance(value, Decimal) for value in _leaves(diagnostics))

    encoded = json.dumps(diagnostics, sort_keys=True, allow_nan=False,
                         default=analyzer._json_default)
    decoded = json.loads(encoded)
    assert decoded["variant"] == "N1"
    assert decoded["fits"]
    assert isinstance(decoded["fits"]["full_A"]["pilot_radius"], str)


def test_json_default_keeps_numpy_scalars_as_json_numbers():
    encoded = json.dumps({"value": np.float64(0.25)}, default=analyzer._json_default,
                         allow_nan=False)
    assert json.loads(encoded) == {"value": 0.25}
