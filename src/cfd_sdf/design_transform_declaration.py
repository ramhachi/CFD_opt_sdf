"""Declared production design transform (PQ0 / I2, I5).

The production runner may not infer filter/projection/interpolation from
legacy control defaults. A run declares them in one JSON document, and the
loader builds the single ``DesignTransform`` instance that owns the forward
chain and both pullback spaces. The declaration also carries the explicit
compile-time volume budget (ProblemSpec v2 has no volume field yet); absent
budget means no volume constraint is solved.

Declaration schema (``kind: design_transform_declaration``):

```json
{
  "kind": "design_transform_declaration",
  "schema_version": 1,
  "filter": {"kind": "cone", "radius_m": 0.075, "spacing_m": 0.05},
  "projection": {"b": 16.0, "eta": 0.5},
  "ramp": {"q": 30.0},
  "volume_budget": {"constraint_id": "volume_fraction_max", "limit": 0.55}
}
```

``filter.kind`` is ``identity`` or ``cone``; the block filter is
diagnostics-only and is refused here. ``volume_budget`` may be ``null``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .design_transform import (
    BlockFilter,
    ConeFilter,
    DesignTransform,
    IdentityFilter,
    RampInterpolation,
    TanhProjection,
)
from .problem_spec_compiler import VolumeBudget

PRODUCTION_FILTER_KINDS = ("identity", "cone")


class DesignTransformDeclarationError(ValueError):
    """Fail-closed design-transform declaration violation."""


@dataclass(frozen=True)
class DesignTransformDeclaration:
    document: dict[str, Any]
    volume_budget: VolumeBudget | None

    @property
    def declaration_hash(self) -> str:
        payload = json.dumps(self.document, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def build(
        self,
        *,
        shape: tuple[int, int, int],
        spacing_m: float,
        active_mask: np.ndarray,
    ) -> DesignTransform:
        filter_block = self.document["filter"]
        kind = filter_block["kind"]
        if kind == "identity":
            filter_instance = IdentityFilter(
                shape=shape, spacing_m=spacing_m, active_mask=active_mask
            )
        elif kind == "cone":
            filter_instance = ConeFilter(
                shape=shape,
                spacing_m=spacing_m,
                active_mask=active_mask,
                radius_m=float(filter_block["radius_m"]),
            )
        elif kind == "block":
            raise DesignTransformDeclarationError(
                "the block filter is diagnostics-only and cannot own a production declaration"
            )
        else:
            raise DesignTransformDeclarationError(
                f"unknown filter kind {kind!r}; production kinds are {PRODUCTION_FILTER_KINDS}"
            )
        projection_block = self.document.get("projection", {})
        ramp_block = self.document.get("ramp", {})
        return DesignTransform(
            shape=shape,
            spacing_m=spacing_m,
            active_mask=active_mask,
            filter=filter_instance,
            projection=TanhProjection(
                float(projection_block.get("b", 0.0)),
                float(projection_block.get("eta", 0.5)),
            ),
            ramp=RampInterpolation(float(ramp_block.get("q", 0.0))),
        )


def load_design_transform_declaration(
    path: str | Path,
) -> DesignTransformDeclaration:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise DesignTransformDeclarationError("declaration must be a JSON object")
    if document.get("kind") != "design_transform_declaration":
        raise DesignTransformDeclarationError(
            "declaration kind must be 'design_transform_declaration'"
        )
    if document.get("schema_version") != 1:
        raise DesignTransformDeclarationError("declaration schema_version must be 1")
    filter_block = document.get("filter")
    if not isinstance(filter_block, dict):
        raise DesignTransformDeclarationError("declaration.filter is required")
    if filter_block.get("kind") not in (*PRODUCTION_FILTER_KINDS, "block"):
        raise DesignTransformDeclarationError(
            f"declaration.filter.kind must be one of {PRODUCTION_FILTER_KINDS} (block is refused)"
        )
    if "spacing_m" not in filter_block:
        raise DesignTransformDeclarationError("declaration.filter.spacing_m is required")
    if filter_block["kind"] == "cone" and "radius_m" not in filter_block:
        raise DesignTransformDeclarationError(
            "declaration.filter.radius_m is required for the cone filter"
        )
    projection_block = document.get("projection", {})
    if not isinstance(projection_block, dict):
        raise DesignTransformDeclarationError("declaration.projection must be an object")
    b = float(projection_block.get("b", 0.0))
    if b < 0.0:
        raise DesignTransformDeclarationError("declaration.projection.b must be non-negative")
    ramp_block = document.get("ramp", {})
    if not isinstance(ramp_block, dict):
        raise DesignTransformDeclarationError("declaration.ramp must be an object")
    q = float(ramp_block.get("q", 0.0))
    if q < 0.0:
        raise DesignTransformDeclarationError("declaration.ramp.q must be non-negative")
    volume_block = document.get("volume_budget")
    volume_budget = None
    if volume_block is not None:
        if not isinstance(volume_block, dict):
            raise DesignTransformDeclarationError(
                "declaration.volume_budget must be an object or null"
            )
        volume_budget = VolumeBudget(
            str(volume_block.get("constraint_id", "")),
            float(volume_block.get("limit", -1.0)),
        )
    return DesignTransformDeclaration(document=document, volume_budget=volume_budget)


__all__ = [
    "PRODUCTION_FILTER_KINDS",
    "DesignTransformDeclaration",
    "DesignTransformDeclarationError",
    "load_design_transform_declaration",
]
