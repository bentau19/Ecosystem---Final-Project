"""
Cross-platform test server (Windows/C# side).

Serves the Android TauSync test page:
  Test 1 (test_msg): echo-back message exchange
  Test 2 (test_bin): binary round-trip with SHA-256 verification
"""
import sys, os, time, hashlib, threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "windows"))
from tausync_py import TauSync


def serve_message_test(tau: TauSync) -> None:
    """Test 1: read a line from the client and echo it back."""
    print("[test_msg] Connecting on 'test_msg' ...")
    stream = tau.connect("test_msg")
    print("[test_msg] Channel open.")

    msg_bytes = stream.read_line()
    msg = msg_bytes.decode("utf-8").rstrip("\n")
    print(f"[test_msg] Received: {msg}")

    stream.write_string(msg + "\n")
    print(f"[test_msg] Echoed back: {msg}")

    stream.close()
    print("[test_msg] DONE")


def serve_binary_test(tau: TauSync) -> None:
    """Test 2: send random data, read echo, verify SHA-256."""
    print("[test_bin] Connecting on 'test_bin' ...")
    stream = tau.connect("test_bin")
    print("[test_bin] Channel open.")

    test_data = bytes(range(256)) * 100  # 25,600 bytes
    sha_sent = hashlib.sha256(test_data).hexdigest()

    stream.write_string(f"{len(test_data)}\n")
    print(f"[test_bin] Sent size header: {len(test_data)}")

    stream.write(test_data)
    print(f"[test_bin] Sent {len(test_data)} bytes, SHA256={sha_sent[:16]}...")

    echo = stream.read_exactly(len(test_data))
    sha_recv = hashlib.sha256(echo).hexdigest()
    print(f"[test_bin] Received {len(echo)} bytes, SHA256={sha_recv[:16]}...")

    if sha_sent == sha_recv:
        stream.write_string("PASS\n")
        print("[test_bin] PASS - checksums match")
    else:
        stream.write_string("FAIL\n")
        print(f"[test_bin] FAIL - sent={sha_sent} recv={sha_recv}")

    stream.close()
    print("[test_bin] DONE")


def main():
    tau = TauSync()
    print("[server] Listening on port 8888 ...")
    tau.listen()
    print("[server] Client connected.\n")

    t1 = threading.Thread(target=serve_message_test, args=(tau,), daemon=True)
    t2 = threading.Thread(target=serve_binary_test, args=(tau,), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    print("\n=== ALL TESTS SERVED ===")
    time.sleep(2)
    tau.dispose()


if __name__ == "__main__":
    main()
