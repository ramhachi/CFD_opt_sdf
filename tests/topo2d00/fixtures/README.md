# WP5 hermetic geometry regression fixture

`wp4_attempt2_E2_sharp.json.gz` contains the unmodified JSON bytes of
`docs/harness/topo2d00_scenes/E2_sharp.json` at WP4 commit
`ba3164c7df4ce5a68cd0ce44be6bdc2c3489f2b9` (decompressed SHA-256
`b89e77a44cca8a9f5434d390dd9422c01c49be33f4445f242d07e0917a863341`). It is intentionally invalid historical input:
its micrometre-scale segment must be refused under registration Amendment 3.
No source code from another worktree is executed by the tests. The source
coordinates remain UNVERIFIED_OCR, not experimental/physical qualification.
The compressed fixture uses gzip with mtime=0; standard-library gzip reads it.
