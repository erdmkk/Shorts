from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD
from ..models import RoundSpec, VideoSpec
from ..puzzles.lucky_pick import (COLORS, CORRIDOR_WIDTH, EAT_ANTICIPATION, EAT_BITE, POST_EAT,
                                  TARGET_SIZE, point_on_path)
from .easing import ease_out_back
from .effects import draw_progress_bar, draw_sparkles
from .layout import scale_point
from .memory import token_image
from .text import font

INTRO_POSITIONS = ((275, 455), (540, 425), (805, 500), (355, 680), (685, 700), (260, 895), (760, 900))
CHARACTER_SIZE = 196


def _scaled(value: float, size: tuple[int, int]) -> int:
    return max(1, round(value * size[0] / 1080))


def _bounds(values: tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    first, second = scale_point((values[0], values[1]), size), scale_point((values[2], values[3]), size)
    return first[0], first[1], second[0], second[1]


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index+2], 16) for index in (0, 2, 4))


def _target(image: Image.Image, target: dict, scale: float = 1.0, glow: bool = False) -> None:
    size = _scaled(TARGET_SIZE * scale, image.size); x, y = scale_point(tuple(target["position"]), image.size)
    if glow:
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0)); draw = ImageDraw.Draw(layer)
        radius = round(size * .68)
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*_rgb(target["color_value"]), 95))
        layer = layer.filter(ImageFilter.GaussianBlur(max(4, _scaled(22, image.size))))
        image.paste(layer, (0, 0), layer)
    asset = token_image(target["shape_id"], target["color_value"], size)
    image.paste(asset, (x-size//2, y-size//2), asset)


def _draw_segment(draw: ImageDraw.ImageDraw, a: list[int], b: list[int], width: int, fill: str) -> None:
    half = width / 2
    if a[0] == b[0]:
        draw.rectangle((round(a[0]-half), min(a[1],b[1]), round(a[0]+half), max(a[1],b[1])), fill=fill)
    else:
        draw.rectangle((min(a[0],b[0]), round(a[1]-half), max(a[0],b[0]), round(a[1]+half)), fill=fill)


@lru_cache(maxsize=48)
def _corridor_layer(size: tuple[int,int], corridor_key: tuple[tuple[tuple[int,int],tuple[int,int]],...],
                    entrance_key: tuple[int,int], surface: str, outline: str, primary: str) -> Image.Image:
    scale = size[0] / 1080
    segments = [[scale_point(point,size) for point in segment] for segment in corridor_key]
    floor_width = round(CORRIDOR_WIDTH*scale)
    floor_mask = Image.new("L",size,0); mask_draw=ImageDraw.Draw(floor_mask)
    for a,b in segments:
        _draw_segment(mask_draw,list(a),list(b),floor_width,255)
    outline_radius=max(1,round(9*scale)); kernel=outline_radius*2+1
    outline_mask=floor_mask.filter(ImageFilter.MaxFilter(kernel))
    outline_opacity=outline_mask.point(lambda value: round(value*.34))
    layer=Image.new("RGBA",size,(0,0,0,0))
    layer.paste(Image.new("RGBA",size,outline+"FF"),(0,0),outline_opacity)
    layer.paste(Image.new("RGBA",size,surface+"FF"),(0,0),floor_mask)
    draw=ImageDraw.Draw(layer)
    entrance=scale_point(entrance_key,size); gate=_scaled(42,size)
    draw.arc((entrance[0]-gate,entrance[1]-gate,entrance[0]+gate,entrance[1]+gate),180,360,
             fill=primary,width=max(2,_scaled(8,size)))
    return layer


def draw_corridor_board(image: Image.Image, item: RoundSpec, palette: dict[str, str]) -> None:
    corridor_key=tuple((tuple(segment[0]),tuple(segment[1])) for segment in item.data["corridors"])
    layer=_corridor_layer(image.size,corridor_key,tuple(item.data["entrance"]),palette["surface"],
                          palette["outline"],palette["primary"])
    image.paste(layer,(0,0),layer)


@lru_cache(maxsize=128)
def chomper_image(size: int, mouth_step: int = 0, happy: bool = False, facing: str = "right") -> Image.Image:
    """Minimal round Puzzly blob; mouth_step is retained only for call compatibility."""
    high=size*2; image=Image.new("RGBA",(high,high),(0,0,0,0)); draw=ImageDraw.Draw(image)
    shadow=Image.new("RGBA",image.size,(0,0,0,0)); ImageDraw.Draw(shadow).ellipse((high*.16,high*.75,high*.86,high*.88),fill=(24,51,61,50))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(high*.035)))
    outline="#244653"; body="#35A6C8"; stroke=max(3,round(high*.027))
    draw.ellipse((high*.12,high*.13,high*.88,high*.83),fill=body,outline=outline,width=stroke)
    draw.ellipse((high*.57,high*.22,high*.75,high*.40),fill="#FFFFFF",outline=outline,width=max(2,round(high*.018)))
    draw.ellipse((high*.65,high*.28,high*.70,high*.335),fill=outline)
    draw.ellipse((high*.56,high*.48,high*.63,high*.55),fill="#FF8B91")
    if happy:
        draw.arc((high*.62,high*.47,high*.79,high*.62),20,155,fill=outline,width=max(3,round(high*.026)))
    else:
        draw.arc((high*.63,high*.48,high*.78,high*.59),20,145,fill=outline,width=max(3,round(high*.022)))
    gloss=Image.new("RGBA",image.size,(0,0,0,0)); ImageDraw.Draw(gloss).ellipse((high*.27,high*.20,high*.51,high*.29),fill=(255,255,255,48))
    image.alpha_composite(gloss.filter(ImageFilter.GaussianBlur(high*.018)))
    image=image.resize((size,size),Image.Resampling.LANCZOS)
    return ImageOps.mirror(image) if facing=="left" else image


