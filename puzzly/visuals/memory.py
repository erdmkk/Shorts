from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..config import (MEMORY_ANSWER_FLIP, MEMORY_ANSWER_HIGHLIGHT, MEMORY_BOARD_ENTRANCE,
                      MEMORY_COMPLETED_HOLD, MEMORY_COVER_DURATION, MEMORY_FINAL_DELAY,
                      MEMORY_FINAL_FLIP, MEMORY_MEMORIZATION_DURATION, MEMORY_QUESTION_DURATION,
                      MEMORY_TARGET_ENTRANCE, MEMORY_THINKING_DURATION)
from ..models import RoundSpec
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import draw_progress_bar, draw_sparkles, rounded_surface
from .layout import scale_point
from .text import font

POSITIONS = ((250, 930), (540, 930), (830, 930), (395, 1290), (685, 1290))
SHAPE_SAFE_BOUNDS = (0.09, 0.09, 0.91, 0.91)
SHAPE_LAYOUT = {
    "circle": (0.94, 0.000, 0.000), "square": (0.91, 0.000, 0.000),
    "triangle": (0.96, 0.000, 0.028), "star": (0.96, 0.000, 0.012),
    "hexagon": (0.94, 0.000, 0.000), "heart": (0.95, 0.000, 0.018),
    "diamond": (0.93, 0.000, 0.000), "pentagon": (0.95, 0.000, 0.012),
}


def _scaled(value: float, size: tuple[int, int]) -> int:
    return max(1, round(value * size[0] / 1080))


def _bounds(values: tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    a = scale_point((values[0], values[1]), size); b = scale_point((values[2], values[3]), size)
    return a[0], a[1], b[0], b[1]


def memory_state(local: float, item: RoundSpec) -> dict[str, object]:
    cover_start = MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION
    questions_start = cover_start + MEMORY_COVER_DURATION
    order = item.data["question_order"]
    if local < MEMORY_BOARD_ENTRANCE:
        return {"phase": "entrance", "open_positions": (), "timer_active": False}
    if local < cover_start:
        return {"phase": "memorize", "open_positions": tuple(range(1, 6)), "timer_active": False}
    if local < questions_start:
        return {"phase": "cover", "open_positions": (), "timer_active": False}
    for question_index, position in enumerate(order):
        start = questions_start + question_index * MEMORY_QUESTION_DURATION
        end = start + MEMORY_QUESTION_DURATION
        if local < end:
            relative = max(0.0, local - start)
            think_start = MEMORY_TARGET_ENTRANCE
            reveal_start = think_start + MEMORY_THINKING_DURATION
            flip_start = reveal_start + MEMORY_ANSWER_HIGHLIGHT
            if relative < reveal_start:
                phase = "question"
            elif relative < flip_start:
                phase = "highlight"
            else:
                phase = "answer_reveal"
            opened = list(order[:question_index])
            if relative >= flip_start + MEMORY_ANSWER_FLIP / 2:
                opened.append(position)
            return {"phase": phase, "question_index": question_index, "target_position": position,
                    "open_positions": tuple(opened), "timer_active": think_start <= relative < reveal_start,
                    "relative": relative}
    final_start = questions_start + 4 * MEMORY_QUESTION_DURATION
    relative = local - final_start; opened = list(order)
    if relative < MEMORY_FINAL_DELAY:
        phase = "final_wait"
    elif relative < MEMORY_FINAL_DELAY + MEMORY_FINAL_FLIP:
        phase = "final_reveal"
        if relative >= MEMORY_FINAL_DELAY + MEMORY_FINAL_FLIP / 2:
            opened.append(item.data["final_position"])
    else:
        phase = "completed"; opened.append(item.data["final_position"])
    return {"phase": phase, "open_positions": tuple(opened), "timer_active": False, "relative": relative}


def _regular_polygon(sides: int, center: float, radius: float, rotation: float = -math.pi / 2) -> list[tuple[float, float]]:
    return [(center + radius * math.cos(rotation + i * 2 * math.pi / sides),
             center + radius * math.sin(rotation + i * 2 * math.pi / sides)) for i in range(sides)]


def token_layout(shape: str, size: int) -> dict[str, object]:
    scale, offset_x, offset_y = SHAPE_LAYOUT[shape]
    safe = size * .70 * scale
    center = (size * (.5 + offset_x), size * (.475 + offset_y))
    return {"content_size": safe, "optical_center": center, "scale": scale,
            "offset": (offset_x, offset_y)}


def _raw_shape_mask(shape: str, size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0); draw = ImageDraw.Draw(mask)
    p, q, c, r = size * .08, size * .92, size / 2, size * .41
    if shape == "circle": draw.ellipse((p, p, q, q), fill=255)
    elif shape == "square": draw.rounded_rectangle((p, p, q, q), radius=round(size * .055), fill=255)
    elif shape == "triangle": draw.polygon(_regular_polygon(3, c, r, -math.pi / 2), fill=255)
    elif shape == "diamond": draw.polygon(_regular_polygon(4, c, r, 0), fill=255)
    elif shape == "pentagon": draw.polygon(_regular_polygon(5, c, r), fill=255)
    elif shape == "hexagon": draw.polygon(_regular_polygon(6, c, r), fill=255)
    elif shape == "star":
        points = [(c + (r if i % 2 == 0 else r * .43) * math.cos(-math.pi/2 + i*math.pi/5),
                   c + (r if i % 2 == 0 else r * .43) * math.sin(-math.pi/2 + i*math.pi/5)) for i in range(10)]
        draw.polygon(points, fill=255)
    elif shape == "heart":
        points = []
        for i in range(181):
            t = 2 * math.pi * i / 180
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t)
            points.append((c + x * size / 43, c - y * size / 43 + size * .04))
        draw.polygon(points, fill=255)
    else: raise ValueError(f"unsupported memory shape: {shape}")
    return mask


