#!/usr/bin/env python3
"""T2-0 SA/SST wall-function dictionaries and multi-body case generation.

Generation only. No solver, Docker or Kaggle command runs from this module.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import t20_case as T
import t20_foam as B
try:
    from . import t2d_multibody_case as M
except ImportError:  # direct CLI
    import t2d_multibody_case as M

MODELS = ('sa-wf', 'sst-wf')
# Source: T2-0b runner constants and force_summary; inherited by T2-0c §5.
CONVERGENCE = {'initial_iterations': 5000, 'continuation_iterations': 15000, 'max_continuations': 1,
               'tail_fraction': .2, 'tail_min_rows': 50, 'block_iterations': 20,
               'plateau_relative_std_limit': .005, 'plateau_relative_drift_limit': .005,
               'unsteady_raw_tail_relative_std': .005,
               'rule_source': 'infra/kaggle/kernel_t20b_cpu/runner.py:force_summary; docs/t20c_registration_2026_10_20.md §5'}


def _patches(patches):
    if patches not in [['airfoil'] + [f'airfoil_{i}' for i in range(2, n + 1)] for n in range(1, 4)]:
        raise ValueError('patches must be ordered airfoil, airfoil_2, airfoil_3 (1–3 bodies)')


def _extra_walls(text: str, patches: list[str]) -> str:
    """Reuse each generated field's airfoil BC verbatim on the additional walls."""
    pattern = r'(^    airfoil\n    \{\n.*?^    \})'
    match = re.search(pattern, text, re.M | re.S)
    if not match:
        raise ValueError('generated field has no airfoil wall block')
    extra = ''.join('\n' + match.group(1).replace('    airfoil\n', f'    {patch}\n', 1) for patch in patches[1:])
    return text[:match.end()] + extra + text[match.end():]


def _force_objects(text: str, patches: list[str]) -> str:
    """Clone T2-0 objects: coefficients and dimensional pressure/viscous split."""
    total_patches = 'patches (' + ' '.join(patches) + ');'
    for name in ('forceCoeffs', 'forces'):
        pattern = rf'(^    {name}\n    \{{\n.*?^    \}})'
        match = re.search(pattern, text, re.M | re.S)
        if not match:
            raise ValueError(f'generated controlDict has no {name} block')
        original = match.group(1)
        total = original.replace('patches (airfoil);', total_patches)
        extra = ''.join('\n' + original.replace(f'    {name}\n', f'    {name}_{patch}\n', 1)
                        .replace('patches (airfoil);', f'patches ({patch});') for patch in patches)
        text = text[:match.start()] + total + extra + text[match.end():]
    return text


def case_files(model: str, family: str, patches: list[str], iters=5000) -> dict[str, str]:
    """Return dictionaries, with optional <=200-iteration development smoke cap."""
    if model not in MODELS or family not in M.FAMILIES:
        raise ValueError(f'model/family must be {MODELS}/{M.FAMILIES}')
    if type(iters) is not int or not (1 <= iters <= 200 or iters == 5000):
        raise ValueError('iterations must be 5000 for production or 1–200 for a development smoke')
    _patches(patches)
    mdl, mesh = T.MODELS[model], T.MESHES[family]
    p = dict(u=T.U_INF, nu=T.NU, chord=T.CHORD, z=T.Z, iters=iters)
    files = {'0/' + key: _extra_walls(value, patches) for key, value in B.fields(mdl, T.U_INF, T.NU, T.TU, T.L_INT).items()}
    files.update(B.system_and_constant(mdl, mesh, p))
    files['system/controlDict'] = _force_objects(files['system/controlDict'], patches)
    cont = B.system_and_constant(mdl, mesh, {**p, 'iters': 15000, 'start': 'latestTime'})
    files['continuation/system/controlDict'] = _force_objects(cont['system/controlDict'], patches)
    return files


def fix_boundary(text: str, patches: list[str]) -> str:
    """Apply T2-0 front/back/ground fix and require each extra element wall."""
    _patches(patches)
    text = B.fix_boundary(text)
    for patch in patches[1:]:
        text, n = re.subn(rf'(\b{re.escape(patch)}\s*\{{[^{{}}]*?)type\s+\w+\s*;', r'\g<1>type wall;', text, count=1)
        if n != 1:
            raise ValueError(f'patch {patch!r} not found in boundary file')
    return text


