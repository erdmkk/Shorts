from __future__ import annotations

from collections import Counter
from dataclasses import replace
import random

from PIL import Image

from puzzly.config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD
from puzzly.generator import generate_spec, mixed_types
from puzzly.puzzles.lucky_pick import (COLORS, EAT_ANTICIPATION, EAT_BITE, EAT_DURATION, SHAPES,
                                       CORRIDOR_WIDTH, TARGET_COUNT, TARGET_SIZE, TEMPLATES, TRAVEL_SPEED,
                                       errors, generate, path_length, point_on_path, template_errors,
                                       template_geometry)
from puzzly.registry import ACTIVE_PUZZLE_TYPES, EXPERIMENTAL_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.renderer import render_cover, render_frame, save_cover
from puzzly.validation import validate_spec
from puzzly.visuals.lucky_pick import CHARACTER_SIZE, INTRO_POSITIONS, chomper_image, lucky_state


def _on_axis_segment(point: tuple[float,float], path: list[list[int]]) -> bool:
    x,y=point
    return any((a[0]==b[0] and abs(x-a[0])<1e-6 and min(a[1],b[1])-1e-6<=y<=max(a[1],b[1])+1e-6) or
               (a[1]==b[1] and abs(y-a[1])<1e-6 and min(a[0],b[0])-1e-6<=x<=max(a[0],b[0])+1e-6)
               for a,b in zip(path,path[1:]))


def test_all_six_curated_entry_templates_and_mirrors_are_valid() -> None:
    assert len(TEMPLATES)==6 and len({item.id for item in TEMPLATES})==6
    for template in TEMPLATES:
        for mirrored in (False,True):
            assert not template_errors(template,mirrored)
            geometry=template_geometry(template,mirrored)
            assert geometry["entrance"]==[540,1450]
            assert len(geometry["terminal_paths"])==len(geometry["terminals"])==7
            assert len({tuple(point) for point in geometry["terminals"]})==7
            assert all((a[0]==b[0] and abs(a[1]-b[1])>=60) or
                       (a[1]==b[1] and abs(a[0]-b[0])>=140) for a,b in geometry["corridors"])
            for path,terminal in zip(geometry["terminal_paths"],geometry["terminals"]):
                assert path[0]==geometry["entrance"] and path[-1]==terminal
                assert all((a[0]==b[0]) != (a[1]==b[1]) for a,b in zip(path,path[1:]))


def test_lucky_pick_700_specs_are_valid_deterministic_and_fair() -> None:
    winners:Counter[int]=Counter(); orders=set(); shapes=set(); templates=set(); mirrors=set()
    for seed in range(700):
        spec=generate(seed); validate_spec(spec)
        assert spec==generate(seed) and spec.fingerprint()==generate(seed).fingerprint()
        assert spec.difficulty is None and spec.round_count==1 and 20.5<=spec.total_duration<=24
        game=spec.rounds[0]; data=game.data; targets=data["targets"]
        assert data["target_count"]==TARGET_COUNT==len(targets)==7
        assert len({target["shape_id"] for target in targets})==1 and data["shape_id"] in SHAPES
        assert len({target["color_id"] for target in targets})==7
        assert set(target["color_id"] for target in targets)==set(COLORS)
        assert data["selection_seconds"]==LUCKY_SELECTION_DURATION==5.0
        assert data["eat_seconds"]==EAT_DURATION==.58
        assert game.answer==data["winner_index"] and data["winner_index"] not in data["elimination_order"]
        assert set(data["elimination_order"])==set(range(7))-{data["winner_index"]}
        assert len(data["elimination_order"])==len(set(data["elimination_order"]))==6
        assert not errors(data,game.answer)
        winners[data["winner_index"]]+=1; orders.add(tuple(data["elimination_order"])); shapes.add(data["shape_id"])
        templates.add(data["corridor_template_id"]); mirrors.add(data["mirrored"])
    expected=700/7
    assert all(abs(count-expected)<=expected*.30 for count in winners.values())
    assert len(orders)>300 and shapes==set(SHAPES) and templates=={item.id for item in TEMPLATES} and mirrors=={False,True}


def test_travel_enters_from_bottom_then_follows_the_corridor_tree() -> None:
    for seed in range(100):
        data=generate(seed).rounds[0].data; previous=None
        for step,target_index in zip(data["movement_steps"],data["elimination_order"]):
            path=step["travel_path"]
            assert path[-1]==data["targets"][target_index]["position"]
            assert path[0]==(data["entrance"] if previous is None else data["targets"][previous]["position"])
            assert all((a[0]==b[0]) != (a[1]==b[1]) for a,b in zip(path,path[1:]))
            for sample in range(101):
                point,_=point_on_path(path,sample/100); assert _on_axis_segment(point,path)
            previous=target_index


