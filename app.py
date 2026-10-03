from __future__ import annotations

import logging
import os
from pathlib import Path
import time

import streamlit as st

from puzzly.config import DEFAULT_ROUNDS, FLASH_DIGITS, FLASH_VISIBLE, exit_hard_average_round, line_average_round, HIDDEN_MOTION_DURATION, LUCKY_INTRO_DURATION, OUTRO_DURATION, OUTPUT_DIR, intro_outro, round_duration
from puzzly.generator import (generate_unique_specs, render_batch, render_draft_previews,
                              rerender_record_final, save_draft_preview)
from puzzly.history import HistoryStore
from puzzly.logging_config import configure_logging
from puzzly.palette import BACKGROUND_LABELS, PALETTE_LABELS
from puzzly.puzzles.hidden_motion_hunt import (COLORS as HIDDEN_COLORS, SHAPES as HIDDEN_SHAPES,
                                               add_manual_object, default_manual_layout,
                                               delete_manual_object, load_manual_layout,
                                               manual_layout_errors, manual_object_by_id,
                                               prepare_background, prepare_object_png,
                                               resolve_selected_object_id,
                                               save_manual_layout, update_manual_object)
from puzzly.registry import active_type_labels
from puzzly.ui.live_motion_controls import live_motion_controls
from puzzly.ui.live_motion_preview import live_motion_preview
from puzzly.visuals.hidden_motion import editor_preview_payload

configure_logging()
LOGGER = logging.getLogger(__name__)
LOGGER.info("Application started")

TYPE_LABELS = {"Karışık": "mixed", **active_type_labels()}
QUICK_MATH_FORMATS = {"Şekil Denklemleri": "shapes", "Kayıp Operatör": "operators"}

st.set_page_config(page_title="Puzzly Shorts Generator", page_icon="🧩", layout="wide")
# Compact layout so the whole page fits a 1080p screen at 100% zoom; 9:16 videos scale to the viewport height
st.markdown("""<style>
.block-container{padding-top:3rem;padding-bottom:1rem}
[data-testid='stVerticalBlock']{gap:0.6rem}
video[data-testid='stVideo']{max-height:calc(100vh - 290px);width:auto!important;max-width:100%;display:block;margin:0 auto}
</style>""", unsafe_allow_html=True)
st.markdown("### 🧩 Puzzly Shorts Generator")
st.caption("Think • Play • Learn — çok turlu, tamamen yerel video üretimi")

video_format = st.radio("Video formatı", ["Shorts / Reels (9:16)", "YouTube uzun video (16:9)"], horizontal=True)
if video_format.startswith("YouTube"):
    from puzzly.ui.longform_panel import longform_panel
    longform_panel()
    st.stop()

controls_col, results_col = st.columns([0.4, 0.6], gap="large")

