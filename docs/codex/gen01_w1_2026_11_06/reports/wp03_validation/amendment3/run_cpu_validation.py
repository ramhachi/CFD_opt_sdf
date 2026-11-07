"""Reuse the recorded short-CPU driver with fresh Amendment 3 output paths.

Runs only 20-step preflights and frozen TA1 captures, sequentially. The reused
driver has a 480 s per-process limit; the full pytest invocation has no cap.
No launcher full-window run, GPU, Kaggle, or manifest edit is performed.
"""
import importlib.util
from pathlib import Path

OUT = Path(__file__).resolve().parent
DRIVER = OUT.parent / "amendment2/run_cpu_validation.py"
spec = importlib.util.spec_from_file_location("grad00_recorded_cpu_driver", DRIVER)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
driver.OUT = OUT

if __name__ == "__main__":
    driver.main()
