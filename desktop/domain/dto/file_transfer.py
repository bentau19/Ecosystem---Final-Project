"""
File transfer status DTO and supporting enums.

Used by :class:`~viewmodels.file_transfer.FileTransferViewModel` to deliver
a single typed object to the view on every transfer event.
"""
from dataclasses import dataclass
from enum import StrEnum


class TransferDirection(StrEnum):
    """Which direction the file is moving."""

    SEND = "send"
    RECEIVE = "receive"


class TransferStatus(StrEnum):
    """Lifecycle stage of a single transfer."""

    STARTED = "started"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class FileTransferStatusDTO:
    """Snapshot of one transfer event delivered to the view layer.

    Attributes:
        filename:  Name of the file being transferred (empty on error).
        direction: Whether the file is being sent or received.
        status:    Current lifecycle stage (started / complete / error).
        detail:    Stage-specific detail — bytes transferred (as str) for a
                   completed send, destination path for a completed receive,
                   or the exception message for an error.
    """

    filename: str
    direction: TransferDirection
    status: TransferStatus
    detail: str
