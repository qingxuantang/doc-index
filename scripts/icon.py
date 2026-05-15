#!/usr/bin/env python3
"""
PWA Icon Generator — Creates simple text-based icons for the doc index PWA.

Usage:
  python3 icon.py <short_name> <color_hex> <output_dir>
  python3 icon.py "Tar" "#8e44ad" /usr/share/nginx/html/tar-docs

Generates icon-192.png and icon-512.png with the first 1-3 characters
of the short_name on a colored background.

Requires: Pillow (pip install Pillow)
Falls back to a simple SVG-to-PNG conversion if Pillow unavailable.
"""

import sys
from pathlib import Path


def hex_to_rgb(hex_color):
    """Convert #RRGGBB to (r, g, b)."""
    c = hex_color.lstrip("#")
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))


def generate_with_pillow(text, color, sizes, output_dir):
    """Generate icons using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    rgb = hex_to_rgb(color)

    for size in sizes:
        img = Image.new("RGB", (size, size), rgb)
        draw = ImageDraw.Draw(img)

        # Try to find a suitable font
        font_size = int(size * 0.45)
        font = None
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for fp in font_paths:
            if Path(fp).exists():
                try:
                    font = ImageFont.truetype(fp, font_size)
                    break
                except Exception:
                    continue
        if font is None:
            font = ImageFont.load_default()

        # Center text
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (size - tw) / 2 - bbox[0]
        y = (size - th) / 2 - bbox[1]

        draw.text((x, y), text, fill="white", font=font)

        output_path = Path(output_dir) / f"icon-{size}.png"
        img.save(output_path, "PNG")
        print(f"Generated: {output_path}")


def generate_with_svg(text, color, sizes, output_dir):
    """Fallback: generate SVG files (no Pillow needed)."""
    for size in sizes:
        font_size = int(size * 0.4)
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">
  <rect width="{size}" height="{size}" fill="{color}" rx="{int(size*0.15)}"/>
  <text x="50%" y="55%" text-anchor="middle" dominant-baseline="middle"
        font-family="system-ui, sans-serif" font-weight="bold"
        font-size="{font_size}" fill="white">{text}</text>
</svg>'''
        # Try converting SVG to PNG with cairosvg or rsvg-convert
        svg_path = Path(output_dir) / f"icon-{size}.svg"
        png_path = Path(output_dir) / f"icon-{size}.png"

        with open(svg_path, "w") as f:
            f.write(svg)

        converted = False
        # Try cairosvg
        try:
            import cairosvg
            cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png_path),
                            output_width=size, output_height=size)
            svg_path.unlink()
            converted = True
            print(f"Generated (cairosvg): {png_path}")
        except ImportError:
            pass

        # Try rsvg-convert
        if not converted:
            import subprocess
            result = subprocess.run(
                ["rsvg-convert", "-w", str(size), "-h", str(size), str(svg_path), "-o", str(png_path)],
                capture_output=True
            )
            if result.returncode == 0:
                svg_path.unlink()
                converted = True
                print(f"Generated (rsvg): {png_path}")

        if not converted:
            print(f"Generated SVG (no PNG converter found): {svg_path}")
            print("  Install Pillow (pip install Pillow) or librsvg2-bin for PNG output")


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 icon.py <short_name> <color_hex> <output_dir>")
        print('Example: python3 icon.py "Tar" "#8e44ad" /tmp/output')
        sys.exit(1)

    text = sys.argv[1][:3]  # Max 3 chars
    color = sys.argv[2]
    output_dir = sys.argv[3]

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    sizes = [192, 512]

    try:
        generate_with_pillow(text, color, sizes, output_dir)
    except ImportError:
        print("Pillow not available, trying SVG fallback...")
        generate_with_svg(text, color, sizes, output_dir)


if __name__ == "__main__":
    main()
