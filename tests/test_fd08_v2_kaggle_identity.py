import json
import re
from pathlib import Path

from scripts.register_fd08_v2_r6 import KERNEL_ID


ROOT = Path(__file__).resolve().parents[1]


def test_kaggle_title_slug_and_round_criteria_share_kernel_identity():
    metadata = json.loads((ROOT / "infra/kaggle/kernel_fd08_v2_r6/kernel-metadata.json").read_text())
    title_slug = re.sub(r"[^a-z0-9]+", "-", metadata["title"].lower()).strip("-")

    assert metadata["id"] == KERNEL_ID
    assert metadata["id"].split("/", 1)[1] == title_slug
    assert metadata["dataset_sources"] == ["ramhachi888/cfd-opt-sdf-fd08-v2-r6"]
