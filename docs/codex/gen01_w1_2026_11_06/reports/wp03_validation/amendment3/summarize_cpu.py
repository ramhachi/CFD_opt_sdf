"""Check the retained CPU preflights, independent TA1 captures, and preservation."""
import hashlib
import json
from pathlib import Path

import integrity_audit as I

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, value):
    with (OUT / name).open("x") as output:
        json.dump(value, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")


def main():
    results = load(OUT / "cpu_results.json")
    rows = {}
    for name, result in results.items():
        assert result["source_sha256_before"] == result["source_sha256_after"], name
        for path, expected in result["source_sha256_after"].items():
            assert sha(ROOT / path) == expected, (name, path)
        assert sha(OUT / name / "output.txt") == result["log_sha256"], name
        if "capture_execution" in name:
            assert result["exit_code"] == 0, name
            continue
        preflight = load(OUT / name / "preflight.json")
        selected = preflight["arms"]["selected_dual"]
        expected_pass = name != "CFDSDFWaterLily_vanLeer_Float32"
        assert preflight["pass"] is expected_pass, name
        assert result["exit_code"] == (0 if expected_pass else 2), name
        assert result["index_status"] == ("PREFLIGHT_ONLY" if expected_pass else "INCOMPLETE"), name
        for component in ("u", "p"):
            location = selected[f"tangent_argmax_{component}"]
            assert len(location["index"]) == (4 if component == "u" else 3)
            assert location["finite"] is selected[f"tangent_{component}_finite"]
            if location["finite"]:
                assert abs(location["value"]) == location["abs_value"] == selected[f"max_abs_tangent_{component}"]
        rows[name] = {"preflight_pass": preflight["pass"], "exit_code": result["exit_code"],
                      "index_status": result["index_status"], "wall_seconds": result["wall_seconds"],
                      "selected_plain_primal_finite": preflight["arms"]["selected_plain"]["primal_finite"],
                      "selected_dual_primal_finite": selected["primal_finite"],
                      "tangent": {c: {"maximum_abs": selected[f"max_abs_tangent_{c}"],
                                      "argmax": selected[f"tangent_argmax_{c}"]} for c in ("u", "p")},
                      "preflight_sha256": sha(OUT / name / "preflight.json")}
    quick_path = OUT / "CFDSDFWaterLily_quick_Float32/preflight.json"
    quick = load(quick_path)
    comparisons = {}
    for kind, filename, selected_name in (("dual", "ta1_reference/quick_control.json", "selected_dual"),
                                          ("plain", "ta1_plain_reference/quick_plain_control.json", "selected_plain")):
        path = OUT / filename
        captured = load(path)
        equal = {f"primal_{c}_sha256": captured[f"primal_{c}_sha256"] == quick["arms"][selected_name][f"primal_{c}_sha256"] for c in ("u", "p")}
        assert all(equal.values()), kind
        comparisons[kind] = {"pass": True, "bit_equal": equal, "capture": str(path.relative_to(ROOT)),
                             "capture_sha256": sha(path), "copy_preflight_sha256": sha(quick_path),
                             "steps": 20, "julia": captured["julia"], "waterlily": captured["waterlily"],
                             "forwarddiff": captured["forwarddiff"],
                             "hashes": {key: captured[key] for key in equal}}
    safe = load(OUT / "CFDSDFWaterLily_vanLeer_safe_Float32/preflight.json")
    assert all(safe[f"vanLeer_primal_{c}_bit_equal"] for c in ("u", "p"))
    assert all(safe["arms"]["selected_plain"][f"primal_{c}_sha256"] == safe["arms"]["vanLeer_plain"][f"primal_{c}_sha256"] for c in ("u", "p"))
    before = load(OUT / "protected_before.json")
    after = I.protected_snapshot()
    assert before["protected_sha256"] == after["protected_sha256"]
    dump("protected_after.json", after)
    dump("cpu_summary.json", {"evidence_class": "20_step_cpu_software_preflight_only", "rows": rows,
                              "vanLeer_safe_plain_vs_vanLeer_bit_equal": True,
                              "claim_limit": "No full-window boundedness, FD agreement, GPU or physics qualification"})
    dump("ta1_bit_comparison.json", {"evidence_class": "cpu_frozen_ta1_20_step_plain_and_dual_value_bit_comparison",
                                      "pass": True, "comparisons": comparisons,
                                      "claim_limit": "Cross-script CPU comparison only, distinct from same-build determinism fields"})
    print("CPU_SUMMARY_PASS profiles=8 TA1_plain_and_Dual_bit_equal=true protected_files=", after["protected_file_count"])


if __name__ == "__main__":
    main()
