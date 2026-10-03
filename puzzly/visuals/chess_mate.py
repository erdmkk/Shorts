"""Chess: Mate in 1 frames. One still frame for the whole video: no timer, no animation, no answer.

Pieces are drawn from local font glyphs (no downloaded artwork). Preferred: the classic chess-diagram pieces of Arial
Unicode MS, drawn like a diagram font: a white body under every piece, then the glyph in black on top, so a black
piece's own details (the king's cross, the queen's diamond, the bishop's cross) show as crisp white lines. Fallback,
when that font is missing: the Segoe UI Symbol glyphs, silhouette plus outline-glyph detail lines.
"""
from __future__ import annotations

from functools import lru_cache

import chess
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..config import CHESS_BOARDS, CHESS_DEFAULT_BOARD, PUZZLE_FIT_PALETTE as PALETTE
from ..models import VideoSpec
from .puzzle_fit import active_theme
from .surfaces import table
from .text import WINDOWS_FONTS, draw_cta, font

SOLID = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
OUTLINE = {"k": "♔", "q": "♕", "r": "♖", "b": "♗", "n": "♘", "p": "♙"}
BOARD_BOX = (60, 480, 1020, 1440)  # logical 1080x1920; 120 px squares
COVER_TIME = 0.0


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _symbol_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(WINDOWS_FONTS / "seguisym.ttf"), size)


DIAGRAM_FONT = WINDOWS_FONTS / "ARIALUNI.TTF"


@lru_cache(maxsize=32)
def piece_sprite(kind: str, white: bool, size: int) -> Image.Image:
    """A size x size RGBA piece."""
    if DIAGRAM_FONT.is_file():
        return _diagram_piece(kind, white, size)
    return _symbol_piece(kind, white, size)


def _centered(image: Image.Image, size: int) -> Image.Image:
    """Move the drawn piece to the exact centre of its square (glyphs sit on the font baseline, i.e. low), then shrink."""
    box = image.getchannel("A").getbbox()
    if box:
        canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
        dx = round((image.width - (box[0] + box[2])) / 2)
        dy = round((image.height - (box[1] + box[3])) / 2)
        canvas.alpha_composite(image, (dx, dy))
        image = canvas
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _diagram_piece(kind: str, white: bool, size: int) -> Image.Image:
    """Diagram-font piece: a white body (everything inside the piece's outline), then the glyph in near-black on top."""
    s = max(8, size * 4)
    face = ImageFont.truetype(str(DIAGRAM_FONT), round(s * .84))
    center = (s / 2, s / 2 + s * .03)
    ink = Image.new("L", (s, s), 0)
    ImageDraw.Draw(ink).text(center, (OUTLINE if white else SOLID)[kind], font=face, fill=255, anchor="mm")
    both = Image.new("L", (s, s), 0)
    draw = ImageDraw.Draw(both)
    draw.text(center, OUTLINE[kind], font=face, fill=255, anchor="mm")
    draw.text(center, SOLID[kind], font=face, fill=255, anchor="mm")
    outside = ImageOps.invert(both.filter(ImageFilter.MaxFilter(5)).point(lambda v: 255 if v > 60 else 0))
    ImageDraw.floodfill(outside, (0, 0), 128)  # the exterior; everything else is the piece's body
    body = outside.point(lambda v: 0 if v == 128 else 255).filter(ImageFilter.MinFilter(3))
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (0, 0), body)
    image.paste((16, 15, 20, 255), (0, 0), ink)
    return _centered(image, size)


