#!/usr/bin/env python3
"""Frozen, solver-free SRCMAP-01 diagnosis; no production or retained-field writes."""
from __future__ import annotations
import argparse
from contextlib import ExitStack, redirect_stdout
import hashlib
import importlib
import importlib.metadata
import io
import json
import locale
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from unittest.mock import patch
import numpy as np
import trimesh
import rtree
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from cfd_sdf import sdf
from cfd_sdf.design.sdf_state import SDFDesignState
SURFACE_SHA = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
E = ROOT / 'docs/evidence/srcmap01_v17_reproducibility_2026_10_12'
OLD = ROOT / 'docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11'
SEED = 20261012
THREADS = ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')

def array_sha(a, order='C', endian='<'):
    a = np.asarray(a)
    dtype = a.dtype.newbyteorder(endian)
    return hashlib.sha256(a.astype(dtype, copy=False).tobytes(order=order)).hexdigest()

def strict(a, b):
    a,b=np.asarray(a),np.asarray(b)
    if a.shape != b.shape or a.dtype.kind != 'f' or a.dtype.itemsize != b.dtype.itemsize:
        raise ValueError('strict comparison requires same-shaped, same-width floating arrays')
    width=a.dtype.itemsize
    ua=a.astype(f'<f{width}',copy=False).view(f'<u{width}')
    ub=b.astype(f'<f{width}',copy=False).view(f'<u{width}')
    bits=ua!=ub
    delta=a.astype(np.float64)-b.astype(np.float64)
    sign=np.signbit(a)!=np.signbit(b)
    zeros=(a==0)&(b==0)&bits
    return {'array_equal':bool(np.array_equal(a,b)), 'bit_equal':bool(np.array_equal(ua,ub)),
            'different_bits_count':int(bits.sum()),'different_values_count':int(np.count_nonzero(a!=b)),
            'different_sign_count':int(sign.sum()),'nonzero_sign_difference_count':int((sign&~zeros).sum()),
            'signed_zero_only_count':int(zeros.sum()),'max_absolute_difference_m':float(np.max(np.abs(delta),initial=0)),
            'abs_difference_counts':{str(t):int(np.count_nonzero(np.abs(delta)>t)) for t in (0,1e-10,1e-9,1e-8)}}

def field_record(a, reference):
    near=np.abs(reference.astype(np.float64))<=1e-7
    return {'dtype':a.dtype.str,'shape':list(a.shape),
            'hash_semantics':'explicit endian, complete array bytes in stated C/F traversal; masks uint8 C order; near subset reference abs(phi)<=1e-7 in C traversal',
            'bytes_sha256':{f'{endian}_{order}':array_sha(a,order,endian) for endian in ('<','>') for order in ('C','F')},
            'sign_mask_sha256':array_sha(np.signbit(a).astype('u1')),
            'negative_mask_sha256':array_sha((a<0).astype('u1')),
            'exact_zero_mask_sha256':array_sha((a==0).astype('u1')),
            'near_surface_count':int(near.sum()),'near_surface_subset_sha256':array_sha(a[near])}

def points_for(state):
    # Identical operations and order to genesis v17 resample (no linspace).
    axes=[state.origin_m[a]+state.spacing_m*np.arange(state.shape[a]) for a in range(3)]
    return np.stack(np.meshgrid(*axes,indexing='ij'),axis=-1).reshape(-1,3)

def permutation(n, variant):
    if variant=='canonical':return np.arange(n)
    if variant=='reverse':return np.arange(n-1,-1,-1)
    if variant=='permuted':return np.random.default_rng(SEED).permutation(n)
    raise ValueError(variant)

def restore(values, order):
    if len(order)!=len(values) or not np.array_equal(np.sort(order),np.arange(len(order))):
        raise ValueError('not a full permutation')
    out=np.empty_like(values);out[order]=values
    return out

