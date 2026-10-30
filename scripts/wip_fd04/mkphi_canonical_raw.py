import numpy as np
from cfd_sdf.design.sdf_state import SDFDesignState
s=SDFDesignState.load('/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v16/sdf_design_state.npz')
open('/private/tmp/claude-501/-Users-sota-projects-FomulaTMU-CFD2026-09/5c0b0b8e-2077-41f6-b6ff-a1db96c87326/scratchpad/canon_phi_f.raw','wb').write(np.asarray(s.phi,dtype='<f4',order='F').tobytes(order='F'))
