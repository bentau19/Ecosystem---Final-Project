"""TauSync PC test console for the Android test suite.

Run this on Windows.  A small GUI window opens: it is the TauSync **server**.
Tap Connect in the Android `TestTauSyncActivity`; the Android device is the
client driving the automated tests.  The console also gives you a
**user-friendly manual playground** — open as many channels as you like and
chat / spam / stress each one in both directions, mirroring exactly what the
phone can do.

Every automated test below is paired with a matching handler in
`TestTauSyncActivity.java` by its **meeting word** (the channel name).

──────────────────────────────────────────────────────────────────────────
  TEST CATALOGUE  (channel word → protocol feature exercised)
──────────────────────────────────────────────────────────────────────────
  GROUP A — Core data I/O
    1.  test_msg                Line-delimited text echo (UTF-8)
    2.  test_bin                25 KB binary round-trip, SHA-256 verified
    3.  test_empty_msg          Empty-line echo (zero-length payload)
    4.  test_unicode            Multi-byte UTF-8 round-trip
    5.  test_large_bin          1 MB binary round-trip, SHA-256 verified

  GROUP B — Stream control
    6.  test_burst              100 rapid sequential lines, no loss
    7.  test_concurrent_a/b     Two channels open at once, no cross-talk
    8.  test_stream_close       Server closes, client detects EOF

  GROUP C — Bidirectionality & multiplexing
    9.  test_bidir              Both sides read AND write at the same time
    10. test_multi_a/b          Two TauSync managers on one socket (new_manager)

  GROUP D — Channel lifecycle
    11. test_reuse              Open → close → reopen same word (ID recycling)
    12. test_pw_alpha/beta      get_peer_waiting_words() discovery-queue API

  GROUP E — Data edge cases
    13. test_long_line          500 KB single line (readLine buffer growth)
    14. test_small_frames       200 KB sent in 100-byte frames (reassembly)
    15. test_raw_stream         getInputStream()/getOutputStream() adapters

  GROUP F — File transfer
    16. test_file_pc_to_android 20 MB file PC→Android, SHA-256 verified
    17. test_file_android_to_pc 20 MB file Android→PC, SHA-256 verified

  GROUP G — Failure & recovery
    18. test_peer_close         Server closes before sending; client sees EOF

  GROUP H — Bugfix validation
    19. test_large_write        5 MB sent in ONE write() — auto-chunking splits into ≤64 KB frames
    20. test_cid_00…09          10 channels opened simultaneously — unique IDs, no cross-talk
    21. test_conc_close         Both sides close at the same time; next channel still works

  Plus the MANUAL CHANNELS panel in the GUI: open any meeting word to get a
  live two-way chat with the phone (Send, Spam xN, optional Echo-back).  Open
  several words at once — each opens its own tab.

──────────────────────────────────────────────────────────────────────────
  HOW TO ADD YOUR OWN TEST
──────────────────────────────────────────────────────────────────────────
  1. Pick a unique meeting word, e.g. "test_myfeature".
  2. Write a `serve_my_feature(tau)` function below that opens the channel
     with `tau.connect("test_myfeature")` and exercises whatever you want.
     End with a PASS/FAIL verdict line if the client needs one.
  3. Register it in `serve_all_tests()` by adding a `run_test_on_thread(...)`.
  4. Add the matching `runMyFeatureTest()` in TestTauSyncActivity.java and
     call it from `onRunAllTestsButtonClicked()`.
  The server pre-spawns one thread per handler; each blocks in connect()
  until the Android side opens the same word, so handler order does not
  matter — only the words have to match.
"""

import hashlib
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext

from tausync_py import TauSync

