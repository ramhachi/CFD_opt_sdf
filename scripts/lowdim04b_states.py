"""Fixed LOWDIM-04 Stage B (#51) inventory; numpy-only state plan shared with the Kaggle runner.

Per grid: the accepted LOWDIM-03 parent first, then the positive ladder along the Stage A robust solution and its reverse diagnostics.
"""
import step01_states as S

BASIS = S.SINGLE_DIRECTIONS
STEPS_MM = (0.3125, 0.625, 0.9375, 1.25)   # 0.25, 0.5, 0.75 and 1.0 of the Stage A normalized step (max |delta phi| = step)
CONTROL_STEPS_MM = (0.625, 1.25)           # reverse diagnostics: never accepted, never selected
PARENT_NAME = 'lowdim04b__parent'
DIRECTION = 'robust_stage_a'


def candidate_name(step_mm):
    return f'lowdim04b__prop__s{step_mm:g}mm'


def control_name(step_mm):
    return f'lowdim04b__ctrl_reverse__s{step_mm:g}mm'


def plan():
    return ([{'name': PARENT_NAME, 'kind': 'parent', 'direction': None, 'step_mm': 0.0, 'sign': 0}]
            + [{'name': candidate_name(s), 'kind': 'candidate', 'direction': DIRECTION, 'step_mm': s, 'sign': 1} for s in STEPS_MM]
            + [{'name': control_name(s), 'kind': 'control', 'direction': DIRECTION, 'step_mm': s, 'sign': -1} for s in CONTROL_STEPS_MM])
