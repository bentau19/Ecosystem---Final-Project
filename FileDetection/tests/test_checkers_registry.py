"""Unit tests for checkers/registry.py — get_checker() dispatch table."""

import pytest

from checkers.image import check_image
from checkers.pdf import check_pdf
from checkers.registry import get_checker
from checkers.zip_based import check_zip


# ---------------------------------------------------------------------------
# Image extensions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext", [
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".ico",
])
def test_image_extensions_return_check_image(ext: str) -> None:
    assert get_checker(ext) is check_image


# ---------------------------------------------------------------------------
# ZIP-based extensions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext", [
    ".zip", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub", ".apk", ".jar",
])
def test_zip_based_extensions_return_check_zip(ext: str) -> None:
    assert get_checker(ext) is check_zip


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def test_pdf_extension_returns_check_pdf() -> None:
    assert get_checker(".pdf") is check_pdf


# ---------------------------------------------------------------------------
# Unknown / unsupported extensions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext", [
    ".mp4", ".txt", ".exe", ".py", ".mp3", ".avi", ".csv", ".xml", ".html",
])
def test_unknown_extensions_return_none(ext: str) -> None:
    assert get_checker(ext) is None


def test_empty_string_returns_none() -> None:
    assert get_checker("") is None


def test_uppercase_extension_returns_none() -> None:
    assert get_checker(".JPG") is None


def test_extension_without_leading_dot_returns_none() -> None:
    assert get_checker("jpg") is None


def test_partial_extension_returns_none() -> None:
    assert get_checker(".pd") is None
