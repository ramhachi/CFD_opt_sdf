from __future__ import annotations

import pytest

from scripts.pq4_1_terminal_stage_s_entry_2026_09 import _stage_s_verdict_from_sweep


def test_stage_s_verdict_uses_selected_threshold_row() -> None:
    sweep = {
        "selected_threshold": 0.5,
        "rows": [
            {
                "threshold": 0.4,
                "status": "ok",
                "ready_for_stage_s": False,
                "stage_s_entry": {"reasons": ["feature_shrink"], "sub_verdicts": {}},
            },
            {
                "threshold": 0.5,
                "status": "ok",
                "ready_for_stage_s": True,
                "stage_s_entry": {"reasons": [], "sub_verdicts": {"clearance": {"pass": True}}},
            },
        ],
    }

    verdict = _stage_s_verdict_from_sweep(sweep)

    assert verdict["ready_for_stage_s"] is True
    assert verdict["selected_threshold"] == pytest.approx(0.5)
    assert verdict["sub_verdicts"]["clearance"]["pass"] is True


def test_stage_s_verdict_rejects_dangling_selection() -> None:
    with pytest.raises(ValueError, match="no matching sweep row"):
        _stage_s_verdict_from_sweep({"selected_threshold": 0.5, "rows": []})
