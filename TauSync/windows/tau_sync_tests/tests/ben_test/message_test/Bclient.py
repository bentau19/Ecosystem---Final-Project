"""
Bclient: connects to server and sends data on "main" and "second".
The server (Bserver) will print what you send here.
Run after Bserver.
"""

import sys
import os
import time
import threading

from tausync_py import TauSync


def read_messages_until_eof(stream, channel_name: str) -> None:
    """Read line-delimited messages until EOF and print each one."""
    while True:
        message = stream.read_line()
        if not message:
            break
        text = message.decode("utf-8", errors="replace").rstrip("\r\n")
        print(f"Client: received on {channel_name}: {text!r}")


def run() -> None:
    tau = TauSync()
    server_ip = (sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1").strip()
    print(f"Client: connecting to {server_ip}...")
    tau.connect_to(server_ip)
    print("Client: connected. Connecting on 'main' and 'second'...")

    stream_main = tau.connect("main")
    stream_second = tau.connect("second")
    print("Client: got both streams. Start reader threads...")

    reader_main = threading.Thread(
        target=read_messages_until_eof,
        args=(stream_main, "main"),
        daemon=True,
    )
    reader_second = threading.Thread(
        target=read_messages_until_eof,
        args=(stream_second, "second"),
        daemon=True,
    )
    reader_main.start()
    reader_second.start()
    time.sleep(0.2)

    stream_main.write_string("from_client_main\n")
    stream_main.flush()
    stream_second.write_string("from_client_second\n")
    stream_second.flush()

    reader_main.join(timeout=5)
    reader_second.join(timeout=5)
    print("Client: wrote back and closed. Done.")


def run_with_timeout(timeout_seconds: int = 30) -> None:
    """Run the client and hard-exit if it hangs (to release the DLL lock)."""
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Client: timeout after {timeout_seconds}s. Exiting to release DLL lock.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(30)
