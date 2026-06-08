import dataclasses


@dataclasses.dataclass
class FileReceivePromptDTO:
    """Payload emitted by ``FileTransferViewModel.metadata_received``.

    Carries only the data the view needs to display an accept/reject prompt.
    ``modified_at`` is intentionally excluded — the ViewModel stores it
    internally and forwards it to the service when the user accepts.

    Attributes:
        filename: Original filename as reported by the sender.
        size: Exact byte count of the file payload.
    """

    filename: str
    size: int
