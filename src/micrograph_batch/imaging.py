"""Image operations: bit-depth normalisation, cropping, and scale bars."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def clamp_crop_box(crop_box: tuple[int, int, int, int], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    left, top, right, bottom = crop_box
    clamped = (
        clamp(left, 0, max(width - 1, 0)),
        clamp(top, 0, max(height - 1, 0)),
        clamp(right, 1, width),
        clamp(bottom, 1, height),
    )

    if clamped[0] >= clamped[2] or clamped[1] >= clamped[3]:
        raise ValueError(f"Invalid crop box after clamping: {clamped} for image size {image_size}")

    return clamped


def crop_box_to_xywh(crop_box: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    if crop_box is None:
        return None
    left, top, right, bottom = crop_box
    return left, top, right - left, bottom - top


def xywh_to_crop_box(x: int, y: int, width: int, height: int) -> tuple[int, int, int, int]:
    return x, y, x + width, y + height


def boxes_equal(
    first: tuple[int, int, int, int] | None,
    second: tuple[int, int, int, int] | None,
) -> bool:
    return first == second


def normalize_to_8bit_grayscale(image: Image.Image) -> Image.Image:
    """Min-max stretch a high-bit-depth frame into displayable 8-bit grayscale.

    Scientific cameras typically write 12/16-bit TIFFs whose values occupy a
    narrow band of the full range; saved directly to JPEG they render black.
    """
    working = image.convert("F")
    low, high = working.getextrema()
    if high <= low:
        color = 255 if high > 0 else 0
        return Image.new("L", image.size, color)

    scale = 255.0 / (high - low)
    return working.point(lambda value: (value - low) * scale).convert("L")


def prepare_image_for_jpeg(image_path: Path) -> Image.Image:
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        image.load()

    if image.mode in {"I;16", "I;16B", "I;16L", "I", "F"}:
        image = normalize_to_8bit_grayscale(image).convert("RGB")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    return image


def format_scale_label(bar_um: float) -> str:
    return f"{bar_um:g} um"


_FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    # Windows
    "arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
]


def load_font(font_size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, font_size)
        except OSError:
            continue
    return ImageFont.load_default()


def scale_bar_length_px(bar_um: float, um_per_px: float) -> int:
    return max(1, int(round(bar_um / um_per_px)))


def add_scale_bar(
    image: Image.Image,
    um_per_px: float,
    bar_um: float,
    position: str,
    margin: int,
    thickness: int,
    color: str,
    show_label: bool,
    label: str | None,
    label_color: str,
    label_font_size: int,
) -> Image.Image:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    bar_px = scale_bar_length_px(bar_um, um_per_px)

    if margin < 0:
        raise ValueError("bar_margin must be non-negative.")

    if thickness <= 0:
        raise ValueError("bar_thickness must be positive.")

    if bar_px > width - 2 * margin:
        raise ValueError(
            f"Scale bar is too wide for the image. bar_px={bar_px}, width={width}, margin={margin}"
        )

    if thickness > height - 2 * margin:
        raise ValueError(
            f"Scale bar is too tall for the image. thickness={thickness}, height={height}, margin={margin}"
        )

    if position == "bottom-right":
        x2 = width - margin
        x1 = x2 - bar_px
        y2 = height - margin
        y1 = y2 - thickness
    elif position == "bottom-left":
        x1 = margin
        x2 = x1 + bar_px
        y2 = height - margin
        y1 = y2 - thickness
    elif position == "top-right":
        x2 = width - margin
        x1 = x2 - bar_px
        y1 = margin
        y2 = y1 + thickness
    else:
        x1 = margin
        x2 = x1 + bar_px
        y1 = margin
        y2 = y1 + thickness

    draw.rectangle([x1, y1, x2, y2], fill=color)

    if show_label and label:
        font = load_font(label_font_size)
        try:
            text_box = draw.textbbox((0, 0), label, font=font)
        except AttributeError:
            text_width, text_height = draw.textsize(label, font=font)
            text_box = (0, 0, text_width, text_height)

        # draw.text() anchors at the layout-box origin, which sits above the
        # visible ink by text_box[1] px — compensate so the gap to the bar is
        # measured from the ink itself, not the layout box.
        ink_left, ink_top, ink_right, ink_bottom = text_box
        text_width = ink_right - ink_left
        text_height = ink_bottom - ink_top
        gap = 6
        text_x = x1 + max(0, (bar_px - text_width) // 2) - ink_left

        if position.startswith("bottom"):
            ink_target_top = max(0, y1 - text_height - gap)
        else:
            ink_target_top = min(height - text_height, y2 + gap)

        draw.text((text_x, ink_target_top - ink_top), label, fill=label_color, font=font)

    return image


def save_as_jpeg(image: Image.Image, output_path: Path, quality: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jpeg_quality = clamp(quality, 1, 100)
    image.save(output_path, format="JPEG", quality=jpeg_quality)
