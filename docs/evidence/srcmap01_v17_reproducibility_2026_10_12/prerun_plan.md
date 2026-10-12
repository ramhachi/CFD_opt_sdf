# SRCMAP-01 frozen solver-free diagnosis

Integration parent: `b94eebacf7d1e4425e1b6303a5e34b4fe08b1863`. Issue #52.
Goal: diagnose strict STL-to-SDF reproducibility without changing any mapping,
volume, retained field, parent, qualification flag or continuation contract.
Historical Oct11 exact dependency versions and actual try/fallback, inner Rtree
and ray retry paths are UNKNOWN. Alternative environment represents project
minimum dependencies and is explicitly not a reconstructed historical runtime.

All distances begin only after independent pre-review approval of the exact
freeze SHA. The runner first creates output directories and verifies no-distance
inventories using the literal frozen Python executable for both environments;
only then does it create the one-shot execution marker. Inventories and mesh loading/hashing before freeze are allowed.
Each of 21 listed full-field jobs runs once in an independent process, sequentially. Stage E is one separate local-analysis process in the frozen current Python. One execution
marker prevents campaign reruns. Unexpected failures stop with UNRESOLVED.
No run is selected or discarded based on agreement. Existing evidence is read only.

A: five canonical v17 + two canonical v16 production runs, chunk 200000.
B: six v17 production runs, chunks 385385,50000,100000,200000,368640,131071.
The actual 121*65*49 node count is 385385 (cell count 368640).
C: three v17 production runs canonical/reverse/permuted, chunk 200000;
permutation seed 20261012; inverse permutation restores canonical traversal.
D: one v17 each direct signed_distance, closest_point+mesh.contains fallback,
unsigned closest_point; chunk 200000. Separate diagnostics, no production adoption.
E: local analysis of the three historical indices (28,24,19), (48,44,23),
(56,44,27), plus exhaustive all-triangle closest-point comparison, adjacency,
barycentric/plane/edge/vertex distances. Three separately labeled diagnostic
retry vectors fixed before results: (0.137,0.271,0.619),
(0.731,0.419,0.173), (0.317,0.823,0.457), evaluated on the three nodes as a batch.
These fixed vectors do not seed or modify production measurement runs.
F: every v17 field's Float32/Float64 difference maps against retained registered
Float32 (exactly promoted for Float64); complete bytes/hash/mask/distributions.
No historical pre-cast Float64 exists: promoted Float32 is not one.
G: exactly two canonical v17 independent minimum-environment runs, chunk200000,
against current A five-run reference. No version sweep or subsequent tuning.

PYTHONHASHSEED=0 for every process. Thread env variables inherit the inventoried
state. NumPy/trimesh random streams remain entropy initialized: logging records
actual generator states/draws and query hashes/known-node membership, without
seeding, drawing extra values or changing behavior. The permutation generator
has its own fixed seed and does not touch the production random stream.
Ray contains_points recursion is instrumented with points/check_direction arguments and parent event IDs; each RNG draw records the active invocation IDs. Rtree batch success/exception and scalar fallback aggregate are instrumented. Instrumentation metadata errors are logged while originals still execute unchanged; any such error forces UNRESOLVED.
Scalar intersection is a lazy generator: logged scalar successes mean iterator
creation returned, not that later iteration completed. Batch exceptions are
recorded directly. Structural runtime (all fields except logged entropy states),
actual imported source/module hashes, loaded mesh/backend inventory and exact
point-coordinate hashes are checked for every run against frozen inventories
before any classification. The only runtime exclusions are numpy_legacy_random_state_sha256 and trimesh_entropy_random_state; both are retained in raw records. Diagnostic source SHA and PYTHONPATH are included. All frozen input hashes are checked again after measurements and before classification. Drift fails closed; entropy state differences are
recorded behavior and do not masquerade as runtime/dependency drift.
All production outputs call actual unchanged cfd_sdf.sdf.signed_distance.

Classification precedence (complete data required): identity groups are
(environment,grid,chunk,ordering,mode). The current canonical v17 group includes
A_v17_1..5, B_chunk_200000 and C_canonical; v16 A1..2 and minimum G1..2 are
also repeated groups. Any group yielding different Float32 OR pre-cast Float64 bytes =>
SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC. Historical proven call path divergence
=> SOURCE_MAPPING_IMPLEMENTATION_PATH_DIVERGENCE (UNKNOWN history cannot satisfy).
Stable repeated environment A registered bytes and stable environment B different
bytes (or reversed) => SOURCE_MAPPING_ENVIRONMENT_DEPENDENT, scoped strictly to
the frozen environment bundle. The bundle changes multiple dependencies; individual
dependency localization is UNKNOWN, and historical environments remain UNKNOWN.
Record the full structural runtime and mesh difference set; no individual-library
or historical-cause attribution follows from bundle sensitivity. Both v16/v17 current
repeats and chunk/order variants registered exact => SOURCE_MAPPING_REPRODUCIBLE,
limited to the observed finite set in the current frozen runtime; historical discrepancy still may be unresolved. If any of the three predeclared E retry vectors changes direct Float64 bytes or contains classification on the known nodes, REPRODUCIBLE is blocked and otherwise falls to UNRESOLVED. Finite repeats never prove universal determinism.
Otherwise SOURCE_MAPPING_UNRESOLVED. Mere chunk/order dependence is UNRESOLVED
when canonical repeats are identical and no other classification is supported.
No allclose or tolerance enters classification. Signed zero is a bit difference.

Reference bytes and authority hashes are in prerun_freeze.json. Every field has
explicit little/big endian C/F hashes; sign,negative,zero uint8 C masks and
reference |phi|<=1e-7 subset. Threshold distribution >0,1e-10,1e-9,1e-8 and local
1e-14 tie census are diagnostic scales only; PASS uses exact bit equality.
Allowed outputs: immutable diagnostic JSON/NPZ/logs, runtime/source locks,
reviews, validation and final evidence hashes. Never authorize P22-v2,
LOWDIM-04A, CFD, Kaggle, shape/parent changes or optimization continuation.
