"""TauSync HTTP file client.

Connects to a TauSync server, sends HTTP GET requests for files,
and saves responses to disk.
"""

import sys
import os
import threading
import TauSync


def _parse_content_length(header_block: bytes) -> int:
    """Extract the Content-Length value from raw header bytes."""
    for line in header_block.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            try:
                return int(line.split(b":", 1)[1].strip())
            except (ValueError, IndexError):
                return 0
    return 0


def receive_response_to_file(stream, out_path: str):
    """Read the HTTP response, save the body directly to disk.

    Streams the body in chunks so memory stays constant regardless of
    file size.  Returns (header_bytes, bytes_written).
    Returns (None, 0) on connection close / error.
    """
    header_block = stream.read_until(b"\r\n\r\n")
    if not header_block:
        return None, 0

    content_length = _parse_content_length(header_block)

    if content_length > 0:
        stream.read_to_file(out_path, content_length)
    else:
        with open(out_path, "wb"):
            pass

    return header_block, os.path.getsize(out_path)


def run() -> None:
    tau = TauSync()
    server_ip = "127.0.0.1"
    tau.connect_to(server_ip)
    print("TauSync client: transport connected.")

    password = "main"
    while True:
        tau = TauSync()
        stream = tau.connect(password)
        print(f"TauSync client: stream '{password}' connected.")

        path = input("Enter path ")
        try:
            request = f"GET {path} HTTP/1.1\r\n\r\n"
            stream.write_string(request)
            stream.flush()
            print("TauSync client: request sent.")

            save_path = path
            if save_path == "/":
                save_path = "/index.html"
            filename = save_path.split('/')[-1]

            header_block, body_size = receive_response_to_file(stream, filename)
            if header_block is None:
                print("TauSync client: no response received.")
            else:
                first_line = header_block.split(b"\r\n")[0].decode()
                print(f"TauSync client: {first_line}  ({body_size} bytes saved to {filename})")

        except Exception as e:
            print(f"Connection Error: {e}")
        stream.close()


def run_with_timeout(timeout_seconds: int = 30) -> None:
    """Run client and hard-exit if hung."""
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Client: timeout after {timeout_seconds}s. Exiting.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(30)
