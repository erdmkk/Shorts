from streamlit.testing.v1 import AppTest


def test_ui_supports_path_types_and_difficulty_duration() -> None:
    app = AppTest.from_file("app.py").run()
    assert not app.exception
    selector = app.selectbox[0]
    assert "Find the Exit" in selector.options and "Line Follow" not in selector.options
    assert "Memory Challenge" in selector.options
    assert "Flash Count" in selector.options
    selector.select("Find the Exit").run()
    app.selectbox[1].select("Hard").run()
    assert "39.4" in app.info[0].value
    assert "Challenges: 4" in app.info[0].value
    app.selectbox[0].select("Karışık").run()
    assert "4–5" in app.info[0].value
    assert not app.exception


def test_flash_count_ui_uses_auto_four_and_dynamic_timing() -> None:
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Flash Count").run()
    assert not app.exception
    assert "Challenges: 4" in app.info[0].value and "26.0" in app.info[0].value
    assert "1.20 sn görünür" in app.caption[-1].value


def test_memory_ui_hides_challenge_control_and_shows_new_timing() -> None:
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Memory Challenge").run()
    assert not app.exception
    assert "4 recall + final reveal" in app.info[0].value
    assert "25.0" in app.info[0].value
    assert all(box.label not in ("Operation", "Challenges per video") for box in app.selectbox)
    assert "5 renkli şekil" in app.caption[-1].value


def test_lucky_pick_ui_hides_difficulty_and_challenges() -> None:
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Lucky Pick").run()
    assert not app.exception
    labels = [box.label for box in app.selectbox]
    assert "Difficulty" not in labels and "Challenges per video" not in labels
    assert "Number of videos" in labels and "Quality" in labels
    assert "1 game" in app.info[0].value and "23.2" in app.info[0].value
    assert "7 renk • 5.0 sn seçim" in app.caption[-1].value
