"""Run the pipeline. Usage: python run.py [--from 2]   (steps: 1 papers, 2 payments, 3 flag, 4 publish)"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "pipeline"))
import s1_papers, s2_payments, s3_flag, s4_publish  # noqa: E402
from common import log  # noqa: E402

STEPS = [("papers", s1_papers), ("payments", s2_payments), ("flag", s3_flag), ("publish", s4_publish)]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=len(STEPS))
    a = ap.parse_args()
    for i, (name, mod) in enumerate(STEPS, 1):
        if a.start <= i <= a.end:
            log(f"=== step {i}: {name} ===", i, len(STEPS))
            mod.main()
    log("done")
