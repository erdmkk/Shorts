"""Streamlit panel for the YouTube long-form (16:9) videos: the ten-game Brain Test and the Quick Math pilot."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import time

import streamlit as st

from ..config import OUTPUT_DIR
from ..palette import BACKGROUND_LABELS

LOGGER = logging.getLogger(__name__)


BRAIN_TEST, QUICK_MATH = "Brain Test — 10 oyun (~9 dk)", "Quick Math — 30 bulmaca (~9 dk)"


def _render(longform, results_col, seed, quality: str, background: str, music: bool) -> None:
    from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException
    status, bar, started = results_col.empty(), results_col.progress(0.0), time.perf_counter()
    ui = {"live": True}

    def progress(share: float) -> None:
        # A click elsewhere on the page asks Streamlit to rerun; that must never abort a long render,
        # so progress updates simply stop until the render has finished and its result is stored.
        if not ui["live"]:
            return
        try:
            bar.progress(min(1.0, share))
            status.info(f"Render ediliyor • %{share * 100:.0f} • {time.perf_counter() - started:.0f} sn")
        except ScriptControlException:
            ui["live"] = False

    extra = {}
    if hasattr(longform, "build_plan"):  # the Brain Test builds its puzzles first, which takes a minute or two
        extra["planning"] = lambda message: status.info(message) if ui["live"] else None
    try:
        result = longform.produce(seed=seed, quality=quality, background=background, music=music, progress=progress, **extra)
    except Exception as exc:
        LOGGER.exception("Long-form generation failed")
        status.error(f"Uzun video üretilemedi: {exc}")
        return
    plan = result["plan"]
    st.session_state["longform_result"] = {key: str(value) for key, value in result.items()
                                           if key in ("video", "thumbnail", "text")}
    st.session_state["longform_meta"] = {**plan.metadata(), "seed": plan.seed, "theme": plan.theme,
                                         "music": plan.music, "sequence": result.get("sequence"),
                                         "episode": getattr(plan, "episode", None)}
    bar.progress(1.0)
    label = f"PZ_{result['sequence']:04d}" if result.get("sequence") else "Draft (geçmişe eklenmedi)"
    status.success(f"Hazır • {time.perf_counter() - started:.0f} sn • {label} • Seed {plan.seed}")


def longform_panel() -> None:
    from .. import braintest, longform
    controls_col, results_col = st.columns([0.4, 0.6], gap="large")
    with controls_col:
        kind = st.radio("Uzun video türü", [BRAIN_TEST, QUICK_MATH], key="longform_kind")
        engine = braintest if kind == BRAIN_TEST else longform
        if engine is braintest:
            st.markdown("**Brain Test — 10 oyun, tek skor (YouTube, 16:9)**")
            st.caption("Açılış → 4 blok, 13 oyun: Cup Shuffle, Puzzle Fit, Quick Math · Cube Count, Matchstick, Mate in 1 · "
                       "Memory, Puzzle Fit, Mate in 1, Quick Math (Kayıp Operatör) · Cube Count, Find the Exit, Line Follow. "
                       "Quick Math her bloğun sonunda (en zoru). Her oyundan önce nasıl oynanır; anlık açılan oyunlarda "
                       "ARE YOU READY? ve 3 saniyelik sayaç. İlk 3 blok sonunda puan kontrolü, sonda final skor. "
                       "Mate in 1 cevabı gösterilir (15 sn düşünme).")
        else:
            st.markdown("**Quick Math — Beynini test et (YouTube, 16:9)**")
            st.caption("Açılış → Tur 1: Şekil Denklemleri (10) → Tur 2: Kayıp Operatör (10) → Şans molası: Bounce Arena (+1 bonus) "
                       "→ Tur 3: Final, en zor seviyeler (10) → Final skor (?/31) → kapanış. Her turdan önce nasıl oynanır, "
                       "sonra puan kartı; oyun sırasında solda tur ve ilerleme, sağda skor tablosu ve sıradaki bölüm.")
        background_col, music_col = st.columns(2)
        background = background_col.selectbox("Arka plan rengi", list(BACKGROUND_LABELS), format_func=BACKGROUND_LABELS.get,
                                              key="longform_background")
        music = music_col.selectbox("Müzik", ["Kapalı", "Açık"], key="longform_music") == "Açık"
        quality_col, seed_col = st.columns(2)
        quality = quality_col.selectbox("Quality", ["Draft", "Final"], key="longform_quality").lower()
        seed_text = seed_col.text_input("Optional Seed", placeholder="Boş = otomatik", key="longform_seed")
        minutes = engine.estimated_duration() / 60
        render_hint = "Draft önizleme birkaç dakika sürer" if quality == "draft" else "Final render yaklaşık 10-20 dk sürer"
        if engine is braintest:
            puzzles = braintest.expected_points()
            st.info(f"Tür: YouTube uzun video • Brain Test #{braintest.episode_number()} • {puzzles} puan • ~{minutes:.1f} dk • {render_hint}")
            st.caption("Kapak numarası yalnızca kaydedilmiş (Final) videolardan sayılır: Draft üretmek veya kaydetmemek numarayı "
                       "harcamaz. Kapağın düzeni, renkleri, öne çıkan oyunu ve başlığı her bölümde değişir.")
        else:
            st.info(f"Tür: YouTube uzun video • {longform.BEST_SCORE - 1} bulmaca + 1 bonus • ~{minutes:.0f} dk • {render_hint}")
        if st.button("Uzun Video Üret", type="primary", use_container_width=True):
            try:
                seed = int(seed_text) if seed_text.strip() else None
            except ValueError:
                st.error("Seed yalnızca tam sayı olmalıdır.")
            else:
                _render(engine, results_col, seed, quality, background, music)
        meta = st.session_state.get("longform_meta", {})
        if meta and not meta.get("sequence") and st.button("Bu videoyu Final olarak üret", use_container_width=True,
                                                            help="Aynı seed, arka plan ve müzikle Final render"):
            _render(braintest if meta.get("episode") else longform, results_col, meta["seed"], "final", meta["theme"], meta["music"])
    result = st.session_state.get("longform_result")
    with controls_col:
        if os.name == "nt" and st.button("Uzun video klasörünü aç", use_container_width=True):
            folder = Path(result["video"]).parent if result and Path(result["video"]).parent.is_dir() else OUTPUT_DIR / "longform"
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)  # type: ignore[attr-defined]
    with results_col:
        if not result:
            st.info("Üretilen uzun video burada görünecek.")
            return
        files = {key: Path(value) for key, value in result.items()}
        if not all(path.is_file() for path in files.values()):
            st.warning("Son üretilen dosyalar bulunamadı (silinmiş olabilir). Yeniden üretebilirsiniz.")
            return
        meta = st.session_state.get("longform_meta", {})
        st.video(str(files["video"]))
        st.image(str(files["thumbnail"]), caption="YouTube kapak görseli (1920×1080)")
        download_cols = st.columns(3)
        downloads = (("video", "Videoyu indir", "video/mp4"), ("thumbnail", "Kapağı indir", "image/jpeg"),
                     ("text", "Metni indir", "text/plain"))
        for column, (key, label, mime) in zip(download_cols, downloads):
            column.download_button(label, data=files[key].read_bytes(), file_name=files[key].name, mime=mime,
                                   use_container_width=True, key=f"longform_download_{key}")
        st.text_input("Başlık", meta.get("title", ""), key=f"longform_title_{meta.get('seed')}")
        st.text_area("Açıklama (bölümler dahil)", meta.get("description", ""), height=260, key=f"longform_description_{meta.get('seed')}")
        st.text_input("Etiketler", meta.get("tags", ""), key=f"longform_tags_{meta.get('seed')}")
        if "seed" in meta:
            episode = f"Brain Test #{meta['episode']} • " if meta.get("episode") else ""
            st.caption(f"{episode}Seed: {meta['seed']} • Arka plan: {BACKGROUND_LABELS.get(meta['theme'], meta['theme'])} • "
                       f"Müzik: {'Açık' if meta['music'] else 'Kapalı'}")
        st.caption(f"Video: {files['video']}\n\nKapak: {files['thumbnail']}\n\nMetin: {files['text']}")
