"""GUI tests for the main window (offscreen, no real providers)."""

import os
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QMessageBox  # noqa: E402

from docfiler.cache_manager import CacheManager  # noqa: E402
from docfiler.gui.main_window import (  # noqa: E402
    COL_CONFIDENCE,
    COL_NEW_NAME,
    MainWindow,
    find_conflicts,
)
from docfiler.models import FilingSuggestion  # noqa: E402

from .conftest import make_config  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path):
    inbox = tmp_path / "inbox"
    library = tmp_path / "library"
    inbox.mkdir()
    library.mkdir()
    for name in ("a.pdf", "b.JPG"):
        (inbox / name).write_bytes(name.encode())
    config = make_config(input_dir=str(inbox), source_dir=str(library))

    with patch("docfiler.gui.main_window.load_config", return_value=config), patch(
        "docfiler.gui.main_window.create_cache_manager", return_value=CacheManager(tmp_path / "cache")
    ), patch("docfiler.gui.main_window.create_vlm_service", return_value=Mock()), patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
    ), patch.object(QMessageBox, "warning") as warning, patch.object(QMessageBox, "information"):
        w = MainWindow()
        qtbot.addWidget(w)
        w.inbox, w.library, w.warning = inbox, library, warning
        yield w


def test_loads_inbox_case_insensitively(window):
    assert [p.name for p in window.files] == ["a.pdf", "b.JPG"]
    assert window.file_list_model.item(0).text() == "a.pdf"  # no marker: not processed


def test_rename_in_place_carries_state(window):
    old = str(window.inbox / "a.pdf")
    window.suggestions[old] = FilingSuggestion("20240101 Bill.pdf", "Finances", 0.9, "r")

    window._execute(move=False)  # b.JPG has no suggestion, so only a.pdf is renamed

    new = window.inbox / "20240101 Bill.pdf"
    assert new.exists() and not (window.inbox / "a.pdf").exists()
    assert str(new) in window.suggestions and old not in window.suggestions
    assert "✓ 20240101 Bill.pdf" in [window.file_list_model.item(i).text() for i in range(2)]


def test_move_uses_dest_base_and_skips_empty_destination(window):
    a, b = str(window.inbox / "a.pdf"), str(window.inbox / "b.JPG")
    window.suggestions[a] = FilingSuggestion("Bill.pdf", "Finances/Bills", 0.9, "r")
    window.suggestions[b] = FilingSuggestion("Photo.JPG", "", 0.9, "r")

    window._execute(move=True)

    assert (window.library / "Finances" / "Bills" / "Bill.pdf").exists()
    assert (window.inbox / "b.JPG").exists()  # skipped: empty destination
    assert [p.name for p in window.files] == ["b.JPG"]


def _is_red(window, row: int) -> bool:
    return window.file_list_model.item(row, COL_NEW_NAME).background().style() != Qt.BrushStyle.NoBrush


def test_existing_target_and_bad_filename_are_refused(window):
    a, b = str(window.inbox / "a.pdf"), str(window.inbox / "b.JPG")
    window.suggestions[a] = FilingSuggestion("b.JPG", "", 0.9, "r")  # collides with b.JPG
    window.suggestions[b] = FilingSuggestion("../escape.JPG", "", 0.9, "r")

    window._execute(move=False)

    assert (window.inbox / "a.pdf").read_bytes() == b"a.pdf"
    assert (window.inbox / "b.JPG").read_bytes() == b"b.JPG"
    assert "Rename it first" in window.warning.call_args.args[2]


