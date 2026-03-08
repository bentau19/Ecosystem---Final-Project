package com.example.tausync_lib.implementations.management;

import java.io.IOException;
import java.io.InputStream;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * A stream that is written to by the routing handler (incoming TPack payloads) and read from by the client.
 * Blocks on read() when no data until more data is written or the stream is completed (FIN).
 * Matches C# BackBufferedStream.
 */
public final class BackBufferedInputStream extends InputStream {

    private final BlockingQueue<byte[]> queue = new LinkedBlockingQueue<>();
    private byte[] currentChunk;
    private int currentOffset;
    private final AtomicBoolean completed = new AtomicBoolean(false);
    private final AtomicBoolean closed = new AtomicBoolean(false);

    /**
     * Appends a payload chunk (called by the registered handler when TPack arrives).
     */
    public void writeChunk(byte[] chunk) {
        if (chunk == null || chunk.length == 0) return;
        if (closed.get() || completed.get()) return;
        queue.offer(chunk);
    }

    /**
     * Marks the stream as complete (FIN received); no more chunks will be written.
     */
    public void complete() {
        completed.set(true);
        queue.offer(new byte[0]); // unblock any waiter
    }

    @Override
    public int read() throws IOException {
        byte[] b = new byte[1];
        int n = read(b, 0, 1);
        return n <= 0 ? -1 : (b[0] & 0xFF);
    }

    @Override
    public int read(byte[] b, int off, int len) throws IOException {
        if (b == null) throw new NullPointerException();
        if (off < 0 || len < 0 || off + len > b.length) throw new IndexOutOfBoundsException();
        if (closed.get()) throw new IOException("Stream closed");

        int totalRead = 0;
        while (len > 0) {
            if (currentChunk != null) {
                int toCopy = Math.min(len, currentChunk.length - currentOffset);
                System.arraycopy(currentChunk, currentOffset, b, off, toCopy);
                off += toCopy;
                len -= toCopy;
                totalRead += toCopy;
                currentOffset += toCopy;
                if (currentOffset >= currentChunk.length) {
                    currentChunk = null;
                }
                continue;
            }

            try {
                byte[] next = queue.take();
                if (next.length == 0 && completed.get()) {
                    return totalRead > 0 ? totalRead : -1;
                }
                if (next.length > 0) {
                    currentChunk = next;
                    currentOffset = 0;
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IOException(e);
            }
        }
        return totalRead;
    }

    @Override
    public void close() throws IOException {
        if (closed.getAndSet(true)) return;
        completed.set(true);
        queue.clear();
        queue.offer(new byte[0]);
    }
}
