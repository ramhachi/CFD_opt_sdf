"""G2-DIAG1 post-hoc addendum: the recorded numbers are the ones the script derives from the kept ledger, and the DIAG1 record is untouched."""
import hashlib
import json
from pathlib import Path

from scripts import posthoc_grad_g2_diag1_addendum as P

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
ADD = json.loads((E / "posthoc_addendum.json").read_text())


def test_ledger_part_is_reproducible_from_the_kept_ledger():
    fresh = json.loads(json.dumps(P.ledger_part()))
    assert fresh == ADD["ledger"]
    assert ADD["ledger"]["poisson_iterations_one_from_step"] == 31 and 1.30 < ADD["ledger"]["net_gain_step_871_start_to_end"] < 1.32
    rel = ADD["ledger"]["poisson_relative_residual"]
    assert all(v["tangent_relative_residual"] > 10 * v["primal_relative_residual"] for v in rel.values())


def test_snapshot_part_records_the_corner_box_and_onset():
    s = ADD["snapshots"]
    assert s["energy"]["900"]["fraction_in_box"] > 0.999 and s["energy"]["900"]["argmax_cell_0based"] == [5, 3, 50]
    assert 780 < s["extrapolated_onset_step_from_500_level"] < 830 and 0.09 < s["growth_rate_box_decade_per_step_900_to_1000"] < 0.1
    assert s["max_abs_tangent_u"]["500"]["in_box"] < 0.02 < 1 < s["max_abs_tangent_u"]["500"]["outside_box"]


def test_diag1_registered_record_is_unchanged():
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    assert hashlib.sha256((E / "prerun_freeze.json").read_bytes()).hexdigest() == (E / "prerun_freeze.json.sha256").read_text().strip()
    analysis = json.loads((E / "diag1_analysis.json").read_text())
    assert analysis["hypotheses"]["H4"] == "refutes" and "H4" in freeze["hypotheses"]     # the registered status stays; the addendum corrects it
    assert "H4" in (E / "posthoc_addendum.md").read_text() and "取り下げ" in (E / "posthoc_addendum.md").read_text()
