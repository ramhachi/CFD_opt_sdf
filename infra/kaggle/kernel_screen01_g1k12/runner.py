#!/usr/bin/env python3
"""harness v1.1 pinned worker for one kernel of a WaterLily T4 campaign (rendered by scripts/harness.py into infra/kaggle/kernel_<campaign>_<k>/runner.py).

Everything campaign-specific is read from the pinned campaign.json of the pinned source commit (its SHA-256 is in PINS); only the PIN block below differs between a formal and a smoke render.
Behaviour equals the proven GRID-02 runner: GPU inventory, sparse checkout and pin verification, Julia install, Pkg.instantiate, the JSON3-free CUDA probe (Tesla T4 only, physical index 0,
singleton UUID), per-state job with per-state/aggregate/kernel budgets, index + manifest, DONE xor ERROR.  Added: a stage-0 self-test before any Julia work and an optional first-state byte gate.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

HARNESS_VERSION = "harness v1.1"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
SCHEMA_REL = "src/cfd_harness/campaign_schema.py"
# --- PIN BEGIN (the only lines that differ between a formal and a smoke render) ---
KERNEL = "g1k12"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-screen01-g1k12"
SOURCE_COMMIT = "2e032cd85db1b53a8c2b3e211807d9ab3e8fbabb"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
CAMPAIGN = "docs/harness/screen01_campaign.json"
SMOKE = False
OUT_DIR_NAME = "screen01_g1k12"
INDEX_NAME = "harness_index.json"
SPARSE = ["docs/evidence/screen01_2026_10_30/inputs/v18__camber_m0.502_pitch_m2.372_reflex_m27.474.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m1.442_pitch_m0.263_reflex_m0.534.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m11.14_pitch_m0.003_reflex_p27.435.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m11.3_reflex_m11.3.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m14.935_pitch_m2.041_reflex_m13.167.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m16.263_pitch_m0.962_reflex_p13.18.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m17.304_pitch_m1.056_reflex_m4.377.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.007_pitch_p0.706_reflex_m26.059.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.7.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.789_pitch_m0.621_reflex_p26.168.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.7_pitch_m0.38.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m21.959_pitch_m2.307_reflex_m24.023.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m23.394_pitch_p0.776_reflex_m21.432.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m25.466_pitch_p2.31_reflex_p4.633.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m26.303_pitch_m1.751_reflex_m15.958.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m28.656_pitch_m0.68_reflex_p2.727.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m3.701_pitch_m2.29_reflex_p17.406.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m4.576_pitch_p0.673_reflex_m10.721.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m7.817_pitch_m2.417_reflex_p7.656.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m8.416_pitch_p0.028_reflex_m3.18.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p13.023_pitch_m1.611_reflex_p11.039.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p15.009_pitch_p2.043_reflex_m11.687.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p15.396_pitch_m1.812_reflex_m17.01.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p16.113_pitch_p1.042_reflex_p28.057.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p16.454_pitch_p1.64_reflex_m16.946.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p17.017_pitch_m0.807_reflex_p23.478.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p19.106_pitch_m2.002_reflex_m23.47.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p19.7.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p2.982_pitch_m1.486_reflex_p6.097.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p3.261_pitch_m3.085_reflex_p28.738.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p6.88_pitch_m2.543_reflex_m19.455.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p9.129_pitch_m0.554_reflex_m28.934.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__pitch_m3.1.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__pitch_p3.1.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__reflex_m29.3.dir_f4_fortran.raw", "docs/evidence/screen01_2026_10_30/inputs/v18__reflex_p29.3.dir_f4_fortran.raw", "docs/evidence/unc01_2026_10_20/inputs/v18__roll_p25.dir_f4_fortran.raw", "docs/evidence/v18_genesis_2026_10_19/v18_parent.phi_f4_fortran.raw", "docs/harness/screen01_campaign.json", "julia/", "julia/CFDSDFWaterLily/src", "julia/CFDSDFWaterLilyT4/Manifest.toml", "julia/CFDSDFWaterLilyT4/Project.toml", "scripts/", "scripts/fd08_v2_campaign_io.py", "scripts/grid01_gpu.py", "scripts/step01_states.py", "scripts/waterlily_lowdim02_flow32_job.jl", "src/cfd_harness/", "src/cfd_harness/campaign_schema.py"]
PINS = {
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m0.502_pitch_m2.372_reflex_m27.474.dir_f4_fortran.raw": "701488cf3431feb57b4f12c3b96a6b1d359547825882b4e692b3d1564305567c",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m1.442_pitch_m0.263_reflex_m0.534.dir_f4_fortran.raw": "9369902afdffadea9fa94c947fa7a6ab6d75d2d9bc2647ebbaf8db323bac926a",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m11.14_pitch_m0.003_reflex_p27.435.dir_f4_fortran.raw": "3335e97bbf8213bca3bddb7eeb1ae9ebb65f868cde9c05740062165f706c20fd",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m11.3_reflex_m11.3.dir_f4_fortran.raw": "9774c5d5c32849b1f2cad78b259918c6d6fd3311317139ee66a43b3a29078624",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m14.935_pitch_m2.041_reflex_m13.167.dir_f4_fortran.raw": "a3c73c1703b766c598109176a62776103cb2e9ea9563c88ed5c12c6b5b7c8db3",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m16.263_pitch_m0.962_reflex_p13.18.dir_f4_fortran.raw": "0a0e1a1a4fb18ad86e21ae33bcd01925e37fd3734a4766d4e0de47931d67b97d",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m17.304_pitch_m1.056_reflex_m4.377.dir_f4_fortran.raw": "245741daa9c344536d5498ee337daa77764558a78316e5f37ba3502a6148f7e3",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.007_pitch_p0.706_reflex_m26.059.dir_f4_fortran.raw": "2a4cb02b577dd0591f79ad6fbd9b14e9c1c7ba7cd6feead4971339e4c9c9e0ed",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.7.dir_f4_fortran.raw": "d103bb0f5e6f366a9a021530b144049415edff65d90c9d79f35477bfa3eac42a",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.789_pitch_m0.621_reflex_p26.168.dir_f4_fortran.raw": "62edc0162aabc0aa505c2b19c689e598feda0a7b99a2c130eec6624437024ae8",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m19.7_pitch_m0.38.dir_f4_fortran.raw": "f496d37dbd63e4ca2a66e0a12a8535fdef2629d024d4a46c85511dd12836a57b",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m21.959_pitch_m2.307_reflex_m24.023.dir_f4_fortran.raw": "59bd719205aa63db7330d96d7ab42d56b1afb6fb03c1233378108dcdc74dacf0",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m23.394_pitch_p0.776_reflex_m21.432.dir_f4_fortran.raw": "600b6b2d866a0b9f62885244acd1450ad9db949066383e59eec91f16ffad6290",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m25.466_pitch_p2.31_reflex_p4.633.dir_f4_fortran.raw": "391cde0e288444f55911569ef98b6f878485d1c42e8499a44eb54f8252de68c4",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m26.303_pitch_m1.751_reflex_m15.958.dir_f4_fortran.raw": "b2ea87d50112731f729e58028a81a353ed2e7a44a38f2542913c4ae41a3e0e14",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m28.656_pitch_m0.68_reflex_p2.727.dir_f4_fortran.raw": "91ca81369c628ef2227e357f6b37badb80a5f2102ffed8d532ef2095670ad0e3",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m3.701_pitch_m2.29_reflex_p17.406.dir_f4_fortran.raw": "9479b08ae7a0bf0bd11b470502127737bbd12deb48e2df7711368ae42a54d4be",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m4.576_pitch_p0.673_reflex_m10.721.dir_f4_fortran.raw": "6a355d1cdfb4f41629a6e286c53291818426740ada6a45ced5cb855616675a4c",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m7.817_pitch_m2.417_reflex_p7.656.dir_f4_fortran.raw": "084e32fd3ff7df042bb475799c01b47b2c2418851dabf7833044893e28c9c680",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_m8.416_pitch_p0.028_reflex_m3.18.dir_f4_fortran.raw": "2f7048c6210fc54292f97819c2f2b5bc42eacf66da80d2fbc40f5f27ef0c1425",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p13.023_pitch_m1.611_reflex_p11.039.dir_f4_fortran.raw": "6ef22ab986ff1abe03a9f63efed56ded28f9f0245c619a677f5458692f03c0b5",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p15.009_pitch_p2.043_reflex_m11.687.dir_f4_fortran.raw": "87fc2a03e7f0bab0f9343c2da4939e664795a75d79f1af2764e51ac1bc03a709",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p15.396_pitch_m1.812_reflex_m17.01.dir_f4_fortran.raw": "337d439012e18f4e4dca783fe55ffa46b295ce64078443bcc705cc6aba200055",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p16.113_pitch_p1.042_reflex_p28.057.dir_f4_fortran.raw": "c0a789b471ffa6cb028622e3c03c4fdfadc40fda8e0ab14325c9dad616420dca",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p16.454_pitch_p1.64_reflex_m16.946.dir_f4_fortran.raw": "3f0b8b2c76d6948750b60024191931f1e4ad9c0fa4a0c869ce8fde17065d71f5",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p17.017_pitch_m0.807_reflex_p23.478.dir_f4_fortran.raw": "6e7c79204f4d990c621eb9b87c7aabc95014427a1539256460238ad0f82fb582",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p19.106_pitch_m2.002_reflex_m23.47.dir_f4_fortran.raw": "43d24727ba7324fc47eabdf6ccc7186f2a15e718b3808aca0fc6e39dab71f73f",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p19.7.dir_f4_fortran.raw": "f99c55afbadbd9fd857a29b16766a410dd0a0d98628a1884e7bd5905a7d51760",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p2.982_pitch_m1.486_reflex_p6.097.dir_f4_fortran.raw": "808aa5a811dae42eff7469521c2ef995d2f66c2515bea4de13a3b03acce43438",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p3.261_pitch_m3.085_reflex_p28.738.dir_f4_fortran.raw": "a949d257bebea2789092b1f12500e99c71e7113919ea6b4ce034d2bc3c1d758d",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p6.88_pitch_m2.543_reflex_m19.455.dir_f4_fortran.raw": "e34cd11927542229b89e59fa01825debfd8e5ddb73f1adc34c927471c4ac7913",
    "docs/evidence/screen01_2026_10_30/inputs/v18__camber_p9.129_pitch_m0.554_reflex_m28.934.dir_f4_fortran.raw": "013c102f0646e7d0144347e0e340108327ff8f368253598e0e6d98041bc54738",
    "docs/evidence/screen01_2026_10_30/inputs/v18__pitch_m3.1.dir_f4_fortran.raw": "c2532e3fad1d01b8da9012ec89f20886b84d1d0627072bdf2589d7bad6eb46ab",
    "docs/evidence/screen01_2026_10_30/inputs/v18__pitch_p3.1.dir_f4_fortran.raw": "7e446d7712f04bdc5bf1b1c5f27bf8ceb7b49619f34bdb94c7849232cff9cc9f",
    "docs/evidence/screen01_2026_10_30/inputs/v18__reflex_m29.3.dir_f4_fortran.raw": "dedd79921bd85d4bd5e4ba1ed4beab91b55d04bb8e3b93ec5a896f6b8de71478",
    "docs/evidence/screen01_2026_10_30/inputs/v18__reflex_p29.3.dir_f4_fortran.raw": "b37c8f4a0229e2d5c7b48785e3143d0ff598b423418b473a690e66576f090d77",
    "docs/evidence/unc01_2026_10_20/inputs/v18__roll_p25.dir_f4_fortran.raw": "2796e8361d4af8eac564e8495b498a202c8000a9e333171299bb06bace4ad040",
    "docs/evidence/v18_genesis_2026_10_19/v18_parent.phi_f4_fortran.raw": "29d53b2318c54548da321f265aa2102d59e24d96bbd04fb2dd70d62fbc10c82a",
    "docs/harness/screen01_campaign.json": "418e0ad8ba9d477c5760e52b9768af822fac732457b507b1863e0721b2c675c9",
    "julia/CFDSDFWaterLily/src": "9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85",
    "julia/CFDSDFWaterLilyT4/Manifest.toml": "c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707",
    "julia/CFDSDFWaterLilyT4/Project.toml": "e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194",
    "scripts/fd08_v2_campaign_io.py": "dda177cda3c8f02626be7af3f9ae2d2cad984c8eeea6a09c3445e64ac906c3d2",
    "scripts/grid01_gpu.py": "bfaed961f3136d14bdeb7e4fccfab807f5fb8c257b45cd3ebb875963104fff38",
    "scripts/step01_states.py": "f3c5ea30cc88c5efe2cbdd8f96ceeb481321ebc0b84228b3287c6ab718b7ca87",
    "scripts/waterlily_lowdim02_flow32_job.jl": "418796ce258e8f9e9945332d18869104a53f74000a96b609d4f4b42c82a21683",
    "src/cfd_harness/campaign_schema.py": "4c3c494ed381930d9d1e51b063efbbdcf1fa4586c1ac7e84d2b999a5c984d1b8",
}
# --- PIN END ---
OUT = Path(os.environ.get("CAMPAIGN_WORK_ROOT", "/kaggle/working")) / OUT_DIR_NAME  # Kaggle default; another GPU backend sets CAMPAIGN_WORK_ROOT
GPU_PROBE_CODE = '''
using CUDA
@assert CUDA.functional()
devs = collect(CUDA.devices())
id(d) = "GPU-" * string(CUDA.uuid(d))
Q = string(Char(34))
q(x) = (s = string(x); @assert !occursin(Q, s) && !occursin(string(Char(92)), s); Q * s * Q)
arr(v) = "[" * join(q.(v), ",") * "]"
kv(k, v) = q(k) * ":" * v
json = "{" * join([
    kv("logical_device_count", string(length(devs))),
    kv("visible_gpu_names", arr([CUDA.name(d) for d in devs])),
    kv("visible_gpu_uuids", arr([id(d) for d in devs])),
    kv("default_device_uuid", q(id(CUDA.device()))),
    kv("cuda_device_order", q(ENV["CUDA_DEVICE_ORDER"])),
    kv("cuda_visible_devices", q(ENV["CUDA_VISIBLE_DEVICES"])),
], ",") * "}"
open(ENV["GRID01_GPU_PROBE_OUT"], "w") do io
    println(io, json)
end
'''


def sha256(path):
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo"))
        return hashlib.sha256(("\n".join(f"{p.relative_to(path)}  {sha256(p)}" for p in files) + "\n").encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(path)


def write_manifest(out):
    files = {str(p.relative_to(out)): sha256(p) for p in sorted(Path(out).rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    write_json(Path(out) / "output_manifest.json", {"files": files})


def nvidia_smi():
    return subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)


def run(args, log_path, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as log:
        result = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    for line in Path(log_path).read_text(errors="replace").splitlines()[-30:]:
        print(line, flush=True)
    return result.returncode


def install_julia(base):
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=120) as response, archive.open("wb") as output:
        while block := response.read(1 << 20):
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia archive SHA-256 mismatch")
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(base)], check=True)
    return base / "julia-1.12.6/bin/julia"


def fetch_source(base):
    source = base / "source"
    source.mkdir()
    git = ["git", "-C", str(source)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["remote", "add", "origin", REPO_URL], check=True)
    subprocess.run(git + ["config", "core.sparseCheckout", "true"], check=True)
    (source / ".git/info/sparse-checkout").write_text("\n".join("/" + p for p in SPARSE) + "\n")
    fetched = subprocess.run(git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", SOURCE_COMMIT])
    if fetched.returncode:
        subprocess.run(git + ["fetch", "-q", "--depth", "1", "origin", SOURCE_COMMIT], check=True)
    subprocess.run(git + ["checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
    head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    if head != SOURCE_COMMIT:
        raise RuntimeError(f"checked-out commit {head} != pinned {SOURCE_COMMIT}")
    return source


def load_schema(source):
    spec = importlib.util.spec_from_file_location("campaign_schema", source / SCHEMA_REL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_phi(S, row, baseline_phi, directions):
    """Regenerate one state's phi from the pinned baseline and direction raws and verify every identity field of the campaign row (both byte orders)."""
    import numpy as np

    phi = baseline_phi if row["direction"] is None else S.perturb(baseline_phi, directions[row["direction"]], row["step_mm"], row["sign"])
    if not np.all(np.isfinite(phi)):
        raise RuntimeError("generated phi has non-finite values")
    raw = S.to_raw(phi)
    if S.sha256_bytes(raw) != row["phi_fortran_order_sha256"]:
        raise RuntimeError("generated phi differs from the campaign (Fortran-order SHA)")
    if hashlib.sha256(np.asarray(phi, dtype="<f4").tobytes(order="C")).hexdigest() != row["phi_c_order_sha256"]:
        raise RuntimeError("generated C-order phi differs from the campaign")
    changed = int(np.count_nonzero(phi != baseline_phi))
    max_change = float(np.max(np.abs(phi.astype(np.float64) - baseline_phi.astype(np.float64))))
    if changed != row["changed_node_count"] or abs(max_change - row["maximum_pointwise_change_m"]) > 1.0e-12:
        raise RuntimeError("generated state change metrics differ from the campaign")
    return raw