with controls_col:
    type_col, difficulty_col = st.columns(2)
    selected_type_label = type_col.selectbox("Puzzle Type", list(TYPE_LABELS))
    selected_type = TYPE_LABELS[selected_type_label]
    min_rating = None
    if selected_type in ("lucky_pick", "hidden_motion_hunt", "bounce_arena"):
        difficulty = None
    elif selected_type == "chess_mate":  # the minimum Lichess puzzle rating replaces the difficulty box
        min_rating = int(difficulty_col.number_input("Min rating", min_value=400, max_value=2400, value=1800, step=50,
                                                     help="Lichess bulmaca puanı; yalnızca bu puan ve üstü kullanılır"))
        difficulty = "hard"
    elif selected_type in ("flash_count", "line_follow", "cup_shuffle", "shade_spot", "memory_challenge", "mind_mix", "laser_maze"):  # produced only in Hard
        difficulty = difficulty_col.selectbox("Difficulty", ["Hard"], disabled=True).lower()
    else:
        difficulty = difficulty_col.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=2).lower()  # Puzzly for You videos are produced in Hard
    background_upload = None
    placement_mode = "auto"
    manual_objects = None
    background_hash = None
    if selected_type == "hidden_motion_hunt":
        st.markdown("<style>.block-container{max-width:1500px}</style>", unsafe_allow_html=True)
        background_upload = st.file_uploader("Background Image Upload", type=["jpg", "jpeg", "png"])
        st.caption("Upload a 9:16 background image. Moving objects will be hidden inside the scene.")
        placement_label = st.radio("Placement Mode", ["Manual Placement", "Auto Placement"], horizontal=True)
        placement_mode = "manual" if placement_label == "Manual Placement" else "auto"
        if background_upload is not None:
            try:
                background_hash = prepare_background(background_upload.getvalue())
                if st.session_state.get("hmh_background_hash") != background_hash:
                    try:
                        restored = load_manual_layout(background_hash)
                    except ValueError as exc:
                        st.warning(str(exc))
                        restored = None
                    st.session_state["hmh_background_hash"] = background_hash
                    st.session_state["hmh_objects"] = restored or default_manual_layout()
                    st.session_state["hidden_object_selected_id"] = st.session_state["hmh_objects"][0]["object_id"]
                if placement_mode == "manual":
                    objects = [dict(item) for item in st.session_state.get("hmh_objects", default_manual_layout())]
                    st.subheader("Hidden Object Editor")
                    editor_controls, editor_preview = st.columns([0.38, 0.62], gap="large")
                    selected_id = resolve_selected_object_id(
                        objects, st.session_state.get("hidden_object_selected_id"))
                    selector_key = f"hmh_layer_selector_{background_hash}"
                    with editor_controls:
                        selected_index = None
                        if objects and selected_id is not None:
                            object_ids = [int(item["object_id"]) for item in objects]
                            selected_id = st.selectbox(
                                "Object layer", object_ids, index=object_ids.index(selected_id),
                                format_func=lambda object_id: (
                                    f"Object {object_id} • {manual_object_by_id(objects, object_id)['shape']} • "
                                    f"{manual_object_by_id(objects, object_id)['size_px']} px"),
                                key=selector_key,
                            )
                            st.session_state["hidden_object_selected_id"] = selected_id
                            selected_index = object_ids.index(selected_id)
                            current = dict(manual_object_by_id(objects, selected_id))
                            identity = current["object_id"]
                            source_label = st.radio(
                                "Object source", ["Shape", "PNG"], horizontal=True,
                                index=0 if current.get("source_type", "shape") == "shape" else 1,
                                key=f"hmh_source_{background_hash}_{identity}")
                            source_type = source_label.lower()
                            shape, color = current["shape"], current["color"]
                            png_asset_hash = current.get("png_asset_hash", "")
                            if source_type == "shape":
                                shape = st.selectbox("Shape", list(HIDDEN_SHAPES),
                                                     index=list(HIDDEN_SHAPES).index(current["shape"]),
                                                     key=f"hmh_shape_{background_hash}_{identity}")
                                color = st.color_picker(
                                    "Color", current.get("color", HIDDEN_COLORS[selected_index % len(HIDDEN_COLORS)]),
                                    key=f"hmh_color_{background_hash}_{identity}")
                            else:
                                object_upload = st.file_uploader(
                                    "Transparent object PNG", type=["png"],
                                    key=f"hmh_png_{background_hash}_{identity}")
                                if object_upload is not None:
                                    png_asset_hash = prepare_object_png(object_upload.getvalue())
                                if png_asset_hash:
                                    st.caption(f"PNG asset: {png_asset_hash[:10]}…")
                            live_values = live_motion_controls(
                                x_pct=float(current["x_pct"]), y_pct=float(current["y_pct"]),
                                size_px=int(current["size_px"]),
                                jump_height_px=int(current["jump_height_px"]),
                                bounce_speed=float(current.get("bounce_speed", 1.0)),
                                key=f"hmh_live_{background_hash}_{identity}")
                            objects = update_manual_object(
                                objects, selected_id, source_type=source_type, png_asset_hash=png_asset_hash,
                                shape=shape, color=color.upper(), **live_values)
                            st.session_state["hmh_objects"] = objects
                            if int(live_values["size_px"]) <= 3:
                                st.warning("Very small objects may disappear after video compression.")
                            elif int(live_values["size_px"]) <= 6:
                                st.info("Small objects may look different after social-media compression.")
                        else:
                            st.session_state["hidden_object_selected_id"] = None
                            st.info("No objects yet. Use Add object to begin.")

                        add_col, delete_col = st.columns(2)
                        if add_col.button("Add object", disabled=len(objects) >= 20, use_container_width=True):
                            objects, selected_id = add_manual_object(objects)
                            st.session_state["hmh_objects"] = objects
                            st.session_state["hidden_object_selected_id"] = selected_id
                            st.session_state.pop(selector_key, None)
                            st.rerun()
                        if delete_col.button("Delete object", disabled=selected_id is None, use_container_width=True):
                            objects, selected_id = delete_manual_object(objects, int(selected_id))
                            st.session_state["hmh_objects"] = objects
                            st.session_state["hidden_object_selected_id"] = selected_id
                            st.session_state.pop(selector_key, None)
                            st.rerun()
                        issues = manual_layout_errors(objects)
                        save_col, clear_col = st.columns(2)
                        if save_col.button("Save layout", disabled=bool(issues) or not objects,
                                           use_container_width=True):
                            path = save_manual_layout(background_hash, objects)
                            st.success(f"Layout saved: {path.name}")
                        if clear_col.button("Clear layout", disabled=not objects, use_container_width=True):
                            st.session_state["hmh_objects"] = []
                            st.session_state["hidden_object_selected_id"] = None
                            st.session_state.pop(selector_key, None)
                            st.rerun()
                        if issues:
                            st.warning("Layout check: " + " • ".join(issues))
                    with editor_preview:
                        live_motion_preview(
                            editor_preview_payload(background_hash, objects, selected_id),
                            key=f"hmh_preview_{background_hash}")
                        st.caption("Live 9:16 Final-coordinate preview • selected object is marked")
                    manual_objects = objects
            except ValueError as exc:
                st.error(str(exc))
    operation = "mixed"
    if selected_type == "quick_math":
        assert difficulty is not None
        operation = QUICK_MATH_FORMATS[st.selectbox("Format", list(QUICK_MATH_FORMATS))]
        from puzzly.config import QUICK_MATH_THINKING
        level_times = "/".join(f"{value:g}" for value in QUICK_MATH_THINKING[difficulty])
        format_label = "Şekil denklemleri" if operation == "shapes" else "Eksik işaretler (+ − × ÷)"
        st.caption(f"{format_label} • seviye seviye zorlaşır • {level_times} sn düşünme • son seviyelerde işlem önceliği tuzağı")
    theme = "boards" if selected_type == "puzzle_fit" else "auto"
    MEMORY_COLOR_LABELS = {"1 · Düşük — belirgin farklı renkler": 1, "2 · Orta — üç renk ailesi": 2,
                           "3 · Yüksek — komşu renk tonları": 3, "4 · Çok yüksek — tek renk ailesi": 4}
    if selected_type == "memory_challenge":
        color_level = MEMORY_COLOR_LABELS[st.selectbox("Renk benzerliği", list(MEMORY_COLOR_LABELS))]
        theme = f"colors_{color_level}"  # higher level = closer colours
    if selected_type == "puzzle_fit":
        st.selectbox("Theme", ["Jigsaw Boards"], disabled=True)
    challenges = None
    challenge_col, count_col = st.columns(2)
    if selected_type not in ("memory_challenge", "lucky_pick", "hidden_motion_hunt", "bounce_arena", "chess_mate", "matchstick",
                             "puzzle_fit", "cup_shuffle", "mind_mix"):
        challenge_label = challenge_col.selectbox("Challenges per video", ["Auto", "3", "4", "5"])
        challenges = None if challenge_label == "Auto" else int(challenge_label)
    else:
        if selected_type == "memory_challenge":
            from puzzly.config import MEMORY_LEVELS
            steps = " → ".join(f"{level['rows'] * level['cols']} kart ({'nerede' if level['kind'] == 'where' else 'hangisi kayboldu'}, "
                               f"{level['memorize']:g} sn ezber)" for level in MEMORY_LEVELS)
            st.caption(f"3 seviye • {steps} • renk benzerliği {color_level}/4 • yorum: skorun / 7")
    if selected_type == "flash_count":
        st.caption(f"Sayı görme • {FLASH_DIGITS[0]} → {FLASH_DIGITS[-1]} basamak • {FLASH_VISIBLE[4]:g} sn görünür (6 basamakta {FLASH_VISIBLE[6]:g} sn) • 3.0 sn düşünme")
    if selected_type == "cube_count":
        from puzzly.config import CUBE_VISIBLE
        st.caption(f"İzometrik küp kuleleri • {CUBE_VISIBLE[difficulty]:g} sn görünür • 3.0 sn düşünme • seviye seviye zorlaşır")
    if selected_type == "lucky_pick":
        st.caption("7 renk • 5.0 sn seçim • yılan kovalamacası • tek oyun")
    if selected_type == "line_follow":
        st.caption("Figürün çizgisi hangi hedefe gider? • ekranı dolduran uzun çizgiler • seviye seviye daha uzun ve karışık • yalnızca Hard")
    if selected_type == "hidden_motion_hunt":
        st.caption("Moving hidden objects • 18.0 sn continuous loop • no reveal")
    if selected_type == "bounce_arena":
        st.caption("6 colors • 5.0 sn Pick One • deterministic arena physics")
    if selected_type == "chess_mate":
        from puzzly.puzzles.chess_mate import rating_pool
        available = len(rating_pool(min_rating))
        st.caption(f"Lichess bulmaca veritabanı • tek hamlede mat • puan {min_rating}+ : {available:,} bulmaca".replace(",", ".")
                   + " • 30 sn sabit tahta • cevap gösterilmez (yorumlarda tartışılsın)")
        if not available:
            st.warning("Bu puanın üstünde bulmaca yok; daha düşük bir min rating gir.")
    if selected_type == "puzzle_fit":
        from puzzly.config import FIT_THINKING
        st.caption(f"Tek büyük resim • 3 eksik parça (A, B, C) • 6 yamuk numaralı şık, 3'ü tuzak • "
                   f"{FIT_THINKING[difficulty]:g} sn düşünme • yorum: A4 B1 C6")
    if selected_type == "mind_mix":
        from puzzly.config import MIX_FIT_THINKING
        st.caption(f"3 oyun, 3 seviye, her oyundan 1 zor seviye • 1. Memory (3×3, nerede?) • 2. Shade Spot (5×5, hangi kare değişti?) • "
                   f"3. Puzzle Fit (3 eksik parça, {MIX_FIT_THINKING:g} sn) • her oyun başında kısa tanıtım kartı • yorum: skorun / 3 • "
                   "nesne paleti uygulanmaz (renkler bulmacanın kendisi)")
    if selected_type == "shade_spot":
        from puzzly.config import SHADE_LEVELS
        steps = " → ".join(f"{level['grid']}×{level['grid']} (fark {level['delta']:g}, {level['thinking']:g} sn)" for level in SHADE_LEVELS)
        st.caption(f"İki ızgara, bir karenin tonu farklı • {steps} • yorum: karenin yeri (örn. B3) • nesne paleti uygulanmaz (renkler bulmacanın kendisi)")
    if selected_type == "laser_maze":
        from puzzly.config import LASER_TIER_SETS, LASER_TIERS
        count = challenges or DEFAULT_ROUNDS["laser_maze"]
        steps = " → ".join(f"{LASER_TIERS[tier]['n']}×{LASER_TIERS[tier]['n']} ({LASER_TIERS[tier]['thinking']:g} sn)" for tier in LASER_TIER_SETS[count])
        st.caption(f"Lazer aynalardan geçip hangi numaralı alıcıya ulaşır? • {count} seviye (en fazla 5), seviye sayısına göre zorluk ayarlanır: "
                   f"{steps} • yorum: alıcı numarası")
    if selected_type == "cup_shuffle":
        from puzzly.config import CUP_LEVELS
        levels = " → ".join(f"{level['cups']} bardak ({level['swaps']} karıştırma, {level['swap_seconds']:g} sn)" for level in CUP_LEVELS)
        st.caption(f"Topu takip et • 3 seviye • {levels} • topun yeri seviye başında gösterilir • yorum: bardak numarası")
    if selected_type == "matchstick":
        from puzzly.config import MATCH_THINKING
        match_times = "/".join(f"{value:g}" for value in MATCH_THINKING[difficulty])
        st.caption(f"Kibrit çöpü denklemleri • 1 çöp oynat, denklemi doğru yap • 3 seviye, her biri daha zor • "
                   f"{match_times} sn düşünme • her bulmacanın tek çözümü var")
    match_frame = None
    if selected_type == "matchstick":
        from puzzly.config import MATCH_FRAMES
        frame_labels = {"random": "Rastgele", **{key: label for key, (label, _) in MATCH_FRAMES.items()}}
        match_frame = st.selectbox("Çerçeve rengi", list(frame_labels), index=1, format_func=frame_labels.get,
                                   help="Kart çerçevesi, talimat balonu ve sayaç rengi")
    maze_shape = None
    if selected_type == "find_the_exit" and difficulty == "hard":
        shape_labels = {"rect": "Dikdörtgen", "circle": "Daire", "hex": "Altıgen", "star": "Yıldız",
                        "diamond": "Elmas", "mixed": "Karışık (rastgele)"}
        maze_shape = st.selectbox("Labirent şekli", list(shape_labels), format_func=shape_labels.get,
                                  help="Daire, altıgen, yıldız ve elmas: başlangıç ortada, çıkışlar çevrede (ilk 3 seviye 4, "
                                       "sonraki 2 seviye 5 çıkış). Karışık: 5 seviyede dikdörtgen, daire, altıgen, yıldız ve elmasın her biri bir kez, rastgele sırada (dikdörtgen dahil); zorluk seviyeyle artar.")
        if maze_shape == "mixed":
            st.caption("Karışık: her seviye farklı bir şekil (5 seviyede beşi de birer kez), sıra rastgele ama aynı tohum hep aynı videoyu üretir; zorluk seviyeyle artar.")
        elif maze_shape != "rect":
            st.caption("Şekil seviyeleri hücre sayısıyla zorlaşır (≈100 → ≈300 hücre); düşünme süreleri dikdörtgenle aynı.")
    chess_board = None
    if selected_type == "chess_mate":
        from puzzly.config import CHESS_BOARDS
        board_labels = {"random": "Rastgele", **{key: label for key, (label, _, _) in CHESS_BOARDS.items()}}
        chess_board = st.selectbox("Tahta rengi", list(board_labels), index=1, format_func=board_labels.get)
    count = count_col.selectbox("Number of videos", [1, 3, 5, 10, 30])
    quality_col, music_col, seed_col = st.columns(3)
    quality = quality_col.selectbox("Quality", ["Draft", "Final"]).lower()
    music_on = music_col.selectbox("Müzik", ["Kapalı", "Açık"]) == "Açık"
    seed_text = seed_col.text_input("Optional Seed", placeholder="Boş = otomatik")
    if music_on and (selected_type in ("missing_number", "hidden_motion_hunt")
                     or (selected_type == "find_the_exit" and difficulty != "hard")):
        st.caption("Müzik yalnızca Puzzly for You görünümündeki oyunlarda çalar; bu seçim müziksiz üretilir.")
    background_col, palette_col = st.columns(2)
    background_choice = background_col.selectbox("Arka plan rengi", list(BACKGROUND_LABELS),
                                                 format_func=BACKGROUND_LABELS.get)
    palette_choice = palette_col.selectbox("Nesne paleti", list(PALETTE_LABELS), format_func=PALETTE_LABELS.get)
    light_theme = selected_type in ("missing_number", "hidden_motion_hunt") or (
        selected_type == "find_the_exit" and difficulty != "hard")
    if light_theme and (background_choice != "random" or palette_choice != "classic"):
        st.caption("Bu oyun açık temalı; renk seçimleri yalnızca Puzzly for You görünümündeki oyunlara uygulanır.")
    elif selected_type == "memory_challenge" and palette_choice != "classic":
        st.caption("Memory Challenge kendi renk benzerliği ayarını kullanır; nesne paleti uygulanmaz.")

    if selected_type == "mixed":
        assert difficulty is not None
        challenge_summary = challenges or "1 veya 4–5 (Auto, türe göre)"
        durations = [(sum(intro_outro(kind, difficulty)) + round_duration(kind, difficulty)) if kind == "memory_challenge"
                     else (sum(intro_outro(kind, None)) + round_duration(kind, None)) if kind == "lucky_pick"
                     else sum(intro_outro(kind, difficulty)) + (challenges or default) * round_duration(kind, difficulty)
                     for kind, default in DEFAULT_ROUNDS.items() if kind not in ("hidden_motion_hunt", "bounce_arena", "chess_mate")]
        duration_summary = f"~{min(durations):.1f}–{max(durations):.1f} sn"
    else:
        if selected_type == "memory_challenge":
            challenge_summary = "3 levels, 7 questions"
            duration_summary = f"~{sum(intro_outro(selected_type, difficulty)) + round_duration(selected_type, difficulty):.1f} sn"
        elif selected_type == "lucky_pick":
            challenge_summary = "1 game"
            duration_summary = f"~{sum(intro_outro(selected_type, None)) + round_duration(selected_type, None):.1f} sn"
        elif selected_type == "hidden_motion_hunt":
            challenge_summary = "7 moving objects"
            duration_summary = f"{HIDDEN_MOTION_DURATION:.1f} sn"
        elif selected_type == "bounce_arena":
            challenge_summary = "1 game"
            duration_summary = "≤30.0 sn (doğal fiziğe göre)"
        elif selected_type == "chess_mate":
            from puzzly.config import CHESS_DURATION
            challenge_summary = "1 position"
            duration_summary = f"{CHESS_DURATION:.1f} sn"
        else:
            effective = challenges or DEFAULT_ROUNDS[selected_type]
            challenge_summary = effective
            if selected_type == "find_the_exit" and difficulty == "hard":
                average_round = exit_hard_average_round(effective)  # maze levels last longer as they grow
            elif selected_type == "line_follow":
                average_round = line_average_round(effective)  # bigger tangles get more thinking time
            elif selected_type == "puzzle_fit":
                from puzzly.config import fit_round
                average_round = fit_round(difficulty)
            elif selected_type == "laser_maze":
                from puzzly.config import laser_default_average
                average_round = laser_default_average(effective)  # bigger boards and longer beams get more time
            else:
                average_round = round_duration(selected_type, difficulty)
            duration_summary = f"~{sum(intro_outro(selected_type, difficulty)) + effective * average_round:.1f} sn"
    st.info(f"Type: {selected_type_label}  •  Challenges: {challenge_summary}  •  Estimated duration: {duration_summary}  •  Quality: {quality.title()}")

    left, right = st.columns(2)
    single_clicked = left.button("1 Video Üret", use_container_width=True, type="primary")
    batch_clicked = right.button("Toplu Video Üret", use_container_width=True)

    if single_clicked or batch_clicked:
        try:
            base_seed = int(seed_text) if seed_text.strip() else None
            if selected_type == "hidden_motion_hunt" and background_hash is None:
                raise ValueError("Background image upload is required.")
            if selected_type == "hidden_motion_hunt" and placement_mode == "manual" and not manual_objects:
                raise ValueError("Manual layout requires at least one object.")
            requested_count = 1 if single_clicked else count
            status, progress_bar, started = results_col.empty(), results_col.progress(0.0), time.perf_counter()

            def update_progress(index: int, total: int, spec, state: str) -> None:
                label = "tamamlandı" if state == "complete" else "işleniyor"
                challenge_text = ("3 levels" if spec.puzzle_type == "memory_challenge" else
                                  ("1 game" if spec.puzzle_type in ("lucky_pick", "bounce_arena", "chess_mate") else
                                   ("7 moving objects" if spec.puzzle_type == "hidden_motion_hunt" else f"{spec.round_count} challenge")))
                status.info(f"{index}/{total} • {spec.puzzle_type} • {challenge_text} • {label} • {time.perf_counter() - started:.1f} sn")
                progress_bar.progress((index if state == "complete" else index - 1) / total)

            background_bytes = background_upload.getvalue() if background_upload is not None else None
            specs = generate_unique_specs(requested_count, selected_type, difficulty or "easy", theme, base_seed,
                                          operation=operation, challenges=challenges, background_bytes=background_bytes,
                                          placement_mode=placement_mode, manual_objects=manual_objects,
                                          background=background_choice, palette=palette_choice, min_rating=min_rating,
                                          maze_shape=maze_shape)
            if music_on:  # stored in metadata, which stays out of the fingerprint
                from dataclasses import replace as _replace
                specs = [_replace(spec, metadata={**spec.metadata, "music": "on"}) for spec in specs]
            if match_frame:  # frame/timer colour: metadata, resolved per video so a Final re-render matches
                import random as _random
                from dataclasses import replace as _replace
                from puzzly.config import MATCH_FRAMES
                specs = [_replace(spec, metadata={**spec.metadata, "frame": match_frame if match_frame != "random"
                                                  else _random.Random(f"match_frame:{spec.seed}").choice(sorted(MATCH_FRAMES))})
                         for spec in specs]
            if chess_board:  # board colours: metadata as well, resolved per video so a Final re-render matches
                import random as _random
                from dataclasses import replace as _replace
                from puzzly.config import CHESS_BOARDS
                specs = [_replace(spec, metadata={**spec.metadata, "board": chess_board if chess_board != "random"
                                                  else _random.Random(f"chess_board:{spec.seed}").choice(sorted(CHESS_BOARDS))})
                         for spec in specs]
            if quality == "draft":
                batch_dir, previews = render_draft_previews(specs, progress=update_progress)
                videos = [preview.video_path for preview in previews]
                st.session_state["draft_previews"] = previews
                st.session_state["draft_saved"] = {}
                st.session_state["draft_final_paths"] = {}
            else:
                batch_dir, videos = render_batch(specs, quality=quality, progress=update_progress)
                st.session_state.pop("draft_previews", None)
                st.session_state["chess_answers"] = {str(path): spec.rounds[0].answer for path, spec in zip(videos, specs)
                                                     if spec.puzzle_type == "chess_mate"}
            progress_bar.progress(1.0)
            if quality == "draft":
                status.success(
                    f"Draft önizleme hazır • output klasörüne kaydedilmedi • {time.perf_counter() - started:.1f} sn")
                st.session_state["videos"], st.session_state["batch_dir"] = [], str(batch_dir)
            else:
                status.success(f"Tamamlandı: {batch_dir} • {time.perf_counter() - started:.1f} sn")
                st.session_state["videos"], st.session_state["batch_dir"] = [str(path) for path in videos], str(batch_dir)
        except ValueError as exc:
            message = str(exc)
            st.error(message if selected_type in ("hidden_motion_hunt", "chess_mate") else "Seed yalnızca tam sayı olmalıdır.")
        except Exception as exc:
            LOGGER.exception("Generation failed")
            st.error(f"Video üretilemedi: {exc}")

