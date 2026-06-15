from enum import StrEnum


class BackupStatus(StrEnum):
    """Lifecycle state of a single file in a backup operation.

    Defined in the domain layer so both the ViewModel and the View can
    import it without creating a cross-layer dependency.

    Values are lowercase strings so they double as QSS dynamic-property
    selectors (e.g. ``[status="active"]``) without any extra conversion.
    """

    QUEUED   = "queued"
    ACTIVE   = "active"
    DONE     = "done"
    FAILED   = "failed"
    SKIPPED  = "skipped"   # transferred OK, not kept locally (filtered or user-removed)
