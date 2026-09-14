import inspect

from PIL import Image

import puzzly.visuals.effects as effects
from puzzly.visuals.effects import rounded_surface, rounded_surface_metrics


def test_radius_and_border_scale_with_local_supersampling() -> None:
    one = rounded_surface_metrics((10, 10, 190, 110), 24, 5, 1)
    four = rounded_surface_metrics((10, 10, 190, 110), 24, 5, 4)
    assert four["radius_px"] == one["radius_px"] * 4
    assert four["border_px"] == one["border_px"] * 4


def test_rounded_surface_is_bounded_antialiased_and_not_clipped() -> None:
    image = Image.new("RGB", (220, 140), "#DFF7F2")
    rounded_surface(image, (20.5, 20.5, 199.5, 119.5), 34, "#FFFDF7", "#244653", 6, shadow=True, local_scale=4)
    assert image.getpixel((0, 0)) == (223, 247, 242)
    assert image.getpixel((110, 70)) == (255, 253, 247)
    # LANCZOS produces intermediate edge pixels rather than a one-bit staircase.
    colors = {image.getpixel((x, y)) for x in range(15, 55) for y in range(15, 55)}
    assert len(colors) > 12
    assert "Image.Resampling.LANCZOS" in inspect.getsource(effects)


def test_excessive_radius_is_safely_clamped_inside_bounds() -> None:
    metrics = rounded_surface_metrics((0, 0, 100, 40), 200, 8, 2)
    assert metrics["radius_px"] == 40
    assert metrics["border_px"] == 16
