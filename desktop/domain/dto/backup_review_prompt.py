import dataclasses


@dataclasses.dataclass
class BackupReviewPromptDTO:
    """View-facing descriptor for one file pending confidence review.

    Emitted by :class:`~services.backup.BackupService` when the ML image
    classifier's argmax favours "remove" but isn't confident enough to act
    automatically (see :class:`~classifer.ScreeningResult.NEEDS_REVIEW`).
    The ViewModel forwards this DTO to the view layer so the user can be
    asked whether to keep or discard the file.

    Attributes:
        channel: TauSync slot channel for this file (e.g. ``"backup_slot_0"``).
            Used as the correlation key passed back to
            :meth:`~viewmodels.backup.BackupViewModel.resolve_review`.
        file_name: Display name of the file under review.
        cache_path: Absolute path to the cached file on disk, used to render
            a preview thumbnail.
        confidence: ``pr(remove)`` — the model's probability that the file is
            unwanted, in ``[0.0, 1.0]``.
    """

    channel: str
    file_name: str
    cache_path: str
    confidence: float