# ── Test parameters ──────────────────────────────────────────────────
SMALL_BINARY_SIZE = 25_600
LARGE_BINARY_SIZE = 1_048_576
BURST_MESSAGE_COUNT = 100
BIDIR_MESSAGE_COUNT = 50
LONG_LINE_LENGTH = 500_000
SMALL_FRAME_TOTAL = 204_800            # 200 KB
SMALL_FRAME_CHUNK = 100                # bytes per write — forces many frames
FILE_PC_TO_ANDROID_SIZE = 20 * 1024 * 1024
PEER_WORDS_WAIT_SECONDS = 45           # generous: Android may reach test 12 late
UNICODE_PAYLOAD = "שלום_世界_\U0001f30d"
TEST_TIMEOUT_SECONDS = 180
LARGE_WRITE_SIZE = 5 * 1024 * 1024    # 5 MB in one write() — auto-chunking must split it
CONCURRENT_ID_COUNT = 10               # simultaneous channels for ID-race regression test


# ── Small helpers ────────────────────────────────────────────────────

def read_text_line(stream) -> str:
    """Read one line and return it as text without the trailing newline."""
    return stream.read_line().decode("utf-8").rstrip("\n")


def send_verdict(stream, passed: bool) -> None:
    """Send the standard PASS/FAIL verdict line to the client."""
    stream.write_string("PASS\n" if passed else "FAIL\n")


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


# ── Group A: core data I/O ───────────────────────────────────────────

def serve_message_echo(tau):
    """Test 1: read a line from the client and echo it back."""
    stream = tau.connect("test_msg")
    try:
        line = read_text_line(stream)
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
        passed = hashlib.sha256(echo).hexdigest() == expected_sha
        send_verdict(stream, passed)
        print(f"  [test_bin]       {'PASS' if passed else 'FAIL'}  ({len(test_data)} bytes)")
    finally:
        stream.close()


def serve_empty_message(tau):
    """Test 3: read an empty line and echo it back."""
    stream = tau.connect("test_empty_msg")
    try:
        line = read_text_line(stream)
        stream.write_string(line + "\n")
        print(f"  [test_empty_msg] echoed empty line (len={len(line)})")
    finally:
        stream.close()


def serve_unicode_round_trip(tau):
    """Test 4: send a Unicode string, read echo, verify."""
    stream = tau.connect("test_unicode")
    try:
        stream.write_string(UNICODE_PAYLOAD + "\n")

        echo = read_text_line(stream)
        passed = echo == UNICODE_PAYLOAD
        send_verdict(stream, passed)
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
        passed = hashlib.sha256(echo).hexdigest() == expected_sha
        send_verdict(stream, passed)
        print(f"  [test_large_bin] {'PASS' if passed else 'FAIL'}  ({len(test_data)} bytes)")
    finally:
        stream.close()


# ── Group B: stream control ──────────────────────────────────────────

def serve_rapid_burst(tau):
    """Test 6: send a burst of numbered messages, verify client received all."""
    stream = tau.connect("test_burst")
    try:
        stream.write_string(f"{BURST_MESSAGE_COUNT}\n")
        for index in range(BURST_MESSAGE_COUNT):
            stream.write_string(f"msg_{index:03d}\n")

        received_count = int(read_text_line(stream))
        passed = received_count == BURST_MESSAGE_COUNT
        send_verdict(stream, passed)
        print(f"  [test_burst]     {'PASS' if passed else 'FAIL'}  (sent={BURST_MESSAGE_COUNT} received={received_count})")
    finally:
        stream.close()


def serve_concurrent_echo(manager, channel_name):
    """Test 7a/7b/10a/10b: read a line and echo it back on a named channel.

    Takes any TauSync manager so it can serve channels opened from a
    secondary manager via new_manager().
    """
    stream = manager.connect(channel_name)
    try:
        line = read_text_line(stream)
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
    print("  [test_stream_close] sent data and closed stream")


# ── Group C: bidirectionality & multiplexing ─────────────────────────

