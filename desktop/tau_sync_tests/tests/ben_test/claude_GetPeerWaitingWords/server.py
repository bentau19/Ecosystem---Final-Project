"""
Server for GetPeerWaitingWords test.

Flow:
    1. listen() and wait for the client to attach.
    2. DO NOT call tau.connect() on any word — that would drain the
       _pendingDiscoveryByWord queue inside ConnectionContext.
    3. The client will fire two REQ frames ("alpha" and "beta") that have
       nowhere to land here, so they sit in the pending queue.
    4. After pressing ENTER, call ConnectionManager.GetPeerWaitingWords()
       and print the snapshot — those are the words the peer is waiting on
       that we have not paired yet.

Run this first, then run client.py.
"""

import os
import sys
import threading

from tausync_py import TauSync


def run() -> None:
    tau = TauSync()
    print("Server: listening for client...")
    tau.listen()
    print("Server: client connected.")
    print("Server: not registering any word locally — peer REQs will queue.")

    input("Server: press ENTER once the client says it has fired both REQs... ")

    waiting = tau.GetPeerWaitingWords()
    words = [str(w) for w in waiting]

    print(f"Server: peer is waiting on {len(words)} word(s): {words}")
    if {"alpha", "beta"}.issubset(set(words)):
        tau.connect("alpha")
        waiting_after_alpha = tau.GetPeerWaitingWords()
        print(f"Server: after connecting 'alpha', peer is waiting on: {waiting_after_alpha}")
        # print("Server: PASS — both expected words present.")
    else:
        print("Server: FAIL — expected {'alpha', 'beta'}, got " + str(words))

    tau.dispose()
    print("Server: done.")


def run_with_timeout(timeout_seconds: int = 120) -> None:
    """Run the server and hard-exit if it hangs (to release the DLL lock)."""
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Server: timeout after {timeout_seconds}s. Exiting to release DLL lock.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(120)
