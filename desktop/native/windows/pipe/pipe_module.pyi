import datetime
from types import TracebackType
from typing import Optional, Type


class ServerNamedPipe:
    """Byte-stream or message-mode Windows named pipe server.

    Args:
        input_buffer_size: Kernel buffer size for inbound data (bytes).
        output_buffer_size: Kernel buffer size for outbound data (bytes).
        pipe_name: Full pipe path, e.g. ``r'\\\\.\\pipe\\MyPipe'``.
        byte_stream: When ``True`` the pipe is created in byte-stream mode
            (``PIPE_TYPE_BYTE``) instead of message mode.  Required for the
            VirtualDrive IPC protocol.  Defaults to ``False`` so existing
            callers (``FileTransferService``) are unaffected.
    """

    def __init__(
        self,
        input_buffer_size: int,
        output_buffer_size: int,
        pipe_name: str,
        byte_stream: bool = False,
    ) -> None: ...

    def wait_for_client(self, timeout: datetime.timedelta | None = None) -> None: ...

    def read(self, timeout: datetime.timedelta | None = None) -> bytes:
        """Read one message (message-mode) or up to buffer size (byte-stream)."""
        ...

    def read_exact(self, n: int, timeout: datetime.timedelta | None = None) -> bytes:
        """Block until exactly *n* bytes have been received.

        Use this for byte-stream frame parsing — call it once for the 4-byte
        length header, then again for the body.  Raises ``TimeoutError`` if
        *timeout* elapses before *n* bytes arrive.
        """
        ...

    def write(self, data: bytes, timeout: datetime.timedelta | None = None) -> None:
        """Write *data* to the connected client."""
        ...

    def close(self) -> None: ...
    def disconnect(self) -> None: ...

    def __enter__(self) -> 'ServerNamedPipe': ...
    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...


class ClientNamedPipe:
    """Windows named pipe client.

    Args:
        input_buffer_size: Kernel buffer size for inbound data (bytes).
        output_buffer_size: Kernel buffer size for outbound data (bytes).
        pipe_name: Full pipe path, e.g. ``r'\\\\.\\pipe\\MyPipe'``.
        duplex: When ``True`` opens the handle with ``GENERIC_READ | GENERIC_WRITE``
            so :meth:`read_exact` is available.  Defaults to ``False`` (write-only)
            so existing callers (``FileHandler.exe`` bridge) are unaffected.
    """

    def __init__(
        self,
        input_buffer_size: int,
        output_buffer_size: int,
        pipe_name: str,
        duplex: bool = False,
    ) -> None: ...

    def write(self, data: bytes, timeout: datetime.timedelta | None = None) -> None: ...

    def read_exact(self, n: int, timeout: datetime.timedelta | None = None) -> bytes:
        """Block until exactly *n* bytes have been received.

        Only meaningful when constructed with ``duplex=True``.
        Raises ``TimeoutError`` if *timeout* elapses before *n* bytes arrive.
        """
        ...

    def close(self) -> None: ...

    def __enter__(self) -> 'ClientNamedPipe': ...
    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None: ...