def serve_bidirectional(tau):
    """Test 9: read and write simultaneously on one stream.

    A writer thread sends N lines while the main thread reads N lines —
    proving the stack is genuinely full-duplex (no read blocks writes or
    vice-versa).  Each side verifies what it received from the other.
    """
    stream = tau.connect("test_bidir")
    received = []

    def write_lines():
        for index in range(BIDIR_MESSAGE_COUNT):
            stream.write_string(f"from_pc_{index:03d}\n")

    try:
        writer = threading.Thread(target=write_lines, daemon=True)
        writer.start()

        for _ in range(BIDIR_MESSAGE_COUNT):
            received.append(read_text_line(stream))
        writer.join(timeout=30)

        expected = [f"from_android_{i:03d}" for i in range(BIDIR_MESSAGE_COUNT)]
        passed = received == expected
        print(f"  [test_bidir]     {'PASS' if passed else 'FAIL'}  (read {len(received)}/{BIDIR_MESSAGE_COUNT} from peer)")
    finally:
        stream.close()


def serve_multi_manager(tau):
    """Test 10: serve two channels from two managers on the same socket.

    Channel 'a' is served by the primary manager and channel 'b' by a
    second manager from new_manager() — both multiplexed over one TCP
    connection at the same time.
    """
    manager_b = tau.new_manager()
    thread_a = run_test_on_thread(serve_concurrent_echo, (tau, "test_multi_a"))
    thread_b = run_test_on_thread(serve_concurrent_echo, (manager_b, "test_multi_b"))
    thread_a.join(timeout=30)
    thread_b.join(timeout=30)
    print("  [test_multi]     both manager channels served")


# ── Group D: channel lifecycle ───────────────────────────────────────

def serve_channel_reuse(tau):
    """Test 11: pair on the same word twice in a row.

    Each round opens 'test_reuse', echoes one line, and closes.  Re-using
    the word exercises local-ID recycling and word re-registration.
    """
    for round_index in range(2):
        stream = tau.connect("test_reuse")
        try:
            line = read_text_line(stream)
            stream.write_string(line + "\n")
            print(f"  [test_reuse]     round {round_index} echoed: {line!r}")
        finally:
            stream.close()


def serve_peer_waiting_words(tau):
    """Test 12: verify get_peer_waiting_words() reports the client's pending REQs.

    The Android side fires connect() on two words and blocks.  Before
    pairing, we poll get_peer_waiting_words() until both appear, then pair
    and report the verdict.  Comparison is case-insensitive because the
    API uppercases words on each side.
    """
    expected = {"TEST_PW_ALPHA", "TEST_PW_BETA"}
    deadline = time.time() + PEER_WORDS_WAIT_SECONDS
    seen = set()

    while time.time() < deadline:
        seen = {word.upper() for word in tau.get_peer_waiting_words()}
        if expected.issubset(seen):
            break
        time.sleep(0.2)

    passed = expected.issubset(seen)

    # Pair with both pending words to release the blocked client threads.
    stream_alpha = tau.connect("test_pw_alpha")
    stream_beta = tau.connect("test_pw_beta")
    try:
        send_verdict(stream_alpha, passed)
        stream_beta.write_string("done\n")
        print(f"  [test_pw]        {'PASS' if passed else 'FAIL'}  (saw {sorted(seen & expected)})")
    finally:
        stream_alpha.close()
        stream_beta.close()


# ── Group E: data edge cases ─────────────────────────────────────────

def serve_long_line(tau):
    """Test 13: send one very long line; client reads it with readLine()."""
    stream = tau.connect("test_long_line")
    try:
        stream.write_string("A" * LONG_LINE_LENGTH + "\n")
        passed = read_text_line(stream) == "PASS"
        print(f"  [test_long_line] {'PASS' if passed else 'FAIL'}  ({LONG_LINE_LENGTH} chars)")
    finally:
        stream.close()


