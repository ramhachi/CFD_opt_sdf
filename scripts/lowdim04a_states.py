"""Fixed LOWDIM-04A Stage A (#51) inventory; numpy-only state plan shared with the Kaggle runner.

Per grid: the accepted LOWDIM-03 parent first, then the eight centered perturbations D0/D1/D2/P1 x -/+ 1.25 mm of that parent.
"""
import step01_states as S

BASIS = S.SINGLE_DIRECTIONS
STEP_MM = 1.25
PARENT_NAME = 'lowdim04a__parent'


def state_name(direction, sign):
    return f"lowdim04a__{direction}__{'plus' if sign > 0 else 'minus'}{STEP_MM:g}mm"


def plan():
    rows = [{'name': PARENT_NAME, 'kind': 'parent', 'direction': None, 'step_mm': 0.0, 'sign': 0}]
    for d in BASIS:
        for sign in (-1, 1):
            rows.append({'name': state_name(d, sign), 'kind': 'perturbation', 'direction': d, 'step_mm': STEP_MM, 'sign': sign})
    return rows