def _chomper(image: Image.Image, center: tuple[float,float], *, facing: str, mouth: float=0,
             happy: bool=False, bounce: float=0) -> None:
    size=_scaled(CHARACTER_SIZE,image.size); asset=chomper_image(size,round(max(0,min(1,mouth))*4),happy,facing)
    x,y=scale_point(center,image.size); y-=round(_scaled(bounce,image.size))
    image.paste(asset,(round(x-size/2),round(y-size/2)),asset)


def _path_facing(path: list[list[int]], segment: int, fallback: str) -> str:
    for index in range(segment,min(len(path)-1,segment+2)):
        dx=path[index+1][0]-path[index][0]
        if dx: return "right" if dx>0 else "left"
    for index in range(segment-1,-1,-1):
        dx=path[index+1][0]-path[index][0]
        if dx: return "right" if dx>0 else "left"
    return fallback


def lucky_state(local: float, item: RoundSpec) -> dict[str, object]:
    selection_end=LUCKY_APPEARANCE_DURATION+LUCKY_SELECTION_DURATION
    if local < LUCKY_APPEARANCE_DURATION:
        return {"phase":"idle","eliminated":(),"character":None,"facing":"right","mouth":0.0}
    if local < selection_end:
        return {"phase":"selection","eliminated":(),"character":None,"facing":"right","mouth":0.0}
    eliminated=[]
    for step in item.data["movement_steps"]:
        relative=local-float(step["start_time"]); target=step["target_index"]
        if relative < 0: break
        hesitation=float(step["hesitation_duration"])
        if relative < hesitation:
            start=tuple(step["travel_path"][0])
            return {"phase":"idle","idle_kind":"hesitation","eliminated":tuple(eliminated),"character":start,
                    "facing":"right","mouth":0.0,"target":target}
        relative-=hesitation; travel_duration=float(step["travel_duration"])
        if relative < travel_duration:
            amount=relative/travel_duration; center,segment=point_on_path(step["travel_path"],amount)
            facing=_path_facing(step["travel_path"],segment,"right")
            return {"phase":"travel","eliminated":tuple(eliminated),"character":center,
                    "facing":facing,"mouth":0.0,"target":target,"travel_progress":amount}
        relative-=travel_duration; endpoint=tuple(step["travel_path"][-1]); previous=tuple(step["travel_path"][-2])
        facing="right" if endpoint[0]>=previous[0] else "left"
        if relative < EAT_ANTICIPATION:
            return {"phase":"eat_anticipation","eliminated":tuple(eliminated),"character":endpoint,
                    "facing":facing,"mouth":0.0,"target":target,"eat_progress":relative/EAT_ANTICIPATION}
        relative-=EAT_ANTICIPATION
        if relative < EAT_BITE:
            bite=relative/EAT_BITE; removed=bite>=.58
            current=tuple(eliminated+[target]) if removed else tuple(eliminated)
            return {"phase":"eat","eliminated":current,"character":endpoint,"facing":facing,
                    "mouth":0.0,"target":target,"eat_progress":bite,"reaction":math.sin(math.pi*bite)}
        relative-=EAT_BITE
        if relative < POST_EAT:
            return {"phase":"post_eat","eliminated":tuple(eliminated+[target]),"character":endpoint,
                    "facing":facing,"mouth":0.0,"target":target}
        eliminated.append(target)
    last=item.data["movement_steps"][-1]["travel_path"][-1]
    winner_age=max(0.0,local-(float(item.data["timeline_duration"])-LUCKY_WINNER_HOLD))
    winner_position=item.data["targets"][item.data["winner_index"]]["position"]
    facing="right" if winner_position[0]>=last[0] else "left"
    return {"phase":"winner","eliminated":tuple(item.data["elimination_order"]),"character":tuple(last),
            "facing":facing,"mouth":0.0,"winner_age":winner_age}


