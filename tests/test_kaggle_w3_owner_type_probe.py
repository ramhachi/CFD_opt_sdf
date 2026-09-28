import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts/verify_kaggle_w3_owner_type_probe.py"
SPEC = importlib.util.spec_from_file_location("w3_owner_type_probe_host", VERIFY_PATH)
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


def fixture(cuda_defined=True):
    return {
        "julia_version": "1.12.6",
        "cuda_jl_version": "6.3.1",
        "waterlily_version": "1.8.0",
        "selected_gpu_name": "Tesla T4",
        "cuda_visible_devices": "0",
        "owner": {
            "type": "CuArray{Float32, 3, CUDACore.DeviceMemory}",
            "eltype": "Float32",
            "ndims": 3,
            "size": [61, 33, 25],
            "memory_parameter": "CUDACore.DeviceMemory",
            "memory_module": {"module": "CUDACore", "package_version": "6.3.1"},
            "module_device_memory_defined": True,
            "module_device_memory_is_parameter": True,
            "cuda_device_memory_defined": cuda_defined,
            "cuda_device_memory_is_parameter": False if cuda_defined else None,
            "cuda_device_memory_is_module_binding": False if cuda_defined else None,
        },
    }


def test_observed_CUDA_and_CUDACore_type_relationship_is_not_assumed():
    criteria = {"backend": {
        "julia_version": "1.12.6", "cuda_jl_version": "6.3.1",
        "waterlily_version": "1.8.0", "gpu_name": "Tesla T4",
    }, "w3_input": {"point_shape": [61, 33, 25]}}
    owner = host.verify_runtime_type(fixture(), criteria)
    assert owner["cuda_device_memory_is_parameter"] is False
    assert owner["module_device_memory_is_parameter"] is True


def test_undefined_CUDA_device_memory_binding_is_recorded_without_comparison():
    criteria = {"backend": {
        "julia_version": "1.12.6", "cuda_jl_version": "6.3.1",
        "waterlily_version": "1.8.0", "gpu_name": "Tesla T4",
    }, "w3_input": {"point_shape": [61, 33, 25]}}
    owner = host.verify_runtime_type(fixture(cuda_defined=False), criteria)
    assert owner["cuda_device_memory_defined"] is False
    assert owner["cuda_device_memory_is_parameter"] is None


def test_type_probe_requires_the_real_parent_module():
    criteria = {"backend": {
        "julia_version": "1.12.6", "cuda_jl_version": "6.3.1",
        "waterlily_version": "1.8.0", "gpu_name": "Tesla T4",
    }, "w3_input": {"point_shape": [61, 33, 25]}}
    observed = fixture()
    observed["owner"]["memory_module"]["module"] = "CUDA"
    with pytest.raises(ValueError, match="parent module"):
        host.verify_runtime_type(observed, criteria)
