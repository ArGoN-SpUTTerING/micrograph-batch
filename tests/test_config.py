from pathlib import Path

import pytest

from micrograph_batch.config import (
    build_crop_box,
    build_output_path,
    build_task_from_row,
    csv_headers,
    parse_bool,
    validate_scale_bar_settings,
    write_starter_config,
)


def minimal_row(**overrides: str) -> dict[str, str]:
    row = {name: "" for name in csv_headers()}
    row["enabled"] = "TRUE"
    row["filename"] = "sample.tif"
    row.update(overrides)
    return row


class TestParseBool:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Y"])
    def test_truthy(self, value):
        assert parse_bool(value, default=False) is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "N"])
    def test_falsy(self, value):
        assert parse_bool(value, default=True) is False

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_blank_falls_back_to_default(self, value):
        assert parse_bool(value, default=True) is True
        assert parse_bool(value, default=False) is False

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_bool("maybe", default=True)


class TestBuildCropBox:
    def test_all_blank_means_no_crop(self):
        assert build_crop_box(minimal_row()) is None

    def test_full_box(self):
        row = minimal_row(crop_left="10", crop_top="20", crop_right="110", crop_bottom="220")
        assert build_crop_box(row) == (10, 20, 110, 220)

    def test_partial_box_raises(self):
        row = minimal_row(crop_left="10")
        with pytest.raises(ValueError):
            build_crop_box(row)


class TestScaleBarSettings:
    def test_both_absent_is_fine(self):
        validate_scale_bar_settings(None, None)

    def test_one_missing_raises(self):
        with pytest.raises(ValueError):
            validate_scale_bar_settings(0.5, None)

    def test_non_positive_raises(self):
        with pytest.raises(ValueError):
            validate_scale_bar_settings(-1.0, 50.0)


class TestBuildTaskFromRow:
    def test_disabled_row_returns_none(self):
        row = minimal_row(enabled="FALSE")
        assert build_task_from_row(2, row, Path("in"), Path("out")) is None

    def test_blank_filename_returns_none(self):
        row = minimal_row(filename="")
        assert build_task_from_row(2, row, Path("in"), Path("out")) is None

    def test_defaults_applied(self):
        task = build_task_from_row(2, minimal_row(), Path("in"), Path("out"))
        assert task is not None
        assert task.brightness == 1.0
        assert task.contrast == 1.0
        assert task.bar_position == "bottom-right"
        assert task.jpeg_quality == 95
        assert task.output_path == Path("out/sample.jpg")

    def test_auto_label_from_bar_um(self):
        row = minimal_row(um_per_px="0.5", bar_um="100", show_label="TRUE")
        task = build_task_from_row(2, row, Path("in"), Path("out"))
        assert task.bar_label == "100 um"

    def test_bad_bar_position_raises(self):
        row = minimal_row(bar_position="center")
        with pytest.raises(ValueError):
            build_task_from_row(2, row, Path("in"), Path("out"))


class TestBuildOutputPath:
    def test_explicit_output_name_wins(self):
        path = build_output_path(Path("in/a.tif"), "renamed.jpg", Path("in"), Path("out"))
        assert path == Path("out/renamed.jpg")

    def test_relative_structure_is_preserved(self):
        path = build_output_path(Path("in/groupA/a.tif"), "", Path("in"), Path("out"))
        assert path == Path("out/groupA/a.jpg")

    def test_suffix_is_always_jpg(self):
        path = build_output_path(Path("in/a.tiff"), "", Path("in"), Path("out"))
        assert path.suffix == ".jpg"


class TestStarterConfig:
    def test_scans_input_dir(self, tmp_path):
        input_dir = tmp_path / "input"
        (input_dir / "nested").mkdir(parents=True)
        (input_dir / "a.tif").touch()
        (input_dir / "nested" / "b.png").touch()
        (input_dir / "notes.txt").touch()

        config_path = tmp_path / "config.csv"
        write_starter_config(config_path, input_dir, recursive=True, overwrite=False)

        content = config_path.read_text(encoding="utf-8-sig")
        assert "a.tif" in content
        assert "nested/b.png" in content
        assert "notes.txt" not in content

    def test_refuses_to_overwrite_without_flag(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        config_path = tmp_path / "config.csv"
        config_path.touch()

        with pytest.raises(SystemExit):
            write_starter_config(config_path, input_dir, recursive=True, overwrite=False)
