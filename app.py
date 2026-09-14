from __future__ import annotations

import logging
import os
from pathlib import Path
import time

import streamlit as st

from puzzly.config import DEFAULT_ROUNDS, FLASH_INTRO_DURATION, FLASH_VISIBLE_DURATIONS, HIDDEN_MOTION_DURATION, INTRO_DURATION, LUCKY_INTRO_DURATION, MEMORY_INTRO_DURATION, OUTRO_DURATION, OUTPUT_DIR, round_duration
from puzzly.generator import generate_unique_specs, render_batch
from puzzly.logging_config import configure_logging
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
OPERATION_LABELS = {"Mixed": "mixed", "Addition": "addition", "Subtraction": "subtraction", "Multiplication": "multiplication"}

st.set_page_config(page_title="Puzzly Shorts Generator", page_icon="🧩", layout="centered")
st.title("🧩 Puzzly Shorts Generator")
st.caption("Think • Play • Learn — çok turlu, tamamen yerel video üretimi")

selected_type_label = st.selectbox("Puzzle Type", list(TYPE_LABELS))
selected_type = TYPE_LABELS[selected_type_label]
difficulty = None if selected_type in ("lucky_pick", "hidden_motion_hunt") else st.selectbox("Difficulty", ["Easy", "Medium", "Hard"]).lower()
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
    available_operations = ["Mixed", "Addition", "Subtraction"] if difficulty == "easy" else list(OPERATION_LABELS)
    operation = OPERATION_LABELS[st.selectbox("Operation", available_operations)]
theme = "boards" if selected_type == "puzzle_fit" else "auto"
if selected_type == "puzzle_fit":
    st.selectbox("Theme", ["Jigsaw Boards"], disabled=True)
challenges = None
if selected_type not in ("memory_challenge", "lucky_pick", "hidden_motion_hunt"):
    challenge_label = st.selectbox("Challenges per video", ["Auto", "3", "4", "5"])
    challenges = None if challenge_label == "Auto" else int(challenge_label)
else:
    if selected_type == "memory_challenge":
        difficulty_hint = {"easy": "Yüksek renk kontrastı", "medium": "Orta renk benzerliği", "hard": "Benzer renk tonları"}[difficulty]
        st.caption(f"5 renkli şekil • 4 hafıza sorusu • {difficulty_hint}")
if selected_type == "flash_count":
    st.caption(f"Tek şekil ve renk • {FLASH_VISIBLE_DURATIONS[difficulty]:.2f} sn görünür • 3.0 sn düşünme")
if selected_type == "lucky_pick":
    st.caption("7 renk • 5.0 sn seçim • tek oyun")
if selected_type == "hidden_motion_hunt":
    st.caption("Moving hidden objects • 18.0 sn continuous loop • no reveal")
count = st.selectbox("Number of videos", [1, 3, 5, 10, 30])
quality = st.selectbox("Quality", ["Draft", "Final"]).lower()
seed_text = st.text_input("Optional Seed", placeholder="Boş = otomatik")

if selected_type == "mixed":
    assert difficulty is not None
    challenge_summary = challenges or "1 veya 4–5 (Auto, türe göre)"
    durations = [(MEMORY_INTRO_DURATION + round_duration(kind, difficulty) + OUTRO_DURATION) if kind == "memory_challenge"
                 else (LUCKY_INTRO_DURATION + round_duration(kind, None) + OUTRO_DURATION) if kind == "lucky_pick"
                 else (FLASH_INTRO_DURATION if kind == "flash_count" else INTRO_DURATION)
                 + (challenges or default) * round_duration(kind, difficulty) + OUTRO_DURATION
                 for kind, default in DEFAULT_ROUNDS.items() if kind not in ("line_follow", "hidden_motion_hunt")]
    duration_summary = f"~{min(durations):.1f}–{max(durations):.1f} sn"
else:
    if selected_type == "memory_challenge":
        challenge_summary = "4 recall + final reveal"
        duration_summary = f"~{MEMORY_INTRO_DURATION + round_duration(selected_type, difficulty) + OUTRO_DURATION:.1f} sn"
    elif selected_type == "lucky_pick":
        challenge_summary = "1 game"
        duration_summary = f"~{LUCKY_INTRO_DURATION + round_duration(selected_type, None) + OUTRO_DURATION:.1f} sn"
    elif selected_type == "hidden_motion_hunt":
        challenge_summary = "7 moving objects"
        duration_summary = f"{HIDDEN_MOTION_DURATION:.1f} sn"
    else:
        effective = challenges or DEFAULT_ROUNDS[selected_type]
        challenge_summary = effective
        intro = FLASH_INTRO_DURATION if selected_type == "flash_count" else INTRO_DURATION
        duration_summary = f"~{intro + effective * round_duration(selected_type, difficulty) + OUTRO_DURATION:.1f} sn"
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
        status, progress_bar, started = st.empty(), st.progress(0.0), time.perf_counter()

        def update_progress(index: int, total: int, spec, state: str) -> None:
            label = "tamamlandı" if state == "complete" else "işleniyor"
            challenge_text = ("4 recall" if spec.puzzle_type == "memory_challenge" else
                              ("1 game" if spec.puzzle_type == "lucky_pick" else
                               ("7 moving objects" if spec.puzzle_type == "hidden_motion_hunt" else f"{spec.round_count} challenge")))
            status.info(f"{index}/{total} • {spec.puzzle_type} • {challenge_text} • {label} • {time.perf_counter() - started:.1f} sn")
            progress_bar.progress((index if state == "complete" else index - 1) / total)

        background_bytes = background_upload.getvalue() if background_upload is not None else None
        specs = generate_unique_specs(requested_count, selected_type, difficulty or "easy", theme, base_seed,
                                      operation=operation, challenges=challenges, background_bytes=background_bytes,
                                      placement_mode=placement_mode, manual_objects=manual_objects)
        batch_dir, videos = render_batch(specs, quality=quality, progress=update_progress)
        progress_bar.progress(1.0)
        status.success(f"Tamamlandı: {batch_dir} • {time.perf_counter() - started:.1f} sn")
        st.session_state["videos"], st.session_state["batch_dir"] = [str(path) for path in videos], str(batch_dir)
    except ValueError as exc:
        message = str(exc)
        st.error(message if selected_type == "hidden_motion_hunt" else "Seed yalnızca tam sayı olmalıdır.")
    except Exception as exc:
        LOGGER.exception("Generation failed")
        st.error(f"Video üretilemedi: {exc}")

if st.session_state.get("videos"):
    st.subheader("Üretilen videolar")
    for video_path in st.session_state["videos"]:
        st.video(video_path)
        cover_path = str(Path(video_path).with_suffix(".jpg"))
        st.caption(f"Video: {video_path}\n\nCover: {cover_path}")

if os.name == "nt" and st.button("Çıktı klasörünü aç"):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    os.startfile(Path(st.session_state.get("batch_dir", OUTPUT_DIR)))  # type: ignore[attr-defined]
