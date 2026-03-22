package com.example.tausync_lib.implementations.management;

import java.io.IOException;
import java.io.InputStream;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Producer/consumer buffer that bridges packet-oriented receive to stream-oriented read.
 *
 * <p>Written to by the routing handler (incoming TPack payloads) and read from by the
 * application. Blocks on {@link #read(byte[], int, int)} when no data is available,
 * unblocking when new data arrives or the stream is completed (FIN).
 *
 * <p>Implements standard InputStream partial-read semantics: returns immediately once
 * any bytes have been copied, even if fewer than requested. Matches C# BackBufferedStream.
 */
public final class BackBufferedInputStream extends InputStream {

    private static final byte[] POISON_PILL = new byte[0];

    private final BlockingQueue<byte[]> queue = new LinkedBlockingQueue<>();
    private byte[] currentChunk;
    private int currentOffset;
    private final AtomicBoolean completed = new AtomicBoolean(false);
    private final AtomicBoolean closed = new AtomicBoolean(false);

    /**
     * Enqueues a payload chunk (called by the registered routing handler).
     *
     * @param chunk the payload bytes; null or empty chunks are ignored
     */
    public void writeChunk(byte[] chunk) {
        if (chunk == null || chunk.length == 0) return;
        if (closed.get() || completed.get()) return;
        queue.offer(chunk);
    }

    /**
     * Marks the stream as complete (FIN received). No more chunks will be written.
     * Idempotent — safe to call multiple times.
     */
    public void complete() {
        if (completed.getAndSet(true)) return;
        queue.offer(POISON_PILL);
    }

    @Override
    public int read() throws IOException {
        byte[] single = new byte[1];
        int n = read(single, 0, 1);
        if (n <= 0) return -1;
        return single[0] & 0xFF;
    }

    /**
     * Reads up to {@code len} bytes into the buffer.
     *
     * <p>Partial-read semantics: if any bytes have been copied, returns immediately
     * without blocking for more — even if fewer bytes than requested are available.
     * Only blocks when zero bytes have been read so far and no chunk is available.
     *
     * @return number of bytes read, or -1 on EOF (stream completed and all data consumed)
     */
    @Override
    public int read(byte[] buffer, int off, int len) throws IOException {
        if (buffer == null) throw new NullPointerException("buffer");
        if (off < 0 || len < 0 || off + len > buffer.length) {
            throw new IndexOutOfBoundsException();
        }
        if (closed.get()) throw new IOException("Stream closed");
        if (len == 0) return 0;

        int totalRead = 0;

        while (len > 0) {
            int copied = copyFromCurrentChunk(buffer, off, len);
            if (copied > 0) {
                totalRead += copied;
                off += copied;
                len -= copied;
                if (len == 0) return totalRead;

                if (!tryLoadNextChunkNonBlocking()) {
                    return totalRead;
                }
                continue;
            }

            if (tryLoadNextChunkNonBlocking()) {
                continue;
            }

            if (completed.get() && queue.isEmpty()) {
                return totalRead > 0 ? totalRead : -1;
            }

            if (totalRead > 0) {
                return totalRead;
            }

            try {
                byte[] next = queue.take();
                if (next == POISON_PILL || next.length == 0) {
                    return -1;
                }
                currentChunk = next;
                currentOffset = 0;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IOException("Read interrupted", e);
            }
        }

        return totalRead;
    }

    @Override
    public void close() throws IOException {
        if (closed.getAndSet(true)) return;
        completed.set(true);
        queue.clear();
        queue.offer(POISON_PILL);
    }

    private int copyFromCurrentChunk(byte[] buffer, int off, int len) {
        if (currentChunk == null) return 0;

        int available = currentChunk.length - currentOffset;
        int toCopy = Math.min(len, available);
        System.arraycopy(currentChunk, currentOffset, buffer, off, toCopy);
        currentOffset += toCopy;

        if (currentOffset >= currentChunk.length) {
            currentChunk = null;
            currentOffset = 0;
        }
        return toCopy;
    }

    private boolean tryLoadNextChunkNonBlocking() {
        byte[] next = queue.poll();
        if (next == null) return false;
        if (next == POISON_PILL || next.length == 0) {
            completed.set(true);
            return false;
        }
        currentChunk = next;
        currentOffset = 0;
        return true;
    }
}
