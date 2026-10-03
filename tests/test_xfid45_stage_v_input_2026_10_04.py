import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_xfid45_stage_v_input_2026_10_04 as b  # noqa: E402


def box(lo, hi):
    x, y, z = np.array(np.meshgrid(*zip(lo, hi), indexing="ij")).reshape(3, -1)
    v = np.column_stack((x, y, z)).astype(float)
    f = np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
                  [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]])
    return v, f


def test_small_component_removed_and_stl_roundtrip():
    v1, f1 = box((0, 0, 0), (1, 1, 1))
    v2, f2 = box((2, 2, 2), (2.001, 2.001, 2.001))
    v = np.vstack((v1, v2))
    f = np.vstack((f1, f2 + len(v1)))
    kv, kf, removed = b.remove_small_components(v, f)
    assert len(kf) == 12 and len(removed) == 1 and removed[0]["faces"] == 12
    sv, sf = b.read_stl(b.stl_bytes(kv, kf))
    assert sf.shape == (12, 3) and np.allclose(np.unique(sv, axis=0), kv)
