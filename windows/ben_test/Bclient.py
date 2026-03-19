"""
Bclient: connects to server and sends data on "main" and "second".
The server (Bserver) will print what you send here.
Run after Bserver.
"""

import sys
import os
import threading

from pythonnet import load
try:
    load("coreclr")
except Exception as e:
    print(f"Note: CoreCLR load status: {e}")

try:
    import clr
except ImportError:
    print("Error: pythonnet is not installed. Install it with: pip install pythonnet")
    sys.exit(1)

script_dir = os.path.dirname(os.path.abspath(__file__))
dll_path = os.path.join(script_dir, "..", "..", "TauSync", "windows", "TauSync.Lib", "bin", "Debug", "net8.0", "TauSync.Lib.dll")
dll_path = os.path.abspath(dll_path)

if not os.path.exists(dll_path):
    print(f"Error: DLL not found at {dll_path}")
    sys.exit(1)

clr.AddReference(dll_path)

from TauSync.Implementations.Management import ConnectionManager  # pyright: ignore[reportMissingImports]
from System import Array, Byte  # pyright: ignore[reportMissingImports]
from System.Text import Encoding  # pyright: ignore[reportMissingImports]


def read_net_stream_to_end(stream, dispose: bool = True) -> bytes:
    """Read .NET Stream until EOF. If dispose is False, stream is left open."""
    chunks = []
    while True:
        buf = Array.CreateInstance(Byte, 8192)
        n = stream.Read(buf, 0, 8192)
        if n <= 0:
            break
        chunks.append(bytes([buf[i] for i in range(n)]))
    if dispose:
        try:
            stream.Dispose()
        except Exception:
            pass
    return b"".join(chunks)


def read_line(stream) -> bytes:
    """Read until newline (\\n). Stream is not disposed."""
    buf = bytearray()
    one = Array.CreateInstance(Byte, 1)
    while True:
        n = stream.Read(one, 0, 1)
        if n <= 0:
            break
        b = one[0]
        buf.append(b)
        if b == 0x0A:  # \n
            break
    return bytes(buf)


def run() -> None:
    connection = ConnectionManager()
    server_ip = (sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1").strip()
    print(f"Client: connecting to {server_ip}...")
    if not connection.IsConnected():
        connection.ConnectTransport(server_ip).GetAwaiter().GetResult()
    print("Client: connected. Connecting on 'main' and 'second'...")
    stream_main = connection.Connect("main").GetAwaiter().GetResult()
    stream_second = connection.Connect("second").GetAwaiter().GetResult()
    print("Client: got both streams. Read then write...")

    # Read line from server (server sent "from_server_main\n" etc.)
    from_main = read_line(stream_main)
    print(f"Client: read from main: {from_main.decode('utf-8').strip()!r}")
    
    from_second = read_line(stream_second)
    print(f"Client: read from second: {from_second.decode('utf-8').strip()!r}")
    # from_main2 = read_line(stream_main)
    # print(f"Client: read from main: {from_main2.decode('utf-8').strip()!r}")
    # Write back then close (server will read to end and get this)
    msg_main = "from_client_main\n"
    msg_second = "from_client_second\n"
    data_main = Encoding.UTF8.GetBytes(msg_main)
    data_second = Encoding.UTF8.GetBytes(msg_second)
    stream_main.Write(data_main, 0, len(msg_main))
    stream_main.Flush()
    stream_main.Dispose()
    stream_second.Write(data_second, 0, len(msg_second))
    stream_second.Flush()
    stream_second.Dispose()
    print("Client: wrote back and closed. Done.")

def run_with_timeout(timeout_seconds: int = 10) -> None:
    """Run the client and hard-exit if it hangs (to release the DLL lock)."""
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Client: timeout after {timeout_seconds}s. Exiting to release DLL lock.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(10)
