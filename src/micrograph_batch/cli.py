"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from micrograph_batch import __version__
from micrograph_batch.batch import run_batch
from micrograph_batch.config import load_tasks, write_starter_config
from micrograph_batch.constants import DEFAULT_CONFIG, DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="micrograph-batch",
        description=(
            "Batch-process microscopy images from a CSV config. "
            "Supports TIFF to JPG conversion, crop, brightness, contrast, per-image scale bars, "
            "and visual crop selection."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="CSV config path.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Base folder for relative filenames in the CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where processed JPG files will be written.",
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Scan subfolders when generating a starter config.",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Generate a starter config by scanning --input-dir and then exit.",
    )
    parser.add_argument(
        "--visual-crop",
        action="store_true",
        help="Open a visual crop tool and save crop coordinates back into the CSV config.",
    )
    parser.add_argument(
        "--auto-process-after-crop",
        action="store_true",
        help="After visual crop mode closes, run the full batch automatically.",
    )
    parser.add_argument(
        "--overwrite-config",
        action="store_true",
        help="Allow --init-config to replace an existing CSV config.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output JPG files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config_path = args.config.expanduser()
    input_dir = args.input_dir.expanduser()
    output_dir = args.output_dir.expanduser()

    if args.init_config:
        write_starter_config(
            config_path=config_path,
            input_dir=input_dir,
            recursive=args.recursive,
            overwrite=args.overwrite_config,
        )
        return

    if args.visual_crop:
        # Imported lazily so headless environments without Tkinter still work.
        from micrograph_batch.visual_crop import visual_crop_mode

        visual_crop_mode(
            config_path=config_path,
            input_dir=input_dir,
            output_dir=output_dir,
            auto_process_after_crop=args.auto_process_after_crop,
            overwrite=args.overwrite,
        )
        return

    tasks = load_tasks(config_path=config_path, input_dir=input_dir, output_dir=output_dir)
    if not tasks:
        raise SystemExit(
            f"No enabled rows found in {config_path}. "
            "Fill the CSV first or regenerate it with --init-config."
        )

    run_batch(tasks=tasks, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
