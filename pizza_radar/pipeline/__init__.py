"""Módulo de orquestração e execução da pipeline do Pizza Radar PT."""

from pizza_radar.pipeline.runner import (
    PipelineResult,
    VendorSyncStatus,
    run_pipeline,
)

__all__ = [
    "PipelineResult",
    "VendorSyncStatus",
    "run_pipeline",
]
