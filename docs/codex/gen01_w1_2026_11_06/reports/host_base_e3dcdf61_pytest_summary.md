# Host baseline: full pytest at the W1 start commit e3dcdf61 (2026-11-06)

Run by Claude on the host (macOS arm64, not the Codex sandbox) in a detached worktree of `e3dcdf61` with the shared `.venv`, so that every WP result can be compared with one baseline. `tests/test_lbm_metal.py` is ignored on both sides because its `mlx.core` import aborts the process inside the Codex sandbox (no Metal device); the six Metal nodes are not part of this baseline.

```
nice -n 10 .venv/bin/python -m pytest -q -rf -p no:cacheprovider --ignore=tests/test_lbm_metal.py
```

Result: **3482 passed, 74 skipped, 0 failed** (52 min 58 s, exit 0). Last line of the log:

```
3482 passed, 74 skipped, 7295 warnings in 3177.74s (0:52:57)
```

Full log SHA-256: 0c78454ee9c7184627e1bf25feb7446058e5090c1bdc651fe743c0863c12be51
 (kept in the session scratchpad; not committed). Evidence class: software regression baseline only.