def traced_production(mesh,points,chunk,mode="production"):
    """Call unmodified production function; wrappers only log actual invocations."""
    events=[];active=[]
    known=np.array([-1.,-.8,-.6])+0.025*np.array([[28,24,19],[48,44,23],[56,44,27]])
    def wrapper(name,original):
        def call(*args,**kwargs):
            event={'call':name,'success':False,'event_id':len(events),'parent_event_ids':active.copy()}
            events.append(event)
            try:
                if name=='rtree_batch_intersection':
                    event['bounds_count']=len(args[1]);event['bounds_min_sha256']=array_sha(args[1]);event['bounds_max_sha256']=array_sha(args[2])
                else:
                    query=np.asarray(kwargs['points'] if 'points' in kwargs else args[1])
                    event['point_count']=len(query)
                    event['query_sha256']=array_sha(query)
                    event['known_problem_nodes_in_query']={str(k):np.flatnonzero(np.all(query==q,axis=1)).tolist() for k,q in enumerate(known)}
                    if len(query)<=32:event['query_points']=query.tolist()
                    if name=='ray_util_contains_points':
                        direction=kwargs.get('check_direction',args[2] if len(args)>2 else None)
                        event['check_direction']=None if direction is None else np.asarray(direction).tolist()
            except Exception as exc:
                event['metadata_error']={'class':type(exc).__name__,'message':str(exc)}
            active.append(event['event_id'])
            try:
                value=original(*args,**kwargs);event['success']=True;return value
            except BaseException as exc:
                event.update(exception_class=type(exc).__name__,exception_message=str(exc));raise
            finally:active.pop()
        return call
    scalar={'call':'rtree_scalar_intersection','invocations':0,'successes':0,'exceptions':[]}
    original_scalar=rtree.index.Index.intersection
    def scalar_call(*args,**kwargs):
        scalar['invocations']+=1
        try:
            result=original_scalar(*args,**kwargs);scalar['successes']+=1;return result
        except BaseException as exc:
            scalar['exceptions'].append({'class':type(exc).__name__,'message':str(exc)});raise
    class RandomProxy:
        def __init__(self, generator):self.generator=generator
        def random(self,*args,**kwargs):
            before=self.generator.bit_generator.state
            value=self.generator.random(*args,**kwargs)
            events.append({'call':'random_retry_draw','active_event_ids':active.copy(),'args':list(args),'value':np.asarray(value).tolist(),
                           'state_before':before,'state_after':self.generator.bit_generator.state})
            return value
        def __getattr__(self,key):return getattr(self.generator,key)
    legacy_random=np.random.random
    def legacy_random_call(*args,**kwargs):
        before=hashlib.sha256(repr(np.random.get_state()).encode()).hexdigest()
        value=legacy_random(*args,**kwargs)
        events.append({'call':'legacy_random_retry_draw','active_event_ids':active.copy(),'args':list(args),'value':np.asarray(value).tolist(),'state_before_sha256':before,
                       'state_after_sha256':hashlib.sha256(repr(np.random.get_state()).encode()).hexdigest()})
        return value
    original_random=getattr(trimesh.util,'random_generator',None)
    def generator_call(*args,**kwargs):
        generator=original_random(*args,**kwargs)
        events.append({'call':'random_generator','seed_args':list(args),'seed_kwargs':kwargs})
        return RandomProxy(generator)
    with ExitStack() as stack:
        stack.enter_context(patch.object(rtree.index.Index,'intersection',scalar_call))
        stack.enter_context(patch.object(np.random,'random',legacy_random_call))
        if hasattr(rtree.index.Index,'intersection_v'):
            stack.enter_context(patch.object(rtree.index.Index,'intersection_v',wrapper('rtree_batch_intersection',rtree.index.Index.intersection_v)))
        if original_random is not None:
            stack.enter_context(patch.object(trimesh.util,'random_generator',generator_call))
        for obj,name,label in ((trimesh.proximity,'signed_distance','try_signed_distance'),
                               (trimesh.proximity,'closest_point','closest_point'),
                               (sdf,'_contains_safe','production_contains_safe'),
                               (trimesh.Trimesh,'contains','mesh_contains'),
                               (type(mesh.ray),'contains_points','ray_contains_points'),
                               (trimesh.ray.ray_util,'contains_points','ray_util_contains_points')):
            stack.enter_context(patch.object(obj,name,wrapper(label,getattr(obj,name))))
        if mode=='production':values=sdf.signed_distance(mesh,points,chunk_size=chunk)
        else:
            values=np.empty(len(points),dtype=np.float64)
            for start in range(0,len(points),chunk):
                q=points[start:start+chunk]
                if mode=='direct':values[start:start+chunk]=-trimesh.proximity.signed_distance(mesh,q)
                else:
                    _,distance,_=trimesh.proximity.closest_point(mesh,q)
                    if mode=='fallback':
                        inside=mesh.contains(q);distance=distance.copy();distance[inside]*=-1
                    values[start:start+chunk]=distance
    events.append(scalar)
    return values,events

