"""Parallel TauSync multiplexing test.

4 independent TauSync manager instances, each sending 5 pictures
simultaneously (20 channels total) over a SINGLE TCP socket (the
SocketTransport is a singleton). 100-byte TPack frames ensure heavy
interleaving so every TargetID is mixed on the wire.

Usage:
    python hub.py              # orchestrator - starts server + client, validates results
    python hub.py --server     # internal: server side (4 managers x 5 channels)
    python hub.py --client     # internal: client side (4 managers x 5 channels)
"""

import sys
import os
import subprocess
import hashlib
import time
import threading
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))

NUM_MANAGERS = 4
CHANNELS_PER_MANAGER = 5
NUM_CHANNELS = NUM_MANAGERS * CHANNELS_PER_MANAGER  # 20
TIMEOUT_SECONDS = 180
FILES_DIR = os.path.join(SCRIPT_DIR, "files")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "hub_output")
CHUNK_SZ = 100

SOURCE_FILES = ["1.jpg", "2.jpg"]


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ======================================================================
#  SERVER MODE
# ======================================================================

def _run_server():
    from tausync_py import TauSync

    tau = TauSync()
    tau.listen()
    print("SERVER: transport connected (singleton socket).", flush=True)

    managers = [tau.new_manager() for _ in range(NUM_MANAGERS)]
    for mi, m in enumerate(managers):
        print(f"SERVER: TauSync[{mi}] created", flush=True)

    results = {}
    lock = threading.Lock()

    def serve_channel(mgr, mgr_idx: int, global_idx: int) -> None:
        word = f"channel_{global_idx}"
        src_file = os.path.join(FILES_DIR, SOURCE_FILES[global_idx % len(SOURCE_FILES)])
        file_size = os.path.getsize(src_file)
        tag = f"[S-M{mgr_idx}-{global_idx:02d}]"
        try:
            stream = mgr.connect(word, chunk_size=CHUNK_SZ)
            print(f"{tag} stream '{word}' connected.", flush=True)

            req_data = stream.read_until(b"\r\n\r\n")
            print(f"{tag} request received: {req_data[:60]}", flush=True)

            header = (
                "HTTP/1.1 200 OK\r\n"
                f"Content-Length: {file_size}\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            stream.write(header.encode())
            stream.write_file(src_file, chunk_size=CHUNK_SZ)
            stream.close()
            print(f"{tag} done - sent {file_size} bytes.", flush=True)
            with lock:
                results[global_idx] = "OK"

        except Exception as e:
            print(f"{tag} ERROR: {e}", flush=True)
            with lock:
                results[global_idx] = f"ERROR: {e}"

    threads = []
    for mi in range(NUM_MANAGERS):
        mgr = managers[mi]
        for ci in range(CHANNELS_PER_MANAGER):
            global_idx = mi * CHANNELS_PER_MANAGER + ci
            t = threading.Thread(
                target=serve_channel,
                args=(mgr, mi, global_idx),
                daemon=True,
            )
            threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join(TIMEOUT_SECONDS)

    print(f"\nSERVER SUMMARY: {json.dumps(results, indent=2)}", flush=True)
    ok_count = sum(1 for v in results.values() if v == "OK")
    print(f"SERVER: {ok_count}/{NUM_CHANNELS} channels served successfully.", flush=True)


# ======================================================================
#  CLIENT MODE
# ======================================================================

def _run_client():
    from tausync_py import TauSync

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    time.sleep(2)

    tau = TauSync()
    tau.connect_to("127.0.0.1")
    print("CLIENT: transport connected (singleton socket).", flush=True)

    managers = [tau.new_manager() for _ in range(NUM_MANAGERS)]
    for mi, m in enumerate(managers):
        print(f"CLIENT: TauSync[{mi}] created", flush=True)

    results = {}
    lock = threading.Lock()

    def request_channel(mgr, mgr_idx: int, global_idx: int) -> None:
        word = f"channel_{global_idx}"
        src_name = SOURCE_FILES[global_idx % len(SOURCE_FILES)]
        out_path = os.path.join(OUTPUT_DIR, f"out_{global_idx:02d}_{src_name}")
        tag = f"[C-M{mgr_idx}-{global_idx:02d}]"
        try:
            stream = mgr.connect(word, chunk_size=CHUNK_SZ)
            print(f"{tag} stream '{word}' connected.", flush=True)

            request = f"GET /{src_name} HTTP/1.1\r\n\r\n"
            stream.write_string(request)
            stream.flush()
            print(f"{tag} request sent: GET /{src_name}", flush=True)

            header_block = stream.read_until(b"\r\n\r\n")

            content_length = 0
            for line in header_block.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    content_length = int(line.split(b":", 1)[1].strip())
                    break

            written = stream.read_to_file(out_path, content_length, chunk_size=CHUNK_SZ)
            stream.close()
            print(f"{tag} done - received {written} bytes -> {os.path.basename(out_path)}", flush=True)
            with lock:
                results[global_idx] = {"file": out_path, "bytes": written}

        except Exception as e:
            print(f"{tag} ERROR: {e}", flush=True)
            with lock:
                results[global_idx] = {"error": str(e)}

    threads = []
    for mi in range(NUM_MANAGERS):
        mgr = managers[mi]
        for ci in range(CHANNELS_PER_MANAGER):
            global_idx = mi * CHANNELS_PER_MANAGER + ci
            t = threading.Thread(
                target=request_channel,
                args=(mgr, mi, global_idx),
                daemon=True,
            )
            threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join(TIMEOUT_SECONDS)

    results_path = os.path.join(OUTPUT_DIR, "results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    ok_count = sum(1 for v in results.values() if "file" in v)
    print(f"\nCLIENT SUMMARY: {ok_count}/{NUM_CHANNELS} channels received successfully.", flush=True)


# ======================================================================
#  ORCHESTRATOR MODE (default)
# ======================================================================

def _run_orchestrator():
    print("=" * 70)
    print("  TauSync Parallel Multiplexing Test")
    print(f"  {NUM_MANAGERS} TauSync managers x {CHANNELS_PER_MANAGER} channels = {NUM_CHANNELS} total")
    print(f"  All on ONE singleton socket, {CHUNK_SZ}-byte TPack frames")
    print("=" * 70)
    print(f"  Source files: {', '.join(SOURCE_FILES)}")
    print(f"  Output dir:   {OUTPUT_DIR}")
    print()

    if os.path.isdir(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            os.remove(os.path.join(OUTPUT_DIR, f))
    else:
        os.makedirs(OUTPUT_DIR)

    expected_hashes = {}
    for i in range(NUM_CHANNELS):
        src = os.path.join(FILES_DIR, SOURCE_FILES[i % len(SOURCE_FILES)])
        expected_hashes[i] = file_sha256(src)

    server_proc = subprocess.Popen(
        [sys.executable, "-u", __file__, "--server"],
        cwd=SCRIPT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    time.sleep(1)

    client_proc = subprocess.Popen(
        [sys.executable, "-u", __file__, "--client"],
        cwd=SCRIPT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def drain(proc, label):
        for line in iter(proc.stdout.readline, b""):
            text = line.decode(errors="replace").rstrip()
            safe_text = text.encode("ascii", errors="replace").decode("ascii")
            print(f"  {label} | {safe_text}", flush=True)

    t_srv = threading.Thread(target=drain, args=(server_proc, "SRV"), daemon=True)
    t_cli = threading.Thread(target=drain, args=(client_proc, "CLI"), daemon=True)
    t_srv.start()
    t_cli.start()

    client_proc.wait(timeout=TIMEOUT_SECONDS + 10)
    server_proc.wait(timeout=TIMEOUT_SECONDS + 10)
    t_srv.join(5)
    t_cli.join(5)

    print()
    print("=" * 70)
    print("  VALIDATION")
    print("=" * 70)

    results_path = os.path.join(OUTPUT_DIR, "results.json")
    if not os.path.exists(results_path):
        print("  FAIL: client did not write results.json")
        sys.exit(1)

    with open(results_path) as f:
        results = json.load(f)

    passed = 0
    failed = 0

    for i in range(NUM_CHANNELS):
        key = str(i)
        src_name = SOURCE_FILES[i % len(SOURCE_FILES)]
        src_path = os.path.join(FILES_DIR, src_name)
        expected_size = os.path.getsize(src_path)
        expected_hash = expected_hashes[i]

        if key not in results:
            print(f"  channel_{i:02d}  FAIL  - no result recorded")
            failed += 1
            continue

        entry = results[key]
        if "error" in entry:
            print(f"  channel_{i:02d}  FAIL  - {entry['error']}")
            failed += 1
            continue

        out_path = entry["file"]
        if not os.path.exists(out_path):
            print(f"  channel_{i:02d}  FAIL  - output file missing: {out_path}")
            failed += 1
            continue

        actual_size = os.path.getsize(out_path)
        if actual_size != expected_size:
            print(f"  channel_{i:02d}  FAIL  - size mismatch: {actual_size} vs {expected_size}")
            failed += 1
            continue

        actual_hash = file_sha256(out_path)
        if actual_hash != expected_hash:
            print(f"  channel_{i:02d}  FAIL  - SHA256 mismatch")
            failed += 1
            continue

        print(f"  channel_{i:02d}  PASS  {src_name} ({actual_size:,} bytes) SHA256 OK")
        passed += 1

    print()
    print(f"  Result: {passed}/{NUM_CHANNELS} passed, {failed}/{NUM_CHANNELS} failed")
    if failed == 0:
        print("  ALL CHANNELS PASSED - parallel multiplexing works correctly.")
    else:
        print("  SOME CHANNELS FAILED - investigate above.")
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)


# ======================================================================

if __name__ == "__main__":
    if "--server" in sys.argv:
        _run_server()
    elif "--client" in sys.argv:
        _run_client()
    else:
        _run_orchestrator()
