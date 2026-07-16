"""Shared defaults and supported formats."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SUPPORTED_INPUT_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}
DEFAULT_CONFIG = Path("image_batch_config.csv")
DEFAULT_INPUT_DIR = Path("input")
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_JPEG_QUALITY = 95
DEFAULT_BAR_POSITION = "bottom-right"
DEFAULT_BAR_MARGIN = 40
DEFAULT_BAR_THICKNESS = 8
DEFAULT_BAR_COLOR = "white"
DEFAULT_SHOW_LABEL = False
DEFAULT_LABEL_COLOR = "white"
DEFAULT_LABEL_FONT_SIZE = 24
DEFAULT_BRIGHTNESS = 1.0
DEFAULT_CONTRAST = 1.0
BAR_POSITIONS = {"bottom-right", "bottom-left", "top-right", "top-left"}
RESAMPLE_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