def write_case(out: Path, geometry: Path | str | dict, model='sa-wf', family='fine30', realisation=0, iters=5000) -> dict:
    """Write mesh/dictionaries and manifest. Each call is one fresh realisation."""
    if type(realisation) is not int or not 0 <= realisation < 8:
        raise ValueError('realisation must be an integer in [0,7]')
    geom = M.load_geometry(geometry)
    patches = [e['patch'] for e in geom['elements']]
    files = case_files(model, family, patches, iters)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f'refusing to overwrite nonempty case {out}')
    out.mkdir(parents=True, exist_ok=True)
    stats = M.build_mesh(geom, family, out / 'mesh.msh')
    for rel, text in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    elements = [{k: v for k, v in e.items() if k != 'points_m'} for e in geom['elements']]
    man = {'config': geom['config'], 'element_count': len(elements), 'elements': elements,
           'model': model, 'foam_model': T.MODELS[model]['foam'], 'family': family, 'mesh': family,
           'mesh_spec': T.MESHES[family], 'realisation': realisation,
           'iterations': iters, 'convergence': CONVERGENCE,
           'h_m': geom['ride_height_m'], 'h_over_c': geom['ride_height_m'] / T.CHORD,
           'h_m_datum': 'minimum current contour clearance; not a published zero-incidence datum',
           'minimum_clearance_m': geom['minimum_clearance_m'], 'main_element_clearance_m': geom['main_element_clearance_m'],
           'nominal_ride_height_m': geom['nominal_ride_height_m'], 'nominal_height_datum': geom['height_datum'],
           'chord_m': T.CHORD, 'reference_chord_m': T.CHORD, 'z_m': T.Z, 'Aref_m2': T.CHORD * T.Z,
           'U_inf': T.U_INF, 'Re_c': T.RE_C, 'nu': T.NU, 'Tu': T.TU, 'L_int_m': T.L_INT,
           'transition_model': 'none', 'trip': False,
           'transition_scope': 'Fully turbulent SA/SST wall functions; no trip is imposed. Natural/free transition is not modelled.',
           'domain_chords': {'up': T.UP, 'down': T.DOWN, 'top': T.TOP},
           'size_far_m': T.SIZE_FAR, 'size_growth': T.GROW,
           'inlet': {'k': 1.5 * (T.TU * T.U_INF) ** 2,
                     'omega': math.sqrt(1.5 * (T.TU * T.U_INF) ** 2) / (.09 ** .25 * T.L_INT), 'nuTilda': 5 * T.NU},
           'force_convention': 'Cl = downforce coefficient (liftDir -y); Cd = drag (+x); all totals/elements normalized by common c1 and Aref=c1*z',
           'force_objects': {'total': 'forceCoeffs', 'elements': {e['name']: 'forceCoeffs_' + e['patch'] for e in elements},
                             'total_dimensional': 'forces',
                             'pressure_vectors': {e['name']: 'forces_' + e['patch'] for e in elements}},
           'mesh_stats': stats, 'mesh_quality_failures': T.quality_failures(stats['quality'], stats['gmsh_min_sicn_tri']),
           'gmsh_version': __import__('gmsh').__version__, 'python': platform.python_version(),
           'geometry_file': geom['geometry_file'], 'geometry_sha256': geom['geometry_sha256'],
           'coords_file': geom['geometry_file'], 'coords_sha256': geom['geometry_sha256'],
           'generator_sha256': {p.name: T.sha256(p) for p in (Path(T.__file__), Path(B.__file__), Path(M.__file__), Path(__file__))},
           'mesh_msh_sha256': T.sha256(out / 'mesh.msh'),
           'te_kind_scope': 'Trusted explicit input metadata; not an automatic cusp or physical-geometry qualification.',
           'geometry_realisation': 'Exact closed input polygon, one gmsh line per segment; no interpolating-curve geometry change.',
           'evidence_class': 'DEVELOPMENT_GENERATED_CASE',
           'realisation_note': 'Fresh gmsh generation; index is a bookkeeping identity, not a seed or guarantee of a distinct mesh.'}
    if 'source_scene_metadata' in geom:
        man['source_scene_metadata'] = geom['source_scene_metadata']
    (out / 'case_manifest.json').write_text(json.dumps(man, indent=1, sort_keys=True, allow_nan=False) + '\n')
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--geometry', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--model', choices=MODELS, default='sa-wf')
    ap.add_argument('--family', choices=M.FAMILIES, default='fine30')
    ap.add_argument('--realisation', type=int, default=0)
    ap.add_argument('--iters', type=int, default=5000)
    args = ap.parse_args(argv)
    man = write_case(args.out, args.geometry, args.model, args.family, args.realisation, args.iters)
    print(json.dumps({'out': str(args.out), 'config': man['config'], 'mesh_msh_sha256': man['mesh_msh_sha256'],
                      'cells': man['mesh_stats']['cells_3d'], 'proxy_failures': man['mesh_quality_failures']}))


if __name__ == '__main__':
    main()
