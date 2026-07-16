"""Batch execution: apply each ImageTask and report a summary."""

from __future__ import annotations

from PIL import ImageEnhance

from micrograph_batch.config import ImageTask
from micrograph_batch.imaging import (
    add_scale_bar,
    clamp_crop_box,
    prepare_image_for_jpeg,
    save_as_jpeg,
)


def process_task(task: ImageTask, overwrite: bool) -> None:
    if task.output_path.exists() and not overwrite:
        print(f"Skip existing: {task.output_path}")
        return

    if not task.source_path.exists():
        raise FileNotFoundError(f"Missing file: {task.source_path}")

    image = prepare_image_for_jpeg(task.source_path)

    if task.crop_box is not None:
        image = image.crop(clamp_crop_box(task.crop_box, image.size))

    if task.brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(task.brightness)

    if task.contrast != 1.0:
        image = ImageEnhance.Contrast(image).enhance(task.contrast)

    if task.um_per_px is not None and task.bar_um is not None:
        image = add_scale_bar(
            image=image,
            um_per_px=task.um_per_px,
            bar_um=task.bar_um,
            position=task.bar_position,
            margin=task.bar_margin,
            thickness=task.bar_thickness,
            color=task.bar_color,
            show_label=task.show_label,
            label=task.bar_label,
            label_color=task.label_color,
            label_font_size=task.label_font_size,
        )

    save_as_jpeg(image, task.output_path, task.jpeg_quality)
    print(f"Saved: {task.output_path}")


def run_batch(tasks: list[ImageTask], overwrite: bool) -> None:
    processed = 0
    failed = 0

    for task in tasks:
        try:
            process_task(task, overwrite=overwrite)
            processed += 1
        except Exception as exc:
            failed += 1
            print(f"Failed at row {task.row_number}: {task.source_path} -> {exc}")

    print("-" * 60)
    print(f"Finished. Processed={processed}, Failed={failed}")
    print("-" * 60)