def show_chess_answer(answer: dict) -> None:
    """The mating move, for the creator only: the video never shows it."""
    from puzzly.puzzles.chess_mate import move_label
    st.success(f"♟️ Mat hamlesi: **{move_label(answer)}**")
    st.caption("Yalnızca sana gösterilir; videoda, kapakta ve açıklamada yer almaz.")


with results_col:
    if not st.session_state.get("draft_previews") and not st.session_state.get("videos"):
        st.info("Üretilen videolar burada görünecek.")
    if st.session_state.get("draft_previews"):
        saved = st.session_state.setdefault("draft_saved", {})
        final_paths = st.session_state.setdefault("draft_final_paths", {})
        for index, preview in enumerate(st.session_state["draft_previews"]):
            key = f"{preview.spec.id}-{index}"
            video_col, action_col = st.columns(2, gap="medium")  # vertical video left, actions beside it
            video_col.video(str(preview.video_path))
            with action_col:
                st.markdown("**Draft önizleme**")
                st.caption("Bu dosyalar geçici önizlemedir; Kaydet düğmesine basılmadan output klasörüne ve geçmişe eklenmez.")
                st.caption(f"Seed: {preview.spec.seed} • {preview.spec.puzzle_type} • geçici Draft")
                if preview.spec.puzzle_type == "chess_mate":
                    show_chess_answer(preview.spec.rounds[0].answer)
                if st.button("Draft'ı Kaydet", key=f"save-draft-{key}",
                             disabled=key in saved, use_container_width=True):
                    try:
                        record, saved_path = save_draft_preview(preview)
                        saved[key] = record.sequence_no
                        st.success(f"Draft kaydedildi: {saved_path}")
                    except Exception as exc:
                        LOGGER.exception("Draft save failed")
                        st.error(f"Draft kaydedilemedi: {exc}")
                if st.button("Final Olarak Üret", key=f"final-draft-{key}",
                             disabled=key in final_paths, use_container_width=True):
                    try:
                        history = HistoryStore()
                        if key in saved:
                            record = history.record(int(saved[key]))
                            if record is None:
                                raise ValueError("Kaydedilmiş Draft geçmişte bulunamadı.")
                            final_path = rerender_record_final(record, history=history)
                        else:
                            _, paths = render_batch([preview.spec], quality="final", history=history)
                            final_path = paths[0]
                            record = history.records()[-1]
                            saved[key] = record.sequence_no
                        final_paths[key] = str(final_path)
                        st.success(f"Final üretildi: {final_path}")
                    except Exception as exc:
                        LOGGER.exception("Draft final render failed")
                        st.error(f"Final üretilemedi: {exc}")
                if key in saved:
                    st.caption(f"History sequence: PZ_{int(saved[key]):04d}")
                if key in final_paths:
                    st.caption(f"Final: {final_paths[key]}")

    if st.session_state.get("videos"):
        for video_path in st.session_state["videos"]:
            video_col, info_col = st.columns(2, gap="medium")
            video_col.video(video_path)
            cover_path = str(Path(video_path).with_suffix(".jpg"))
            info_col.markdown("**Üretilen video**")
            info_col.caption(f"Video: {video_path}\n\nCover: {cover_path}")
            if video_path in st.session_state.get("chess_answers", {}):
                with info_col:
                    show_chess_answer(st.session_state["chess_answers"][video_path])

