"""openclay_icon.py — Generate OpenClay app icon using Pillow.
Creates openclay_512.png, openclay.ico, and attempts openclay.icns on Mac.
"""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).parent
CLAY_BROWN = (92, 61, 46)  # #5C3D2E
WHITE = (255, 255, 255)

def generate_icon(size: int = 512) -> "Image":
    """Generate the OpenClay icon as a PIL Image."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = int(size * 0.43)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CLAY_BROWN)
    # Draw "C" letter
    font_size = int(size * 0.55)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "C", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = cx - tw // 2 - bbox[0]
    ty = cy - th // 2 - bbox[1]
    draw.text((tx, ty), "C", fill=WHITE, font=font)
    # Neural node dot above C
    dot_r = int(size * 0.027)
    dot_x = cx + int(size * 0.08)
    dot_y = cy - int(size * 0.22)
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=WHITE)
    return img

def save_png(output_path: str = "", size: int = 512) -> str:
    """Save as PNG."""
    p = Path(output_path) if output_path else BASE_DIR / "openclay_512.png"
    img = generate_icon(size)
    img.save(str(p), "PNG")
    return str(p)

def save_ico(output_path: str = "") -> str:
    """Save as .ico with multiple sizes."""
    p = Path(output_path) if output_path else BASE_DIR / "openclay.ico"
    sizes = [16, 32, 64, 128, 256]
    icons = [generate_icon(s).resize((s, s)) for s in sizes]
    icons[0].save(str(p), format="ICO", sizes=[(s, s) for s in sizes],
                  append_images=icons[1:])
    return str(p)

def save_icns(output_path: str = "") -> str:
    """Save as .icns using iconutil (Mac only). Returns empty string if unavailable."""
    p = Path(output_path) if output_path else BASE_DIR / "openclay.icns"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            iconset = Path(tmpdir) / "openclay.iconset"
            iconset.mkdir()
            for size in [16, 32, 64, 128, 256, 512]:
                img = generate_icon(size)
                img.save(str(iconset / f"icon_{size}x{size}.png"), "PNG")
                if size <= 256:
                    img2 = generate_icon(size * 2)
                    img2.save(str(iconset / f"icon_{size}x{size}@2x.png"), "PNG")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(p)],
                           capture_output=True, timeout=10, check=True)
        return str(p)
    except (FileNotFoundError, subprocess.CalledProcessError, Exception):
        return ""

def generate_all() -> dict:
    """Generate all icon formats."""
    results = {}
    results["png"] = save_png()
    results["ico"] = save_ico()
    results["icns"] = save_icns()
    return results

# ── Self test ───────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify icon generation produces correct sizes."""
    try:
        from PIL import Image
    except ImportError:
        return True  # Skip if Pillow not installed
    png_path = save_png()
    assert Path(png_path).exists(), "PNG not created"
    img = Image.open(png_path)
    assert img.size == (512, 512), f"PNG wrong size: {img.size}"
    ico_path = save_ico()
    assert Path(ico_path).exists(), "ICO not created"
    return True

if __name__ == "__main__":
    print("self_test:", self_test())