def shape_mask(shape: str, size: int) -> Image.Image:
    raw = _raw_shape_mask(shape, size); box = raw.getbbox()
    if box is None: raise ValueError(f"empty memory shape: {shape}")
    content = raw.crop(box); layout = token_layout(shape, size); target = float(layout["content_size"])
    factor = min(target/content.width, target/content.height)
    resized = content.resize((round(content.width*factor), round(content.height*factor)), Image.Resampling.LANCZOS)
    center_x, center_y = layout["optical_center"]
    left, top = round(center_x-resized.width/2), round(center_y-resized.height/2)
    result = Image.new("L", (size,size), 0); result.paste(resized,(left,top)); return result


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#"); return tuple(int(raw[i:i+2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=128)
def token_image(shape: str, color_value: str, size: int) -> Image.Image:
    high_size = size * 2; mask = shape_mask(shape, high_size)
    base = _rgb(color_value)
    top = tuple(min(255, round(channel * .82 + 255 * .18)) for channel in base)
    bottom = tuple(max(0, round(channel * .82)) for channel in base)
    strip = Image.new("RGBA", (1, high_size))
    strip.putdata([tuple(round(top[c] + (bottom[c] - top[c]) * y / (high_size - 1)) for c in range(3)) + (255,) for y in range(high_size)])
    gradient = strip.resize((high_size, high_size))
    result = Image.new("RGBA", (high_size, high_size), (0,0,0,0))
    shadow = Image.new("RGBA", result.size, (0,0,0,0)); shadow_mask = Image.new("L", result.size, 0)
    shadow_mask.paste(mask, (0, round(high_size*.025))); shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(high_size*.020)))
    shadow_color = Image.new("RGBA", result.size, (24,51,61,75)); shadow_color.putalpha(shadow.getchannel("A")); result.alpha_composite(shadow_color)
    outline_size = max(3, round(high_size * .045)) | 1
    outline_mask = mask.filter(ImageFilter.MaxFilter(outline_size))
    outline_layer = Image.new("RGBA", result.size, (36,70,83,255)); outline_layer.putalpha(outline_mask); result.alpha_composite(outline_layer)
    result.paste(gradient, (0,0), mask)
    shine = Image.new("L", result.size, 0); ImageDraw.Draw(shine).ellipse((high_size*.20, high_size*.14, high_size*.72, high_size*.45), fill=80)
    shine = ImageChops.multiply(shine, mask); gloss = Image.new("RGBA", result.size, (255,255,255,0)); gloss.putalpha(shine.filter(ImageFilter.GaussianBlur(high_size*.018))); result.alpha_composite(gloss)
    return result.resize((size, size), Image.Resampling.LANCZOS)