with controls_col:
    if os.name == "nt" and st.button("Çıktı klasörünü aç", use_container_width=True):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(Path(st.session_state.get("batch_dir", OUTPUT_DIR)))  # type: ignore[attr-defined]

    history_records = [record for record in HistoryStore().records()  # long-form videos are rendered from their own panel
                       if record.output_filename and not record.puzzle_type.startswith("longform")]
    if history_records:
        with st.expander("Kaydedilmiş videoyu Final olarak yeniden üret"):
            selected_sequence = st.selectbox(
                "Kaydedilmiş video",
                [record.sequence_no for record in reversed(history_records)],
                format_func=lambda sequence: next(
                    f"PZ_{record.sequence_no:04d} • {record.puzzle_type} • {record.quality or 'eski kayıt'}"
                    for record in history_records if record.sequence_no == sequence),
            )
            st.markdown("Kayıtlı VideoSpec ve seed kullanılır; yeni bulmaca oluşturulmaz.")
            if st.button("Seçili Videoyu Final Yeniden Üret", use_container_width=True):
                try:
                    history = HistoryStore()
                    record = history.record(int(selected_sequence))
                    if record is None:
                        raise ValueError("Video geçmiş kaydı bulunamadı.")
                    final_path = rerender_record_final(record, history=history)
                    st.success(f"Final hazır: {final_path}")
                    results_col.video(str(final_path))
                except Exception as exc:
                    LOGGER.exception("Saved video final rerender failed")
                    st.error(f"Final yeniden üretilemedi: {exc}")
