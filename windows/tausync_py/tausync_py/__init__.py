"""TauSync Python SDK - socket-like interface over TauSync multiplexed streams.

Wraps the TauSync.Lib .NET DLL so callers never touch CLR init, GCHandle,
or raw System.Byte arrays.  One import, three lines, and you're connected.

Quick-start (server)::

    from tausync_py import TauSync

    tau = TauSync()
    tau.listen()
    with tau.connect("main") as stream:
        data = stream.read(4096)
        stream.write(b"HTTP/1.1 200 OK\\r\\n\\r\\n")

Quick-start (client)::

    from tausync_py import TauSync

    tau = TauSync()
    tau.connect_to("192.168.1.50")
    with tau.connect("main") as stream:
        stream.write(b"GET / HTTP/1.1\\r\\n\\r\\n")
        response = stream.read_all()
"""

from tausync_py._core import TauSync, TauSyncStream

__all__ = ["TauSync", "TauSyncStream"]
