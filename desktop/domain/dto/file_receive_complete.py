import dataclasses


@dataclasses.dataclass
class FileReceiveCompleteDTO:
    """Payload emitted by ``file_receive_complete`` / ``receive_complete`` signals.

    Attributes:
        filename: Base name of the file that was received.
        dest_path: Absolute path on disk where the file was written.
    """

    filename: str
    dest_path: str