def inventory():
    modules={}
    for name in ('numpy','scipy','trimesh','rtree','shapely','pyembree','embreex'):
        try:
            m=importlib.import_module(name);p=Path(m.__file__)
            try:version=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:version=getattr(m,'__version__','unknown')
            dist=importlib.metadata.distribution(name)
            record=next((Path(dist.locate_file(f)) for f in dist.files or [] if str(f).endswith('.dist-info/RECORD')),None)
            modules[name]={'version':version,'module_path':str(p),'module_sha256':sha(p),
                           'distribution_record_sha256':sha(record) if record else None}
        except Exception as exc:modules[name]={'available':False,'exception_class':type(exc).__name__,'exception_message':str(exc)}
    import rtree
    try:libversion=rtree.core.rt.SIDX_Version().decode()
    except Exception as exc:libversion={'exception':repr(exc)}
    buf=io.StringIO()
    with redirect_stdout(buf):np.show_config()
    try:cpu=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip()
    except Exception:cpu=platform.processor()
    return {'python':sys.version,'python_executable':sys.executable,'python_executable_sha256':sha(sys.executable),
            'platform':platform.platform(),'os':platform.system(),'kernel':platform.release(),'architecture':platform.machine(),
            'cpu':cpu,'byteorder':sys.byteorder,'locale':locale.setlocale(locale.LC_ALL,None),
            'thread_env':{k:os.environ.get(k) for k in THREADS},'modules':modules,
            'libspatialindex_version':libversion,'libspatialindex_path':str(rtree.core.rt._name),
            'libspatialindex_sha256':sha(rtree.core.rt._name),'numpy_build_blas_lapack_config':buf.getvalue(),
            'compiler':platform.python_compiler(),'installed_distribution_lock':sorted(f'{d.metadata["Name"]}=={d.version}' for d in importlib.metadata.distributions()),'lock_method':'importlib.metadata (current uv-managed venv has no pip module)' ,
            'numpy_legacy_random_state_sha256':hashlib.sha256(repr(np.random.get_state()).encode()).hexdigest(),
            'trimesh_entropy_random_state':getattr(getattr(trimesh.util,'_RANDOM_DEFAULT',None),'bit_generator',None).state if hasattr(trimesh.util,'_RANDOM_DEFAULT') else None,
            'pythonhashseed':os.environ.get('PYTHONHASHSEED'),'pythonpath':os.environ.get('PYTHONPATH'),
            'diagnostic_source_path':str(Path(__file__).resolve()),'diagnostic_source_sha256':sha(__file__),
            'backend_sources':{name:{'path':importlib.import_module(name).__file__,'sha256':sha(importlib.import_module(name).__file__)} for name in ('trimesh.proximity','trimesh.ray.ray_triangle','trimesh.ray.ray_util','trimesh.triangles','trimesh.util','rtree.index')},
            'production_module_path':sdf.__file__,'production_source_sha256':sha(sdf.__file__)}

def mesh_inventory(mesh):
    return {'source_path':str(OLD/'inputs/reference_surface.stl'),'source_sha256':SURFACE_SHA,
            'load_call':'trimesh.load(path, force="mesh")','process_argument':'omitted; trimesh.Trimesh default process=True',
            'force_mesh_semantics':'trimesh load legacy wrapper converts Scene to one mesh using to_mesh; exact installed source hashed',
            'vertices':{'dtype':mesh.vertices.dtype.str,'shape':list(mesh.vertices.shape),'c_little_sha256':array_sha(mesh.vertices)},
            'faces':{'dtype':mesh.faces.dtype.str,'shape':list(mesh.faces.shape),'c_little_sha256':array_sha(mesh.faces)},
            'bounds':mesh.bounds.tolist(),'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
            'connected_components':len(mesh.split(only_watertight=False)),'ray_backend_class':f'{type(mesh.ray).__module__}.{type(mesh.ray).__name__}'}

def load_inputs(grid):
    authority=json.loads((ROOT/f'docs/evidence/sdf_native_genesis_{grid}_2026_09.json').read_text())['state']
    retained=OLD/'inputs'/('v16_reference.npz' if grid=='v16' else 'v17_baseline.npz')
    if sha(retained)!=authority['state_file_sha256']:raise ValueError('retained NPZ identity changed')
    state=SDFDesignState.load(retained)
    if state.state_sha256!=authority['state_sha256'] or state.phi_sha256()!=authority['phi_sha256']:
        raise ValueError('retained state identity changed')
    source=OLD/'inputs/reference_surface.stl'
    if sha(source)!=SURFACE_SHA:raise ValueError('source bytes changed')
    return state,trimesh.load(source,force='mesh')

