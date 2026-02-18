"""Generate HotMic app icon — wireframe mic with red hot dot.

Requires Pillow: pip install Pillow
"""

from PIL import Image, ImageDraw
import math


SIZE = 256


def draw_icon(size):
    """Draw the HotMic icon at the given size."""
    s = SIZE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = s // 2, s // 2
    stroke = int(s * 0.045)  # thick strokes for visibility at small sizes
    dark = (50, 50, 55, 255)  # near-black for wireframe

    # ── Microphone outline (pill shape) ──
    mic_w = s * 0.30
    mic_h = s * 0.44
    mic_top = s * 0.08
    mic_r = mic_w / 2

    draw.rounded_rectangle(
        [cx - mic_w / 2, mic_top, cx + mic_w / 2, mic_top + mic_h],
        radius=mic_r,
        outline=dark,
        width=stroke,
    )

    # Horizontal lines inside mic head (grille detail)
    grille_top = mic_top + mic_h * 0.25
    grille_bot = mic_top + mic_h * 0.65
    num_lines = 3
    for i in range(num_lines):
        t = i / (num_lines - 1)
        y = grille_top + t * (grille_bot - grille_top)
        # Width of line at this y position (follows pill curvature)
        # Pill is a rectangle with semicircle caps
        rect_top = mic_top + mic_r
        rect_bot = mic_top + mic_h - mic_r
        if y < rect_top:
            dy = rect_top - y
            hw = math.sqrt(max(0, mic_r * mic_r - dy * dy))
        elif y > rect_bot:
            dy = y - rect_bot
            hw = math.sqrt(max(0, mic_r * mic_r - dy * dy))
        else:
            hw = mic_w / 2
        inset = stroke * 1.5
        if hw > inset:
            draw.line(
                [cx - hw + inset, y, cx + hw - inset, y],
                fill=dark,
                width=max(2, stroke // 2),
            )

    # ── Arc (U-shape holder) ──
    arc_w = s * 0.44
    arc_top_y = mic_top + mic_h * 0.45
    arc_bot_y = mic_top + mic_h + s * 0.08

    draw.arc(
        [cx - arc_w / 2, arc_top_y, cx + arc_w / 2, arc_bot_y + (arc_bot_y - arc_top_y) * 0.4],
        start=0,
        end=180,
        fill=dark,
        width=stroke,
    )

    # ── Stand (vertical line) ──
    stand_top = arc_bot_y + (arc_bot_y - arc_top_y) * 0.4 * 0.45
    stand_bot = stand_top + s * 0.10
    draw.line(
        [cx, stand_top, cx, stand_bot],
        fill=dark,
        width=stroke,
    )

    # ── Base ──
    base_w = s * 0.22
    draw.line(
        [cx - base_w / 2, stand_bot, cx + base_w / 2, stand_bot],
        fill=dark,
        width=stroke,
    )

    # ── Red "hot" recording dot (upper right) ──
    dot_r = s * 0.055
    dot_cx = cx + s * 0.32
    dot_cy = s * 0.12

    # Glow behind dot
    for i in range(6, 0, -1):
        r = dot_r + i * 2.5
        alpha = int(35 - i * 5)
        draw.ellipse(
            [dot_cx - r, dot_cy - r, dot_cx + r, dot_cy + r],
            fill=(255, 50, 50, max(0, alpha)),
        )

    # Solid red dot
    draw.ellipse(
        [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
        fill=(230, 45, 45, 255),
    )
    # Highlight
    hl_r = dot_r * 0.3
    draw.ellipse(
        [dot_cx - hl_r - 1, dot_cy - hl_r - 1, dot_cx + hl_r - 1, dot_cy + hl_r - 1],
        fill=(255, 180, 180, 200),
    )

    if size != s:
        img = img.resize((size, size), Image.LANCZOS)

    return img


def save_ico(path):
    """Save a single 256x256 .ico file."""
    img = draw_icon(256)
    img.save(path, format="ICO", sizes=[(256, 256)])
    print(f"Saved {path} (256x256)")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "hotmic.ico"
    save_ico(str(out))

    preview = out.with_suffix(".png")
    draw_icon(256).save(str(preview))
    print(f"Preview: {preview}")
