"""micrograph-batch: CSV-driven batch processing for microscopy images.

Convert, crop, adjust, and annotate micrographs (TIFF and friends) into
publication-ready JPEGs with calibrated scale bars, driven by a single
spreadsheet-editable CSV config.
"""

from micrograph_batch.config import (
    ConfigEntry,
    ImageTask,
    load_config_entries,
    load_tasks,
    write_starter_config,
)
from micrograph_batch.batch import process_task, run_batch
from micrograph_batch.imaging import add_scale_bar, prepare_image_for_jpeg

__version__ = "1.0.1"

__all__ = [
    "ConfigEntry",
    "ImageTask",
    "add_scale_bar",
    "load_config_entries",
    "load_tasks",
    "prepare_image_for_jpeg",
    "process_task",
    "run_batch",
    "write_starter_config",
    "__version__",
]