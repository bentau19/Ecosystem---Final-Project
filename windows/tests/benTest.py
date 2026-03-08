"""
benTest.py – Windows as server: wait for Android to connect, then send clipboard via TauSync.
Uses only ConnectionManager (no direct dependency on transport).
"""

import sys
import os
from datetime import datetime

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
    print("Please build the C# project first: dotnet build TauSync/windows/TauSync.Lib/TauSync.Lib.csproj")
    sys.exit(1)

clr.AddReference(dll_path)

from TauSync.Implementations.Management import ConnectionManager  # pyright: ignore[reportMissingImports]
from System.IO import MemoryStream  # pyright: ignore[reportMissingImports]
from System.Text import Encoding   # pyright: ignore[reportMissingImports]


def run() -> None:
    """
    Run as server: wait for phone to connect, then send a new clipboard payload via TauSync SmartSend.
    """
    print("TauSync – Windows (server) waiting for phone to connect")
    print("Connect from the phone to this PC's IP on port 8888.")
    print()

    manager = ConnectionManager()

    print("Waiting for phone to connect...")
    manager.Connect("").GetAwaiter().GetResult()
    print("Phone connected.")

    if not manager.IsConnected():
        print("Error: Not connected after Connect().")
        return

    # New clipboard content to send
    clipboard_text = f"Ben tau"
    print(f"Sending clipboard: {clipboard_text!r}")

    bytes_net = Encoding.UTF8.GetBytes(clipboard_text)
    stream = MemoryStream(bytes_net)

    send_task = manager.SmartSend(stream, "CLIPBOARD", None)
    send_task.GetAwaiter().GetResult()

    print("Clipboard sent successfully.")
    manager.Dispose()


if __name__ == "__main__":
    run()