def test_name_conflicts_are_red_and_refused_until_renamed(window):
    manuals = window.library / "Manuals"
    manuals.mkdir()
    (manuals / "Guide.pdf").write_bytes(b"older guide")
    a, b = str(window.inbox / "a.pdf"), str(window.inbox / "b.JPG")
    window._on_file_processed(a, FilingSuggestion("Guide.pdf", "Manuals", 0.9, "r"))  # exists in library
    window._on_file_processed(b, FilingSuggestion("Photo.jpg", "Manuals", 0.9, "r"))
    assert _is_red(window, 0) and not _is_red(window, 1)

    window._execute(move=True)
    assert (window.inbox / "a.pdf").exists()  # refused
    assert (manuals / "Guide.pdf").read_bytes() == b"older guide"
    assert (manuals / "Photo.jpg").exists()  # the other file still moved

    window.file_list.setCurrentIndex(window.file_list_model.index(0, 0))
    window._on_viewer_edited(filename="Guide v2.pdf")
    assert not _is_red(window, 0)
    window._execute(move=True)
    assert (manuals / "Guide v2.pdf").read_bytes() == b"a.pdf"


def test_same_new_name_within_batch_refuses_both(window):
    for name in ("a.pdf", "b.JPG"):
        window._on_file_processed(str(window.inbox / name), FilingSuggestion("Guide.pdf", "Manuals", 0.9, "r"))
    assert _is_red(window, 0) and _is_red(window, 1)

    window._execute(move=True)

    assert not (window.library / "Manuals").exists()
    assert len(window.files) == 2


def test_find_conflicts(tmp_path):
    (tmp_path / "taken.pdf").touch()
    targets = {
        str(tmp_path / "1.pdf"): tmp_path / "taken.pdf",
        str(tmp_path / "2.pdf"): tmp_path / "dup.pdf",
        str(tmp_path / "3.pdf"): tmp_path / "dup.pdf",
        str(tmp_path / "4.pdf"): tmp_path / "free.pdf",
        str(tmp_path / "taken.pdf"): tmp_path / "taken.pdf",  # unchanged name: fine
        str(tmp_path / "5.pdf"): None,
    }
    assert set(find_conflicts(targets)) == {str(tmp_path / f"{n}.pdf") for n in (1, 2, 3)}


def test_table_shows_new_name_and_confidence(window):
    key = str(window.inbox / "a.pdf")
    window._on_file_processed(key, FilingSuggestion("Bill.pdf", "Finances/Bills", 0.876, "r"))
    model = window.file_list_model
    assert model.item(0).text() == "✓ a.pdf" and model.item(0).isCheckable()
    assert model.item(0, COL_NEW_NAME).text() == "Finances/Bills/Bill.pdf"
    assert model.item(0, COL_CONFIDENCE).text() == "88%"

    window.file_list.setCurrentIndex(model.index(0, 0))
    window._on_viewer_edited(destination="")
    assert model.item(0, COL_NEW_NAME).text() == "Bill.pdf"


def test_viewer_shows_start_of_long_name(window):
    long_name = "20240101 " + "Very Long Description " * 20 + ".pdf"
    window.file_viewer.set_suggestion(long_name, "Some/Deep/Destination", 0.5, "r")
    assert window.file_viewer.filename_edit.cursorPosition() == 0
    assert window.file_viewer.dest_edit.cursorPosition() == 0


def test_selecting_failed_file_keeps_error(window):
    key = str(window.inbox / "a.pdf")
    window._on_file_processed(key, RuntimeError("boom"))
    window.file_list.setCurrentIndex(window.file_list_model.index(1, 0))
    window.file_list.setCurrentIndex(window.file_list_model.index(0, 0))
    assert isinstance(window.suggestions[key], RuntimeError)
    assert window.file_list_model.item(0).text().startswith("❌")


def test_manual_edit_creates_suggestion(window):
    window.file_list.setCurrentIndex(window.file_list_model.index(0, 0))
    window._on_viewer_edited(filename="Manual.pdf")
    s = window.suggestions[str(window.inbox / "a.pdf")]
    assert isinstance(s, FilingSuggestion) and s.filename == "Manual.pdf"


def test_provider_switch_reverts_when_unavailable(window):
    window.provider_combo.setCurrentText("openai")  # no OPENAI key in test config
    assert window.config.vlm_provider == "claude"
    assert window.provider_combo.currentText() == "claude"
    assert window.warning.called

    window.provider_combo.setCurrentText("claude-cli")
    assert window.config.vlm_provider == "claude-cli"