def worker(output,grid,chunk,order,mode):
    state,mesh=load_inputs(grid);points=points_for(state);indices=permutation(len(points),order)
    pts=points[indices];started=time.time();runtime_before=inventory()
    values,events=traced_production(mesh,pts,chunk,mode)
    values=restore(values,indices).reshape(state.shape)
    final=values.astype(np.float32)
    output=Path(output)
    if output.exists() or output.with_suffix('.npz').exists():raise ValueError('refusing overwrite')
    np.savez_compressed(output.with_suffix('.npz'),phi_float64=values,phi_float32=final)
    write_json(output,{'grid':grid,'chunk_size':chunk,'ordering':order,'mode':mode,'seed':SEED,
                       'runtime_before':runtime_before,'runtime_after':inventory(),'mesh':mesh_inventory(mesh),'point_coordinates_c_little_sha256':array_sha(points),
                       'permutation_c_little_sha256':array_sha(indices.astype('<i8')),'events':events,
                       'fallback_invoked':any(e['call']=='production_contains_safe' for e in events),
                       'phi_float64':field_record(values,state.phi),'phi_float32':field_record(final,state.phi),
                       'comparison_float32_registered':strict(final,state.phi),
                       'unsigned_float32_vs_registered_magnitude':strict(np.abs(final),np.abs(state.phi)),
                       'comparison_float64_to_registered_promoted':strict(values,state.phi.astype(np.float64)),
                       'float64_reference_note':'registered has Float32 only; promoted registered is not historical pre-cast Float64',
                       'elapsed_seconds':time.time()-started,'npz_sha256':sha(output.with_suffix('.npz'))})

