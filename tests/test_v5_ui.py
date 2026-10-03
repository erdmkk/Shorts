from streamlit.testing.v1 import AppTest


def test_ui_supports_path_types_and_difficulty_duration() -> None:
    app = AppTest.from_file("app.py").run()
    assert not app.exception
    selector = app.selectbox[0]
    assert "Find the Exit" in selector.options and "Line Follow" in selector.options
    assert "Memory Challenge" not in selector.options and "Mind Mix" in selector.options  # memory is paused: it plays in Mind Mix
    assert "Flash Count" in selector.options
    selector.select("Find the Exit").run()
    app.selectbox[1].select("Hard").run()
    assert "46.0" in app.info[0].value  # 1.0 intro + levels of 6/7/8/9 s thinking + 3.6 outro
    assert "Challenges: 4" in app.info[0].value
    app.selectbox[0].select("Karışık").run()
    assert "4–5" in app.info[0].value
    assert not app.exception


def test_flash_count_ui_uses_auto_four_and_dynamic_timing() -> None:
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Flash Count").run()
    assert not app.exception
    assert "Challenges: 4" in app.info[0].value and "32.0" in app.info[0].value  # Hard only: 4.0 (hook + READY) + 4 x 6.1 + 3.6
    assert "0.2 sn görünür" in app.caption[-1].value
    difficulty = next(box for box in app.selectbox if box.label == "Difficulty")
    assert difficulty.options == ["Hard"] and difficulty.disabled and "4 → 6 basamak" in app.caption[-1].value


def test_mind_mix_ui_hides_challenge_control_and_shows_its_timing() -> None:
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Mind Mix").run()
    assert not app.exception
    assert "Challenges: 3" in app.info[0].value and "61.1" in app.info[0].value  # 1.0 hook + 3 x (1.8 card + game) + 3.6 end card
    assert all(box.label not in ("Operation", "Challenges per video", "Renk benzerliği") for box in app.selectbox)
    difficulty = next(box for box in app.selectbox if box.label == "Difficulty")
    assert difficulty.options == ["Hard"] and difficulty.disabled  # produced only in Hard
    assert "3 oyun" in app.caption[-1].value and "Memory" in app.caption[-1].value and "Puzzle Fit" in app.caption[-1].value


def test_lucky_pick_ui_hides_difficulty_and_challenges() -> None:
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Lucky Pick").run()
    assert not app.exception
    labels = [box.label for box in app.selectbox]
    assert "Difficulty" not in labels and "Challenges per video" not in labels
    assert "Number of videos" in labels and "Quality" in labels
    assert "1 game" in app.info[0].value and "26.5" in app.info[0].value  # 24.5 before the end card grew by 2 s
    assert "7 renk • 5.0 sn seçim" in app.caption[-1].value and "yılan kovalamacası" in app.caption[-1].value


def test_music_toggle_defaults_off() -> None:
    app = AppTest.from_file("app.py").run()
    music = next(box for box in app.selectbox if box.label == "Müzik")
    assert music.value == "Kapalı" and music.options == ["Kapalı", "Açık"]
    music.select("Açık").run()
    app.selectbox[0].select("Missing Number").run()
    assert not app.exception and any("yalnızca Puzzly for You" in caption.value for caption in app.caption)
    app.selectbox[0].select("Flash Count").run()  # now in the Puzzly for You look, so it has music
    assert not any("yalnızca Puzzly for You" in caption.value for caption in app.caption)
    app.selectbox[0].select("Cube Count").run()
    assert not any("yalnızca Puzzly for You" in caption.value for caption in app.caption)
