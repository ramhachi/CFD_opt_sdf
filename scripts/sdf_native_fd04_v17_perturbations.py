"""#43 diagnostic: stage v17 baseline + registered-generator perturbations as raw f4 Fortran phi.

Uses the unchanged FD generator (generate_directions / perturbed_state) on the v17 state.
Output layout matches the round-5 dataset so the FD-04 Julia diagnostics can read it.
usage: python scripts/sdf_native_fd04_v17_perturbations.py <state.npz> <out_dir>
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.gradients.directional_fd import generate_directions, perturbed_state  # noqa: E402

EPSILONS = {"0p0005": 0.0005, "0p0010": 0.001, "0p0025": 0.0025, "0p0050": 0.005, "0p0100": 0.01}

state = SDFDesignState.load(Path(sys.argv[1]))
out = Path(sys.argv[2])
(out / "perturbations").mkdir(parents=True, exist_ok=True)
write = lambda path, phi: path.write_bytes(np.asarray(phi, dtype=np.float32).tobytes(order="F"))
write(out / "canonical_v16_phi_f4_fortran.raw", state.phi)  # name kept for the Julia reader
for did, d in generate_directions(state).items():
    for tag, eps in EPSILONS.items():
        for sign, name in ((-1, "minus"), (1, "plus")):
            child, _ = perturbed_state(state, d, epsilon_m=eps, sign=sign)
            write(out / "perturbations" / f"{did}__eps_{tag}m__{name}.phi-f4-fortran.raw", child.phi)
print("shape", state.shape, "files", len(list((out / "perturbations").iterdir())))
