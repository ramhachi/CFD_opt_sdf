#!/usr/bin/env python3
"""harness v1 CLI (WaterLily T4 campaigns): build, freeze, smoke, verify.  See docs/harness/README.md.

  build  CAMPAIGN_JSON --source-commit X   render infra/kaggle/kernel_<campaign>_<k>/ (refuses to overwrite)
  freeze CAMPAIGN_JSON --source-commit X   identity-free check, clean tree, commit on a remote head, pins -> <campaign>.prerun_freeze.json (refuses to overwrite)
  smoke  CAMPAIGN_JSON --source-commit X   the SAME runner under a -smoke slug, first state of the cheapest case; prints the kaggle push command, never pushes
  verify KERNEL_DIR... --campaign CAMPAIGN_JSON --freeze FREEZE   integrity half of an analyzer -> validated state-force table JSON
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_harness import campaign_build as B  # noqa: E402
from cfd_harness import campaign_verify as V  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("build", "freeze", "smoke"):
        s = sub.add_parser(name)
        s.add_argument("campaign", type=Path)
        s.add_argument("--source-commit", required=True)
        if name == "smoke":
            s.add_argument("--kernel", help="default: the cheapest case")
    s = sub.add_parser("verify")
    s.add_argument("kernel_dirs", nargs="+", type=Path)
    s.add_argument("--campaign", type=Path, required=True)
    s.add_argument("--freeze", type=Path, help="required unless --smoke")
    s.add_argument("--smoke", action="store_true", help="verify a smoke output (one kernel, first state, no freeze)")
    s.add_argument("--out", type=Path, help="write the table here (never overwrites); default stdout")
    a = p.parse_args(argv)
    try:
        if a.cmd == "build":
            print("\n".join(str(d) for d in B.build(a.campaign, a.source_commit)))
        elif a.cmd == "freeze":
            print("freeze", B.freeze(a.campaign, a.source_commit))
        elif a.cmd == "smoke":
            d, cmd = B.smoke(a.campaign, a.source_commit, a.kernel)
            print(f"rendered {d}\nnot pushed; push with:\n  {' '.join(cmd)}")
        else:
            table = V.verify(a.campaign, a.kernel_dirs, a.freeze, a.smoke)
            data = json.dumps(table, sort_keys=True, indent=2, allow_nan=False) + "\n"
            if a.out is None:
                print(data, end="")
            else:
                with a.out.open("x") as handle:
                    handle.write(data)
    except (ValueError, RuntimeError, FileExistsError, OSError) as exc:
        print(f"{a.cmd} FAILED (fail closed): {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc


if __name__ == "__main__":
    main()
