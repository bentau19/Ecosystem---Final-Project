"""TauSync HTTP file server.

Listens for TauSync connections on a meeting-word, receives HTTP GET
requests, and serves files from the ``files/`` directory.
"""

import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tausync_py import TauSync


def get_file_info(filename: str):
    """Return (file_path, file_size) if the file exists, otherwise None."""
    file_path = os.path.join("files", filename)
    if not os.path.isfile(file_path):
        return None
    try:
        return file_path, os.path.getsize(file_path)
    except OSError:
        return None


def handle_request(request_data: str):
    """Parse the HTTP request and return (header_bytes, file_path_or_None, should_close).

    For responses that include a file body (200 OK), file_path is set so
    the caller can stream the file in chunks instead of loading it all at once.
    For header-only responses (301, 404), file_path is None.
    """
    if not request_data:
        return b"", None, True

    lines = request_data.split('\r\n')
    if len(lines) < 1:
        return b"", None, True

    try:
        request_line = lines[0].split()
        if len(request_line) < 2:
            return b"", None, True
        path = request_line[1]
    except ValueError:
        return b"", None, True

    client_connection = "close"
    for line in lines:
        lower_line = line.lower()
        if lower_line.startswith("connection:"):
            parts = line.split(":", 1)
            if len(parts) > 1:
                client_connection = parts[1].strip()
            break

    if path == "/redirect":
        header = (
            "HTTP/1.1 301 Moved Permanently\r\n"
            "Connection: close\r\n"
            "Location: /result.html\r\n"
            "\r\n"
        )
        return header.encode(), None, True

    if path == "/" or path == "/index.html":
        filename = "index.html"
    else:
        filename = path.lstrip('/')

    file_info = get_file_info(filename)

    if file_info is not None:
        file_path, file_size = file_info

        if client_connection.lower() == "keep-alive":
            conn_header = "keep-alive"
            should_close = False
        else:
            conn_header = "close"
            should_close = True

        header = (
            "HTTP/1.1 200 OK\r\n"
            f"Connection: {conn_header}\r\n"
            f"Content-Length: {file_size}\r\n"
            "\r\n"
        )
        return header.encode(), file_path, should_close

    header = (
        "HTTP/1.1 404 Not Found\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return header.encode(), None, True


def main():
    tau = TauSync()
    try:
        tau.listen()
        print("TauSync server: transport connected.", flush=True)

        password = "main"
        while True:
            tau = TauSync()
            stream = tau.connect(password)
            print(f"TauSync server: stream '{password}' connected.", flush=True)

            try:
                raw = stream.read_until(b"\r\n\r\n")
                if not raw:
                    break
                print("TauSync server: request received.", flush=True)

                request_text = raw.decode('utf-8')
                print(request_text, flush=True)
                header_bytes, file_path, should_close = handle_request(request_text)

                stream.write(header_bytes)

                if file_path is not None:
                    stream.write_file(file_path)
                else:
                    stream.flush()

                print("TauSync server: response sent.", flush=True)
            except Exception:
                break

            stream.close()

    except Exception as e:
        print(f"Server Error: {e}", flush=True)


def run_with_timeout(timeout_seconds: int = 30) -> None:
    """Run server and hard-exit if hung."""
    worker = threading.Thread(target=main, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        print(f"Server: timeout after {timeout_seconds}s. Exiting.")
        os._exit(1)


if __name__ == "__main__":
    run_with_timeout(30)