def test_character_is_hidden_during_selection_and_mouth_is_state_driven() -> None:
    game=generate(9010).rounds[0]; first=game.data["movement_steps"][0]
    idle=lucky_state(.05,game); selection=lucky_state(LUCKY_APPEARANCE_DURATION+.2,game)
    travel=lucky_state(float(first["start_time"])+float(first["travel_duration"])/2,game)
    entrance=lucky_state(float(first["start_time"]),game)
    eat_start=float(first["end_time"])-EAT_DURATION
    anticipation=lucky_state(eat_start+EAT_ANTICIPATION/2,game)
    eat=lucky_state(eat_start+EAT_ANTICIPATION+EAT_BITE/2,game)
    pop=lucky_state(eat_start+EAT_ANTICIPATION+EAT_BITE*.66,game)
    post=lucky_state(eat_start+EAT_ANTICIPATION+EAT_BITE+.05,game)
    winner=lucky_state(float(game.data["timeline_duration"])-LUCKY_WINNER_HOLD+.2,game)
    assert idle["phase"]=="idle" and idle["character"] is None and idle["mouth"]==0
    assert selection["phase"]=="selection" and selection["character"] is None and selection["mouth"]==0
    assert entrance["character"]==tuple(game.data["entrance"])
    assert travel["phase"]=="travel" and travel["mouth"]==0
    assert anticipation["phase"]=="eat_anticipation" and anticipation["mouth"]==0
    assert eat["phase"]=="eat" and eat["mouth"]==0
    assert pop["phase"]=="eat" and pop["mouth"]==0 and first["target_index"] in pop["eliminated"]
    assert post["phase"]=="post_eat" and post["mouth"]==0
    assert winner["phase"]=="winner" and winner["mouth"]==0
    assert game.data["winner_index"] not in winner["eliminated"] and len(winner["eliminated"])==6


def test_movement_uses_one_fixed_speed_and_character_dominates_targets() -> None:
    steps=generate(77).rounds[0].data["movement_steps"]
    assert TRAVEL_SPEED==640.0
    assert all(step["hesitation_duration"]==0 for step in steps)
    assert all(abs(step["travel_duration"]-round(path_length(step["travel_path"])/TRAVEL_SPEED,4))<1e-9
               for step in steps)
    assert TARGET_SIZE==136 and CHARACTER_SIZE==196 and CORRIDOR_WIDTH==170
    assert TARGET_SIZE<CHARACTER_SIZE and CHARACTER_SIZE*.76<CORRIDOR_WIDTH
    assert steps[5]["eat_duration"]==steps[0]["eat_duration"]==.58


def test_lucky_fingerprint_tracks_entry_tree_identity() -> None:
    spec=generate(88); game=spec.rounds[0]
    changed=dict(game.data); changed["shape_id"]="circle" if changed["shape_id"]!="circle" else "star"
    assert spec.fingerprint()!=replace(spec,rounds=(replace(game,data=changed),)).fingerprint()


def test_lucky_frames_simple_character_and_standard_cover(tmp_path) -> None:
    spec=generate(616); game=spec.rounds[0]
    assert len(INTRO_POSITIONS)==len(set(INTRO_POSITIONS))==7
    asset=chomper_image(180,0,False,"right"); assert asset.getbbox() and asset.size==(180,180)
    assert asset.tobytes()==chomper_image(180,4,False,"right").tobytes()
    first=game.data["movement_steps"][0]; eat=float(first["end_time"])-EAT_DURATION+EAT_ANTICIPATION+EAT_BITE/2
    moments=(1.0,spec.intro_duration+.5,spec.intro_duration+float(first["start_time"])+.2,
             spec.intro_duration+eat,spec.total_duration-spec.outro_duration-.2)
    for moment in moments: assert render_frame(spec,moment,(540,960)).size==(540,960)
    assert render_cover(spec).size==(1080,1920)
    path=tmp_path/"lucky.jpg"; save_cover(spec,path)
    with Image.open(path) as image:
        assert image.format=="JPEG" and image.size==(1080,1920); image.verify()


def test_lucky_is_active_and_line_follow_stays_disabled() -> None:
    assert "lucky_pick" in ACTIVE_PUZZLE_TYPES
    assert "line_follow" in EXPERIMENTAL_PUZZLE_TYPES and "line_follow" not in ACTIVE_PUZZLE_TYPES
    assert set(mixed_types(700,random.Random(10)))==set(MIXED_PUZZLE_TYPES)
    assert generate_spec("lucky_pick",17).difficulty is None
