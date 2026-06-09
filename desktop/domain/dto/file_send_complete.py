import dataclasses


@dataclasses.dataclass
class FileSendCompleteDTO:
    """Payload emitted by ``file_send_complete`` / ``send_complete`` signals.

    Attributes:
        filename: Base name of the file that was successfully sent.
        total_bytes: Total number of bytes written to the data channel.
    """

    filename: str
    total_bytes: int
