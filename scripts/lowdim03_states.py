"""Fixed LOWDIM-03 inventory; numpy-only state plan shared with the runner."""
import step01_states as S

BASIS = S.SINGLE_DIRECTIONS
STEPS_MM = (0.625, 1.25, 2.5)
BASELINE_NAME = 'lowdim03__baseline'
ANALYSIS_SHA256 = 'ec00ed9afe4f44926dd40ff1e87f303dd9baf89195b19cb550103606beedb69c'
PROPOSAL_SHA256 = 'c0f69676929c3eb17b1b623c599bfd97ea286d09810c63848e0d7499437e0bf5'


def candidate_name(step_mm):
    return f'lowdim03__prop__s{step_mm:g}mm'


def control_name(step_mm):
    return f'lowdim03__ctrl_reverse__s{step_mm:g}mm'


def plan():
    return ([{'name': BASELINE_NAME, 'kind': 'baseline', 'step_mm': 0.0, 'sign': 0}]
            + [{'name': candidate_name(s), 'kind': 'candidate', 'step_mm': s, 'sign': 1} for s in STEPS_MM]
            + [{'name': control_name(s), 'kind': 'control', 'step_mm': s, 'sign': -1} for s in STEPS_MM])