def serve_small_frames(tau):
    """Test 14: send a payload in tiny 100-byte writes; client reassembles.

    Exercises frame fragmentation/reassembly: many small TPack frames must
    rebuild into the exact original payload (verified by SHA-256 echo).
    """
    stream = tau.connect("test_small_frames")
    try:
        data = os.urandom(SMALL_FRAME_TOTAL)
        expected_sha = hashlib.sha256(data).hexdigest()

        stream.write_string(f"{len(data)}\n")
        for offset in range(0, len(data), SMALL_FRAME_CHUNK):
            stream.write(data[offset:offset + SMALL_FRAME_CHUNK])

        echo = stream.read_exactly(len(data))
        passed = hashlib.sha256(echo).hexdigest() == expected_sha
        send_verdict(stream, passed)
        frames = (len(data) + SMALL_FRAME_CHUNK - 1) // SMALL_FRAME_CHUNK
        print(f"  [test_small_frames] {'PASS' if passed else 'FAIL'}  ({frames} frames)")
    finally:
        stream.close()


def serve_raw_stream(tau):
    """Test 15: echo a line so the client can exercise raw stream adapters."""
    stream = tau.connect("test_raw_stream")
    try:
        line = read_text_line(stream)
        stream.write_string(line + "\n")
        print(f"  [test_raw_stream] echoed: {line!r}")
    finally:
        stream.close()


# ── Group F: file transfer ───────────────────────────────────────────

def serve_file_pc_to_android(tau):
    """Test 16: stream a 20 MB file to the client and have it verify SHA-256."""
    stream = tau.connect("test_file_pc_to_android")
    temp_path = None
    try:
        temp_path = _make_temp_file(FILE_PC_TO_ANDROID_SIZE)
        expected_sha = sha256_of_file(temp_path)

        stream.write_string(f"{os.path.getsize(temp_path)}\n")
        stream.write_string(f"{expected_sha}\n")
        stream.write_file(temp_path)

        passed = read_text_line(stream) == "PASS"
        print(f"  [test_file_pc_to_android] {'PASS' if passed else 'FAIL'}  ({FILE_PC_TO_ANDROID_SIZE} bytes)")
    finally:
        stream.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def serve_file_android_to_pc(tau):
    """Test 17: receive a file from the client and verify its SHA-256."""
    stream = tau.connect("test_file_android_to_pc")
    temp_path = None
    try:
        size = int(read_text_line(stream))
        expected_sha = read_text_line(stream)

        handle, temp_path = tempfile.mkstemp(prefix="tausync_recv_", suffix=".bin")
        os.close(handle)
        stream.read_to_file(temp_path, size)

        passed = sha256_of_file(temp_path) == expected_sha
        send_verdict(stream, passed)
        print(f"  [test_file_android_to_pc] {'PASS' if passed else 'FAIL'}  ({size} bytes)")
    finally:
        stream.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ── Group G: failure & recovery ──────────────────────────────────────

def serve_peer_close(tau):
    """Test 18: close immediately without sending; client must detect EOF."""
    stream = tau.connect("test_peer_close")
    stream.close()
    print("  [test_peer_close] paired and closed without sending")


# ── Group H: bugfix validation ───────────────────────────────────────

def serve_large_write(tau):
    """Test 19: send 5 MB in a single write() — auto-chunking must split it into ≤64 KB frames."""
    stream = tau.connect("test_large_write")
    try:
        data = os.urandom(LARGE_WRITE_SIZE)
        expected_sha = hashlib.sha256(data).hexdigest()
        stream.write_string(f"{len(data)}\n")
        stream.write_string(f"{expected_sha}\n")
        stream.write(data)  # ONE write call — sender auto-chunking handles splitting
        passed = read_text_line(stream) == "PASS"
        print(f"  [test_large_write] {'PASS' if passed else 'FAIL'}  ({LARGE_WRITE_SIZE} bytes, 1 write call)")
    finally:
        stream.close()


def _serve_single_id_channel(tau, word, expected_payload):
    """Helper for test 20: echo back PASS/FAIL for one concurrent channel."""
    stream = tau.connect(word)
    try:
        line = read_text_line(stream)
        passed = (line == expected_payload)
        send_verdict(stream, passed)
        if not passed:
            print(f"  [{word}] FAIL  expected={expected_payload!r} got={line!r}")
    finally:
        stream.close()


