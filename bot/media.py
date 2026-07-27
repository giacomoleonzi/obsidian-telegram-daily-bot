#!/usr/bin/env python3
"""Image compression helpers."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


def compress_image_to_limit(
    image_path: Path,
    max_bytes: int,
    max_dimension: int,
    quality_start: int,
    quality_min: int,
    quality_step: int,
) -> Path:
    """Compress an image with Pillow until it fits under ``max_bytes``.

    Args:
        image_path: Source image path.
        max_bytes: Target maximum file size in bytes.
        max_dimension: Max width/height while resizing.
        quality_start: Initial JPEG quality.
        quality_min: Minimum JPEG quality.
        quality_step: Quality decrement per attempt (must be > 0).

    Returns:
        Path to the (possibly replaced) JPEG file.
    """
    if image_path.stat().st_size <= max_bytes:
        return image_path

    output_path = image_path.with_suffix(".jpg")
    with Image.open(image_path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")

    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    for quality in range(quality_start, quality_min - 1, -quality_step):
        image.save(
            output_path,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        if output_path.stat().st_size <= max_bytes:
            if output_path != image_path and image_path.exists():
                image_path.unlink()
            return output_path

    width, height = image.size
    scaled = image.resize(
        (max(1, int(width * 0.8)), max(1, int(height * 0.8))),
        Image.Resampling.LANCZOS,
    )
    scaled.save(
        output_path,
        format="JPEG",
        quality=quality_min,
        optimize=True,
        progressive=True,
    )
    if output_path != image_path and image_path.exists():
        image_path.unlink()
    return output_path
