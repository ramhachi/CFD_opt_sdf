"""SDF-native canonical design-state contracts."""

from .genesis import (
    GenesisError,
    GenesisResult,
    persist_genesis_report,
    sdf_state_from_handoff,
)
from .sdf_state import (
    DEFAULT_REINITIALIZATION_POLICY_ID,
    DEFAULT_TOPOLOGY_POLICY_ID,
    SDF_STATE_SCHEMA_VERSION,
    SIGN_CONVENTION,
    SDFDesignState,
    SDFStateError,
    sdf_state_sha256,
)
from .volume_semantics import (
    SMOOTHED_VOLUME_CONTRACT_ID,
    SMOOTHED_VOLUME_CONTRACT_SHA256,
    SMOOTHED_VOLUME_LIMIT_M3,
    SMOOTHED_VOLUME_LIMIT_SOURCE_REGISTRATION_ID,
    SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256,
    SMOOTHED_VOLUME_SCHEMA_VERSION,
    SmoothedVolumeResult,
    smoothed_volume_and_gradient,
)

__all__ = [
    "DEFAULT_REINITIALIZATION_POLICY_ID",
    "DEFAULT_TOPOLOGY_POLICY_ID",
    "SDF_STATE_SCHEMA_VERSION",
    "SIGN_CONVENTION",
    "SDFDesignState",
    "SDFStateError",
    "GenesisError",
    "GenesisResult",
    "sdf_state_sha256",
    "sdf_state_from_handoff",
    "persist_genesis_report",
    "SMOOTHED_VOLUME_CONTRACT_ID",
    "SMOOTHED_VOLUME_CONTRACT_SHA256",
    "SMOOTHED_VOLUME_LIMIT_M3",
    "SMOOTHED_VOLUME_LIMIT_SOURCE_REGISTRATION_ID",
    "SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256",
    "SMOOTHED_VOLUME_SCHEMA_VERSION",
    "SmoothedVolumeResult",
    "smoothed_volume_and_gradient",
]
