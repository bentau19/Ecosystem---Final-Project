"""Short-TTL cache of full directory listings for the virtual drive.

WinFsp enumerates a directory one page at a time, so
:class:`~services.virtual_drive.VirtualDriveService` receives a burst of
``list_page`` ops for the same path. Each one is backed by a ``list_full``
round-trip to the phone that ships the *entire* directory as JSON, of which a
single page is kept — so an N-entry folder cost ``ceil(N / LIST_PAGE_SIZE)``
complete enumerations. This cache collapses that burst to one fetch.

Why a TTL and not revalidation against Android's ``dir_mtime_ms`` token:

1. ``list_full`` returns the token *together with* the listing, so revalidating
   costs exactly as much as refetching. There is no cheap "read the directory
   mtime" op, and adding one would buy nothing.
2. A directory's mtime changes when children are added, removed or renamed —
   but **not** when a child is rewritten in place. Revalidation alone would
   serve a stale ``size`` indefinitely; a TTL bounds staleness unconditionally.

The token is still recorded on :class:`CachedListing`: it costs nothing and
leaves the door open for opt-in revalidation under an absolute age ceiling.

Entries are stored **sorted by name**. Android's ``list_full`` is backed by
``File.listFiles()``, which is unordered, and the page cursor
(``VirtualDriveService._page_entries``) binary-searches on name — so sorting is
what makes pagination correct, not a presentation detail.

Mirrors the design of :mod:`services.sessions`: a dataclass value object plus a
registry that owns its own lock, with every mutating method idempotent.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass


def _parent_path(path: str) -> str | None:
    # Virtual parent of `path`, or None for the root. Mirrors the C++
    # InvalidateStat parent logic so both caches evict the same set.
    if not path or path == "/":
        return None
    slash = path.rfind("/")
    if slash <= 0:
        return "/"
    return path[:slash]


@dataclass
class CachedListing:
    """One directory's full listing as fetched from the phone.

    Attributes:
        entries: Every child entry, **sorted by name**. The page cursor
            binary-searches this list, so the order is load-bearing.
        dir_mtime_ms: Android's cache-validity token for the directory. ``0``
            means unknown (Android's ``stat`` returned null — a restricted
            subtree such as ``/Android/data``, or a directory that vanished).
            Recorded but not currently used to decide freshness; see the module
            docstring.
        fetched_at: ``time.monotonic()`` when the listing was fetched.
    """

    entries: list[dict]
    dir_mtime_ms: int
    fetched_at: float


class ListingCache:
    """Thread-safe TTL + LRU cache of :class:`CachedListing` keyed by path.

    Keys are the normalised virtual paths the C++ side sends (leading ``/``,
    forward slashes, no trailing slash). Keys are **not** case-folded: Explorer
    is case-insensitive but the phone's filesystem is not, so folding could
    merge two genuinely different directories. The cost of not folding is at
    worst a duplicate fetch for ``/DCIM`` versus ``/dcim``.
    """

    def __init__(self, ttl_s: float, max_dirs: int) -> None:
        """Initialize an empty cache.

        Args:
            ttl_s: Seconds a listing stays servable after it was fetched.
            max_dirs: Maximum directories retained; the least recently used is
                evicted beyond this.
        """
        self._ttl_s: float = ttl_s
        self._max_dirs: int = max_dirs
        self._lock: threading.Lock = threading.Lock()
        self._listings: OrderedDict[str, CachedListing] = OrderedDict()

    def get(self, path: str, now: float | None = None) -> CachedListing | None:
        """Return the cached listing for *path*, or ``None`` if absent/expired.

        A hit marks *path* as most recently used. An expired entry is dropped.
        """
        moment = time.monotonic() if now is None else now
        with self._lock:
            listing = self._listings.get(path)
            if listing is None:
                return None
            if moment - listing.fetched_at > self._ttl_s:
                del self._listings[path]
                return None
            self._listings.move_to_end(path)
            return listing

    def put(
            self,
            path: str,
            entries: list[dict],
            dir_mtime_ms: int,
            now: float | None = None,
    ) -> CachedListing:
        """Cache *entries* (already sorted by name) for *path* and return them.

        Drops expired neighbours opportunistically, then evicts least-recently-used
        entries until the cache is within ``max_dirs``.
        """
        moment = time.monotonic() if now is None else now
        listing = CachedListing(
            entries=entries, dir_mtime_ms=dir_mtime_ms, fetched_at=moment)
        with self._lock:
            self._listings[path] = listing
            self._listings.move_to_end(path)
            for stale_path in [
                p for p, c in self._listings.items()
                if p != path and moment - c.fetched_at > self._ttl_s
            ]:
                del self._listings[stale_path]
            while len(self._listings) > self._max_dirs:
                self._listings.popitem(last=False)
        return listing

    def invalidate(self, path: str) -> None:
        """Drop the cached listing for *path*, if any."""
        with self._lock:
            self._listings.pop(path, None)

    def invalidate_parent(self, path: str) -> None:
        """Drop the listing of *path*'s parent — its child set or sizes changed.

        Also drops *path* itself: when *path* is a directory, its own listing is
        unaffected by a rename of a sibling but is stale after the entry itself
        was created, truncated or written.
        """
        with self._lock:
            self._listings.pop(path, None)
            parent = _parent_path(path)
            if parent is not None:
                self._listings.pop(parent, None)

    def drop_subtree(self, path: str) -> None:
        """Drop *path* and every listing beneath it.

        Renaming or deleting a directory orphans every cached listing under it.
        Matches on the ``path + "/"`` prefix so ``/A`` never drops ``/AB``.
        """
        prefix = path if path.endswith("/") else path + "/"
        with self._lock:
            for cached in [
                p for p in self._listings
                if p == path or p.startswith(prefix)
            ]:
                del self._listings[cached]

    def clear(self) -> None:
        """Forget every cached listing (called on service stop)."""
        with self._lock:
            self._listings.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._listings)

    def __contains__(self, path: object) -> bool:
        with self._lock:
            return path in self._listings
