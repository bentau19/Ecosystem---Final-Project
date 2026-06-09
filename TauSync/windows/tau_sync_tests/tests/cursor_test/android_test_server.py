"""TauSync test server for the Android test suite.

Run on Windows, then tap Connect in the Android app.

Manual mode:
  Open channel "main", Send a message, Read Line to get the echo.
  The server echoes every line back. Repeat as many times as you want.

Automated tests (tap Run All Tests):
  1. test_msg          Message echo round-trip
  2. test_bin           Binary round-trip with SHA-256 verification (25 KB)
  3. test_empty_msg     Empty-line echo (zero-length payload)
  4. test_unicode       Multi-byte UTF-8 round-trip
  5. test_large_bin     Large binary round-trip (1 MB)
  6. test_burst         Rapid sequential message burst (100 lines)
  7. test_concurrent_a  Concurrent channel A echo  (run with B)
  8. test_concurrent_b  Concurrent channel B echo  (run with A)
  9. test_stream_close  Server-initiated close / EOF detection
"""

import hashlib
import os
import threading
import time

from tausync_py import TauSync

SMALL_BINARY_SIZE = 25_600
LARGE_BINARY_SIZE = 1_048_576
BURST_MESSAGE_COUNT = 100
UNICODE_PAYLOAD = "\u05e9\u05dc\u05d5\u05dd_\u4e16\u754c_\U0001f30d"
TEST_TIMEOUT_SECONDS = 120
MANUAL_CHANNEL_WORD = "main"


# ── Manual echo loop ─────────────────────────────────────────────────

def serve_manual_echo_loop(tau):
    """Echo every line the Android client sends on the 'main' channel.

    Re-opens the channel after each close so the user can disconnect
    and reconnect as many times as needed.
    """
    while True:
        try:
            print(f"\n  [manual] Waiting for channel '{MANUAL_CHANNEL_WORD}'...")
            stream = tau.connect(MANUAL_CHANNEL_WORD)
            print(f"  [manual] Channel '{MANUAL_CHANNEL_WORD}' opened. Echoing lines.")

            while True:
                data = stream.read_line()
                if not data:
                    break
                text = data.decode("utf-8").rstrip("\n")
                stream.write_string(text + "\n")
                print(f"  [manual] echoed: {text!r}")

            stream.close()
            print(f"  [manual] Channel '{MANUAL_CHANNEL_WORD}' closed by client.")
        except Exception as exception:
            print(f"  [manual] Channel ended: {exception}")


#── Individual test dialogs ──────────────────────────────────────────

def serve_message_echo(tau):
    """Test 1: read a line from the client and echo it back."""
    stream = tau.connect("test_msg")
    try:
        line = stream.read_line().decode("utf-8").rstrip("\n")
        stream.write_string(line + "\n")
        print(f"  [test_msg]       echoed: {line!r}")
    finally:
        stream.close()


def serve_binary_round_trip(tau):
    """Test 2: send random bytes, read echo, verify SHA-256."""
    stream = tau.connect("test_bin")
    try:
        test_data = os.urandom(SMALL_BINARY_SIZE)
        expected_sha = hashlib.sha256(test_data).hexdigest()

        stream.write_string(f"{len(test_data)}\n")
        stream.write(test_data)

        echo = stream.read_exactly(len(test_data))
        actual_sha = hashlib.sha256(echo).hexdigest()

        passed = expected_sha == actual_sha
        stream.write_string("PASS\n" if passed else "FAIL\n")
        print(f"  [test_bin]       {'PASS' if passed else 'FAIL'}  ({len(test_data)} bytes)")
    finally:
        stream.close()


def serve_empty_message(tau):
    """Test 3: read an empty line and echo it back."""
    stream = tau.connect("test_empty_msg")
    try:
        line = stream.read_line().decode("utf-8").rstrip("\n")
        stream.write_string(line + "\n")
        print(f"  [test_empty_msg] echoed empty line (len={len(line)})")
    finally:
        stream.close()


def serve_unicode_round_trip(tau):
    """Test 4: send a Unicode string, read echo, verify."""
    stream = tau.connect("test_unicode")
    try:
        stream.write_string(UNICODE_PAYLOAD + "\n")

        echo = stream.read_line().decode("utf-8").rstrip("\n")
        passed = echo == UNICODE_PAYLOAD
        stream.write_string("PASS\n" if passed else "FAIL\n")
        print(f"  [test_unicode]   {'PASS' if passed else 'FAIL'}  sent={UNICODE_PAYLOAD!r} got={echo!r}")
    finally:
        stream.close()