def _symbol_piece(kind: str, white: bool, size: int) -> Image.Image:
    """Fallback: Segoe UI Symbol silhouette with outline-glyph details (white pieces grey lines, black pieces white)."""
    s = max(8, size * 4)
    face = _symbol_font(round(s * .88))
    center = (s / 2, s / 2 + s * .02)
    solid = Image.new("L", (s, s), 0)
    ImageDraw.Draw(solid).text(center, SOLID[kind], font=face, fill=255, anchor="mm")
    lines = Image.new("L", (s, s), 0)
    ImageDraw.Draw(lines).text(center, OUTLINE[kind], font=face, fill=255, anchor="mm")
    inside = solid.filter(ImageFilter.MinFilter(max(3, (round(s * .03) // 2) * 2 + 1)))
    detail = ImageChops.multiply(lines, inside)
    # A thick dark rim frames white pieces; black pieces get a thin one, or the rim and body merge into a swollen blob.
    rim = solid.filter(ImageFilter.MaxFilter(max(3, (round(s * (.05 if white else .02)) // 2) * 2 + 1)))
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    image.paste((14, 13, 18, 255), (0, 0), rim)
    if white:
        image.paste((255, 255, 255, 255), (0, 0), solid)
        image.paste((168, 164, 158, 255), (0, 0), detail.point(lambda v: v * 3 // 4))
    else:
        thin = detail.filter(ImageFilter.MinFilter(max(3, (round(s * .003) // 2) * 2 + 1)))  # fine white details
        image.paste((18, 17, 22, 255), (0, 0), solid)
        image.paste((236, 233, 226, 255), (0, 0), thin)
    return _centered(image, size)


def square_at(row: int, column: int, flipped: bool) -> int:
    """The chess square drawn at screen row/column (0 = top-left); flipped puts Black at the bottom."""
    return chess.square(7 - column, row) if flipped else chess.square(column, 7 - row)


def board_colors(board_id: str | None) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    _, light, dark = CHESS_BOARDS.get(board_id or CHESS_DEFAULT_BOARD, CHESS_BOARDS[CHESS_DEFAULT_BOARD])
    return _rgb(light), _rgb(dark)


def board_for(spec: VideoSpec) -> str:
    """The video's board colours: the creator's choice stored in metadata (outside the fingerprint), else the default."""
    chosen = spec.metadata.get("board")
    return chosen if chosen in CHESS_BOARDS else CHESS_DEFAULT_BOARD


@lru_cache(maxsize=8)
def board_image(fen: str, side: str, px: int, board_id: str = CHESS_DEFAULT_BOARD) -> Image.Image:
    """The board (px x px) seen from the side to move, with file letters and rank numbers inside the edge squares."""
    board = chess.Board(fen)
    flipped = side == "black"
    cell = px / 8
    LIGHT, DARK = board_colors(board_id)
    image = Image.new("RGBA", (px, px), LIGHT + (255,))
    draw = ImageDraw.Draw(image)
    label = font(max(6, round(cell * .2)))
    for row in range(8):
        for column in range(8):
            x1, y1 = round(column * cell), round(row * cell)
            x2, y2 = round((column + 1) * cell), round((row + 1) * cell)
            square = square_at(row, column, flipped)
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            color = LIGHT if light else DARK
            draw.rectangle((x1, y1, x2, y2), fill=color)
            other = DARK if light else LIGHT
            if column == 0:
                draw.text((x1 + cell * .07, y1 + cell * .05), str(chess.square_rank(square) + 1), font=label, fill=other, anchor="lt")
            if row == 7:
                draw.text((x2 - cell * .07, y2 - cell * .04), chess.FILE_NAMES[chess.square_file(square)], font=label,
                          fill=other, anchor="rb")
            piece = board.piece_at(square)
            if piece:
                size = round(cell * .96)
                sprite = piece_sprite(piece.symbol().lower(), piece.color == chess.WHITE, size)
                image.alpha_composite(sprite, (round(x1 + (cell - size) / 2), round(y1 + (cell - size) / 2)))
    return image


def _side_pill(image: Image.Image, center: tuple[float, float], side: str, scale: float) -> None:
    from .effects import rounded_surface
    text = f"{side.upper()} TO MOVE"
    face = font(round(54 * scale))
    width = ImageDraw.Draw(image).textlength(text, font=face)
    dot = 30 * scale
    half_w, half_h = (width + dot + 28 * scale) / 2 + 44 * scale, 46 * scale
    x, y = center
    fill, ink = ((250, 247, 238), (20, 18, 26)) if side == "white" else ((24, 22, 30), (250, 247, 238))
    rounded_surface(image, (x - half_w, y - half_h, x + half_w, y + half_h), half_h, fill + (255,),
                    outline=_rgb(PALETTE["accent"]) + (255,), width=max(1, round(4 * scale)))
    left = x - (width + dot + 28 * scale) / 2
    draw = ImageDraw.Draw(image)
    stone, rim = ((250, 247, 238), (20, 18, 26)) if side == "white" else ((20, 18, 26), (250, 247, 238))  # the side's colour
    draw.ellipse((left, y - dot / 2, left + dot, y + dot / 2), fill=stone, outline=rim, width=max(1, round(4 * scale)))
    draw.text((left + dot + 28 * scale, y + 2 * scale), text, font=face, fill=ink, anchor="lm")


@lru_cache(maxsize=4)
def _still(fen: str, side: str, rating: int, theme: str, board_id: str, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = table(size, theme, "felt", (540, 960)).convert("RGBA")  # a felt cloth under a lamp, in the video's tone
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((410 * scale, 118 * scale, 446 * scale, 154 * scale), radius=round(10 * scale),
                           fill=_rgb(PALETTE["accent"]))
    draw.text((462 * scale, 136 * scale), "Puzzly for You", font=font(round(40 * scale), "regular"), fill=(255, 255, 255),
              anchor="lm")
    try:
        title = ImageFont.truetype(str(WINDOWS_FONTS / "seguibl.ttf"), round(124 * scale))
    except OSError:
        title = font(round(124 * scale))
    draw.text((540 * scale, 262 * scale + 6 * scale), "MATE IN 1", font=title, fill=(0, 0, 0, 150), anchor="mm")
    draw.text((540 * scale, 262 * scale), "MATE IN 1", font=title, fill=(255, 255, 255), anchor="mm")
    _side_pill(image, (540 * scale, 392 * scale), side, scale)
    x1, y1, x2, y2 = (value * scale for value in BOARD_BOX)
    frame = 14 * scale
    shadow = Image.new("L", size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x1 - frame, y1 - frame + 16 * scale, x2 + frame, y2 + frame + 26 * scale),
                                             radius=round(26 * scale), fill=200)
    image.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(max(1, 24 * scale))))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((x1 - frame, y1 - frame, x2 + frame, y2 + frame), radius=round(22 * scale),
                           fill=_rgb(PALETTE["surface"]), outline=_rgb(PALETTE["surface_edge"]), width=max(1, round(3 * scale)))
    image.alpha_composite(board_image(fen, side, round(x2 - x1), board_id), (round(x1), round(y1)))
    draw = ImageDraw.Draw(image)
    draw.text((540 * scale, 1526 * scale), "One move. Checkmate.", font=font(round(56 * scale)), fill=(255, 255, 255),
              anchor="mm")
    draw.text((540 * scale, 1606 * scale), "Comment your move ↓", font=font(round(46 * scale)),
              fill=_rgb(PALETTE["accent"]), anchor="mm")
    draw.text((540 * scale, 1672 * scale), f"Lichess puzzle rating {rating}", font=font(round(32 * scale), "regular"),
              fill=_rgb(PALETTE["text_muted"]), anchor="mm")
    draw_cta(image, (round(540 * scale), round(1784 * scale)), round(46 * scale), PALETTE["accent"], PALETTE["background"])
    return image.convert("RGB")


def draw_chess_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    data = spec.rounds[0].data
    return _still(data["fen"], data["side"], int(data["rating"]), active_theme(), board_for(spec), size).copy()


# ---------------------------------------------------------------- the long video (16:9 Brain Test) version

def long_phases() -> dict[str, float]:
    """A timed level for the long video: 15 s to think, then the mating move is shown on the board."""
    from ..config import CHESS_LONG_ENTRANCE, CHESS_LONG_REVEAL, CHESS_LONG_THINKING
    think_end = CHESS_LONG_ENTRANCE + CHESS_LONG_THINKING
    return {"think_end": think_end, "arrow_end": think_end + .8, "end": think_end + CHESS_LONG_REVEAL}


def square_center(square: int, flipped: bool) -> tuple[float, float]:
    """Logical centre of a chess square on the board as drawn (the board box is 960 px, 120 px squares)."""
    file, rank = chess.square_file(square), chess.square_rank(square)
    column, row = (7 - file, rank) if flipped else (file, 7 - rank)
    return BOARD_BOX[0] + (column + .5) * 120, BOARD_BOX[1] + (row + .5) * 120


@lru_cache(maxsize=4)
def _long_base(fen: str, side: str, theme: str, board_id: str, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = table(size, theme, "felt", (540, 960)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    face = font(round(86 * scale))
    draw.text((540 * scale, 150 * scale + 5 * scale), "MATE IN 1", font=face, fill=(0, 0, 0, 150), anchor="mm")
    draw.text((540 * scale, 150 * scale), "MATE IN 1", font=face, fill=(255, 255, 255), anchor="mm")
    _side_pill(image, (540 * scale, 392 * scale), side, scale)
    x1, y1, x2, y2 = (value * scale for value in BOARD_BOX)
    frame = 14 * scale
    shadow = Image.new("L", size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x1 - frame, y1 - frame + 16 * scale, x2 + frame, y2 + frame + 26 * scale),
                                             radius=round(26 * scale), fill=200)
    image.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(max(1, 24 * scale))))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((x1 - frame, y1 - frame, x2 + frame, y2 + frame), radius=round(22 * scale),
                           fill=_rgb(PALETTE["surface"]), outline=_rgb(PALETTE["surface_edge"]), width=max(1, round(3 * scale)))
    image.alpha_composite(board_image(fen, side, round(x2 - x1), board_id), (round(x1), round(y1)))
    return image


def draw_chess_long(spec: VideoSpec, local: float, size: tuple[int, int]) -> Image.Image:
    """One frame of the long video's chess level: a numeric timer while the viewer thinks, then an arrow shows the move."""
    from .easing import ease_out_cubic
    from .puzzle_fit import _snap_burst, _text, _timer
    data = spec.rounds[0].data
    answer = spec.rounds[0].answer
    scale = size[0] / 1080
    times = long_phases()
    flipped = data["side"] == "black"
    image = _long_base(data["fen"], data["side"], active_theme(), board_for(spec), size).copy()
    thinking = times["think_end"] - .5
    if local < times["think_end"]:
        remaining = times["think_end"] - local
        _timer(image, min(thinking, remaining), thinking, min(1.0, local / .25), scale)
        _text(image, (540 * scale, 1526 * scale), "Find the checkmate.", font(round(58 * scale)), "#FFFFFF", min(1.0, local / .4))
        return image.convert("RGB")
    start = square_center(chess.parse_square(answer["uci"][:2]), flipped)
    end = square_center(chess.parse_square(answer["uci"][2:4]), flipped)
    progress = ease_out_cubic(min(1.0, (local - times["think_end"]) / .8))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    green = _rgb(PALETTE["success"])
    for square in (start, end):  # both squares light up
        cx, cy = square[0] * scale, square[1] * scale
        draw.rectangle((cx - 60 * scale, cy - 60 * scale, cx + 60 * scale, cy + 60 * scale), fill=green + (round(95 * progress),))
    tip = (start[0] + (end[0] - start[0]) * progress, start[1] + (end[1] - start[1]) * progress)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(1.0, (dx * dx + dy * dy) ** .5)
    ux, uy = dx / length, dy / length
    gold = _rgb(PALETTE["warning"])
    back = (start[0] + ux * 30, start[1] + uy * 30)
    neck = (tip[0] - ux * 44, tip[1] - uy * 44)
    if progress > .15:
        draw.line(((back[0] * scale, back[1] * scale), (neck[0] * scale, neck[1] * scale)), fill=gold + (225,),
                  width=max(2, round(26 * scale)))
        px, py = -uy, ux
        draw.polygon(((tip[0] * scale, tip[1] * scale), ((neck[0] + px * 34) * scale, (neck[1] + py * 34) * scale),
                      ((neck[0] - px * 34) * scale, (neck[1] - py * 34) * scale)), fill=gold + (235,))
    image.alpha_composite(layer)
    label = f"{answer['san']}"
    since = local - times["arrow_end"]
    _text(image, (540 * scale, 1526 * scale), label, font(round(110 * scale)), PALETTE["success"], min(1.0, max(0.0, (local - times["think_end"] - .3) / .3)))
    if since >= 0:
        _snap_burst(image, end, 110, since, scale)
    return image.convert("RGB")
