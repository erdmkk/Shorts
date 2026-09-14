from __future__ import annotations

from PIL import Image, ImageDraw

from .config import BRANDING_DIR, PALETTES
from .visuals.effects import rounded_surface
from .visuals.text import font


def draw_brand_mark(image: Image.Image, center: tuple[int, int], diameter: int,
                    palette: dict[str, str] | None = None, symbol: str | None = "?") -> None:
    palette = palette or PALETTES[0]
    logo_path = BRANDING_DIR / "logo.png"
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((diameter * 2, diameter * 2), Image.Resampling.LANCZOS)
        image.paste(logo, (center[0] - logo.width // 2, center[1] - logo.height // 2), logo)
        return
    draw = ImageDraw.Draw(image)
    x, y = center
    r = diameter // 2
    rounded_surface(image, (x - r, y - r, x + r, y + r), r // 5, palette["primary"], palette["outline"], max(3, diameter // 25))
    knob = r // 3
    draw.ellipse((x - knob, y - r - knob // 2, x + knob, y - r + knob * 3 // 2), fill=palette["primary"], outline=palette["outline"], width=max(3, diameter // 25))
    if symbol:
        draw.text((x, y), symbol, font=font(int(diameter * 0.75)), fill=palette["text_light"], anchor="mm")
