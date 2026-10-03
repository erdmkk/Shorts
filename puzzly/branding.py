from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw

from .config import BRANDING_DIR, PALETTES
from .visuals.effects import rounded_surface
from .visuals.text import font


PROFILE_PHOTO = BRANDING_DIR / "profile.jpg"  # the channel's profile picture (the same as on Instagram and YouTube)


@lru_cache(maxsize=16)
def _profile_disc(diameter: int) -> Image.Image | None:
    """The profile photo cut to a circle exactly as the social apps do: the centred square of the picture, round, antialiased."""
    if not PROFILE_PHOTO.exists():
        return None
    with Image.open(PROFILE_PHOTO) as photo:
        photo = photo.convert("RGB")
    side = min(photo.size)
    left, top = (photo.width - side) // 2, (photo.height - side) // 2
    square = photo.crop((left, top, left + side, top + side))
    big = diameter * 4  # cut at 4x, then shrink once, so the edge is smooth
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    disc = square.resize((big, big), Image.Resampling.LANCZOS).convert("RGBA")
    disc.putalpha(mask)
    ring = ImageDraw.Draw(disc)
    ring.ellipse((0, 0, big - 1, big - 1), outline=(255, 255, 255, 70), width=max(2, big // 40))  # a thin rim, as on Instagram
    return disc.resize((diameter, diameter), Image.Resampling.LANCZOS)


def draw_profile_mark(image: Image.Image, center: tuple[int, int], diameter: int,
                      palette: dict[str, str] | None = None) -> None:
    """The channel's round profile photo next to `Puzzly for You` on the end cards (the generic mark if the photo is missing)."""
    disc = _profile_disc(max(8, diameter))
    if disc is None:
        draw_brand_mark(image, center, diameter, palette, symbol=None)
        return
    image.paste(disc, (center[0] - disc.width // 2, center[1] - disc.height // 2), disc)


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