def schema_dry_write(SC, tmp):
    """Write a synthetic index, force CSV and manifest through the runner's own writers and read them back through the schema's checks."""
    tmp = Path(tmp)
    row = {"kind": "parent", "direction": None, "step_mm": 0.0, "sign": 0}
    index = SC.new_index("selftest", "owner/selftest", "case")
    index["states"].append(SC.index_entry("s0", row, 0, 1.0, "0" * 64, True))
    SC.validate_index(index)
    write_json(tmp / "index.json", index)
    (tmp / "case.forces.csv").write_text(",".join(SC.FORCE_COLUMNS) + "\n")
    write_manifest(tmp)
    SC.check_manifest(tmp, ["index.json", "case.forces.csv"])
    SC.selftest_force_check()


def remaining(started, kernel_timeout_s, margin_s):
    left = kernel_timeout_s - margin_s - (time.time() - started)
    if left <= 60:
        raise RuntimeError("kernel time budget exhausted")
    return left


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=False)
    stage = "gpu_inventory"
    identity = {"runner_sha256": sha256(__file__), "python_version": sys.version, "numpy_version": None, "platform": " ".join(os.uname()), "kernel": KERNEL, "kernel_id": KERNEL_ID,
                "source_commit": SOURCE_COMMIT, "pins": PINS, "direction_files": {}, "config": None, "expected_names": None, "case_id": None, "failure_stage": None,
                "harness_version": HARNESS_VERSION, "campaign_sha256": PINS[CAMPAIGN], "smoke": SMOKE,
                "campaign_work_root": os.environ.get("CAMPAIGN_WORK_ROOT", "/kaggle/working")}
    index = {"kernel": KERNEL, "kernel_id": KERNEL_ID, "case_id": None, "states": [], "status": "RUNNING"}
    write_json(OUT / "run_identity.json", identity)
    write_json(OUT / INDEX_NAME, index)
    failed = False
    try:
        import numpy as np
        identity["numpy_version"] = np.__version__
        gpu = nvidia_smi()
        (OUT / "nvidia_smi.csv").write_text(gpu)
        with tempfile.TemporaryDirectory(prefix="harness-", dir=OUT.parent) as temp:
            base = Path(temp)
            stage = "source_checkout"
            source = fetch_source(base)
            verified = {}
            for rel, expected in PINS.items():
                verified[rel] = sha256(source / rel)
                if verified[rel] != expected:
                    raise RuntimeError(f"pinned file SHA-256 mismatch: {rel}")
            identity["verified"] = verified
            write_json(OUT / "run_identity.json", identity)
            stage = "self_test"
            sys.path.insert(0, str(source / "scripts"))
            SC = load_schema(source)
            import step01_states as S
            from grid01_gpu import select_worker_gpu
            campaign = SC.jload(source / CAMPAIGN)
            SC.validate_campaign(campaign)
            if campaign["harness_version"] != HARNESS_VERSION or SC.HARNESS_VERSION != HARNESS_VERSION:
                raise RuntimeError("harness version differs between the runner, the schema and the campaign")
            kernel = campaign["kernels"][KERNEL]
            if kernel["kernel_id"] + ("-smoke" if SMOKE else "") != KERNEL_ID or SC.out_dir_name(campaign, KERNEL) != OUT_DIR_NAME or SC.index_name(campaign) != INDEX_NAME:
                raise RuntimeError("the baked kernel identity or output names differ from the campaign")
            cfg, case_id, job = kernel["config"], kernel["case"]["case_id"], kernel["job"]
            names = SC.run_names(kernel)[:1] if SMOKE else SC.run_names(kernel)
            runs = SC.runs_by_name(kernel)
            for rel, want in [(campaign["baseline"]["path"], campaign["baseline"]["sha256_fortran_raw"])] + [(d["path"], d["sha256_fortran_raw"]) for d in campaign["directions"].values()]:
                if PINS.get(rel) != want:
                    raise RuntimeError(f"the baseline or a direction raw is not pinned to the campaign hash: {rel}")
            if job not in PINS or CAMPAIGN not in PINS or SCHEMA_REL not in PINS:
                raise RuntimeError("the job, the campaign or the schema is not pinned")
            identity.update(direction_files={n: PINS[d["path"]] for n, d in campaign["directions"].items()}, config=cfg, expected_names=names, case_id=case_id)
            index["case_id"] = case_id
            selected_gpu = select_worker_gpu(gpu)
            gpu_uuid = selected_gpu["uuid"]
            identity.update(selected_gpu=selected_gpu, cuda_device_order="PCI_BUS_ID", cuda_visible_devices="0")
            write_json(OUT / "run_identity.json", identity)
            write_json(OUT / INDEX_NAME, index)
            baseline_phi = S.read_f4(source / campaign["baseline"]["path"])
            directions = {n: S.read_f4(source / d["path"]) for n, d in campaign["directions"].items()}
            if not all(np.all(np.isfinite(a)) for a in [baseline_phi, *directions.values()]):
                raise RuntimeError("baseline or direction phi has non-finite values")
            raws = {n: generate_phi(S, campaign["states"][runs[n]["state"]], baseline_phi, directions) for n in names}
            with tempfile.TemporaryDirectory(prefix="dry-", dir=base) as dry:
                schema_dry_write(SC, dry)
            self_test = {"harness_version": HARNESS_VERSION, "imports": True, "schema_dry_write": True, "phi_identities_verified": len(raws), "gpu_probe": False}
            julia = install_julia(base)
            env = os.environ.copy()
            env.update({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_NUM_THREADS": "1"})
            project = f"--project={source / PROJECT}"
            margin = cfg["reserve_s"]
            stage = "instantiate"
            if run([str(julia), project, "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env, min(cfg["instantiate_timeout_s"], remaining(started, cfg["kernel_timeout_s"], margin))):
                raise RuntimeError("Pkg.instantiate failed")
            for rel in ("Project.toml", "Manifest.toml"):
                if sha256(source / PROJECT / rel) != PINS[f"{PROJECT}/{rel}"]:
                    raise RuntimeError(f"{rel} changed during instantiate")
            stage = "observed_cuda_device_probe"
            probe_env = dict(env, GRID01_GPU_PROBE_OUT=str(OUT / "gpu_device_probe.json"))
            if run([str(julia), "--startup-file=no", project, "-e", GPU_PROBE_CODE], OUT / "gpu_device_probe.log", probe_env, min(cfg["gpu_probe_timeout_s"], remaining(started, cfg["kernel_timeout_s"], margin))):
                raise RuntimeError("independent CUDA device UUID probe failed")
            observed = json.loads((OUT / "gpu_device_probe.json").read_text())
            expected_device = dict(SC.GPU_EXPECTED, visible_gpu_uuids=[gpu_uuid], default_device_uuid=gpu_uuid)
            if observed != expected_device:
                raise RuntimeError("observed CUDA singleton/default UUID differs from selected physical GPU")
            self_test["gpu_probe"] = True
            write_json(OUT / "self_test.json", self_test)
            solver_elapsed_s = 0.0
            for position, name in enumerate(names):
                run_spec = runs[name]
                row = campaign["states"][run_spec["state"]]
                stage = f"state:{name}"
                outdir = OUT / "states" / name
                outdir.mkdir(parents=True, exist_ok=False)
                phi_path = base / (name + ".phi.f32f")
                phi_path.write_bytes(raws[name])
                t0 = time.time()
                code = run([str(julia), "--startup-file=no", project, str(source / job), str(phi_path), str(outdir)], outdir / "job.log", SC.job_env(campaign, run_spec, row, env, gpu_uuid),
                           min(cfg["per_state_timeout_s"], remaining(started, cfg["kernel_timeout_s"], margin), cfg["solver_wall_time_cap_s"] - solver_elapsed_s))
                resolved_phi = phi_path.resolve()
                if resolved_phi.parent != base.resolve() or resolved_phi.name != name + ".phi.f32f":
                    raise RuntimeError("unexpected temporary phi cleanup target")
                resolved_phi.unlink()
                csv = outdir / SC.forces_name(case_id)
                seconds = time.time() - t0
                complete = code == 0 and csv.is_file() and (outdir / "W4_JOB_DONE").is_file() and (outdir / SC.summary_name(case_id)).is_file()
                entry = SC.index_entry(name, row, code, seconds, sha256(csv) if csv.is_file() else None, complete)
                gate = kernel.get("first_state_csv_sha256") if position == 0 else None
                if gate:
                    entry["matches_retained_parent_reference"] = entry["forces_csv_sha256"] == gate
                solver_elapsed_s += seconds
                index["solver_process_wall_seconds_total"] = solver_elapsed_s
                index["states"].append(entry)
                write_json(OUT / INDEX_NAME, index)
                if seconds > cfg["per_state_timeout_s"] or solver_elapsed_s > cfg["solver_wall_time_cap_s"]:
                    raise RuntimeError("registered per-state or aggregate solver wall-time budget exceeded")
                if not complete:
                    raise RuntimeError(f"state did not complete: {name} (exit {code})")
                if position == 0:
                    index["parent_forces_csv_sha256"] = entry["forces_csv_sha256"]
                    write_json(OUT / INDEX_NAME, index)
                    if gate and not entry["matches_retained_parent_reference"]:
                        raise RuntimeError("first-state force CSV differs from the pinned historical CSV")
            if [entry["name"] for entry in index["states"]] != names:
                raise RuntimeError("completed state sequence differs from the registered plan")
        stage = "completed"
        index["status"] = "COMPLETE"
        identity["failure_stage"] = None
        SC.validate_index(index, terminal=True)
        SC.validate_identity(identity)
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / INDEX_NAME, index)
    except BaseException:
        failed = True
        index["status"] = "ERROR"
        identity["failure_stage"] = stage
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / INDEX_NAME, index)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        if not failed:
            (OUT / "DONE").write_text("all registered states of this kernel completed; host integrity (scripts/harness.py verify) and the campaign analysis are still required.\n")
        write_manifest(OUT)
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
