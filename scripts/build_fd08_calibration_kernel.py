#!/usr/bin/env python3
"""Build the single-file Kaggle FD-08 script from its hash-bound core."""

from __future__ import annotations

import base64
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra/kaggle/kernel_fd08_calibration/runner.py.template"
CORE = ROOT / "infra/kaggle/kernel_fd08_calibration/runner_base.py"
OUTPUT = ROOT / "infra/kaggle/kernel_fd08_calibration/runner.py"
TOKEN = "@@FD08_CORE_SOURCE_B85@@"


def render_kernel_source(template: bytes, core_source: bytes) -> bytes:
    text = template.decode("utf-8")
    if text.count(TOKEN) != 1:
        raise ValueError("FD-08 kernel template must contain its embedded-core token exactly once")
    encoded = base64.b85encode(zlib.compress(core_source, level=9)).decode("ascii")
    chunks = [encoded[index:index + 100] for index in range(0, len(encoded), 100)]
    literal = "(\n" + "\n".join(f'    "{chunk}"' for chunk in chunks) + "\n)"
    rendered = text.replace(f'"{TOKEN}"', literal)
    compile(rendered, "fd08-kaggle-runner.py", "exec")
    return rendered.encode("utf-8")


def build() -> Path:
    if not TEMPLATE.is_file() or not CORE.is_file():
        raise FileNotFoundError("FD-08 Kaggle runner template or core source is missing")
    output = render_kernel_source(TEMPLATE.read_bytes(), CORE.read_bytes())
    OUTPUT.write_bytes(output)
    return OUTPUT


if __name__ == "__main__":
    print(build().relative_to(ROOT).as_posix())