def serve_concurrent_ids(tau):
    """Test 20: open CONCURRENT_ID_COUNT channels simultaneously — IDs must be unique, no cross-talk."""
    threads = [
        run_test_on_thread(_serve_single_id_channel,
                           (tau, f"test_cid_{i:02d}", f"payload_{i:02d}"))
        for i in range(CONCURRENT_ID_COUNT)
    ]
    for thread in threads:
        thread.join(timeout=30)
    print(f"  [test_concurrent_ids] served {CONCURRENT_ID_COUNT} concurrent channels")


def serve_concurrent_close(tau):
    """Test 21: both sides close at the same time; the next channel must still work cleanly."""
    # Round 1: Android signals 'ready' then closes; we close at the same time.
    stream = tau.connect("test_conc_close")
    try:
        read_text_line(stream)  # blocks until Android writes 'ready\n' and closes
    finally:
        stream.close()

    # Round 2: verify the transport is clean — if double-FIN corrupted ID state this echo fails.
    stream2 = tau.connect("test_conc_close_verify")
    try:
        line = read_text_line(stream2)
        stream2.write_string(line + "\n")
        print(f"  [test_conc_close]  verify echo: {line!r}")
    finally:
        stream2.close()


# ── Helpers ──────────────────────────────────────────────────────────

def _make_temp_file(size_bytes: int) -> str:
    """Create a temp file of random bytes and return its path."""
    handle, path = tempfile.mkstemp(prefix="tausync_send_", suffix=".bin")
    with os.fdopen(handle, "wb") as file:
        remaining = size_bytes
        while remaining > 0:
            block = os.urandom(min(remaining, 1024 * 1024))
            file.write(block)
            remaining -= len(block)
    return path


# ── Orchestrator ──────────────────────────────────────────────────────

def run_test_on_thread(target, args=()):
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    return thread


def serve_all_tests(tau):
    """Spawn one thread per test channel and wait for all to complete.

    Re-callable: tap 'Re-arm Automated Tests' in the console to serve a
    fresh round so the phone can run the whole suite again.
    """
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
        run_test_on_thread(serve_bidirectional, (tau,)),
        run_test_on_thread(serve_multi_manager, (tau,)),
        run_test_on_thread(serve_channel_reuse, (tau,)),
        run_test_on_thread(serve_peer_waiting_words, (tau,)),
        run_test_on_thread(serve_long_line, (tau,)),
        run_test_on_thread(serve_small_frames, (tau,)),
        run_test_on_thread(serve_raw_stream, (tau,)),
        run_test_on_thread(serve_file_pc_to_android, (tau,)),
        run_test_on_thread(serve_file_android_to_pc, (tau,)),
        run_test_on_thread(serve_peer_close, (tau,)),
        run_test_on_thread(serve_large_write, (tau,)),
        run_test_on_thread(serve_concurrent_ids, (tau,)),
        run_test_on_thread(serve_concurrent_close, (tau,)),
    ]

    for thread in threads:
        thread.join(timeout=TEST_TIMEOUT_SECONDS)

    timed_out = [t for t in threads if t.is_alive()]
    if timed_out:
        print(f"\n  WARNING: {len(timed_out)} test(s) still running after {TEST_TIMEOUT_SECONDS}s")


# ── Manual playground GUI ─────────────────────────────────────────────

