import gc
import time
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from audio_to_video import gui  # noqa: E402
from audio_to_video.gui import (  # noqa: E402
    DEFAULT_RESOLUTION,
    FORMAT_CHOICES,
    RESOLUTION_CHOICES,
    options_from_choices,
)

pytestmark = pytest.mark.gui


def test_options_from_choices():
    mkv_label = next(k for k, v in FORMAT_CHOICES.items() if v == "mkv")
    opts = options_from_choices(mkv_label, "Original image size")
    assert opts.output_format == "mkv"
    assert opts.max_width is None
    assert RESOLUTION_CHOICES[DEFAULT_RESOLUTION] == 1280


@pytest.fixture(scope="module")
def root():
    # One Tk interpreter per module: repeatedly creating tk.Tk() in one
    # process is unreliable on Windows.
    try:
        tk_root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    tk_root.withdraw()
    yield tk_root
    tk_root.destroy()


@pytest.fixture
def app(root, monkeypatch):
    # Never block on dialogs during tests.
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: False)
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: None)
    window = tk.Toplevel(root)
    window.withdraw()
    application = gui.App(window)
    yield application
    window.destroy()
    # Free Tk objects on the main thread, not later from a worker thread.
    gc.collect()


def _wait_until_idle(app, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if app._worker is not None and not app._worker.is_alive():
            # Let the polling loop drain the remaining events.
            for _ in range(5):
                app.update()
                time.sleep(0.12)
            return
        time.sleep(0.05)
    raise TimeoutError("conversion did not finish")


def test_set_audio_suggests_output(app):
    app.set_audio(str(Path("music") / "song.flac"))
    assert app.output_var.get() == str(Path("music") / "song.mp4")


def test_format_change_updates_extension(app):
    app.set_audio("song.wav")
    app.format_var.set(next(k for k, v in FORMAT_CHOICES.items() if v == "mkv"))
    app._sync_output_extension()
    assert app.output_var.get().endswith("song.mkv")


def test_start_without_files_does_nothing(app):
    app.start()
    assert app._worker is None


@pytest.mark.integration
def test_full_conversion_through_gui(app, media, tmp_path):
    out = tmp_path / "gui.mp4"
    app.set_audio(str(media["mp3"]))
    app.image_var.set(str(media["png"]))
    app.output_var.set(str(out))
    app.start()
    assert str(app.convert_button["state"]) == "disabled"
    _wait_until_idle(app)
    assert out.is_file()
    assert app.status_var.get().startswith("Done")
    assert app.progress_var.get() == 1.0
    assert str(app.convert_button["state"]) == "normal"


@pytest.mark.integration
def test_gui_reports_error(app, tmp_path, media):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio")
    app.set_audio(str(bad))
    app.image_var.set(str(media["png"]))
    app.output_var.set(str(tmp_path / "o.mp4"))
    app.start()
    _wait_until_idle(app)
    assert app.status_var.get() == "Error"