def serve_large_binary_round_trip(tau):
    """Test 5: send 1 MB of random data, read echo, verify SHA-256."""
    stream = tau.connect("test_large_bin")
    try:
        test_data = os.urandom(LARGE_BINARY_SIZE)
        expected_sha = hashlib.sha256(test_data).hexdigest()

        stream.write_string(f"{len(test_data)}\n")
        stream.write(test_data)

        echo = stream.read_exactly(len(test_data))
        actual_sha = hashlib.sha256(echo).hexdigest()

        passed = expected_sha == actual_sha
        stream.write_string("PASS\n" if passed else "FAIL\n")
        print(f"  [test_large_bin] {'PASS' if passed else 'FAIL'}  ({len(test_data)} bytes)")
    finally:
        stream.close()


def serve_rapid_burst(tau):
    """Test 6: send a burst of numbered messages, verify client received all."""
    stream = tau.connect("test_burst")
    try:
        stream.write_string(f"{BURST_MESSAGE_COUNT}\n")

        for index in range(BURST_MESSAGE_COUNT):
            stream.write_string(f"msg_{index:03d}\n")

        count_line = stream.read_line().decode("utf-8").strip()
        received_count = int(count_line)

        passed = received_count == BURST_MESSAGE_COUNT
        stream.write_string("PASS\n" if passed else "FAIL\n")
        print(f"  [test_burst]     {'PASS' if passed else 'FAIL'}  (sent={BURST_MESSAGE_COUNT} received={received_count})")
    finally:
        stream.close()


def serve_concurrent_echo(tau, channel_name):
    """Test 7a/7b: read a line and echo it back on a named channel."""
    stream = tau.connect(channel_name)
    try:
        line = stream.read_line().decode("utf-8").rstrip("\n")
        stream.write_string(line + "\n")
        print(f"  [{channel_name}] echoed: {line!r}")
    finally:
        stream.close()


def serve_stream_close(tau):
    """Test 8: write data then close — client must detect EOF."""
    stream = tau.connect("test_stream_close")
    try:
        stream.write_string("CLOSE_TEST_DATA")
    finally:
        stream.close()
    print("  [test_close]     sent data and closed stream")


# ── Orchestrator ──────────────────────────────────────────────────────

def run_test_on_thread(target, args=()):
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    return thread


def serve_all_tests(tau):
    """Spawn one thread per test channel and wait for all to complete."""
    threads = [
        run_test_on_thread(serve_message_echo, (tau,)),
        run_test_on_thread(serve_binary_round_trip, (tau,)),
        run_test_on_thread(serve_empty_message, (tau,)),
        run_test_on_thread(serve_unicode_round_trip, (tau,)),
        run_test_on_thread(serve_large_binary_round_trip, (tau,)),
        run_test_on_thread(serve_rapid_burst, (tau,)),
        run_test_on_thread(serve_concurrent_echo, (tau, "test_concurrent_a")),
        run_test_on_thread(serve_concurrent_echo, (tau, "test_concurrent_b")),
        run_test_on_thread(serve_stream_close, (tau,)),
    ]

    for thread in threads:
        thread.join(timeout=TEST_TIMEOUT_SECONDS)

    timed_out = [t for t in threads if t.is_alive()]
    if timed_out:
        print(f"\n  WARNING: {len(timed_out)} test(s) timed out after {TEST_TIMEOUT_SECONDS}s")


def main():
    tau = TauSync()
    print("Listening for Android client...")
    tau.listen()
    print("Client connected.\n")

    manual_thread = run_test_on_thread(serve_manual_echo_loop, (tau,))
    print("Manual echo active on channel 'main'. Send/Read Line ready.")
    print("Tap 'Run All Tests' on the phone to start automated tests.\n")
    print("Serving automated test channels:")

    serve_all_tests(tau)

    print("\n=== AUTOMATED TESTS SERVED ===")
    print("Manual echo still active. Press Ctrl+C to stop.\n")

    try:
        manual_thread.join()
    except KeyboardInterrupt:
        print("\nShutting down.")
        tau.dispose()


if __name__ == "__main__":
    main()