def local_nodes():
    state,mesh=load_inputs('v17');points=points_for(state);runtime_before=inventory()
    old=json.loads((OLD/'source_replay_recheck_2026_10_12.json').read_text())
    saved=np.load(OLD/'inputs/v17_source_replay_2026_10_12.npz')['phi']
    records=[]
    for example in old['examples']:
        ijk=tuple(example['ijk']);p=points[np.ravel_multi_index(ijk,state.shape)]
        q=p[None,:];nearest,distance,triangle=trimesh.proximity.closest_point(mesh,q);tid=int(triangle[0]);tri=mesh.triangles[tid]
        independent=trimesh.triangles.closest_point(mesh.triangles,np.broadcast_to(p,(len(mesh.faces),3)))
        all_dist=np.linalg.norm(independent-p,axis=1);minimum=float(all_dist.min())
        # Diagnostic scale only; never a mapping PASS tolerance.
        ties=np.flatnonzero(all_dist<=minimum+1e-14)
        bary=trimesh.triangles.points_to_barycentric(tri[None],nearest)[0]
        edges=[]
        for a,b in ((0,1),(1,2),(2,0)):
            d=tri[b]-tri[a];t=np.clip(np.dot(p-tri[a],d)/np.dot(d,d),0,1)
            edges.append(float(np.linalg.norm(p-(tri[a]+t*d))))
        direct_values,direct_events=traced_production(mesh,q,200000,'direct');raw=float(direct_values[0])
        fallback_values,fallback_events=traced_production(mesh,q,200000,'fallback')
        inside=bool(fallback_values[0]<0) # unsigned distance is nonzero at all three historical nodes
        adjacent=mesh.face_adjacency[np.any(mesh.face_adjacency==tid,axis=1)].tolist()
        normal=mesh.face_normals[tid];projection=p-np.dot(p-nearest[0],normal)*normal
        pbary=trimesh.triangles.points_to_barycentric(tri[None],projection[None])[0]
        records.append({'ijk':list(ijk),'coordinates_m':p.tolist(),'registered_float32':float(state.phi[ijk]),
                        'historical_saved_replay_float32':float(saved[ijk]),'direct_project_float64':raw,
                        'direct_project_float32':float(np.float32(raw)),'difference_float64_vs_registered':raw-float(state.phi[ijk]),
                        'nominal_direct_events':direct_events,'nominal_fallback_events':fallback_events,
                        'registered_signbit':bool(np.signbit(state.phi[ijk])),'direct_signbit':bool(np.signbit(raw)),
                        'nearest_triangle_index':tid,'nearest_point':nearest[0].tolist(),'nearest_distance_m':float(distance[0]),
                        'barycentric_nearest':bary.tolist(),'barycentric_plane_projection':pbary.tolist(),'triangle_vertices':tri.tolist(),
                        'triangle_normal':normal.tolist(),'plane_signed_distance_m':float(np.dot(p-nearest[0],normal)),
                        'edge_distances_m':edges,'vertex_distances_m':np.linalg.norm(tri-p,axis=1).tolist(),
                        'adjacent_triangle_pairs':adjacent,'mesh_contains':inside,'fallback_project_float64':float(distance[0]*(-1 if inside else 1)),
                        'independent_all_triangles_minimum_unsigned_distance_m':minimum,'independent_equal_minimum_triangle_ids':np.flatnonzero(all_dist==minimum).tolist(),
                        'diagnostic_near_tie_1e14_triangle_ids':ties.tolist(),
                        'tie_triangle_details':[{'index':int(t),'distance_m':float(all_dist[t]),'normal':mesh.face_normals[t].tolist(),'vertices':mesh.triangles[t].tolist()} for t in ties],
                        'trimesh_tol_merge_m':float(trimesh.constants.tol.merge)})
    query=points[[np.ravel_multi_index(tuple(e['ijk']),state.shape) for e in old['examples']]]
    causal=[]
    for vector in ([0.137,0.271,0.619],[0.731,0.419,0.173],[0.317,0.823,0.457]):
        draws=[]
        class FixedDraw:
            def random(self,*args,**kwargs):
                if args!=(3,):raise ValueError('unexpected fixed diagnostic draw shape')
                draws.append(vector)
                return np.array(vector,dtype=np.float64)
        target='random_generator' if hasattr(trimesh.util,'random_generator') else None
        with ExitStack() as stack:
            if target:stack.enter_context(patch.object(trimesh.util,target,lambda *args,**kwargs:FixedDraw()))
            else:stack.enter_context(patch.object(np.random,'random',FixedDraw().random))
            direct=-trimesh.proximity.signed_distance(mesh,query)
            contains=mesh.contains(query)
        causal.append({'fixed_retry_vector':vector,'direct_project_float64':direct.tolist(),'contains':contains.tolist(),'actual_retry_draws':draws})
    return {'runtime_before':runtime_before,'runtime_after':inventory(),'mesh':mesh_inventory(mesh),'fixed_ray_retry_direction_diagnostic':causal,'fixed_direction_scope':'only three historical nodes, three predeclared vectors; separate diagnostic, production runs entropy untouched',
            'nodes':records,'independent_geometry_method':'trimesh.triangles.closest_point exhaustively over every triangle; bypasses proximity Rtree candidate pruning',
            'near_tie_threshold_m':1e-14,'threshold_role':'diagnostic only; no strict comparison tolerance'}

def classify(repeat_same,registered_exact,perturb_exact,environment_match=False,historical_path_proven=False,complete=True,local_direction_sensitive=False):
    if not complete:return 'SOURCE_MAPPING_UNRESOLVED'
    if not repeat_same:return 'SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC'
    if historical_path_proven:return 'SOURCE_MAPPING_IMPLEMENTATION_PATH_DIVERGENCE'
    if environment_match:return 'SOURCE_MAPPING_ENVIRONMENT_DEPENDENT'
    if registered_exact and perturb_exact and not local_direction_sensitive:return 'SOURCE_MAPPING_REPRODUCIBLE'
    return 'SOURCE_MAPPING_UNRESOLVED'

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('inventory','worker','nodes'));p.add_argument('--output',required=True)
    p.add_argument('--grid',choices=('v16','v17'),default='v17');p.add_argument('--chunk',type=int,default=200000)
    p.add_argument('--order',choices=('canonical','reverse','permuted'),default='canonical')
    p.add_argument('--mode',choices=('production','direct','fallback','unsigned'),default='production');a=p.parse_args()
    if a.action=='inventory':
        _,mesh=load_inputs('v17');write_json(a.output,{'runtime':inventory(),'mesh':mesh_inventory(mesh)})
    elif a.action=='worker':worker(a.output,a.grid,a.chunk,a.order,a.mode)
    else:write_json(a.output,local_nodes())
if __name__=='__main__':main()
