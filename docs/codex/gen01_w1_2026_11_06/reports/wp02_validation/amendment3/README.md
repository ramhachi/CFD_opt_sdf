# FORCE-00 Amendment 3 CPU acceptance captures

Current source-bound records for the afac79ed continuation; see [wp02_report.md](../../wp02_report.md)
for the complete report.
These are CPU software/geometry/solved-cylinder diagnostics, not registered GPU
evidence, a gate write, or readout adoption. The production FORCE-00 evidence
root remains absent. Previous final/ records belong to Amendment 2.

The uniform JSON is deterministic over two new process runs. The CPU production
job comparison uses the unmodified registered job and the copied variant; all
legacy/cur tokens and final solver arrays match. closure_check.json also records
direct production provenance/box validators and all20 registered references.
full_suite_comparison.json records the completed result failure-node set against
the owner-provided completed host baseline. log_archive.json maps every original
log/JUnit path and SHA to a verified lossless gzip. SHA256SUMS is repository-relative.

The code supports CPU/GPU array kernels, but GPU compilation/execution and F1-F3
remain unverified. Only Kaggle T4 can satisfy the registered byte reference. The
project parent's built-in/CV force gap remains unknown until those user runs.

Commit/push/PR84 update belongs to Claude on the host per Amendment3. The complete
intended worktree inventory is commit_inventory.json; no move/restoration/deletion
was needed in this continuation.