class ManualChannelPanel(ttk.Frame):
    """One tab in the console: a live two-way chat over a single meeting word.

    Pairs with the phone when both sides open the same word.  An auto-reader
    thread displays every line the phone sends; Send / Spam push lines back.
    'Echo back received' bounces each incoming line straight back, which keeps
    the phone's send-then-read and spam workflows working without manual help.
    """

    def __init__(self, notebook, console, tau, word):
        super().__init__(notebook)
        self.console = console
        self.tau = tau
        self.word = word
        self.stream = None
        self.closed = False
        self.echo_var = tk.BooleanVar(value=True)
        self._build()
        threading.Thread(target=self._open, daemon=True).start()

    # — layout —
    def _build(self):
        self.status = ttk.Label(self, text=f"Pairing on '{self.word}'…")
        self.status.pack(anchor="w", padx=6, pady=(6, 2))

        self.incoming = scrolledtext.ScrolledText(self, height=12, state="disabled", wrap="word")
        self.incoming.pack(fill="both", expand=True, padx=6, pady=2)

        send_row = ttk.Frame(self)
        send_row.pack(fill="x", padx=6, pady=2)
        self.message_var = tk.StringVar(value="Hello from PC!")
        entry = ttk.Entry(send_row, textvariable=self.message_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self._send())
        self.send_btn = ttk.Button(send_row, text="Send", command=self._send, state="disabled")
        self.send_btn.pack(side="left", padx=4)

        spam_row = ttk.Frame(self)
        spam_row.pack(fill="x", padx=6, pady=(2, 6))
        ttk.Label(spam_row, text="Spam count:").pack(side="left")
        self.spam_var = tk.StringVar(value="50")
        ttk.Entry(spam_row, textvariable=self.spam_var, width=8).pack(side="left", padx=4)
        self.spam_btn = ttk.Button(spam_row, text="Spam xN", command=self._spam, state="disabled")
        self.spam_btn.pack(side="left")
        ttk.Checkbutton(spam_row, text="Echo back received", variable=self.echo_var).pack(side="left", padx=12)
        ttk.Button(spam_row, text="Close Channel", command=self.close).pack(side="right")

    # — connection lifecycle —
    def _open(self):
        try:
            stream = self.tau.connect(self.word)
        except Exception as exc:
            self.console.post(lambda: self._set_status(f"Open failed: {exc}"))
            return
        self.stream = stream
        self.console.post(self._on_opened)
        self._read_loop()

    def _on_opened(self):
        self._set_status(f"Channel '{self.word}' open — live two-way chat.")
        self.send_btn.config(state="normal")
        self.spam_btn.config(state="normal")

    def _read_loop(self):
        try:
            while not self.closed:
                data = self.stream.read_line()
                if not data:
                    break
                text = data.decode("utf-8", errors="replace").rstrip("\n")
                self.console.post(lambda value=text: self._display(f"peer: {value}"))
                if self.echo_var.get():
                    self.stream.write_string(text + "\n")
        except Exception as exc:
            if not self.closed:
                self.console.post(lambda: self._display(f"[reader stopped: {exc}]"))
        self.console.post(lambda: self._set_status(f"Channel '{self.word}' closed (peer EOF)."))

    # — actions (run on the Tk thread) —
    def _send(self):
        if self.stream is None:
            return
        text = self.message_var.get()
        self._display(f"me:   {text}")
        threading.Thread(target=lambda: self._write_line(text), daemon=True).start()

    def _write_line(self, text):
        try:
            self.stream.write_string(text + "\n")
        except Exception as exc:
            self.console.post(lambda: self._display(f"[send error: {exc}]"))

    def _spam(self):
        if self.stream is None:
            return
        try:
            count = max(1, int(self.spam_var.get()))
        except ValueError:
            count = 50
        message = self.message_var.get()
        self._display(f"[spam: sending {count} lines of \"{message}\" + index]")
        threading.Thread(target=lambda: self._spam_worker(count, message), daemon=True).start()

    def _spam_worker(self, count, message):
        start = time.time()
        try:
            for index in range(count):
                self.stream.write_string(f"{message}{index}\n")
        except Exception as exc:
            self.console.post(lambda: self._display(f"[spam error: {exc}]"))
            return
        elapsed_ms = (time.time() - start) * 1000
        self.console.post(lambda: self._display(f"[spam: sent {count} lines in {elapsed_ms:.0f}ms]"))

    def close(self):
        self.closed = True
        try:
            if self.stream is not None:
                self.stream.close()
        except Exception:
            pass
        self.console.remove_channel(self.word)

    # — display (Tk thread only) —
    def _display(self, line):
        self.incoming.config(state="normal")
        self.incoming.insert("end", line + "\n")
        self.incoming.see("end")
        self.incoming.config(state="disabled")

    def _set_status(self, text):
        self.status.config(text=text)


