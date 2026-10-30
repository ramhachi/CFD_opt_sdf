# P2a generation attempt 1 (incomplete, preserved)

Evidence class: `solver_free_post_hoc_calibration_diagnostic_unregistered_partial`.

The solver-free computation reached JSON and figure generation after verifying the R5 criteria, existing analysis, dataset inputs, runner manifest, and all 47 force histories. The attempt stopped during note rendering with `KeyError: 'summary_a5'` because the output renderer referenced the wrong in-memory result key (`a5_numeric_summary`). This was a reporting-only defect. No criteria, gates, R5 evidence, or solver outputs were changed. These files are preserved as generated; they are not the final P2a result and are not used as a verdict.

Files present before the failure:

- `diagnostic_result.json`: SHA-256 `9a7d577479aaedc1b07217bb068d8ac7fedc227ebd343eb989834be3dd69660a`
- `plateau_windows.png`: SHA-256 `08b42575e0f1804a4e682716c673bb7b217cdc0e0d264f1099dcb42e941517c3`
- `sdf_functionals_D0.png`: SHA-256 `f9d9bf3e5c7dfa7e3afd96e27fb5171926bc4048830646b605533504d88d1f3e`
- `sdf_functionals_D1.png`: SHA-256 `ab74dd2333998cf27bb8e36a6a65951c918a5ea346eee183ef2e03c3a513aee8`
- `sdf_functionals_D2.png`: SHA-256 `94ca3fef3494d8b3adaa23803a82d60ad29f4097cf38fec7f7a0ad9fbb344a07`

The script revision that generated the preserved partial result had SHA-256 `8c87cfbb676d0219df8164ffa128ed97a554e9d8ac92eddbd366c13d8bc414d9`.
