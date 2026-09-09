"""FP32 Metal execution of the periodic D2Q9 reference step.

This kernel has no walls, forcing, turbulence or shape derivatives. It is a
backend-parity probe, not an aerodynamic optimization solver.
"""
from __future__ import annotations

from functools import lru_cache
import math

from .lbm_reference import DIRECTIONS, WEIGHTS


def require_metal():
    try:
        import mlx.core as mx
    except ImportError as exc:
        raise RuntimeError(
            "Metal backend requires Apple Silicon and the 'metal' package extra."
        ) from exc
    if not mx.metal.is_available():
        raise RuntimeError("MLX is installed but no Metal device is available.")
    return mx


@lru_cache(maxsize=1)
def _step_kernel():
    mx = require_metal()
    return mx.fast.metal_kernel(
        name="cfd_d2q9_periodic",
        input_names=["f", "cx", "cy", "weights", "omega"],
        output_names=["out"],
        source="""
            uint cell = thread_position_in_grid.x;
            int ny = f_shape[1], nx = f_shape[2];
            int cells = nx * ny;
            if (cell >= uint(cells)) return;
            int x = cell % nx, y = cell / nx;
            float rho = 0.0f, jx = 0.0f, jy = 0.0f;
            for (int q = 0; q < 9; ++q) {
                float fq = f[q * cells + cell];
                rho += fq;
                jx += fq * float(cx[q]);
                jy += fq * float(cy[q]);
            }
            float ux = jx / rho, uy = jy / rho;
            float u2 = ux * ux + uy * uy;
            for (int q = 0; q < 9; ++q) {
                float cu = float(cx[q]) * ux + float(cy[q]) * uy;
                float eq = weights[q] * rho *
                    (1.0f + 3.0f * cu + 4.5f * cu * cu - 1.5f * u2);
                float fq = f[q * cells + cell];
                int to_x = (x + cx[q] + nx) % nx;
                int to_y = (y + cy[q] + ny) % ny;
                out[q * cells + to_y * nx + to_x] = fq + omega[0] * (eq - fq);
            }
        """,
    )


class MetalStepper:
    """Keep constants on the GPU; materialize each step to bound graph memory."""

    def __init__(self, viscosity: float):
        """Create a stepper for the fixed reference D2Q9 stencil.

        The kernel is intentionally not a generic lattice backend.  Taking
        directions from the caller would allow a shape-valid but invalid
        stencil (for example a displacement larger than one cell) to produce
        out-of-bounds periodic indices in the Metal kernel.  Reusing the
        reference constants here keeps CPU/Metal parity an explicit contract.
        """
        if isinstance(viscosity, bool):
            raise ValueError("viscosity must be finite and positive")
        try:
            viscosity = float(viscosity)
        except (TypeError, ValueError) as exc:
            raise ValueError("viscosity must be finite and positive") from exc
        if not math.isfinite(viscosity) or not 0.0 < viscosity < 0.5:
            raise ValueError("viscosity must be finite and keep BGK tau below 2")
        mx = require_metal()
        self.mx = mx
        self.kernel = _step_kernel()
        self.constants = [
            mx.array(DIRECTIONS[:, 0], dtype=mx.int32),
            mx.array(DIRECTIONS[:, 1], dtype=mx.int32),
            mx.array(WEIGHTS, dtype=mx.float32),
            mx.array([1.0 / (0.5 + 3.0 * viscosity)], dtype=mx.float32),
        ]
        mx.eval(*self.constants)

    def __call__(self, f):
        mx = self.mx
        if f.ndim != 3 or f.shape[0] != 9 or min(f.shape[1:]) < 1:
            raise ValueError("population shape must be (9, ny, nx)")
        if f.dtype != mx.float32:
            raise ValueError("Metal populations must use float32")
        result = self.kernel(
            inputs=[f, *self.constants],
            grid=(f.shape[1] * f.shape[2], 1, 1),
            threadgroup=(256, 1, 1),
            output_shapes=[f.shape],
            output_dtypes=[mx.float32],
            stream=mx.gpu,
        )[0]
        mx.eval(result)
        return result
