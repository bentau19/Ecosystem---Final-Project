import dataclasses


@dataclasses.dataclass
class BackupFileDTO:
    """View-facing descriptor for one file in the backup queue.

    Used by :class:`~viewmodels.backup.BackupViewModel` to describe the set
    of files that are about to be — or are currently being — backed up,
    without exposing any view-layer types.

    Attributes:
        path: Absolute source path on disk.  Used as the primary key in all
            per-file progress and status lookups.
        name: Display name shown in the progress window (typically
            ``Path(path).name``).
        size_bytes: Total file size in bytes.
    """

    path: str
    name: str
    size_bytes: int
    mtime: int = 0  # Unix-ms timestamp; used by review dialog for "modified" display
