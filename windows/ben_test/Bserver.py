"""
Bserver: connects on "main" and "second" (same as client). When both sides Connect on the same word they get paired.
Run first, then run Bclient.
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


def read_net_stream_to_end(stream) -> bytes:
    """Read .NET Stream until EOF."""
    chunks = []
    while True:
        buf = Array.CreateInstance(Byte, 8192)
        n = stream.Read(buf, 0, 8192)
        if n <= 0:
            break
        chunks.append(bytes([buf[i] for i in range(n)]))
    try:
        stream.Dispose()
    except Exception:
        pass
    return b"".join(chunks)


def run() -> None:
    import time
    connection = ConnectionManager()
    print("Server: listening for client...")
    connection.ConnectTransport("").GetAwaiter().GetResult()
    print("Server: client connected. Connecting on 'main' and 'second' (same API as client)...")
    stream_main = connection.Connect("main").GetAwaiter().GetResult()
    stream_second = connection.Connect("second").GetAwaiter().GetResult()
    print("Server: got both streams. Writing then reading...")

    # Write to client first (client will read line then write back)
    msg_main = "from_server_main\n"
    msg_second = "from_server_second\n"
    data_main = Encoding.UTF8.GetBytes(msg_main)
    data_second = Encoding.UTF8.GetBytes(msg_second)
    stream_main.Write(data_main, 0, len(msg_main))
    # stream_main.Write(data_main, 0, len(msg_main))
    stream_main.Flush()
    # stream_main.Write(data_main, 0, len(msg_main))
    stream_second.Write(data_second, 0, len(msg_second))
    stream_second.Flush()
    
    def read_and_print_main() -> None:
        data = read_net_stream_to_end(stream_main)
        try:
            text = data.decode("utf-8", errors="replace")
            print(f"[main] received ({len(data)} bytes): {text}")
        except Exception:
            print(f"[main] received ({len(data)} bytes): {data!r}")

    def read_and_print_second() -> None:
        data = read_net_stream_to_end(stream_second)
        try:
            text = data.decode("utf-8", errors="replace")
            print(f"[second] received ({len(data)} bytes): {text}")
        except Exception:
            print(f"[second] received ({len(data)} bytes): {data!r}")

    t1 = threading.Thread(target=read_and_print_main, daemon=True)
    t2 = threading.Thread(target=read_and_print_second, daemon=True)
    
    t1.start()
    t2.start()
    print("Server: waiting for client to send data (5s)...")
    time.sleep(5)
    connection.Dispose()
    print("Server: done.")
    t1.join(timeout=10)
    t2.join(timeout=10)


def run_with_timeout(timeout_seconds: int = 10) -> None:
    """Run the server and hard-exit if it hangs (to release the DLL lock)."""
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Server: timeout after {timeout_seconds}s. Exiting to release DLL lock.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(10)
