#!/usr/bin/env python3
"""Independent saved-array verification; never imports campaign code or queries geometry."""
from pathlib import Path
import hashlib
import itertools
import json
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[4]
E = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design import volume_semantics as V
KEYS = ('unsigned_float64', 'sign_int8', 'phi_float64', 'phi_float32')

def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def ah(a): return hashlib.sha256(a.astype(a.dtype.newbyteorder('<'), copy=False).tobytes(order='C')).hexdigest()
def exact(a, b): return a.shape == b.shape and a.dtype == b.dtype and a.tobytes(order='C') == b.tobytes(order='C')
def require(ok, message):
    if not ok: raise ValueError(message)

def counts(a, b):
    bits = a.view(f'u{a.dtype.itemsize}') != b.view(f'u{b.dtype.itemsize}')
    signs = np.signbit(a) != np.signbit(b)
    zeros = (a == 0) & (b == 0) & bits
    return {'different_bits_count': int(bits.sum()), 'different_sign_count': int(signs.sum()),
            'nonzero_sign_difference_count': int((signs & ~zeros).sum()),
            'signed_zero_only_count': int(zeros.sum())}

def verify():
    freeze = read(E / 'prerun_freeze.json')
    terminal = read(E / 'classification.json')
    require(terminal.get('complete') is True, 'campaign incomplete; no verification of partial result')
    require(len(freeze['jobs']) == len({j['id'] for j in freeze['jobs']}) == 32, 'expected preregistered 32 jobs')
    require(set(terminal['completed_job_ids']) == {j['id'] for j in freeze['jobs']}, 'completed job identities')
    frozen = []
    for f in freeze['files']:
        require(sha(ROOT / f['path']) == f['sha256'], 'frozen file changed: ' + f['path'])
        frozen.append(f['path'])
    old = ROOT / 'docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs'
    refs = {g: SDFDesignState.load(old / name) for g, name in
            [('v16', 'v16_reference.npz'), ('v17', 'v17_baseline.npz')]}
    coordinates = {}
    for grid, ref in refs.items():
        axes = [ref.origin_m[k] + ref.spacing_m * np.arange(ref.shape[k]) for k in range(3)]
        coordinates[grid] = np.stack(np.meshgrid(*axes, indexing='ij'), axis=-1).reshape(-1, 3)
        require(ah(coordinates[grid]) == freeze['point_coordinate_hashes'][grid], 'coordinate authority')
    arrays, rows, hashed, volumes, old_counts = {}, {}, 0, [], []
    for job in freeze['jobs']:
        name = job['id']; row = read(E / 'diagnostics' / (name + '.json'))
        path = E / 'diagnostics' / (name + '.npz')
        require(sha(path) == row['npz_sha256'], name + ': NPZ hash')
        with np.load(path, allow_pickle=False) as z: a = {k: z[k] for k in z.files}
        require(set(a) == set(row['arrays']), name + ': saved array keys')
        for key, x in a.items():
            r = row['arrays'][key]
            require(ah(x) == r['sha256'] and list(x.shape) == r['shape'] and x.dtype.str == r['dtype'], name + ': ' + key)
            require(np.isfinite(x).all(), name + ': finite ' + key); hashed += 1
        for key, source in [('grid','grid'), ('candidate','candidate'), ('chunk_size','chunk'), ('ordering','order')]:
            require(row[key] == job[source], name + ': fixed job contract ' + key)
        require(row['point_coordinates_c_little_sha256'] == ah(coordinates[job['grid']]), name + ': coordinates')
        n = len(coordinates[job['grid']]); perm = np.arange(n)
        if job['order'] == 'reverse': perm = perm[::-1]
        elif job['order'] == 'permuted': perm = np.random.default_rng(20261013).permutation(n)
        require(ah(perm.astype('i8')) == row['permutation_c_little_sha256'], name + ': permutation')
        u, raw = a['unsigned_float64'], a['raw_signer_float64']
        require(u.dtype == np.dtype('f8') and u.shape == refs[job['grid']].shape, name + ': unsigned schema')
        require(not (u < 0).any() and not np.signbit(u[u == 0]).any(), name + ': unsigned positive zero')
        require(not ((raw == 0) & (u > 0)).any(), name + ': unresolved signer zero')
        sign = np.sign(raw).astype('i1'); sign[u == 0] = 0
        phi = sign.astype('f8') * u; phi[u == 0] = 0.0
        require(exact(sign, a['sign_int8']) and exact(phi, a['phi_float64']), name + ': sign composition')
        cast = phi.astype('f4'); cast[cast == 0] = 0.0
        require(exact(cast, a['phi_float32']), name + ': Float32 cast and declared zero normalization')
        require(not np.signbit(a['phi_float32'][a['phi_float32'] == 0]).any(), name + ': Float32 positive zero')
        require(row['exact_zero_count'] == int((u == 0).sum()) and row['zero_semantics_pass'], name + ': zero report')
        r = refs[job['grid']]
        state = SDFDesignState.create(phi=a['phi_float32'], origin_m=r.origin_m, spacing_m=r.spacing_m,
            design_mask=r.design_mask, fixed_solid_mask=r.fixed_solid_mask, forbidden_mask=r.forbidden_mask,
            root_mask=r.root_mask, narrow_band_width_m=r.narrow_band_width_m, generation=r.generation,
            source_sha256=r.source_sha256, topology_policy_id=r.topology_policy_id,
            reinitialization_policy_id=r.reinitialization_policy_id)
        require(state.state_sha256 == row['state_sha256'], name + ': state hash')
        smooth = V.smoothed_volume_and_gradient(state)
        volume = {'hard_volume_m3': V.sharp_volume_m3(state), 'solid_center_count': V.sampled_solid_centers_count(state),
            'exact_zero_centers_fluid': int((V._corner_mean(state.phi) == 0).sum()),
            'smooth_volume_m3': smooth.smoothed_volume_m3, 'smooth_gV': smooth.constraint_residual}
        require(all(row['volume'][k] == v for k, v in volume.items()), name + ': volume')
        diff = counts(a['phi_float32'], r.phi)
        require(all(row['comparison_float32_registered'][k] == v for k, v in diff.items()), name + ': registered difference')
        old_counts.append({'id': name, **diff}); volumes.append({'id': name, **volume})
        arrays[name], rows[name] = a, row
    def compare(j, k):
        a, b = arrays[j['id']], arrays[k['id']]
        result = {x: exact(a[x], b[x]) for x in KEYS}
        result['state'] = rows[j['id']]['state_sha256'] == rows[k['id']]['state_sha256']
        return {'a': j['id'], 'b': k['id'], 'arrays_exact': result, 'exact': all(result.values())}
    results = {'repeat': [], 'chunk_order': [], 'environment': []}; bases = {}; stable = {}
    for c in ('A','B'):
        jobs = [j for j in freeze['jobs'] if j['candidate'] == c and j['stage'] == 'B']
        require(len(jobs) == 5, 'five independent repeats'); bases[c] = jobs[0]
        repeat = [compare(a,b) for a,b in itertools.combinations(jobs,2)]
        perturb = [compare(jobs[0],j) for j in freeze['jobs'] if j['candidate'] == c and j['stage'] == 'C']
        env = [compare(jobs[0],j) for j in freeze['jobs'] if j['candidate'] == c and j['stage'] == 'D']
        require(len(perturb) == 9 and len(env) == 1, 'fixed perturbation/environment matrix')
        for key, value in [('repeat',repeat),('chunk_order',perturb),('environment',env)]: results[key].extend(value)
        stable[c] = all(p['exact'] for p in repeat + perturb)
    agreement = {}; material_count = 0; zero_ok = True
    for grid in ('v17','v16'):
        selected = bases if grid == 'v17' else {c: next(j for j in freeze['jobs'] if j['stage']=='G' and j['candidate']==c) for c in ('A','B')}
        a, b = (arrays[selected[c]['id']] for c in ('A','B'))
        unequal = a['sign_int8'] != b['sign_int8']; nonzero = (a['unsigned_float64'] > 0) & (b['unsigned_float64'] > 0)
        material = int((unequal & nonzero).sum()); zero = int((unequal & ~nonzero).sum())
        agreement[grid] = {'different_sign_count': int(unequal.sum()), 'nonzero': material, 'zero': zero}
        material_count += material; zero_ok &= zero == 0
    for label, filename, field in [('repeat','repeatability.json','pairwise'),
            ('chunk_order','chunk_order.json','comparisons_to_first_repeat'), ('environment','cross_environment.json','comparisons')]:
        summary = read(E / filename)['candidates']
        for c in ('A','B'):
            declared = summary[c][field]
            lookup = {(p['a'],p['b']):p for p in results[label]}
            require(len(declared) == (10 if label == 'repeat' else 9 if label == 'chunk_order' else 1), 'summary comparison count')
            require(all(p['exact'] == lookup[(p['a'],p['b'])]['exact'] for p in declared), 'summary pair verdict')
            require(summary[c]['pass'] == all(p['exact'] for p in declared), 'summary candidate verdict')
    authority = read(E / 'authority_saved_nodes.json'); known = []
    for node in authority['nodes']:
        ijk = tuple(node['ijk'])
        known.append({'ijk': node['ijk'], **{c: int(arrays[bases[c]['id']]['sign_int8'][ijk]) for c in ('A','B')}})
    reported = read(E / 'problem_nodes.json')['nodes']
    require(len(known) == len(reported) == 19, 'known node population')
    for node, r in zip(known, reported):
        require(node['ijk'] == r['ijk'] and all(node[c] == r['candidates'][c]['sign'] for c in ('A','B')), 'known node report')
    fixture = read(E / 'analytic_fixtures.json'); analytic = True
    for f in fixture['fixtures']:
        for c in ('A','B'):
            r = f['candidates'][c]; u = np.asarray(r['unsigned']); raw = np.asarray(r['raw_signer'])
            s = np.sign(raw).astype('i1'); s[u == 0] = 0
            analytic &= not ((raw == 0) & (u > 0)).any() and s.tolist() == f['expected_signs']
            analytic &= not np.signbit(np.asarray(r['combined'])[u == 0]).any()
    cross = all(p['exact'] for p in results['environment'])
    if not analytic or not zero_ok: expected = 'SRCMAP02_INCONCLUSIVE'
    elif not stable['A']: expected = 'PSEUDONORMAL_NOT_DETERMINISTIC'
    elif not stable['B']: expected = 'WINDING_CONTROL_NOT_STABLE'
    elif material_count: expected = 'DETERMINISTIC_SIGNER_DISAGREEMENT'
    elif not cross: expected = 'SRCMAP02_INCONCLUSIVE'
    else: expected = 'DETERMINISTIC_SIGNER_QUALIFIED'
    require(terminal['terminal_classification'] == expected, 'independent terminal classification')
    return {'pass': True, 'scope': 'saved arrays only; no primary script imports, geometry queries or reruns',
        'checker_sha256': sha(Path(__file__)), 'freeze_sha256': sha(E/'prerun_freeze.json'), 'jobs_checked': len(arrays),
        'array_hashes_checked': hashed, 'npz_hashes_checked': len(arrays), 'frozen_files_checked': len(frozen),
        'comparisons': results, 'candidate_agreement': agreement, 'known_19_node_signs': known,
        'registered_float32_differences': old_counts, 'volumes': volumes, 'analytic_saved_labels_pass': bool(analytic),
        'expected_terminal_classification': expected, 'cross_environment_exact': cross}

if __name__ == '__main__':
    output = E / 'independent_numeric_check.json'
    require(not output.exists(), 'refusing overwrite')
    result = verify()
    with output.open('x') as stream: json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False); stream.write('\n')
    print(json.dumps({k: result[k] for k in ('pass','jobs_checked','array_hashes_checked','expected_terminal_classification')}))
