"""CSV config parsing: one row per image, blank cells fall back to defaults."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from micrograph_batch.constants import (
    BAR_POSITIONS,
    DEFAULT_BAR_COLOR,
    DEFAULT_BAR_MARGIN,
    DEFAULT_BAR_POSITION,
    DEFAULT_BAR_THICKNESS,
    DEFAULT_BRIGHTNESS,
    DEFAULT_CONTRAST,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_LABEL_COLOR,
    DEFAULT_LABEL_FONT_SIZE,
    DEFAULT_SHOW_LABEL,
    SUPPORTED_INPUT_SUFFIXES,
)
from micrograph_batch.imaging import format_scale_label


@dataclass(frozen=True)
class ImageTask:
    row_number: int
    source_path: Path
    output_path: Path
    brightness: float
    contrast: float
    crop_box: tuple[int, int, int, int] | None
    um_per_px: float | None
    bar_um: float | None
    bar_position: str
    bar_margin: int
    bar_thickness: int
    bar_color: str
    show_label: bool
    bar_label: str | None
    label_color: str
    label_font_size: int
    jpeg_quality: int


@dataclass
class ConfigEntry:
    row_index: int
    row_number: int
    row_data: dict[str, str]
    task: ImageTask


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES


def iter_image_files(folder: Path, recursive: bool) -> Iterable[Path]:
    pattern = "**/*" if recursive else "*"
    for path in sorted(folder.glob(pattern)):
        if is_image_file(path):
            yield path


def csv_headers() -> list[str]:
    return [
        "enabled",
        "filename",
        "output_name",
        "um_per_px",
        "bar_um",
        "crop_left",
        "crop_top",
        "crop_right",
        "crop_bottom",
        "brightness",
        "contrast",
        "bar_position",
        "bar_margin",
        "bar_thickness",
        "bar_color",
        "show_label",
        "bar_label",
        "label_color",
        "label_font_size",
        "jpeg_quality",
    ]


def ensure_fieldnames(fieldnames: list[str] | None) -> list[str]:
    merged: list[str] = []
    for name in (fieldnames or []) + csv_headers():
        if name and name not in merged:
            merged.append(name)
    return merged


def write_starter_config(config_path: Path, input_dir: Path, recursive: bool, overwrite: bool) -> None:
    if config_path.exists() and not overwrite:
        raise SystemExit(
            f"Config already exists: {config_path}\n"
            "Use --overwrite-config if you want to replace it."
        )

    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    image_paths = list(iter_image_files(input_dir, recursive))
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with config_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_headers())
        writer.writeheader()
        for image_path in image_paths:
            writer.writerow(
                {
                    "enabled": "TRUE",
                    "filename": image_path.relative_to(input_dir).as_posix(),
                    "output_name": "",
                    "um_per_px": "",
                    "bar_um": "",
                    "crop_left": "",
                    "crop_top": "",
                    "crop_right": "",
                    "crop_bottom": "",
                    "brightness": f"{DEFAULT_BRIGHTNESS}",
                    "contrast": f"{DEFAULT_CONTRAST}",
                    "bar_position": DEFAULT_BAR_POSITION,
                    "bar_margin": str(DEFAULT_BAR_MARGIN),
                    "bar_thickness": str(DEFAULT_BAR_THICKNESS),
                    "bar_color": DEFAULT_BAR_COLOR,
                    "show_label": "FALSE",
                    "bar_label": "",
                    "label_color": DEFAULT_LABEL_COLOR,
                    "label_font_size": str(DEFAULT_LABEL_FONT_SIZE),
                    "jpeg_quality": str(DEFAULT_JPEG_QUALITY),
                }
            )

    print(f"Starter config written: {config_path}")
    print(f"Images listed: {len(image_paths)}")


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    text = value.strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value}")


def parse_float(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    return float(value)


def parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def parse_optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


def parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


def resolve_source_path(filename: str, input_dir: Path) -> Path:
    source = Path(filename)
    return source if source.is_absolute() else input_dir / source


def build_output_path(source_path: Path, output_name: str, input_dir: Path, output_dir: Path) -> Path:
    if output_name.strip():
        relative_output = Path(output_name)
    else:
        try:
            relative_output = source_path.relative_to(input_dir)
        except ValueError:
            relative_output = Path(source_path.name)

    return (output_dir / relative_output).with_suffix(".jpg")


def build_crop_box(row: dict[str, str]) -> tuple[int, int, int, int] | None:
    left = parse_optional_int(row.get("crop_left"))
    top = parse_optional_int(row.get("crop_top"))
    right = parse_optional_int(row.get("crop_right"))
    bottom = parse_optional_int(row.get("crop_bottom"))
    values = [left, top, right, bottom]

    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("Crop requires crop_left, crop_top, crop_right, and crop_bottom together.")

    return int(left), int(top), int(right), int(bottom)


def validate_scale_bar_settings(um_per_px: float | None, bar_um: float | None) -> None:
    if um_per_px is None and bar_um is None:
        return
    if um_per_px is None or bar_um is None:
        raise ValueError("Scale bar requires both um_per_px and bar_um.")
    if um_per_px <= 0 or bar_um <= 0:
        raise ValueError("um_per_px and bar_um must be positive.")


def read_config_table(config_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not config_path.exists():
        raise SystemExit(
            f"Config file not found: {config_path}\n"
            "Run with --init-config first, or create the CSV manually."
        )

    with config_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Config is empty: {config_path}")

        fieldnames = ensure_fieldnames(reader.fieldnames)
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append({name: (row.get(name) or "") for name in fieldnames})

    return fieldnames, rows


def write_config_table(config_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_task_from_row(
    row_number: int,
    row: dict[str, str],
    input_dir: Path,
    output_dir: Path,
) -> ImageTask | None:
    enabled = parse_bool(row.get("enabled"), True)
    filename = (row.get("filename") or "").strip()
    if not filename or not enabled:
        return None

    source_path = resolve_source_path(filename, input_dir)
    output_path = build_output_path(
        source_path=source_path,
        output_name=row.get("output_name") or "",
        input_dir=input_dir,
        output_dir=output_dir,
    )

    crop_box = build_crop_box(row)
    um_per_px = parse_optional_float(row.get("um_per_px"))
    bar_um = parse_optional_float(row.get("bar_um"))
    validate_scale_bar_settings(um_per_px, bar_um)

    show_label = parse_bool(row.get("show_label"), DEFAULT_SHOW_LABEL)
    bar_label = (row.get("bar_label") or "").strip() or None
    if show_label and bar_label is None and bar_um is not None:
        bar_label = format_scale_label(bar_um)

    bar_position = (row.get("bar_position") or DEFAULT_BAR_POSITION).strip().lower()
    if bar_position not in BAR_POSITIONS:
        raise ValueError(f"Unsupported bar_position: {bar_position}")

    return ImageTask(
        row_number=row_number,
        source_path=source_path,
        output_path=output_path,
        brightness=parse_float(row.get("brightness"), DEFAULT_BRIGHTNESS),
        contrast=parse_float(row.get("contrast"), DEFAULT_CONTRAST),
        crop_box=crop_box,
        um_per_px=um_per_px,
        bar_um=bar_um,
        bar_position=bar_position,
        bar_margin=parse_int(row.get("bar_margin"), DEFAULT_BAR_MARGIN),
        bar_thickness=parse_int(row.get("bar_thickness"), DEFAULT_BAR_THICKNESS),
        bar_color=(row.get("bar_color") or DEFAULT_BAR_COLOR).strip() or DEFAULT_BAR_COLOR,
        show_label=show_label,
        bar_label=bar_label,
        label_color=(row.get("label_color") or DEFAULT_LABEL_COLOR).strip() or DEFAULT_LABEL_COLOR,
        label_font_size=parse_int(row.get("label_font_size"), DEFAULT_LABEL_FONT_SIZE),
        jpeg_quality=parse_int(row.get("jpeg_quality"), DEFAULT_JPEG_QUALITY),
    )


def load_config_entries(
    config_path: Path,
    input_dir: Path,
    output_dir: Path,
) -> tuple[list[str], list[dict[str, str]], list[ConfigEntry]]:
    fieldnames, rows = read_config_table(config_path)
    entries: list[ConfigEntry] = []

    for row_index, row in enumerate(rows):
        row_number = row_index + 2
        try:
            task = build_task_from_row(
                row_number=row_number,
                row=row,
                input_dir=input_dir,
                output_dir=output_dir,
            )
        except Exception as exc:
            raise SystemExit(f"Invalid config row {row_number}: {exc}") from exc

        if task is None:
            continue

        entries.append(
            ConfigEntry(
                row_index=row_index,
                row_number=row_number,
                row_data=row,
                task=task,
            )
        )

    return fieldnames, rows, entries


def load_tasks(config_path: Path, input_dir: Path, output_dir: Path) -> list[ImageTask]:
    _, _, entries = load_config_entries(config_path=config_path, input_dir=input_dir, output_dir=output_dir)
    return [entry.task for entry in entries]


def update_row_crop(row: dict[str, str], crop_box: tuple[int, int, int, int] | None) -> None:
    if crop_box is None:
        row["crop_left"] = ""
        row["crop_top"] = ""
        row["crop_right"] = ""
        row["crop_bottom"] = ""
        return

    left, top, right, bottom = crop_box
    row["crop_left"] = str(left)
    row["crop_top"] = str(top)
    row["crop_right"] = str(right)
    row["crop_bottom"] = str(bottom)
