"""Parse GRID-01's visible T4 inventory and select its physical index-zero GPU."""
from __future__ import annotations

import csv
from io import StringIO
from typing import Any


def select_worker_gpu(text: str) -> dict[str, Any]:
    """Require visible T4 devices and select physical GPU index 0 by index."""
    rows = []
    for fields in csv.reader(StringIO(text)):
        if not fields or all(not field.strip() for field in fields):
            continue
        if len(fields) != 5:
            raise ValueError("nvidia-smi inventory must have five columns")
        index, name, uuid, memory, driver = (field.strip() for field in fields)
        if not index.isdigit() or not uuid.startswith("GPU-") or not memory or not driver:
            raise ValueError("nvidia-smi inventory contains a malformed device row")
        rows.append({"index": int(index), "name": name, "uuid": uuid})
    if not rows:
        raise ValueError("nvidia-smi inventory is empty")
    if len({row["index"] for row in rows}) != len(rows):
        raise ValueError("nvidia-smi inventory contains duplicate physical indices")
    if any(row["name"] != "Tesla T4" for row in rows):
        raise ValueError("every visible worker GPU must be a Tesla T4")
    selected = [row for row in rows if row["index"] == 0]
    if len(selected) != 1:
        raise ValueError("physical GPU index 0 must occur exactly once")
    return selected[0]
