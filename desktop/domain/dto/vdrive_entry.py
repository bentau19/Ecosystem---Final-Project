"""
Data Transfer Object for a file or folder on the phone's storage.

Returned by both :meth:`~services.phone_filesystem_client.PhoneFileSystemClient.list_dir`
(one entry per directory child) and
:meth:`~services.phone_filesystem_client.PhoneFileSystemClient.stat`
(single entry for a specific path).  Android always includes the name
because it knows the filename from the path it was asked about.

Consumed by the C++ WinFsp callbacks (``ReadDirectory``, ``Open``,
``GetFileInfo``) via pybind11.
"""

import dataclasses


@dataclasses.dataclass
class VDriveEntryDTO:
    """Metadata for a single file or folder on the phone.

    Attributes:
        name: Basename of the file or folder (no directory component).
        is_dir: ``True`` if this entry is a directory.
        size: Size in bytes.  Always ``0`` for directories.
        mtime_ms: Last-modified timestamp in Unix epoch milliseconds.
            ``0`` means the timestamp was unavailable.
    """

    name: str
    is_dir: bool
    size: int
    mtime_ms: int
