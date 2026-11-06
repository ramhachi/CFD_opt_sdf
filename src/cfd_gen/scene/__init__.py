"""Solver-free primitive scenes; no optimizer or flow evaluation."""

from .primitives import BoxBody, EndplatePlate, MeshBody, PlateElement
from .scene import MergedElement, Scene

__all__ = ["BoxBody", "EndplatePlate", "MeshBody", "PlateElement", "MergedElement", "Scene"]
