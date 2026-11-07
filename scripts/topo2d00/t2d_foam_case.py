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
    from .collect_rans import CONVERGENCE
except ImportError:  # direct CLI
    import t2d_multibody_case as M
    from collect_rans import CONVERGENCE

MODELS = ('sa-wf', 'sst-wf')
# TOPO-2D-00 §2: published double-element combined chord (all arms report h/c).
COMBINED_CHORD_M = .380


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
    # The runner uses the unchanged T2-0b _continue, which changes only endTime
    # and startFrom; retain the inherited initial writeInterval in this preview.
    files['continuation/system/controlDict'] = re.sub(r'^endTime .*;$', 'endTime 15000;',
        re.sub(r'^startFrom .*;$', 'startFrom latestTime;', files['system/controlDict'], flags=re.M), flags=re.M)
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


def write_case(out: Path, geometry: Path | str | dict, model='sa-wf', family='fine30', realisation=0, iters=5000,
               boundary_layer_plan=None, *, expected_height_m=None) -> dict:
    """Write a case bound to the indexed mesh input and declared physical h."""
    if type(realisation) is not int or not 0 <= realisation < 8:
        raise ValueError('realisation must be an integer in [0,7]')
    geom = M.load_geometry(geometry, family, expected_height_m=expected_height_m)
    if boundary_layer_plan is None:
        if iters == 5000:
            raise ValueError('production requires a study-wide boundary-layer plan from all six configurations')
        boundary_layer_plan = M.boundary_layer_plan({geom['config']: geometry}, require_complete=False)
    elif not isinstance(boundary_layer_plan, dict):
        boundary_layer_plan = json.loads(Path(boundary_layer_plan).read_text())
    if iters == 5000 and (boundary_layer_plan.get('scope') != 'study' or
                         set(boundary_layer_plan.get('geometry_sha256', {})) != M.STUDY_CONFIGS):
        raise ValueError('production boundary-layer plan must bind all six study configurations')
    if iters == 5000 and expected_height_m is None:
        raise ValueError('production requires the declared expected_height_m for this configuration')
    fixed_layers = M.boundary_layer_settings(boundary_layer_plan, geom, family)
    patches = [e['patch'] for e in geom['elements']]
    files = case_files(model, family, patches, iters)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f'refusing to overwrite nonempty case {out}')
    out.mkdir(parents=True, exist_ok=True)
    stats = M.build_mesh(geom, family, out / 'mesh.msh', boundary_layers=boundary_layer_plan, realisation=realisation)
    for rel, text in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    elements = [{k: v for k, v in e.items() if k != 'points_m'} for e in geom['elements']]
    man = {'config': geom['config'], 'element_count': len(elements), 'elements': elements,
           'model': model, 'foam_model': T.MODELS[model]['foam'], 'family': family, 'mesh': family,
           'mesh_spec': T.MESHES[family], 'realisation': realisation,
           'iterations': iters, 'convergence': CONVERGENCE,
           'height_m': geom['height_m'], 'expected_height_m': expected_height_m,
           'h_m': geom['height_m'], 'h_over_c1': geom['height_m'] / T.CHORD,
           'h_over_c': geom['height_m'] / COMBINED_CHORD_M,
           'h_m_datum': geom['physical_height_datum'],
           'minimum_clearance_m': geom['minimum_clearance_m'], 'main_element_clearance_m': geom['main_element_clearance_m'],
           'nominal_ride_height_m': geom['nominal_ride_height_m'], 'nominal_height_datum': geom['height_datum'],
           'nominal_h_over_c1': None if geom['nominal_ride_height_m'] is None else geom['nominal_ride_height_m'] / T.CHORD,
           'nominal_h_over_c': None if geom['nominal_ride_height_m'] is None else geom['nominal_ride_height_m'] / COMBINED_CHORD_M,
           'combined_chord_m': COMBINED_CHORD_M,
           'n_layers': fixed_layers['n_layers'], 'boundary_layer_plan': boundary_layer_plan,
           'boundary_layer_plan_sha256': M.plan_sha256(boundary_layer_plan),
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
           'geometry_realisation': 'Exact closed input polygon with indexed start-vertex rotation, one gmsh line per segment; no body movement or resampling.',
           'mesh_realisation': stats['mesh_realisation'],
           'evidence_class': 'DEVELOPMENT_GENERATED_CASE',
           'realisation_note': 'TOPO-2D-00 Amendment 3 §2: index fixes polygon ordering and Halton(2,3) far-field shifts; mesh-realisation intervals use these eight inputs. One mesh per fresh generator process; verify same-index determinism on each backend and eight distinct SHAs. The local synthetic test and Kaggle determinism record are separate.'}
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
    ap.add_argument('--boundary-layer-plan', type=Path)
    ap.add_argument('--expected-height-m', type=float, help='declared study height for this configuration; required for production')
    args = ap.parse_args(argv)
    man = write_case(args.out, args.geometry, args.model, args.family, args.realisation, args.iters, args.boundary_layer_plan,
                     expected_height_m=args.expected_height_m)
    print(json.dumps({'out': str(args.out), 'config': man['config'], 'mesh_msh_sha256': man['mesh_msh_sha256'],
                      'cells': man['mesh_stats']['cells_3d'], 'proxy_failures': man['mesh_quality_failures']}))


if __name__ == '__main__':
    main()
