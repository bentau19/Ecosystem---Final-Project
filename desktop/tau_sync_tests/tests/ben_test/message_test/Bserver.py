"""
Bserver: connects on "main" and "second" (same as client). When both sides Connect on the same word they get paired.
Run first, then run Bclient.
"""

import os
import threading

from tausync_py import TauSync


def run() -> None:
    tau = TauSync()
    print("Server: listening for client...")
    tau.listen()
    print("Server: client connected. Connecting on 'main' and 'second'...")

    stream_main = tau.connect("main")
    stream_second = tau.connect("second")
    print("Server: got both streams. Writing then reading...")

    msg_main = "from_server_main\ndddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
    msg_second = "from_server_second\n"

    stream_second.write_string(msg_second)
    stream_second.flush()
    stream_main.write_string(msg_main)
    stream_main.flush()
    stream_main.write_string(msg_main)

    stream_second.write_string(msg_second)
    stream_second.flush()

    print("Server: waiting for client to send data (5s)...")
    tau.dispose()
    print("Server: done.")


def run_with_timeout(timeout_seconds: int = 30) -> None:
    """Run the server and hard-exit if it hangs (to release the DLL lock)."""
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Server: timeout after {timeout_seconds}s. Exiting to release DLL lock.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(30)