def _paste_token(image: Image.Image, token: dict, center: tuple[int, int], logical_size: float, amount: float = 1.0) -> None:
    size = _scaled(logical_size * max(.05, amount), image.size); asset = token_image(token["shape"], token["color_value"], size)
    x, y = scale_point(center, image.size); image.paste(asset, (x-size//2, y-size//2), asset)


def _card(image: Image.Image, center: tuple[int, int], palette: dict[str, str]) -> None:
    cx, cy = center
    rounded_surface(image, _bounds((cx-128, cy-138, cx+128, cy+138), image.size), _scaled(44, image.size),
                    palette["surface"], palette["outline"], _scaled(5, image.size), shadow=True)


def _tile(image: Image.Image, center: tuple[int, int], number: int, palette: dict[str, str], width_scale: float = 1, glow: float = 0) -> None:
    cx, cy = scale_point(center, image.size); hw, hh = _scaled(128*max(.035,width_scale), image.size), _scaled(138, image.size)
    if glow:
        g = _scaled(15+10*glow, image.size); rounded_surface(image,(cx-hw-g,cy-hh-g,cx+hw+g,cy+hh+g),_scaled(50,image.size),palette["success"],opacity=round(65*glow))
    rounded_surface(image,(cx-hw,cy-hh,cx+hw,cy+hh),_scaled(44,image.size),palette["secondary"] if glow<.5 else palette["success"],palette["outline"],_scaled(5,image.size),shadow=True)
    if width_scale > .4: ImageDraw.Draw(image).text((cx,cy),str(number),font=font(_scaled(88,image.size)),fill=palette["text_light"],anchor="mm")


def draw_memory_round(image: Image.Image, item: RoundSpec, local: float, palette: dict[str, str]) -> None:
    state = memory_state(local, item); phase = state["phase"]; tokens = item.data["tokens"]; opened = set(state["open_positions"])
    draw = ImageDraw.Draw(image)
    question_position = state.get("target_position")
    if question_position:
        token = tokens[int(question_position)-1]; relative = float(state.get("relative",0))
        amount = ease_out_back(relative/MEMORY_TARGET_ENTRANCE)
        rounded_surface(image,_bounds((315,220,765,610),image.size),_scaled(62,image.size),palette["surface"],palette["outline"],_scaled(6,image.size),shadow=True)
        _paste_token(image,token,(540,405),385,amount)
        draw.text(scale_point((540,690),image.size),"?",font=font(_scaled(128,image.size)),fill=palette["primary"],anchor="mm")
    cover_start = MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION
    questions_start = cover_start + MEMORY_COVER_DURATION
    for index,(token,center) in enumerate(zip(tokens,POSITIONS),start=1):
        _card(image,center,palette)
        if phase in ("entrance","memorize"):
            amount = ease_out_back(local/MEMORY_BOARD_ENTRANCE) if phase=="entrance" else 1
            _paste_token(image,token,center,225,amount); continue
        if index in opened:
            _paste_token(image,token,center,225); continue
        width_scale, glow = 1.0, 0.0
        if phase=="cover": width_scale=ease_out_cubic((local-cover_start)/MEMORY_COVER_DURATION)
        if question_position==index and phase in ("highlight","answer_reveal"):
            relative=float(state["relative"]); reveal=MEMORY_TARGET_ENTRANCE+MEMORY_THINKING_DURATION
            glow=ease_in_out((relative-reveal)/MEMORY_ANSWER_HIGHLIGHT)
            if phase=="answer_reveal":
                flip=(relative-reveal-MEMORY_ANSWER_HIGHLIGHT)/MEMORY_ANSWER_FLIP
                if flip<.5: width_scale=1-flip*2
                else: _paste_token(image,token,center,225,ease_out_back((flip-.5)*2)); continue
        if phase=="final_reveal" and index==item.data["final_position"]:
            flip=(float(state["relative"])-MEMORY_FINAL_DELAY)/MEMORY_FINAL_FLIP
            if flip<.5: width_scale=1-flip*2; glow=1
            else: _paste_token(image,token,center,225,ease_out_back((flip-.5)*2)); continue
        _tile(image,center,index,palette,width_scale,glow)
    if state["timer_active"]:
        relative=float(state["relative"])-MEMORY_TARGET_ENTRANCE
        draw_progress_bar(image,_bounds((245,1580,835,1602),image.size),1-relative/MEMORY_THINKING_DURATION,palette["background_2"],palette["primary"])
    if phase=="completed": draw_sparkles(draw,image.size,palette["accent"],min(1,float(state["relative"])/MEMORY_COMPLETED_HOLD))


def draw_memory_intro(image: Image.Image, t: float, palette: dict[str, str]) -> None:
    demo = ({"shape":"circle","color_value":"#DCA915"},{"shape":"triangle","color_value":"#D9434E"},
            {"shape":"square","color_value":"#2874C6"},{"shape":"star","color_value":"#3A9B55"})
    centers=((390,535),(690,535),(390,820),(690,820))
    amount=ease_out_back(t/.30)
    ImageDraw.Draw(image).text(scale_point((540,235),image.size),"?",font=font(_scaled(170,image.size)),fill=palette["primary"],anchor="mm")
    for token,center in zip(demo,centers):
        _card(image,center,palette); _paste_token(image,token,center,190,amount)
