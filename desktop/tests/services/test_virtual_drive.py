"""Unit tests for VirtualDriveService._page_entries pagination.

Critical invariant: ``next_after`` is ALWAYS a string, never ``None``.

VirtualDrive.exe's C++ ``ReadDirectory`` reads this field with nlohmann
``j.value("next_after", "")``, which falls back to the default ONLY when the key
is absent. A present-but-``null`` value makes ``get<std::string>()`` throw
``type_error.302``; that exception escapes the WinFsp callback and terminates the
(un-rebuildable) binary, tearing the drive down with "the I/O operation has been
aborted" on every empty folder. So an empty/last page must serialise
``next_after`` as ``""`` — never ``None``.
"""

from services.virtual_drive import VirtualDriveService


def _entries(*names: str) -> list[dict]:
    """Build a sorted listing of entry dicts shaped like Android's response."""
    return [{"name": n, "is_dir": False, "size": 0, "mtime_ms": 0} for n in names]


def test_empty_dir_next_after_is_empty_string_not_none() -> None:
    """An empty directory must page to ``next_after == ""`` (never ``None``).

    This is the exact regression that crashed VirtualDrive.exe: ``None`` →
    JSON ``null`` → nlohmann ``type_error.302`` inside ``ReadDirectory``.
    """
    result = VirtualDriveService._page_entries([], None, 200)

    assert result == {
        "ok": True,
        "entries": [],
        "has_more": False,
        "next_after": "",
    }
    # Guard the invariant explicitly so a future refactor can't reintroduce null.
    assert result["next_after"] is not None
    assert isinstance(result["next_after"], str)


def test_last_page_next_after_is_string() -> None:
    """A non-empty page that exhausts the listing: ``has_more`` False, cursor a str."""
    result = VirtualDriveService._page_entries(_entries("a", "b"), None, 200)

    assert [e["name"] for e in result["entries"]] == ["a", "b"]
    assert result["has_more"] is False
    assert result["next_after"] == "b"
    assert isinstance(result["next_after"], str)


def test_full_page_sets_has_more_and_cursor() -> None:
    """More entries than the limit: ``has_more`` True, cursor = last name of page."""
    result = VirtualDriveService._page_entries(_entries("a", "b", "c"), None, 2)

    assert [e["name"] for e in result["entries"]] == ["a", "b"]
    assert result["has_more"] is True
    assert result["next_after"] == "b"


def test_after_cursor_advances_to_remainder() -> None:
    """Paging with the previous page's cursor returns only the remainder."""
    result = VirtualDriveService._page_entries(_entries("a", "b", "c"), "b", 2)

    assert [e["name"] for e in result["entries"]] == ["c"]
    assert result["has_more"] is False
    assert result["next_after"] == "c"


def test_after_cursor_past_end_is_empty_page() -> None:
    """A cursor at/after the last entry yields an empty page with ``next_after == ""``."""
    result = VirtualDriveService._page_entries(_entries("a", "b"), "b", 200)

    assert result["entries"] == []
    assert result["has_more"] is False
    assert result["next_after"] == ""