def draw_lucky_intro(image: Image.Image, spec: VideoSpec, t: float, palette: dict[str,str]) -> None:
    item=spec.rounds[0]; draw_corridor_board(image,item,palette)
    draw=ImageDraw.Draw(image)
    draw.text(scale_point((540,155),image.size),"Pick One",font=font(_scaled(76,image.size)),fill=palette["text_dark"],anchor="mm")
    amount=ease_out_back(t/.28)
    for target in item.data["targets"]:
        _target(image,target,max(.08,amount))


def draw_lucky_game(image: Image.Image,item:RoundSpec,local:float,palette:dict[str,str]) -> None:
    draw_corridor_board(image,item,palette); state=lucky_state(local,item); eliminated=set(state["eliminated"]); winner=item.data["winner_index"]
    appearance=ease_out_back(local/LUCKY_APPEARANCE_DURATION) if local<LUCKY_APPEARANCE_DURATION else 1.0
    for target in item.data["targets"]:
        if target["index"] in eliminated: continue
        scale,glow=appearance,False
        if state["phase"]=="eat" and target["index"]==state.get("target"):
            bite=float(state["eat_progress"])
            scale=1+.12*math.sin(math.pi*min(1,bite/.20)) if bite<.20 else max(.08,1-.92*(bite-.20)/.38)
        if state["phase"]=="winner" and target["index"]==winner:
            age=float(state["winner_age"]); scale=1+.16*ease_out_back(age/.40); glow=True
        _target(image,target,scale,glow)
    draw=ImageDraw.Draw(image)
    if state["phase"] in ("idle","selection") and local<LUCKY_APPEARANCE_DURATION+LUCKY_SELECTION_DURATION:
        draw.text(scale_point((540,150),image.size),"Pick One",font=font(_scaled(70,image.size)),fill=palette["text_dark"],anchor="mm")
    if state["phase"]=="selection":
        progress=1-(local-LUCKY_APPEARANCE_DURATION)/LUCKY_SELECTION_DURATION
        draw_progress_bar(image,_bounds((245,1580,835,1602),image.size),progress,palette["background_2"],palette["primary"])
    if state["phase"]=="eat" and float(state["eat_progress"])>=.42:
        target=item.data["targets"][int(state["target"])]
        x,y=scale_point(tuple(target["position"]),image.size); age=(float(state["eat_progress"])-.42)/.58
        radius=_scaled(76+28*age,image.size); dot=max(2,_scaled(7*(1-age),image.size))
        for angle in (35,145,225,315):
            px=x+math.cos(math.radians(angle))*radius; py=y+math.sin(math.radians(angle))*radius
            draw.ellipse((px-dot,py-dot,px+dot,py+dot),fill=palette["accent"])
    happy=state["phase"]=="winner"; bounce=0
    if state["character"] is not None:
        _chomper(image,state["character"],facing=str(state["facing"]),mouth=float(state["mouth"]),happy=happy,bounce=bounce)
    if state["phase"]=="winner": draw_sparkles(draw,image.size,palette["accent"],float(state["winner_age"])/.65)
