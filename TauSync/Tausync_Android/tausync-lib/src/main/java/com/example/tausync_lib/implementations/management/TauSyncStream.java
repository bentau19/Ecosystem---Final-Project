package com.example.tausync_lib.implementations.management;

import com.example.tausync_lib.interfaces.IConnectionManager;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.Closeable;
import java.io.EOFException;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * Bidirectional stream returned by {@code connect(word)}.
 *
 * <p>Follows the {@link java.net.Socket} pattern:
 * <ul>
 *   <li>{@link #getInputStream()} — reads incoming data
 *   <li>{@link #getOutputStream()} — sends data via TPack frames
 *   <li>{@link #close()} — sends FIN and releases the local ID
 * </ul>
 *
 * <p>Also provides convenience methods mirroring Python {@code tausync_py}:
 * {@link #readLine()}, {@link #readExactly(int)}, {@link #writeString(String)},
 * {@link #writeFile(String)}, {@link #readToFile(String, long)}.
 */
public final class TauSyncStream implements Closeable {

    private static final int DEFAULT_CHUNK_SIZE = 65536;
    private static final int MAX_CHUNK_SIZE = 16 * 1024 * 1024;
    private static final int MAX_LINE_LENGTH = 1_048_576;

    private final InputStream inputStream;
    private final TauSyncOutputStream outputStream;
    private final int localId;
    private final IConnectionManager connectionManager;
    private volatile boolean closed;
    private volatile boolean finSent;

    public TauSyncStream(InputStream readStream, int localId, IConnectionManager connectionManager) {
        if (readStream == null) throw new IllegalArgumentException("readStream must not be null");
        if (connectionManager == null) throw new IllegalArgumentException("connectionManager must not be null");
        // Buffer the source so byte-at-a-time reads (readLine) pull from an in-memory
        // buffer instead of allocating per byte and contending on the chunk queue.
        this.inputStream = readStream instanceof BufferedInputStream
                ? readStream
                : new BufferedInputStream(readStream, DEFAULT_CHUNK_SIZE);
        this.localId = localId;
        this.connectionManager = connectionManager;
        this.outputStream = new TauSyncOutputStream();
    }

    /** @return an InputStream that reads incoming data from the peer */
    public InputStream getInputStream() {
        return inputStream;
    }

    /** @return an OutputStream that sends data to the peer via TPack frames */
    public OutputStream getOutputStream() {
        return outputStream;
    }

    /** @return the local ID assigned to this stream */
    public int getLocalId() {
        return localId;
    }

    // ── Convenience read methods ──────────────────────────────────────

    /**
     * Reads exactly {@code count} bytes, blocking until all arrive or EOF.
     *
     * @param count number of bytes to read (must be >= 0)
     * @return byte array of exactly {@code count} bytes
     * @throws EOFException if EOF before all bytes are read
     * @throws IOException  on I/O error
     */
    public byte[] readExactly(int count) throws IOException {
        checkOpen();
        if (count < 0) throw new IllegalArgumentException("count must be >= 0, got " + count);
        if (count == 0) return new byte[0];

        byte[] result = new byte[count];
        int total = 0;
        while (total < count) {
            int n = inputStream.read(result, total, count - total);
            if (n < 0) {
                throw new EOFException(
                        "Expected " + count + " bytes, got " + total + " before EOF");
            }
            total += n;
        }
        return result;
    }

    /**
     * Reads a single line terminated by {@code \n}.
     *
     * <p>Returns the line <b>without</b> the trailing newline for convenience.
     * Returns {@code null} on EOF (peer closed the stream).
     *
     * @return the line as a UTF-8 string without the trailing newline, or null on EOF
     * @throws IOException on I/O error
     */
    public String readLine() throws IOException {
        return readLine(MAX_LINE_LENGTH);
    }

    /**
     * Reads a single line with a custom length limit.
     *
     * @param maxLength safety limit to prevent unbounded reads
     * @return the line without trailing newline, or null on EOF
     * @throws IOException on I/O error
     */
    public String readLine(int maxLength) throws IOException {
        checkOpen();
        if (maxLength < 1) throw new IllegalArgumentException("maxLength must be >= 1");

        // Grow the buffer as the line is read rather than pre-allocating maxLength,
        // so a short line costs a few bytes instead of a 1 MB allocation per call.
        ByteArrayOutputStream line = new ByteArrayOutputStream(128);
        while (line.size() < maxLength) {
            int b = inputStream.read();
            if (b < 0) {
                return line.size() > 0
                        ? new String(line.toByteArray(), StandardCharsets.UTF_8)
                        : null;
            }
            if (b == '\n') {
                return new String(line.toByteArray(), StandardCharsets.UTF_8);
            }
            line.write(b);
        }
        return new String(line.toByteArray(), StandardCharsets.UTF_8);
    }

    /**
     * Reads all remaining data until the peer closes the stream (EOF).
     *
     * @return all bytes read
     * @throws IOException on I/O error
     */
    public byte[] readAll() throws IOException {
        return readAll(DEFAULT_CHUNK_SIZE);
    }

    /**
     * Reads all remaining data with a custom buffer size.
     *
     * @param chunkSize read buffer size
     * @return all bytes read
     * @throws IOException on I/O error
     */
    public byte[] readAll(int chunkSize) throws IOException {
        checkOpen();
        validateChunkSize(chunkSize);
        java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[chunkSize];
        int n;
        while ((n = inputStream.read(buf, 0, chunkSize)) > 0) {
            bos.write(buf, 0, n);
        }
        return bos.toByteArray();
    }

    // ── Convenience write methods ─────────────────────────────────────

    /**
     * Writes raw bytes to the stream.
     *
     * @param data bytes to send
     * @return number of bytes written
     * @throws IOException on I/O error
     */
    public int write(byte[] data) throws IOException {
        checkOpen();
        if (data == null) throw new IllegalArgumentException("data must not be null");
        if (data.length == 0) return 0;
        outputStream.write(data, 0, data.length);
        return data.length;
    }

    /**
     * Encodes a string as UTF-8 and writes it to the stream.
     *
     * @param text the string to send
     * @return number of bytes written
     * @throws IOException on I/O error
     */
    public int writeString(String text) throws IOException {
        checkOpen();
        if (text == null) throw new IllegalArgumentException("text must not be null");
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        return write(bytes);
    }

    // ── File transfer helpers ─────────────────────────────────────────

    /**
     * Streams a local file into the TauSync channel.
     *
     * @param path path to the file to send
     * @return total bytes written
     * @throws IOException on I/O error or file not found
     */
    public long writeFile(String path) throws IOException {
        return writeFile(path, DEFAULT_CHUNK_SIZE);
    }

    /**
     * Streams a local file with a custom chunk size.
     *
     * @param path      path to the file to send
     * @param chunkSize size of each write chunk
     * @return total bytes written
     * @throws IOException on I/O error
     */
    public long writeFile(String path, int chunkSize) throws IOException {
        checkOpen();
        validateChunkSize(chunkSize);
        if (path == null) throw new IllegalArgumentException("path must not be null");
        File file = new File(path);
        if (!file.isFile()) throw new IOException("File not found: " + path);

        long total = 0;
        byte[] buf = new byte[chunkSize];
        try (FileInputStream fis = new FileInputStream(file)) {
            int n;
            while ((n = fis.read(buf, 0, chunkSize)) > 0) {
                outputStream.write(buf, 0, n);
                total += n;
            }
        }
        return total;
    }

    /**
     * Receives exactly {@code length} bytes and writes them to a file.
     *
     * @param path   destination file path
     * @param length exact number of bytes to receive
     * @return bytes written to disk
     * @throws IOException  on I/O error
     * @throws EOFException if EOF before all bytes are received
     */
    public long readToFile(String path, long length) throws IOException {
        return readToFile(path, length, DEFAULT_CHUNK_SIZE);
    }

    /**
     * Receives exactly {@code length} bytes to a file with custom chunk size.
     *
     * @param path      destination file path
     * @param length    exact number of bytes to receive
     * @param chunkSize read buffer size
     * @return bytes written to disk
     * @throws IOException on I/O error
     */
    public long readToFile(String path, long length, int chunkSize) throws IOException {
        checkOpen();
        validateChunkSize(chunkSize);
        if (path == null) throw new IllegalArgumentException("path must not be null");
        if (length < 0) throw new IllegalArgumentException("length must be >= 0");

        long total = 0;
        byte[] buf = new byte[chunkSize];
        try (FileOutputStream fos = new FileOutputStream(path)) {
            while (total < length) {
                int toRead = (int) Math.min(chunkSize, length - total);
                int n = inputStream.read(buf, 0, toRead);
                if (n < 0) {
                    throw new EOFException(
                            "Expected " + length + " bytes, got " + total + " before EOF");
                }
                fos.write(buf, 0, n);
                total += n;
            }
        }
        return total;
    }

    // ── Lifecycle ─────────────────────────────────────────────────────

    /**
     * Sends FIN to the peer and releases the local ID.
     * Idempotent — safe to call multiple times.
     */
    @Override
    public void close() throws IOException {
        if (closed) return;
        closed = true;

        if (!finSent) {
            finSent = true;
            connectionManager.completeStream(localId);
        }

        try {
            inputStream.close();
        } catch (IOException ignored) {}
    }

    // ── Internals ─────────────────────────────────────────────────────

    private void checkOpen() throws IOException {
        if (closed) throw new IOException("Stream is closed");
    }

    private static void validateChunkSize(int chunkSize) {
        if (chunkSize < 1 || chunkSize > MAX_CHUNK_SIZE) {
            throw new IllegalArgumentException(
                    "chunkSize must be 1.." + MAX_CHUNK_SIZE + ", got " + chunkSize);
        }
    }

    /**
     * Internal OutputStream that delegates writes to ConnectionManager.sendStreamData.
     */
    private final class TauSyncOutputStream extends OutputStream {

        @Override
        public void write(int b) throws IOException {
            write(new byte[]{(byte) b}, 0, 1);
        }

        @Override
        public void write(byte[] buffer, int offset, int count) throws IOException {
            if (closed) throw new IOException("Stream closed");
            if (finSent) return;
            if (buffer == null) throw new NullPointerException("buffer");
            if (offset < 0 || count < 0 || offset + count > buffer.length) {
                throw new IndexOutOfBoundsException();
            }
            if (count == 0) return;

            connectionManager.sendStreamData(localId, buffer, offset, count);
        }

        @Override
        public void flush() {}

        @Override
        public void close() throws IOException {
            TauSyncStream.this.close();
        }
    }
}
