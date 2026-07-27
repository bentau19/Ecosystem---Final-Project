"""Unit tests for the virtual-drive directory-listing cache.

These exercise :class:`~services.vdrive_cache.ListingCache` in isolation — no Qt,
no service, no streams. The service-level behaviour it enables is covered in
``test_virtual_drive.py``.
"""

from services.vdrive_cache import ListingCache


def _entries(*names: str) -> list[dict]:
    """Build a sorted listing of entry dicts shaped like Android's response."""
    return [{"name": n, "is_dir": False, "size": 0, "mtime_ms": 0} for n in names]


def _cache(ttl_s: float = 5.0, max_dirs: int = 8) -> ListingCache:
    return ListingCache(ttl_s=ttl_s, max_dirs=max_dirs)


def test_put_then_get_returns_the_listing() -> None:
    """A freshly cached listing is served back with its entries and token."""
    cache = _cache()
    cache.put("/D", _entries("a", "b"), dir_mtime_ms=42, now=100.0)

    hit = cache.get("/D", now=100.5)

    assert hit is not None
    assert [e["name"] for e in hit.entries] == ["a", "b"]
    assert hit.dir_mtime_ms == 42


def test_get_misses_on_unknown_path() -> None:
    """An uncached path is a miss, not an error."""
    assert _cache().get("/nope", now=0.0) is None


def test_entry_expires_after_ttl() -> None:
    """A listing older than the TTL is a miss and is dropped."""
    cache = _cache(ttl_s=5.0)
    cache.put("/D", _entries("a"), dir_mtime_ms=0, now=100.0)

    assert cache.get("/D", now=104.9) is not None
    assert cache.get("/D", now=105.1) is None
    assert "/D" not in cache


def test_zero_mtime_token_is_still_cached() -> None:
    """dir_mtime_ms == 0 (Android stat returned null) must not disable caching.

    Freshness is decided by the TTL, not the token, and refusing to cache these
    would leave exactly the pathological folders paying a fetch per page.
    """
    cache = _cache()
    cache.put("/Android/data", [], dir_mtime_ms=0, now=1.0)

    hit = cache.get("/Android/data", now=1.5)

    assert hit is not None
    assert hit.entries == []


def test_evicts_least_recently_used_beyond_cap() -> None:
    """Past the cap the least recently *used* entry goes, not the oldest written."""
    cache = _cache(max_dirs=2)
    cache.put("/A", _entries("a"), dir_mtime_ms=0, now=1.0)
    cache.put("/B", _entries("b"), dir_mtime_ms=0, now=1.0)

    cache.get("/A", now=1.1)                                  # /A becomes MRU
    cache.put("/C", _entries("c"), dir_mtime_ms=0, now=1.2)   # evicts /B

    assert "/A" in cache
    assert "/C" in cache
    assert "/B" not in cache
    assert len(cache) == 2


def test_invalidate_parent_drops_both_path_and_parent() -> None:
    """A mutation invalidates the parent's listing and the entry's own."""
    cache = _cache()
    cache.put("/A", _entries("B"), dir_mtime_ms=0, now=1.0)
    cache.put("/A/B", _entries("x"), dir_mtime_ms=0, now=1.0)
    cache.put("/other", _entries("z"), dir_mtime_ms=0, now=1.0)

    cache.invalidate_parent("/A/B")

    assert "/A" not in cache
    assert "/A/B" not in cache
    assert "/other" in cache


def test_invalidate_parent_of_root_child_drops_root() -> None:
    """A top-level entry's parent is the root itself."""
    cache = _cache()
    cache.put("/", _entries("A"), dir_mtime_ms=0, now=1.0)

    cache.invalidate_parent("/A")

    assert "/" not in cache


def test_invalidate_parent_of_root_is_a_noop() -> None:
    """The root has no parent; invalidating it must not raise."""
    cache = _cache()
    cache.put("/", _entries("A"), dir_mtime_ms=0, now=1.0)

    cache.invalidate_parent("/")

    assert "/" not in cache  # the path itself is still dropped


def test_drop_subtree_removes_descendants_only() -> None:
    """Dropping /A removes /A and everything under it — but never a sibling /AB."""
    cache = _cache()
    for path in ("/A", "/A/B", "/A/B/C", "/AB", "/A2", "/other"):
        cache.put(path, _entries("x"), dir_mtime_ms=0, now=1.0)

    cache.drop_subtree("/A")

    assert "/A" not in cache
    assert "/A/B" not in cache
    assert "/A/B/C" not in cache
    # Prefix-boundary guard: these merely start with the same characters.
    assert "/AB" in cache
    assert "/A2" in cache
    assert "/other" in cache


def test_clear_forgets_everything() -> None:
    """clear() empties the cache (used on service stop)."""
    cache = _cache()
    cache.put("/A", _entries("a"), dir_mtime_ms=0, now=1.0)
    cache.put("/B", _entries("b"), dir_mtime_ms=0, now=1.0)

    cache.clear()

    assert len(cache) == 0
