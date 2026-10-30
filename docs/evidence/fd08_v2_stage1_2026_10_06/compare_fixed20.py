"""Compare saved primary/blind results only; neither evaluator is imported."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOLERANCE = 1e-9


def main():
    primary = {row["id"]: row["result"] for row in json.loads(
        (HERE / "primary_fixed20_results.json").read_text())["cases"]}
    independent = {row["id"]: row for row in json.loads(
        (HERE / "independent_fixed20_results.json").read_text())["results"]}
    assert set(primary) == set(independent) and len(primary) == 20
    numeric, exact = [], []

    def compare(case, field, left, right):
        if isinstance(left, list):
            assert isinstance(right, list) and len(left) == len(right), field
            for index, (a, b) in enumerate(zip(left, right)):
                compare(case, f"{field}[{index}]", a, b)
        elif isinstance(left, (bool, str, int)) or left is None:
            exact.append(dict(case=case, field=field, primary=left, independent=right,
                              passed=left == right))
        else:
            difference = abs(left - right)
            scale = max(abs(left), abs(right))
            relative = difference / scale if scale else 0.
            numeric.append(dict(case=case, field=field, primary=left, independent=right,
                                absolute_difference=difference, relative_difference=relative,
                                passed=relative <= TOLERANCE))

    def fits(case, prefix, a, b):
        for name_a, name_b in (("beta", "coefficients_mm"), ("covariance", "covariance_mm"),
                               ("pilot_s_n", "pilot_predictions_n"),
                               ("weights", "weights_n_inverse_squared"),
                               ("g_n_per_m", "g_n_per_m"), ("se_g_n_per_m", "se_g_n_per_m")):
            compare(case, f"{prefix}.{name_a}", a[name_a], b[name_b])

    for case, a in primary.items():
        b = independent[case]
        compare(case, "verdict", a["verdict"], b["verdict"])
        compare(case, "n_points", a["n_points"], b["n"])
        compare(case, "dof", a["dof"], b["dof"])
        for model, name in (("A", "model_a"), ("B", "model_b")):
            fits(case, name, a[name], b["full_fits"][model])
        for name in a["items"]:
            blind_name = "holdout" if name == "internal_holdout" else name
            compare(case, f"items.{name}.passed", a["items"][name]["passed"], b["items"][blind_name]["pass"])
        for name, value in (("relative_se", "value"), ("nested_stability", "maximum_relative_shift"),
                            ("model_difference", "value"), ("magnitude", "point_count")):
            compare(case, f"items.{name}.{value}", a["items"][name][value], b["items"][name]["value"])
        assert len(a["nested"]) == len(b["nested"])
        for index, (pa, pb) in enumerate(zip(a["nested"], b["nested"])):
            prefix = f"nested[{index}]"
            for name in ("drop", "used_for_sign", "used_for_stability"):
                compare(case, prefix + "." + name, pa[name], pb[name])
            compare(case, prefix + ".relative_shift_a", pa["relative_shift_a"], pb["relative_g_A_change"])
            for model, name in (("A", "model_a"), ("B", "model_b")):
                fits(case, prefix + "." + name, pa[name], pb["fits"][model])
        assert len(a["holdout"]) == len(b["holdouts"])
        for index, (pa, pb) in enumerate(zip(a["holdout"], b["holdouts"])):
            prefix = f"holdout[{index}]"
            for name_a, name_b in (("index", "index"), ("s_pred_n", "prediction_n"),
                                   ("sigma_pred_n", "sigma_prediction_n"), ("error_n", "absolute_error_n"),
                                   ("limit_n", "tolerance_n"), ("passed", "pass")):
                compare(case, prefix + "." + name_a, pa[name_a], pb[name_b])
            fits(case, prefix + ".fit", pa["fit"], pb["fit"])
    mismatches = [row for row in numeric if not row["passed"]]
    exact_mismatches = [row for row in exact if not row["passed"]]
    summary = {
        "input_cases": len(primary), "relative_tolerance": TOLERANCE,
        "relative_definition": "abs(a-b)/max(abs(a),abs(b)); both zero -> zero; NO absolute tolerance",
        "numeric_comparisons": len(numeric), "numeric_mismatch_count": len(mismatches),
        "maximum_relative_difference": max(row["relative_difference"] for row in numeric),
        "maximum_absolute_difference": max(row["absolute_difference"] for row in numeric),
        "exact_comparisons": len(exact), "exact_mismatch_count": len(exact_mismatches),
        "verdict_mismatch_count": sum(row["field"] == "verdict" for row in exact_mismatches),
        "strict_numeric_agreement": not mismatches and not exact_mismatches,
        "numeric_mismatches": mismatches, "exact_mismatches": exact_mismatches,
        "per_field_max_relative_difference": {
            field: max(row["relative_difference"] for row in numeric if row["field"] == field)
            for field in sorted({row["field"] for row in numeric})}}
    def rounded(value):
        if isinstance(value, dict):
            return {key: rounded(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rounded(item) for item in value]
        return float(format(value, ".12g")) if isinstance(value, float) else value
    (HERE / "independent_comparison.json").write_text(
        json.dumps(rounded(summary), indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in ("numeric_mismatches", "exact_mismatches", "per_field_max_relative_difference")},
                     sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
