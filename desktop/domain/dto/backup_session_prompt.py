import dataclasses


@dataclasses.dataclass(frozen=True)
class BackupSessionPromptDTO:
    """View-facing summary of an incoming Android backup session.

    Emitted by :class:`~viewmodels.backup.BackupViewModel` via
    ``dest_dir_requested`` when Android sends a backup manifest. The view
    uses this to render a meaningful folder-picker title such as
    "Save 42 files (1.2 GB) from your phone — choose a folder".

    Intentionally lean: the full ``list[BackupFileDTO]`` is held inside the
    ViewModel and never forwarded to the view layer directly.

    Attributes:
        file_count:       Total number of files in the manifest.
        total_size_bytes: Combined byte size of all files in the manifest.
                          Always the sum of *original* file sizes — a safe
                          upper bound for disk-space checks. When
                          ``storage_saver`` is ``True``, actual bytes
                          transferred will be lower (images are re-encoded).
        classify:         Whether the PC should run local content screening
                          (corrupt/duplicate/ML-filter checks) on received
                          files.  Independent of the per-file
                          ``backup_file_result_{i}`` "succ"/"fail" report,
                          which is always sent.  Defaults to ``True``
                          (classify is on).
        storage_saver:    Whether the Android side will re-encode images
                          before sending them (Storage Saver mode).  When
                          ``True``, the folder-picker dialog should display
                          "Up to X GB · Storage Saver on" rather than a
                          hard byte count.  Defaults to ``False``.
    """

    file_count: int
    total_size_bytes: int
    classify: bool = True
    storage_saver: bool = False
