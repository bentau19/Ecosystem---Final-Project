"""Unit tests for checkers/pdf.py — check_pdf()."""

from pathlib import Path

import pytest

from checkers.pdf import check_pdf

_MINIMAL_VALID_PDF: bytes = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\n%%EOF"


# ---------------------------------------------------------------------------
# Valid PDFs
# ---------------------------------------------------------------------------

def test_minimal_valid_pdf_returns_false(tmp_path: Path) -> None:
    path = tmp_path / "valid.pdf"
    path.write_bytes(_MINIMAL_VALID_PDF)
    assert check_pdf(path) is False


def test_eof_marker_within_last_1024_bytes_returns_false(tmp_path: Path) -> None:
    padding = b"X" * 2000
    path = tmp_path / "large.pdf"
    path.write_bytes(b"%PDF-1.4\n" + padding + b"\n%%EOF\n")
    assert check_pdf(path) is False


# ---------------------------------------------------------------------------
# Corrupt / invalid PDFs
# ---------------------------------------------------------------------------

def test_missing_header_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "no_header.pdf"
    path.write_bytes(b"This is not a PDF at all\n%%EOF")
    assert check_pdf(path) is True


def test_wrong_header_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "wrong_header.pdf"
    path.write_bytes(b"%PD-1.4\nsome content\n%%EOF")
    assert check_pdf(path) is True


def test_missing_eof_marker_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "no_eof.pdf"
    path.write_bytes(b"%PDF-1.4\nsome content without end marker")
    assert check_pdf(path) is True


def test_eof_marker_too_far_from_end_returns_true(tmp_path: Path) -> None:
    # %%EOF appears early, followed by more than 1024 bytes of garbage
    early_eof = b"%PDF-1.4\n%%EOF\n"
    tail_garbage = b"Z" * 2000
    path = tmp_path / "eof_too_early.pdf"
    path.write_bytes(early_eof + tail_garbage)
    assert check_pdf(path) is True


def test_empty_file_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.touch()
    assert check_pdf(path) is True


def test_header_only_no_eof_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "header_only.pdf"
    path.write_bytes(b"%PDF-")
    assert check_pdf(path) is True


def test_nonexistent_path_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "ghost.pdf"
    assert check_pdf(path) is True


def test_garbage_bytes_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "garbage.pdf"
    path.write_bytes(b"\x00\x01\x02\x03" * 200)
    assert check_pdf(path) is True
