from types import TracebackType
from typing import Optional, Type


class PipeError(RuntimeError):
    """Base class for all pipe exceptions."""
    ...


class PipeConnectionError(PipeError):
    """Raised when server pipe is not listening (phone not connected, app not running)."""
    ...


class PipeTransferError(PipeError):
    """Raised when pipe was opened but I/O failed (server crashed, connection dropped)."""
    ...


class ServerNamedPipe:
    def __init__(self, input_buffer_size: int, output_buffer_size: int, pipe_name: str): ...

    def wait_for_client(self) -> None: ...

    def read(self) -> str: ...

    def close(self) -> None: ...

    def disconnect(self) -> None: ...

    def __enter__(self) -> 'ServerNamedPipe': ...

    def __exit__(self,
                 exc_type: Optional[Type[BaseException]],
                 exc_val: Optional[BaseException],
                 exc_tb: Optional[TracebackType]) -> None: ...


class ClientNamedPipe:
    def __init__(self, input_buffer_size: int, output_buffer_size: int, pipe_name: str): ...

    def write(self, data: bytes) -> None: ...

    def close(self) -> None: ...

    def __enter__(self) -> 'ClientNamedPipe': ...

    def __exit__(self,
                 exc_type: Optional[Type[BaseException]],
                 exc_val: Optional[BaseException],
                 exc_tb: Optional[TracebackType]) -> None: ...
