import csv

import numpy as np
import pytest
from PIL import Image

from micrograph_batch.cli import main
from micrograph_batch.config import csv_headers


@pytest.fixture()
def demo_batch(tmp_path):
    """A 16-bit TIFF plus a config asking for crop + scale bar + rename."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    counts = np.linspace(1200, 9800, 300 * 400, dtype=np.uint16).reshape(300, 400)
    Image.fromarray(counts).save(input_dir / "frame.tif", format="TIFF")

    row = {name: "" for name in csv_headers()}
    row.update(
        {
            "enabled": "TRUE",
            "filename": "frame.tif",
            "output_name": "frame_final.jpg",
            "um_per_px": "0.5",
            "bar_um": "50",
            "crop_left": "50",
            "crop_top": "30",
            "crop_right": "350",
            "crop_bottom": "270",
            "show_label": "TRUE",
        }
    )

    config_path = tmp_path / "config.csv"
    with config_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_headers())
        writer.writeheader()
        writer.writerow(row)

    return tmp_path, config_path, input_dir


def run_cli(tmp_path, config_path, input_dir, *extra: str) -> None:
    main(
        [
            "--config",
            str(config_path),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(tmp_path / "output"),
            *extra,
        ]
    )


def test_batch_produces_cropped_jpeg(demo_batch):
    tmp_path, config_path, input_dir = demo_batch
    run_cli(tmp_path, config_path, input_dir)

    output_path = tmp_path / "output" / "frame_final.jpg"
    assert output_path.exists()

    with Image.open(output_path) as image:
        assert image.format == "JPEG"
        assert image.size == (300, 240)  # crop box 50..350 x 30..270


def test_existing_output_is_skipped_without_overwrite(demo_batch, capsys):
    tmp_path, config_path, input_dir = demo_batch
    run_cli(tmp_path, config_path, input_dir)
    first_mtime = (tmp_path / "output" / "frame_final.jpg").stat().st_mtime_ns

    run_cli(tmp_path, config_path, input_dir)
    assert "Skip existing" in capsys.readouterr().out
    assert (tmp_path / "output" / "frame_final.jpg").stat().st_mtime_ns == first_mtime


def test_missing_config_exits_with_message(tmp_path):
    with pytest.raises(SystemExit, match="Config file not found"):
        main(["--config", str(tmp_path / "nope.csv")])