class TauSyncTestConsole(tk.Tk):
    """The PC-side window: status, system log, manual channels, test serving."""

    def __init__(self):
        super().__init__()
        self.title("TauSync PC Test Console")
        self.geometry("780x680")

        self.tau = TauSync()
        self.ui_queue = queue.Queue()
        self.manual_channels = {}
        self._closing = False

        self.status_var = tk.StringVar(value="Starting server…")
        self.word_var = tk.StringVar(value="main")

        self._build_ui()
        self.after(80, self._drain_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._listen_and_serve, daemon=True).start()

    # — cross-thread UI posting —
    def post(self, func):
        self.ui_queue.put(func)

    def _drain_ui_queue(self):
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        if not self._closing:
            self.after(80, self._drain_ui_queue)

    # — layout —
    def _build_ui(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(header, text="TauSync PC Test Console", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(header, textvariable=self.status_var, foreground="#1565C0").pack(anchor="w")

        self.system_log = scrolledtext.ScrolledText(self, height=6, state="disabled", wrap="word")
        self.system_log.pack(fill="x", padx=8, pady=4)

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=4)
        ttk.Label(controls, text="Manual channel word:").pack(side="left")
        ttk.Entry(controls, textvariable=self.word_var, width=20).pack(side="left", padx=4)
        self.open_btn = ttk.Button(controls, text="Open Channel", command=self._on_open_channel, state="disabled")
        self.open_btn.pack(side="left", padx=4)
        self.rearm_btn = ttk.Button(controls, text="Re-arm Automated Tests",
                                    command=self._on_rearm_tests, state="disabled")
        self.rearm_btn.pack(side="left", padx=16)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    # — server lifecycle —
    def _listen_and_serve(self):
        self.post(lambda: self.status_var.set("Waiting for Android client to connect…"))
        self.post(lambda: self._log_system("Listening for Android client…"))
        try:
            self.tau.listen()
        except Exception as exc:
            self.post(lambda: self.status_var.set(f"listen() failed: {exc}"))
            return
        self.post(lambda: self.status_var.set("Android connected — manual channels enabled, tests armed."))
        self.post(self._enable_controls)
        self._arm_tests()

    def _enable_controls(self):
        self.open_btn.config(state="normal")
        self.rearm_btn.config(state="normal")
        self._log_system("Android connected. Open manual channels or tap 'Run All Tests' on the phone.")

    def _arm_tests(self):
        self.post(lambda: self._log_system("Arming automated test channels…"))
        threading.Thread(target=self._serve_tests_once, daemon=True).start()

    def _serve_tests_once(self):
        serve_all_tests(self.tau)
        self.post(lambda: self._log_system("Automated test round served. Re-arm to run again."))

    def _on_rearm_tests(self):
        self._log_system("Re-arming automated test channels…")
        self._arm_tests()

    # — manual channels —
    def _on_open_channel(self):
        word = self.word_var.get().strip()
        if not word:
            return
        if word in self.manual_channels:
            self._log_system(f"Channel '{word}' is already open.")
            return
        panel = ManualChannelPanel(self.notebook, self, self.tau, word)
        self.manual_channels[word] = panel
        self.notebook.add(panel, text=word)
        self.notebook.select(panel)
        self._log_system(f"Opening manual channel '{word}'…")

    def remove_channel(self, word):
        def do():
            panel = self.manual_channels.pop(word, None)
            if panel is not None:
                self.notebook.forget(panel)
                self._log_system(f"Closed manual channel '{word}'.")
        self.post(do)

    # — system log (Tk thread only) —
    def _log_system(self, text):
        self.system_log.config(state="normal")
        self.system_log.insert("end", text + "\n")
        self.system_log.see("end")
        self.system_log.config(state="disabled")

    def _on_close(self):
        self._closing = True
        try:
            self.tau.dispose()
        except Exception:
            pass
        self.destroy()


def main():
    TauSyncTestConsole().mainloop()


if __name__ == "__main__":
    main()
