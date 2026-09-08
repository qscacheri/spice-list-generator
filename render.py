#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path


def parse_point(value: str) -> tuple[int, int]:
    try:
        x, y = value.split(",")
        return int(x.strip()), int(y.strip())
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("point must be two integers, for example 100,100")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer")
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def find_font(name: str):
    normalized_name = "".join(character for character in name.lower() if character.isalnum())
    if not normalized_name:
        return None
    matches = []
    font_directories = [
        Path.home() / "Library/Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path.home() / ".local/share/fonts",
        Path("/usr/local/share/fonts"),
        Path("/usr/share/fonts"),
    ]

    for directory in font_directories:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.suffix.lower() not in {".otf", ".ttc", ".ttf"}:
                continue
            normalized_stem = "".join(
                character for character in path.stem.lower() if character.isalnum()
            )
            if normalized_stem == normalized_name:
                return path
            if normalized_stem.startswith(normalized_name):
                matches.append((len(normalized_stem), str(path), path))

    return min(matches)[2] if matches else None


def small_caps_runs(text: str):
    runs = []
    for character in text:
        is_small = character.islower()
        rendered_character = character.upper() if is_small else character
        if runs and runs[-1][0] == is_small:
            runs[-1] = (is_small, runs[-1][1] + rendered_character)
        else:
            runs.append((is_small, rendered_character))
    return runs


def output_name(text: str) -> str:
    return text.replace("/", "_").replace("\\", "_") + ".png"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render each line of a text file onto an image."
    )
    parser.add_argument("-s", required=True, type=Path, help="newline-separated text file")
    parser.add_argument("-i", required=True, type=Path, help="source image")
    parser.add_argument("-o", required=True, type=Path, help="output folder")
    parser.add_argument(
        "-p", required=True, type=parse_point, help="center point, for example 100,100"
    )
    parser.add_argument(
        "-z",
        "--font-size",
        type=positive_int,
        default=48,
        help="font size in pixels (default: 48)",
    )
    parser.add_argument(
        "-c", "--font-color", default="black", help="text color name or hex value (default: black)"
    )
    parser.add_argument(
        "-f", "--font-name", help="font file path or name (default: Pillow's built-in font)"
    )
    parser.add_argument(
        "--small-caps", action="store_true", help="enable the font's OpenType small-caps feature"
    )
    args = parser.parse_args()

    try:
        from PIL import Image, ImageColor, ImageDraw, ImageFont
    except ImportError:
        parser.error("Pillow is required; install dependencies with: uv sync")

    try:
        ImageColor.getrgb(args.font_color)
    except ValueError:
        parser.error(f"invalid font color: {args.font_color!r}")

    resolved_font = args.font_name
    if args.font_name:
        try:
            font = ImageFont.truetype(args.font_name, args.font_size)
        except OSError as error:
            resolved_font = find_font(args.font_name)
            if resolved_font is None:
                parser.error(f"could not load font {args.font_name!r}: {error}")
            font = ImageFont.truetype(resolved_font, args.font_size)
    else:
        font = ImageFont.load_default(size=args.font_size)

    small_caps_size = max(1, round(args.font_size * 0.75))
    if args.small_caps:
        small_caps_font = (
            ImageFont.truetype(resolved_font, small_caps_size)
            if resolved_font
            else ImageFont.load_default(size=small_caps_size)
        )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    args.o.mkdir(parents=True, exist_ok=True)
    logger.info("Output folder: %s", args.o.resolve())

    with args.s.open(encoding="utf-8") as source:
        items = [line.rstrip("\r\n") for line in source]
    logger.info("Loaded %d text items from %s", len(items), args.s)
    logger.info(
        "Using %s text at %d px with font %s",
        args.font_color,
        args.font_size,
        resolved_font or "Pillow default",
    )
    if args.small_caps:
        logger.info("Synthetic small caps enabled at %d px", small_caps_size)
    line_spacing = max(4, round(args.font_size * 0.2))
    logger.info("Rendering one word per line with %d px spacing", line_spacing)

    with Image.open(args.i) as source_image:
        source_image.load()
        logger.info(
            "Opened source image %s (%dx%d, mode %s)",
            args.i,
            source_image.width,
            source_image.height,
            source_image.mode,
        )
        logger.info("Centering text on point (%d, %d)", *args.p)
        if not (0 <= args.p[0] < source_image.width and 0 <= args.p[1] < source_image.height):
            logger.warning("The center point is outside the source image")

        for index, item in enumerate(items, start=1):
            image = source_image.copy()
            draw = ImageDraw.Draw(image)
            lines = item.split() or [""]
            if args.small_caps:
                measured_lines = []
                bounds = None
                ascent, descent = font.getmetrics()
                line_advance = ascent + descent + line_spacing
                for line_index, line in enumerate(lines):
                    measured_runs = []
                    cursor = 0.0
                    line_bounds = None
                    for is_small, run_text in small_caps_runs(line):
                        run_font = small_caps_font if is_small else font
                        run_bounds = draw.textbbox(
                            (cursor, 0), run_text, font=run_font, anchor="ls"
                        )
                        line_bounds = (
                            run_bounds
                            if line_bounds is None
                            else (
                                min(line_bounds[0], run_bounds[0]),
                                min(line_bounds[1], run_bounds[1]),
                                max(line_bounds[2], run_bounds[2]),
                                max(line_bounds[3], run_bounds[3]),
                            )
                        )
                        measured_runs.append((cursor, run_text, run_font))
                        cursor += draw.textlength(run_text, font=run_font)
                    line_bounds = line_bounds or (0, 0, 0, 0)
                    line_x = -(line_bounds[0] + line_bounds[2]) / 2
                    baseline = line_index * line_advance
                    positioned_bounds = (
                        line_bounds[0] + line_x,
                        line_bounds[1] + baseline,
                        line_bounds[2] + line_x,
                        line_bounds[3] + baseline,
                    )
                    bounds = (
                        positioned_bounds
                        if bounds is None
                        else (
                            min(bounds[0], positioned_bounds[0]),
                            min(bounds[1], positioned_bounds[1]),
                            max(bounds[2], positioned_bounds[2]),
                            max(bounds[3], positioned_bounds[3]),
                        )
                    )
                    measured_lines.append((line_x, baseline, measured_runs))
                bounds = bounds or (0, 0, 0, 0)
                x = args.p[0]
                y = args.p[1] - (bounds[1] + bounds[3]) / 2
            else:
                rendered_text = "\n".join(lines)
                bounds = draw.multiline_textbbox(
                    (0, 0), rendered_text, font=font, spacing=line_spacing, align="center"
                )
                x = args.p[0] - (bounds[0] + bounds[2]) / 2
                y = args.p[1] - (bounds[1] + bounds[3]) / 2
            output_path = args.o / output_name(item)
            logger.info(
                "[%d/%d] Rendering %r as %d lines at (%.1f, %.1f), bounds=%s",
                index,
                len(items),
                item,
                len(lines),
                x,
                y,
                bounds,
            )
            if args.small_caps:
                for line_x, baseline, measured_runs in measured_lines:
                    for cursor, run_text, run_font in measured_runs:
                        draw.text(
                            (x + line_x + cursor, y + baseline),
                            run_text,
                            fill=args.font_color,
                            font=run_font,
                            anchor="ls",
                        )
            else:
                draw.multiline_text(
                    (x, y),
                    rendered_text,
                    fill=args.font_color,
                    font=font,
                    spacing=line_spacing,
                    align="center",
                )
            image.save(output_path, format="PNG")
            logger.info("[%d/%d] Wrote %s", index, len(items), output_path)


if __name__ == "__main__":
    main()
