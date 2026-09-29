"""Solver-neutral gradient-engine contracts."""

from .base import GradientEngine, GradientEvaluation, GradientRequest
from .directional_comparison import (
    CenteredDirectionalFD,
    DirectionalComparisonError,
    DirectionalGradientComparison,
    compare_field_gradient_to_centered_fd,
    field_direction_sha256,
)

__all__ = [
    "CenteredDirectionalFD",
    "DirectionalComparisonError",
    "DirectionalGradientComparison",
    "GradientEngine",
    "GradientEvaluation",
    "GradientRequest",
    "compare_field_gradient_to_centered_fd",
    "field_direction_sha256",
]
