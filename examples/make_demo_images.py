"""Generate synthetic micrograph-like 16-bit TIFFs for the demo.

The real tool was built for optical-microscopy data that cannot be published,
so the example images are simulated: dark, low-contrast 16-bit frames that
occupy only a narrow band of the sensor range — exactly the kind of file that
looks black when saved to JPEG naively.

Run from the examples/ folder:

    python make_demo_images.py

Requires numpy (demo only; the tool itself needs just Pillow).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

RNG = np.random.default_rng(42)
OUT_DIR = Path(__file__).parent / "input"
SIZE = (1200, 1600)  # rows, cols


def _to_16bit_tiff(field: np.ndarray, path: Path, low: int = 1200, high: int = 9800) -> None:
    """Map a 0..1 field into a narrow 16-bit band, mimicking a scientific camera."""
    field = np.clip(field, 0.0, 1.0)
    counts = (low + field * (high - low)).astype(np.uint16)
    Image.fromarray(counts).save(path, format="TIFF")
    print(f"Wrote {path}")


def droplets_frame() -> np.ndarray:
    """Simulated emulsion droplets: bright circles with soft edges on a noisy background."""
    rows, cols = SIZE
    y, x = np.mgrid[0:rows, 0:cols].astype(np.float64)
    field = RNG.normal(0.08, 0.02, SIZE)

    for _ in range(28):
        cx = RNG.uniform(60, cols - 60)
        cy = RNG.uniform(60, rows - 60)
        radius = RNG.uniform(25, 110)
        distance = np.hypot(x - cx, y - cy)
        rim = np.exp(-((distance - radius) ** 2) / (2 * (radius * 0.06) ** 2))
        interior = 0.35 * (distance < radius)
        field += 0.55 * rim + interior * RNG.uniform(0.4, 1.0)

    return field / field.max()


def texture_frame(phase: float) -> np.ndarray:
    """Simulated birefringent texture: crossed sinusoidal domains plus grain noise."""
    rows, cols = SIZE
    y, x = np.mgrid[0:rows, 0:cols].astype(np.float64)
    angle = np.deg2rad(35)
    u = x * np.cos(angle) + y * np.sin(angle)
    v = -x * np.sin(angle) + y * np.cos(angle)

    field = (
        0.5
        + 0.28 * np.sin(u / 42 + phase) * np.cos(v / 63 - phase / 2)
        + 0.14 * np.sin((x + y) / 150 + 2 * phase)
    )
    field += RNG.normal(0, 0.03, SIZE)
    return (field - field.min()) / (field.max() - field.min())


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _to_16bit_tiff(droplets_frame(), OUT_DIR / "droplets_16bit.tif")
    _to_16bit_tiff(texture_frame(0.0), OUT_DIR / "texture_t0_16bit.tif")
    _to_16bit_tiff(texture_frame(1.3), OUT_DIR / "texture_t1_16bit.tif")


if __name__ == "__main__":
    main()
