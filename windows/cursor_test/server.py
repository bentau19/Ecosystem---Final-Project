"""
TauSync server: listens for a client, receives multiple channels in parallel.
Tests routing of multiple simultaneous streams (multiple IDs).
Uses v3 API: ConnectTransport("") then Listen(...) for each channel.
Run this first, then run client.py (point it to this machine's IP).
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
from System import Action  # pyright: ignore[reportMissingImports]
from System.IO import Stream  # pyright: ignore[reportMissingImports]

# Channels to listen on; we collect all payloads per channel (list of bytes)
CHANNELS = ["CLIPBOARD", "TEXT", "FILE", "LOG"]
# Expected number of connections per channel (client sends 2 per channel = 8 total)
EXPECTED_PER_CHANNEL = 2
EXPECTED_TOTAL = len(CHANNELS) * EXPECTED_PER_CHANNEL


def run() -> None:
    """
    Run as TauSync server: wait for client, receive multiple parallel streams per channel,
    verify routing by ID (each stream's data stays on its channel).
    """
    print("TauSync server – multi-channel parallel test (routing by ID)")
    print("Run client.py with this machine's IP (e.g. python client.py 192.168.1.10)")
    print(f"Channels: {CHANNELS}, expecting {EXPECTED_PER_CHANNEL} connections per channel ({EXPECTED_TOTAL} total)")
    print()

    # Per-channel: list of received payloads (bytes); each item = one connection's data
    received: dict[str, list[bytes]] = {ch: [] for ch in CHANNELS}
    lock = threading.Lock()
    count_done = threading.Event()

    def read_stream_to_list(stream, out_list: list, channel_name: str) -> None:
        """Read from .NET stream until EOF, append to out_list, then signal."""
        try:
            buf = bytearray(8192)
            total = []
            while True:
                n = stream.Read(buf, 0, len(buf))
                if n <= 0:
                    break
                total.append(bytes(buf[:n]))
            payload = b"".join(total) if total else b""
            with lock:
                out_list.append(payload)
                total_received = sum(len(v) for v in received.values())
                if total_received >= EXPECTED_TOTAL:
                    count_done.set()
        except Exception as e:
            with lock:
                print(f"[Server] Error reading {channel_name}: {e}")
        finally:
            try:
                stream.Dispose()
            except Exception:
                pass

    def make_on_connect(channel_name: str):
        def on_connect(stream, local_id) -> None:
            print(f"[Server] {channel_name} connection, localId={local_id}")
            t = threading.Thread(
                target=read_stream_to_list,
                args=(stream, received[channel_name], channel_name),
                daemon=True,
            )
            t.start()
        return on_connect

    manager = ConnectionManager()
    on_connect_type = Action[Stream, int]
    for ch in CHANNELS:
        manager.Listen(ch, on_connect_type(make_on_connect(ch)))

    print("Listening on port 8888...")
    manager.ConnectTransport("").GetAwaiter().GetResult()
    print("Client connected. Waiting for parallel streams...")

    if not manager.IsConnected():
        print("Error: Not connected after ConnectTransport().")
        return

    ok = count_done.wait(timeout=30)
    manager.Dispose()

    print()
    print("=" * 60)
    print("RESULTS (routing by ID)")
    print("=" * 60)
    all_ok = True
    for ch in CHANNELS:
        payloads = received.get(ch, [])
        n = len(payloads)
        expected = EXPECTED_PER_CHANNEL
        if n != expected:
            print(f"[FAIL] {ch}: expected {expected} streams, got {n}")
            all_ok = False
        else:
            print(f"[OK]   {ch}: {n} streams")
            for i, p in enumerate(payloads):
                preview = (p[:40].decode("utf-8", errors="replace") + "…") if len(p) > 40 else p.decode("utf-8", errors="replace")
                print(f"       #{i+1}: {preview}")
    total = sum(len(received.get(ch, [])) for ch in CHANNELS)
    if total != EXPECTED_TOTAL:
        print(f"[FAIL] Total streams: expected {EXPECTED_TOTAL}, got {total}")
        all_ok = False
    else:
        print(f"[OK]   Total streams: {total}")
    print("=" * 60)
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    run()
