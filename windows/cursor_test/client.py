"""
TauSync client: connects to server and sends multiple streams in parallel.
Tests routing of multiple simultaneous streams (multiple IDs).
Uses v3 API: ConnectTransport(server_ip) then Connect(word) for each stream.
Usage: python client.py [server_ip]
Default server_ip is 127.0.0.1 (run server.py on the same machine first).
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
dll_path = os.path.join(script_dir, "..", "TauSync", "windows", "TauSync.Lib", "bin", "Debug", "net8.0", "TauSync.Lib.dll")
dll_path = os.path.abspath(dll_path)

if not os.path.exists(dll_path):
    print(f"Error: DLL not found at {dll_path}")
    print("Please build the C# project first: dotnet build TauSync/windows/TauSync.Lib/TauSync.Lib.csproj")
    sys.exit(1)

clr.AddReference(dll_path)

from TauSync.Implementations.Management import ConnectionManager  # pyright: ignore[reportMissingImports]
from System.Text import Encoding  # pyright: ignore[reportMissingImports]

# Same as server: 4 channels, 2 connections per channel = 8 parallel streams
CHANNELS = ["CLIPBOARD", "TEXT", "FILE", "LOG"]
CONNECTIONS_PER_CHANNEL = 2


def send_one(manager, word: str, payload: str, thread_name: str) -> None:
    """Open one stream for `word`, write `payload`, dispose. Used from multiple threads."""
    try:
        stream = manager.Connect(word).GetAwaiter().GetResult()
        try:
            data = Encoding.UTF8.GetBytes(payload)
            stream.Write(data, 0, data.Length)
            stream.Flush()
        finally:
            stream.Dispose()
        print(f"  [{thread_name}] {word} sent: {payload[:50]!r}...")
    except Exception as e:
        print(f"  [{thread_name}] {word} ERROR: {e}")


def run() -> None:
    """
    Run as TauSync client: connect to server and send multiple streams in parallel
    (several channels × several connections per channel) to stress-test ID routing.
    """
    server_ip = (sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1").strip()

    print(f"TauSync client – connecting to {server_ip}:8888")
    print(f"Channels: {CHANNELS}, {CONNECTIONS_PER_CHANNEL} connections per channel")
    print("Launching all streams in parallel...")
    print()

    manager = ConnectionManager()
    manager.ConnectTransport(server_ip).GetAwaiter().GetResult()

    if not manager.IsConnected():
        print("Error: Could not connect to server.")
        return

    # Build (word, payload) for each stream; payload must be unique so server can verify routing
    tasks: list[tuple[str, str, str]] = []
    for ch in CHANNELS:
        for i in range(CONNECTIONS_PER_CHANNEL):
            payload = f"{ch}_payload_{i+1}_id"
            tasks.append((ch, payload, f"{ch}_{i+1}"))

    threads = []
    for word, payload, name in tasks:
        t = threading.Thread(target=send_one, args=(manager, word, payload, name), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=15)

    done = sum(1 for t in threads if not t.is_alive())
    print()
    print(f"Done. {done}/{len(tasks)} streams completed.")
    manager.Dispose()

    if done != len(tasks):
        print("Warning: not all streams completed.")
        sys.exit(1)


if __name__ == "__main__":
    run()
