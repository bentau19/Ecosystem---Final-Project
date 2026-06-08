"""
Domain enum for the lifecycle state of a single file in a backup queue.

Defined here (domain layer) so both the ViewModel and the View can import it
without creating a cross-layer dependency.
"""
from enum import StrEnum


class BackupStatus(StrEnum):
    """Lifecycle state of a single file in a backup operation.

    Values are lowercase strings so they double as QSS dynamic-property
    selectors (e.g. ``[status="active"]``) without any extra conversion.
    """

    QUEUED = "queued"
    ACTIVE = "active"
    DONE   = "done"
    FAILED = "failed"
