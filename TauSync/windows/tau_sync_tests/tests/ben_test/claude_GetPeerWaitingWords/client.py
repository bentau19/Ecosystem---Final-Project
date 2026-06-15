"""
Client for GetPeerWaitingWords test.

Flow:
    1. connect_to(server_ip).
    2. Fire two REQ words ("alpha" and "beta") from background threads.
       Each tau.connect(word) call sends a REQ frame and then blocks
       waiting for the server's OK. The server will not pair, so each
       call sits inside the 30s handshake timeout window.
    3. While they sit, the user presses ENTER on the server, which
       calls GetPeerWaitingWords() and reads our two queued REQs.
    4. The connect() calls eventually time out / raise — that is expected
       and considered success here, because pairing is not the point.

Run after server.py is up.
"""

import os
import sys
import threading

from tausync_py import TauSync


def open_word(tau: TauSync, word: str) -> None:
    print(f"Client: sending REQ for {word!r} (will block until pair or timeout)...")
    try:
        stream = tau.connect(word)
        print(f"Client: unexpectedly paired on {word!r} — closing.")
        stream.close()
    except Exception as ex:
        print(f"Client: {word!r} ended (expected): {type(ex).__name__}: {ex}")


def run() -> None:
    tau = TauSync()
    server_ip = (sys.argv[1] if len(sys.argv) > 1 else "192.168.1.104").strip()
    print(f"Client: connecting to {server_ip}...")
    tau.connect_to(server_ip)
    print("Client: transport up.")

    threads = [
        threading.Thread(target=open_word, args=(tau, "alpha"), daemon=True),
        threading.Thread(target=open_word, args=(tau, "beta"), daemon=True),
    ]
    for t in threads:
        t.start()

    print("Client: both REQs fired. Now go to the server window and press ENTER.")
    print("Client: the connect() calls will block here until the server pairs")
    print("Client: them or the 30s handshake timeout fires (whichever first).")

    for t in threads:
        t.join()

    tau.dispose()
    print("Client: done.")


def run_with_timeout(timeout_seconds: int = 120) -> None:
    """Run the client and hard-exit if it hangs (to release the DLL lock)."""
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Client: timeout after {timeout_seconds}s. Exiting to release DLL lock.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(120)
