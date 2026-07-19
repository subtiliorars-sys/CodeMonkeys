"""
Generate desktop/codemonkeys.ico from the design in desktop/icon.svg.
Requires Pillow. Usage: python scripts/generate-icon.py
"""
from PIL import Image, ImageDraw
import math

SIZE = 256
OUTPUT = "desktop/codemonkeys.ico"

def h2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def fcircle(img, cx, cy, r, color):
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

def fellipse(img, cx, cy, rx, ry, color):
    d = ImageDraw.Draw(img)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=color)

def draw_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / SIZE
    cx, cy = size / 2, size / 2
    r_bg = int(120 * s)
    top = h2rgb("#fbbf24")
    bot = h2rgb("#d97706")

    # Gradient background circle — horizontal slices
    for yy in range(int(cy - r_bg), int(cy + r_bg) + 1):
        dy = yy - cy
        if abs(dy) > r_bg:
            continue
        dx = int(math.sqrt(max(0, r_bg * r_bg - dy * dy)))
        xl, xr = max(0, int(cx - dx)), min(size - 1, int(cx + dx))
        if xl >= xr:
            continue
        f = max(0, min(1, (yy - (cy - r_bg)) / (2 * r_bg)))
        rgb = tuple(int((1 - f) * top[i] + f * bot[i]) for i in range(3))
        for xx in range(xl, xr + 1):
            img.putpixel((xx, yy), rgb + (255,))

    brown = h2rgb("#4b2e1c")
    inner = h2rgb("#6b3f2a")
    black = (28, 28, 28, 255)
    white = (255, 255, 255, 255)

    # Ears
    for ecx, ecy in [(int(60 * s), int(100 * s)), (int(196 * s), int(100 * s))]:
        fcircle(img, ecx, ecy, int(24 * s), brown)
        fcircle(img, ecx, ecy, int(14 * s), inner)

    # Face
    fellipse(img, cx, int(148 * s), int(64 * s), int(56 * s), brown)

    # Eyes
    for ecx, ecy in [(int(100 * s), int(108 * s)), (int(156 * s), int(108 * s))]:
        fcircle(img, ecx, ecy, int(14 * s), black)
        fcircle(img, int(ecx - 6 * s), int(ecy - 6 * s), int(5 * s), white)

    # Nostrils
    for ncx in [int(118 * s), int(138 * s)]:
        fellipse(img, ncx, int(150 * s), int(6 * s), int(4 * s), black)

    # Mouth arc
    my = int(168 * s)
    draw.arc(
        [(int(108 * s), my - int(10 * s)), (int(148 * s), my + int(20 * s))],
        start=200, end=340, fill=black, width=max(1, int(3 * s))
    )

    return img


def main():
    master = draw_icon(SIZE)
    master.save("desktop/icon-256.png", "PNG")
    print(f"Saved desktop/icon-256.png ({SIZE}x{SIZE})")

    sizes = [256, 64, 48, 32, 16]
    frames = [master if s == SIZE else draw_icon(s) for s in sizes]
    frames[0].save(OUTPUT, format="ICO",
                   sizes=[(s, s) for s in sizes],
                   append_images=frames[1:])
    print(f"Saved {OUTPUT} with sizes: {sizes}")


if __name__ == "__main__":
    main()
