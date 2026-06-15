import dataclasses


@dataclasses.dataclass()
class FileMetadataDTO:
    """Data transfer object for incoming file metadata.

    Attributes:
        name: Original filename as reported by the sender.
        size: Exact byte count of the file payload.
        modified_at: Last-modified timestamp in Unix epoch milliseconds as
            reported by the sender's filesystem.  ``0`` means the sender did
            not supply a timestamp (legacy senders); callers should skip
            ``os.utime`` in that case.
    """

    name: str
    size: int
    modified_at: int = 0  # Unix epoch ms; 0 = not provided
