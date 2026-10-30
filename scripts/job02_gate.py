#!/usr/bin/env python3
"""JOB-02 (#59) byte-identity gate: each registered run's force CSV must equal its historical reference byte for byte (no tolerance).

  job02_gate.py --spec SPEC --table TABLE --kernel-root DIR [--out RESULT]

SPEC  the frozen gate spec (docs/evidence/job02_gate_2026_10_19/gate_spec.json): campaign hash and, per (kernel, run), the reference CSV path and SHA-256.
TABLE the formal `harness.py verify` state-force table of the campaign (smoke tables are rejected).
DIR   the directory holding the downloaded kernel outputs (<out_prefix><kernel>/states/<run>/<case>.forces.csv).
Exit 0 and verdict JOB02_GATE_PASS only if every comparison holds; otherwise exit 1 with JOB02_GATE_FAIL (malformed inputs exit 3). Nothing here is a measurement.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_harness import campaign_schema as SC  # noqa: E402

SPEC_KIND, RESULT_KIND = "job02_byte_identity_gate_spec", "job02_byte_identity_gate_result"


def gate(spec_path, table_path, kernel_root, repo=ROOT):
    spec, table = SC.jload(spec_path), SC.require_formal_table(SC.jload(table_path))
    SC.req(spec.get("kind") == SPEC_KIND and spec.get("comparisons"), "not a JOB-02 gate spec")
    campaign = SC.jload(Path(repo) / spec["campaign_path"])
    SC.req(SC.sha256_path(Path(repo) / spec["campaign_path"]) == spec["campaign_sha256"] == table["campaign_sha256"], "campaign differs from the spec or the table")
    SC.req(len({(c["kernel"], c["run"]) for c in spec["comparisons"]}) == len(spec["comparisons"]), "duplicate comparison")
    SC.req({(c["kernel"], c["run"]) for c in spec["comparisons"]} == {(k, n) for k, kernel in campaign["kernels"].items() for n in SC.run_names(kernel)}, "the spec must cover exactly the campaign's runs")
    for k in campaign["kernels"]:  # the CSVs read below are the bytes `verify` checked: same output manifest as the table records, and every file still matches it
        out = Path(kernel_root) / SC.out_dir_name(campaign, k)
        SC.req(table["kernel_manifest_sha256"][k] == SC.sha256_path(out / SC.MANIFEST_NAME), f"kernel {k}: output differs from the verified table")
        try:
            SC.check_manifest(out, [])
        except ValueError as exc:
            raise ValueError(f"kernel {k}: output differs from the verified table ({exc})") from exc
    rows = []
    for c in spec["comparisons"]:
        kernel = campaign["kernels"][c["kernel"]]
        ref = Path(repo) / SC.safe_rel(c["reference_csv"])
        SC.req(SC.sha256_path(ref) == c["reference_sha256"], f"reference CSV differs from the spec: {c['reference_csv']}")
        got = Path(kernel_root) / SC.out_dir_name(campaign, c["kernel"]) / "states" / c["run"] / SC.forces_name(kernel["case"]["case_id"])
        table_sha = table["state_forces_n"][c["kernel"]][c["run"]]["forces_csv_sha256"]
        same = got.read_bytes() == ref.read_bytes() and table_sha == c["reference_sha256"]
        rows.append({**c, "output_csv_sha256": SC.sha256_path(got), "table_csv_sha256": table_sha, "byte_identical": same})
    ok = all(r["byte_identical"] for r in rows)
    return {"kind": RESULT_KIND, "verdict": "JOB02_GATE_PASS" if ok else "JOB02_GATE_FAIL", "spec_sha256": SC.sha256_path(spec_path), "table_sha256": SC.sha256_path(table_path),
            "campaign_sha256": spec["campaign_sha256"], "table_source_commit": table.get("source_commit"), "table_freeze_sha256": table.get("freeze_sha256"), "comparisons": rows}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--table", type=Path, required=True)
    p.add_argument("--kernel-root", type=Path, required=True)
    p.add_argument("--out", type=Path, help="write the result here (never overwrites); default stdout")
    a = p.parse_args(argv)
    try:
        result = gate(a.spec, a.table, a.kernel_root)
        data = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if a.out is None:
            print(data, end="")
        else:
            with a.out.open("x") as handle:
                handle.write(data)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"gate FAILED (fail closed): {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    print(result["verdict"], file=sys.stderr)
    raise SystemExit(0 if result["verdict"] == "JOB02_GATE_PASS" else 1)


if __name__ == "__main__":
    main()
