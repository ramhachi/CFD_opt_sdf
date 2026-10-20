"""GRIDRES-01 state plan: numpy-free constants shared by the builder, the Kaggle runner and the analyzer (the runner imports it from the pinned source).

The five states are the OPT-01 Stage B states that exist on every grid: the OPT-01 v1 parent, +0.3125/+0.625/+1.25 mm and the -1.25 mm reverse diagnostic along the
Stage A robust direction (byte-identical phi, hash-checked against the frozen OPT-01 Stage B inventory), so the state names are the Stage B names.
"""
PARENT_NAME = "opt01b__parent"
DIRECTION = "robust_opt01a"
STEPS_MM = (0.3125, 0.625, 1.25, -1.25)   # signed; the parent (0 mm) adds a zero row to a no-intercept fit and is not listed
OPT01B_REL = "docs/evidence/opt01b_stage_b_2026_10_15"
OPT01B_INVENTORY_SHA = "e571e729f3152d4f71ada1db6c815a66488f3f229e4f5d239349d367ca30bac7"
OPT01B_ANALYSIS_SHA = "63413dc228980e4cf29c31e6e820ed194aa08697f35a13445b4998dc0a1c01bd"
# Plan Amendment 1 G2 + Amendment 2 H2.  The flow_40 kernel runs the instrumented OPT-01 parent on the retained grids first (PARENT_RERUNS, 1800 s each), then the five flow_40 states:
# aggregate cap 10800 s over the 7 runs (expected about 1.5 h in all; the 1800 s per-state timeout still binds each run).  cells x 0.8 m reference length gives the spacing; the base box is 5 m x 2.4 m x 1.8 m.  flow_48 keeps its un-frozen parameterization and needs
# two kernels (Kaggle GPU session limit) before any flow_48 freeze; it has no parent reruns here.
RERUN_DIMS = {"flow_24": (150, 72, 54), "flow_32": (200, 96, 72)}
RERUN_CELLS = {"flow_24": 24, "flow_32": 32}
RETAINED_KERNEL = {"flow_24": "a", "flow_32": "b"}   # OPT-01 Stage B kernel letters of the retained grids
GRIDS = {"flow_40": {"cells": 40, "dims": (250, 120, 90), "kernel_suffix": "f40", "per_state_timeout_s": 1800, "solver_wall_time_cap_s": 10800, "kernel_timeout_s": 21600, "parent_reruns": ("flow_24", "flow_32")},
         "flow_48": {"cells": 48, "dims": (300, 144, 108), "kernel_suffix": "f48", "per_state_timeout_s": 3600, "solver_wall_time_cap_s": 18000, "kernel_timeout_s": 43000, "parent_reruns": ()}}
# Amendment 2 H1/H3 descriptive Poisson label: WaterLily 1.8.0 solves the pressure with at most POISSON_ITERATION_CAP iterations per solve; a grid "saturates" when a larger fraction of its solves
# used all of them.  POISSON_CONFOUNDED iff, for flow_24 or flow_40, the cap-hit fraction minus flow_32's exceeds POISSON_MATERIAL_ABS (absolute; flow_40 = the largest of its five states).
POISSON_ITERATION_CAP = 32
POISSON_MATERIAL_ABS = 0.10


def state_name(step_mm):
    return PARENT_NAME if step_mm == 0 else f"opt01b__prop__s{step_mm:g}mm" if step_mm > 0 else f"opt01b__ctrl_reverse__s{-step_mm:g}mm"


NAMES = tuple([PARENT_NAME] + [state_name(s) for s in STEPS_MM])


def plan():
    return [{"name": PARENT_NAME, "kind": "parent", "direction": None, "step_mm": 0.0, "sign": 0}] + [
        {"name": state_name(s), "kind": "candidate" if s > 0 else "control", "direction": DIRECTION, "step_mm": abs(s), "sign": 1 if s > 0 else -1} for s in STEPS_MM]
