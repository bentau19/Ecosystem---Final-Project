"""Unit tests for utils.styles — _replace_colors_placeholders and load_stylesheet."""

from unittest.mock import MagicMock, patch

import pytest

from resources.colors import Colors, ColorsEnum
from utils.styles import _replace_colors_placeholders, load_stylesheet


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _TwoColors(ColorsEnum):
    PRIMARY = "#112233"
    SECONDARY = "#aabbcc"


@pytest.fixture()
def mock_qfile() -> MagicMock:
    qfile = MagicMock()
    qfile.open.return_value = True
    return qfile


@pytest.fixture()
def mock_stream() -> MagicMock:
    stream = MagicMock()
    stream.readAll.return_value = ""
    return stream


# ---------------------------------------------------------------------------
# _replace_colors_placeholders
# ---------------------------------------------------------------------------


def test_replace_substitutes_single_placeholder() -> None:
    result = _replace_colors_placeholders("color: {{PRIMARY}};", _TwoColors)
    assert result == "color: #112233;"


def test_replace_substitutes_multiple_placeholders() -> None:
    result = _replace_colors_placeholders(
        "a: {{PRIMARY}}; b: {{SECONDARY}};", _TwoColors
    )
    assert result == "a: #112233; b: #aabbcc;"


def test_replace_leaves_unknown_placeholder_unchanged() -> None:
    result = _replace_colors_placeholders("color: {{UNKNOWN}};", _TwoColors)
    assert result == "color: {{UNKNOWN}};"


def test_replace_empty_qss_returns_empty() -> None:
    result = _replace_colors_placeholders("", _TwoColors)
    assert result == ""


def test_replace_qss_with_no_placeholders_unchanged() -> None:
    original = "background: red; color: blue;"
    result = _replace_colors_placeholders(original, _TwoColors)
    assert result == original


def test_replace_same_placeholder_multiple_times() -> None:
    result = _replace_colors_placeholders(
        "{{PRIMARY}} and {{PRIMARY}}", _TwoColors
    )
    assert result == "#112233 and #112233"


def test_replace_uses_colors_enum_values() -> None:
    result = _replace_colors_placeholders(
        "{{SURFACE_PRIMARY}}", Colors
    )
    assert result == Colors.SURFACE_PRIMARY.value


# ---------------------------------------------------------------------------
# load_stylesheet — FileNotFoundError
# ---------------------------------------------------------------------------


def test_load_stylesheet_raises_when_file_not_found(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    mock_qfile.open.return_value = False

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
        pytest.raises(FileNotFoundError),
    ):
        load_stylesheet("missing.qss")


def test_load_stylesheet_error_message_contains_path(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    mock_qfile.open.return_value = False

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
        pytest.raises(FileNotFoundError, match="missing.qss"),
    ):
        load_stylesheet("missing.qss")


# ---------------------------------------------------------------------------
# load_stylesheet — happy path
# ---------------------------------------------------------------------------


def test_load_stylesheet_returns_string(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    mock_stream.readAll.return_value = "background: red;"

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
    ):
        result = load_stylesheet("style.qss")

    assert isinstance(result, str)


def test_load_stylesheet_applies_default_colors_to_placeholders(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    mock_stream.readAll.return_value = "color: {{TEXT_PRIMARY}};"

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
    ):
        result = load_stylesheet("style.qss")

    assert "{{TEXT_PRIMARY}}" not in result
    assert Colors.TEXT_PRIMARY.value in result


def test_load_stylesheet_applies_custom_color_class(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    mock_stream.readAll.return_value = "border: {{PRIMARY}};"

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
    ):
        result = load_stylesheet("style.qss", color_classes=[_TwoColors])

    assert result == "border: #112233;"


def test_load_stylesheet_applies_multiple_custom_color_classes(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    class _Extra(ColorsEnum):
        HIGHLIGHT = "#ffffff"

    mock_stream.readAll.return_value = "a: {{PRIMARY}}; b: {{HIGHLIGHT}};"

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
    ):
        result = load_stylesheet("style.qss", color_classes=[_TwoColors, _Extra])

    assert "{{PRIMARY}}" not in result
    assert "{{HIGHLIGHT}}" not in result
    assert "#112233" in result
    assert "#ffffff" in result


def test_load_stylesheet_closes_file_after_reading(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    mock_stream.readAll.return_value = ""

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
    ):
        load_stylesheet("style.qss")

    mock_qfile.close.assert_called_once()


def test_load_stylesheet_closes_file_even_when_no_color_classes(
    mock_qfile: MagicMock, mock_stream: MagicMock
) -> None:
    mock_stream.readAll.return_value = ""

    with (
        patch("utils.styles.QFile", return_value=mock_qfile),
        patch("utils.styles.QTextStream", return_value=mock_stream),
    ):
        load_stylesheet("style.qss", color_classes=None)

    mock_qfile.close.assert_called_once()
