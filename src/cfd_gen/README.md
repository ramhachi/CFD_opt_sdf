`src/cfd_sdf` and `julia/CFDSDFWaterLily/src` are enumerated by historical source freezes.
Place new GEN-01 code in `src/cfd_gen/` and `julia/CFDSDFWaterLily/gen01/`.
Reuse existing `cfd_sdf` modules by import without changing their frozen source.
