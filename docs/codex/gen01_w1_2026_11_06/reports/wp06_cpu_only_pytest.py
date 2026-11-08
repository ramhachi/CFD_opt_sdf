"""Explicit CPU-only pytest profile for BOTH WP6 and its detached baseline.

The unrestricted baseline aborted in mlx.core before JUnit could be written.
WP6 forbids GPU execution. Skip exactly the six pre-existing Metal tests,
before any of their imports run, without changing conftest or pinned tests.
Every other collected test still runs. Unexpected Metal node IDs fail closed.
This profile does not turn the aborted unrestricted run into a complete run.
"""
import pytest

METAL_NODE_IDS = frozenset({
    "tests/test_lbm_metal.py::test_metal_periodic_step_matches_cpu_on_rectangular_grid",
    "tests/test_lbm_metal.py::test_metal_non_float32_is_explicitly_rejected",
    *(f"tests/test_lbm_metal.py::test_metal_rejects_invalid_bgk_viscosity[{v}]" for v in ("0.0","0.5","0.6","bad")),
})


def pytest_collection_modifyitems(items):
    selected = [i for i in items if i.nodeid.split("::",1)[0]=="tests/test_lbm_metal.py"]
    if selected and {i.nodeid for i in selected}!=METAL_NODE_IDS:
        raise pytest.UsageError("WP6 CPU profile requires exactly the six reviewed Metal node IDs")
    for item in selected:
        item.add_marker(pytest.mark.skip(reason="WP6 CPU-only profile: GPU prohibited; baseline mlx.core import aborted"))


if __name__=="__main__":
    class Item:
        def __init__(self,nodeid):
            self.nodeid,self.marks = nodeid,[]
        def add_marker(self,marker):
            self.marks.append(marker)
    items = [Item(n) for n in sorted(METAL_NODE_IDS)]+[Item("tests/test_other.py::test_cpu")]
    pytest_collection_modifyitems(items)
    assert [len(i.marks) for i in items]==[1]*6+[0]
    try:
        pytest_collection_modifyitems(items+[Item("tests/test_lbm_metal.py::unexpected")])
    except pytest.UsageError:
        pass
    else:
        raise AssertionError("unexpected Metal IDs were not rejected")
    print("CPU profile self-check: six exact Metal IDs skipped; other test retained; unknown IDs rejected")
