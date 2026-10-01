# Rejected pre-execution W2a-C draft

This directory preserves the exact pre-execution Round 1 draft as reviewed
before output-recorder revisions. It made no solver calls or measurements. The
immutable criteria hash is `5ceb07437014b3baeb7286ffad856e77a0d7369e2ab979243f1609ac3e37d35f`, and the source-manifest hash is
`5e35729e9d071dee542ebbb958a97d74dffc26784c054cc08ca1997091ba590e`.

Snapshot runner SHA-256: `2c49cca2e00aba805eb390acf365c80125438b99b6861f5329ab2da4faf8e59c`.
Snapshot job SHA-256: `001679adb926586632faf097f82338db55c39d0487db8aeb0551d15ef1084ef0`.
Snapshot initialization-preflight SHA-256: `8947af9aef943bafc2780dcc0c38810b5b0647ae9e882f56abd7c4d468a004bc`.

It was superseded before any measurement after review found that failed/timed
out solver processes would lose in-memory samples, transcripts were written
only after successful exit, and the native control represented its not
applicable SDF margin as non-standard JSON `NaN`. It is retained as an
append-only snapshot; the subsequent criteria round must bind corrected source
hashes and write per-sample data durably.
