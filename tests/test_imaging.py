import numpy as np
import pytest
from PIL import Image

from micrograph_batch.imaging import (
    add_scale_bar,
    clamp_crop_box,
    crop_box_to_xywh,
    normalize_to_8bit_grayscale,
    prepare_image_for_jpeg,
    scale_bar_length_px,
    xywh_to_crop_box,
)


class TestCropGeometry:
    def test_clamp_keeps_valid_box(self):
        assert clamp_crop_box((10, 10, 90, 90), (100, 100)) == (10, 10, 90, 90)

    def test_clamp_trims_overflow(self):
        assert clamp_crop_box((-5, -5, 150, 150), (100, 100)) == (0, 0, 100, 100)

    def test_degenerate_box_raises(self):
        with pytest.raises(ValueError):
            clamp_crop_box((50, 50, 50, 60), (100, 100))

    def test_xywh_round_trip(self):
        box = (10, 20, 110, 220)
        assert xywh_to_crop_box(*crop_box_to_xywh(box)) == box


class TestScaleBar:
    def test_length_math(self):
        # 100 um at 0.5 um/px -> 200 px
        assert scale_bar_length_px(bar_um=100, um_per_px=0.5) == 200

    def test_bar_is_drawn(self):
        image = Image.new("RGB", (400, 300), "black")
        add_scale_bar(
            image,
            um_per_px=0.5,
            bar_um=50,
            position="bottom-right",
            margin=20,
            thickness=8,
            color="white",
            show_label=False,
            label=None,
            label_color="white",
            label_font_size=24,
        )
        # bar occupies 100 px ending 20 px from the right edge
        assert image.getpixel((379, 275)) == (255, 255, 255)
        assert image.getpixel((200, 150)) == (0, 0, 0)

    def test_bar_wider_than_image_raises(self):
        image = Image.new("RGB", (100, 100), "black")
        with pytest.raises(ValueError):
            add_scale_bar(
                image,
                um_per_px=0.1,
                bar_um=100,  # 1000 px bar in a 100 px image
                position="bottom-right",
                margin=10,
                thickness=8,
                color="white",
                show_label=False,
                label=None,
                label_color="white",
                label_font_size=24,
            )


class TestBitDepthNormalisation:
    def test_narrow_band_is_stretched_to_full_range(self):
        # counts in [1000, 5000] out of 65535 — nearly black without normalisation
        counts = np.linspace(1000, 5000, 100 * 100, dtype=np.uint16).reshape(100, 100)
        normalized = normalize_to_8bit_grayscale(Image.fromarray(counts))
        low, high = normalized.getextrema()
        assert low == 0
        assert high == 255

    def test_flat_image_does_not_crash(self):
        counts = np.full((50, 50), 3000, dtype=np.uint16)
        normalized = normalize_to_8bit_grayscale(Image.fromarray(counts))
        assert normalized.getextrema() == (255, 255)

    def test_prepare_16bit_tiff(self, tmp_path):
        counts = np.linspace(1000, 5000, 60 * 80, dtype=np.uint16).reshape(60, 80)
        path = tmp_path / "frame.tif"
        Image.fromarray(counts).save(path, format="TIFF")

        image = prepare_image_for_jpeg(path)
        assert image.mode == "RGB"
        assert image.size == (80, 60)
