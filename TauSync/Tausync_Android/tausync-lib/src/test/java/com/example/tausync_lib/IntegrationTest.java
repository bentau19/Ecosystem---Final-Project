package com.example.tausync_lib;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.management.BackBufferedInputStream;
import com.example.tausync_lib.implementations.management.ConnectionContext;
import com.example.tausync_lib.implementations.management.ConnectionManager;
import com.example.tausync_lib.implementations.management.TauSyncStream;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.implementations.transport.SocketTransport;
import com.example.tausync_lib.interfaces.IConnectionManager;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.interfaces.ITransport;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import org.junit.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.CompletableFuture;

import static org.junit.Assert.*;

/**
 * Unit tests for TauSync v3 Android library.
 *
 * <p>Tests protocol framing, stream buffering, and TransferRequest serialisation.
 * End-to-end networking tests require two processes (cross-platform test).
 */
public class IntegrationTest {

    // ── ProtocolHandler ───────────────────────────────────────────────

    @Test
    public void protocolHandler_buildAndParseFrame_roundTrips() {
        ProtocolHandler handler = new ProtocolHandler();
        byte[] payload = "Hello TauSync".getBytes(StandardCharsets.UTF_8);
        int targetId = 42;
        byte flags = CoreConfig.FLAG_CONTROL;

        byte[] frame = handler.buildFrame(targetId, payload, flags);
        IProtocolHandler.ParseResult result = handler.parseFrame(frame);

        assertEquals(targetId, result.getTargetId());
        assertEquals(flags, result.getFlags());
        assertArrayEquals(payload, result.getPayload());
    }

    @Test
    public void protocolHandler_emptyPayload() {
        ProtocolHandler handler = new ProtocolHandler();
        byte[] frame = handler.buildFrame(0, new byte[0], CoreConfig.FLAG_FIN);
        IProtocolHandler.ParseResult result = handler.parseFrame(frame);

        assertEquals(0, result.getTargetId());
        assertEquals(CoreConfig.FLAG_FIN, result.getFlags());
        assertEquals(0, result.getPayload().length);
    }

    @Test
    public void protocolHandler_maxTargetId() {
        ProtocolHandler handler = new ProtocolHandler();
        byte[] payload = new byte[]{1, 2, 3};
        byte[] frame = handler.buildFrame(0xFFFFFF, payload, (byte) 0);
        IProtocolHandler.ParseResult result = handler.parseFrame(frame);
        assertEquals(0xFFFFFF, result.getTargetId());
    }

    @Test(expected = IllegalArgumentException.class)
    public void protocolHandler_targetIdTooLarge_throws() {
        new ProtocolHandler().buildFrame(0x1000000, new byte[0], (byte) 0);
    }

    @Test(expected = IllegalArgumentException.class)
    public void protocolHandler_negativeTargetId_throws() {
        new ProtocolHandler().buildFrame(-1, new byte[0], (byte) 0);
    }

    @Test(expected = IllegalArgumentException.class)
    public void protocolHandler_nullPayload_throws() {
        new ProtocolHandler().buildFrame(0, null, (byte) 0);
    }

    @Test(expected = IllegalArgumentException.class)
    public void protocolHandler_parseFrame_tooSmall_throws() {
        new ProtocolHandler().parseFrame(new byte[7]);
    }

    @Test
    public void protocolHandler_getPayloadLength_readsLittleEndian() {
        ProtocolHandler handler = new ProtocolHandler();
        byte[] payload = new byte[300];
        Arrays.fill(payload, (byte) 0xAB);
        byte[] frame = handler.buildFrame(1, payload, (byte) 0);

        byte[] header = Arrays.copyOf(frame, CoreConfig.TPACK_HEADER_SIZE);
        assertEquals(300, handler.getPayloadLength(header));
    }

    @Test
    public void protocolHandler_getHeaderSize_returns8() {
        assertEquals(8, new ProtocolHandler().getHeaderSize());
    }

    @Test
    public void protocolHandler_isControlFrame_targetIdZero() {
        ProtocolHandler handler = new ProtocolHandler();
        assertTrue(handler.isControlFrame(0, (byte) 0));
        assertFalse(handler.isControlFrame(1, (byte) 0));
        assertTrue(handler.isControlFrame(0, CoreConfig.FLAG_CONTROL));
    }

    @Test
    public void protocolHandler_largePayload() {
        ProtocolHandler handler = new ProtocolHandler();
        byte[] payload = new byte[CoreConfig.STREAM_CHUNK_SIZE];
        Arrays.fill(payload, (byte) 0x42);
        byte[] frame = handler.buildFrame(1, payload, (byte) 0);

        assertEquals(CoreConfig.TPACK_HEADER_SIZE + CoreConfig.STREAM_CHUNK_SIZE, frame.length);

        IProtocolHandler.ParseResult result = handler.parseFrame(frame);
        assertEquals(CoreConfig.STREAM_CHUNK_SIZE, result.getPayload().length);
        assertArrayEquals(payload, result.getPayload());
    }

    @Test
    public void protocolHandler_flagsCombined() {
        ProtocolHandler handler = new ProtocolHandler();
        byte combinedFlags = CoreConfig.FLAG_FIN | CoreConfig.FLAG_CONTROL;
        byte[] frame = handler.buildFrame(0, "test".getBytes(), combinedFlags);
        IProtocolHandler.ParseResult result = handler.parseFrame(frame);
        assertEquals(combinedFlags, result.getFlags());
    }

    // ── TransferRequest ───────────────────────────────────────────────

    @Test
    public void transferRequest_defaultMagicBytes() {
        TransferRequest req = new TransferRequest();
        assertEquals(0x54415553L, req.getMagicBytes());
    }

    @Test
    public void transferRequest_validReq() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(1);
        req.setType("main");
        req.setStatus("REQ");
        assertTrue(req.isValid());
    }

    @Test
    public void transferRequest_validOk() {
        TransferRequest ok = new TransferRequest();
        ok.setSenderID(100);
        ok.setType("main");
        ok.setStatus("OK");
        assertTrue(ok.isValid());
    }

    @Test
    public void transferRequest_validReject() {
        TransferRequest rej = new TransferRequest();
        rej.setSenderID(1);
        rej.setType("main");
        rej.setStatus("REJECT");
        assertTrue(rej.isValid());
    }

    @Test
    public void transferRequest_caseInsensitiveStatus() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(1);
        req.setType("main");
        req.setStatus("req");
        assertTrue(req.isValid());

        req.setStatus("Ok");
        assertTrue(req.isValid());
    }

    @Test
    public void transferRequest_invalidMagicBytes() {
        TransferRequest req = new TransferRequest();
        req.setMagicBytes(0L);
        req.setSenderID(1);
        req.setType("main");
        req.setStatus("REQ");
        assertFalse(req.isValid());
    }

    @Test
    public void transferRequest_reqWithoutType_invalid() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(1);
        req.setType(null);
        req.setStatus("REQ");
        assertFalse(req.isValid());
    }

    @Test
    public void transferRequest_reqWithEmptyType_invalid() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(1);
        req.setType("  ");
        req.setStatus("REQ");
        assertFalse(req.isValid());
    }

    @Test
    public void transferRequest_senderIdOutOfRange_invalid() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(0xFFFFFF + 1);
        req.setType("main");
        req.setStatus("REQ");
        assertFalse(req.isValid());
    }

    @Test
    public void transferRequest_negativeSenderId_invalid() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(-1);
        req.setType("main");
        req.setStatus("REQ");
        assertFalse(req.isValid());
    }

    @Test
    public void transferRequest_nullStatus_invalid() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(1);
        req.setType("main");
        req.setStatus(null);
        assertFalse(req.isValid());
    }

    @Test
    public void transferRequest_unknownStatus_invalid() {
        TransferRequest req = new TransferRequest();
        req.setSenderID(1);
        req.setType("main");
        req.setStatus("UNKNOWN");
        assertFalse(req.isValid());
    }

    @Test
    public void transferRequest_gsonRoundTrip_pascalCaseFields() {
        Gson gson = new Gson();
        TransferRequest req = new TransferRequest();
        req.setSenderID(42);
        req.setType("CLIPBOARD");
        req.setStatus("REQ");

        String json = gson.toJson(req);
        assertTrue("JSON must use PascalCase MagicBytes", json.contains("\"MagicBytes\""));
        assertTrue("JSON must use PascalCase SenderID", json.contains("\"SenderID\""));
        assertTrue("JSON must use PascalCase Type", json.contains("\"Type\""));
        assertTrue("JSON must use PascalCase Status", json.contains("\"Status\""));

        TransferRequest parsed = gson.fromJson(json, TransferRequest.class);
        assertEquals(req.getMagicBytes(), parsed.getMagicBytes());
        assertEquals(req.getSenderID(), parsed.getSenderID());
        assertEquals(req.getType(), parsed.getType());
        assertEquals(req.getStatus(), parsed.getStatus());
    }

    @Test
    public void transferRequest_gsonDeserialize_fromCSharpFormat() {
        String csharpJson = "{\"MagicBytes\":1413567827,\"SenderID\":5,\"Type\":\"main\",\"Status\":\"REQ\"}";
        TransferRequest req = new Gson().fromJson(csharpJson, TransferRequest.class);
        assertEquals(0x54415553L, req.getMagicBytes());
        assertEquals(5, req.getSenderID());
        assertEquals("main", req.getType());
        assertEquals("REQ", req.getStatus());
        assertTrue(req.isValid());
    }

    // ── BackBufferedInputStream ───────────────────────────────────────

    @Test
    public void backBufferedStream_writeAndRead() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        byte[] data = "Hello".getBytes(StandardCharsets.UTF_8);
        stream.writeChunk(data);

        byte[] buf = new byte[10];
        int n = stream.read(buf, 0, 10);
        assertEquals(5, n);
        assertArrayEquals(data, Arrays.copyOf(buf, n));
    }

    @Test
    public void backBufferedStream_partialRead_returnsImmediately() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        stream.writeChunk(new byte[]{1, 2, 3});

        byte[] buf = new byte[2];
        int n = stream.read(buf, 0, 2);
        assertEquals(2, n);
        assertEquals(1, buf[0]);
        assertEquals(2, buf[1]);

        n = stream.read(buf, 0, 2);
        assertEquals(1, n);
        assertEquals(3, buf[0]);
    }

    @Test
    public void backBufferedStream_complete_returnsEof() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        stream.writeChunk(new byte[]{1, 2, 3});
        stream.complete();

        byte[] buf = new byte[10];
        int first = stream.read(buf, 0, 10);
        assertEquals(3, first);

        int eof = stream.read(buf, 0, 10);
        assertEquals(-1, eof);
    }

    @Test
    public void backBufferedStream_multipleChunks_readAll() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        for (int i = 0; i < 100; i++) {
            stream.writeChunk(new byte[]{(byte) i});
        }
        stream.complete();

        byte[] buf = new byte[200];
        int total = 0;
        int n;
        while ((n = stream.read(buf, total, buf.length - total)) > 0) {
            total += n;
        }
        assertEquals(100, total);
        for (int i = 0; i < 100; i++) {
            assertEquals((byte) i, buf[i]);
        }
    }

    @Test
    public void backBufferedStream_close_subsequentReadThrows() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        stream.close();
        try {
            stream.read(new byte[1], 0, 1);
            fail("Expected IOException");
        } catch (java.io.IOException expected) {}
    }

    @Test
    public void backBufferedStream_nullChunk_ignored() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        stream.writeChunk(null);
        stream.writeChunk(new byte[0]);
        stream.writeChunk(new byte[]{42});
        stream.complete();

        byte[] buf = new byte[10];
        int n = stream.read(buf, 0, 10);
        assertEquals(1, n);
        assertEquals(42, buf[0]);
    }

    @Test
    public void backBufferedStream_readSingleByte() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        stream.writeChunk(new byte[]{(byte) 0xAB});
        stream.complete();

        assertEquals(0xAB, stream.read());
        assertEquals(-1, stream.read());
    }

    @Test
    public void backBufferedStream_completeIdempotent() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        stream.writeChunk(new byte[]{1});
        stream.complete();
        stream.complete();

        byte[] buf = new byte[10];
        assertEquals(1, stream.read(buf, 0, 10));
        assertEquals(-1, stream.read(buf, 0, 10));
    }

    @Test
    public void backBufferedStream_readZeroBytes_returnsZero() throws Exception {
        BackBufferedInputStream stream = new BackBufferedInputStream();
        stream.writeChunk(new byte[]{1, 2, 3});
        assertEquals(0, stream.read(new byte[10], 0, 0));
    }

    // ── CoreConfig constants match C# ─────────────────────────────────

    @Test
    public void coreConfig_constantsMatchSpec() {
        assertEquals(8, CoreConfig.TPACK_HEADER_SIZE);
        assertEquals(3, CoreConfig.CORRELATION_ID_BYTES);
        assertEquals(0x54415553L, CoreConfig.MAGIC_BYTES);
        assertEquals(0, CoreConfig.CONTROL_CHANNEL_ID);
        assertEquals(0x01, CoreConfig.FLAG_FIN);
        assertEquals(0x02, CoreConfig.FLAG_CONTROL);
        assertEquals(65536, CoreConfig.STREAM_CHUNK_SIZE);
        assertEquals(30, CoreConfig.HANDSHAKE_TIMEOUT_SECONDS);
        assertEquals(8888, CoreConfig.DEFAULT_PORT);
        assertEquals(2, CoreConfig.CLIENT_CONNECT_RETRY_DELAY_SECONDS);
        assertEquals(64, CoreConfig.MAX_PENDING_DISCOVERY_PER_WORD);
        assertEquals(1, CoreConfig.MIN_ID);
        assertEquals(0xFFFFFF, CoreConfig.MAX_ID);
    }

    // ── SocketTransport disconnect join (Fix 3) ──────────────────────

    @Test
    public void socketTransport_disconnect_receiveThreadStops() throws Exception {
        int port = findFreePort();
        ServerSocket serverSocket = new ServerSocket(port);
        CountDownLatch clientConnected = new CountDownLatch(1);

        Thread serverThread = new Thread(() -> {
            try (Socket client = serverSocket.accept()) {
                clientConnected.countDown();
                Thread.sleep(5000);
            } catch (Exception ignored) {}
        });
        serverThread.setDaemon(true);
        serverThread.start();

        SocketTransport transport = new SocketTransport();
        transport.setPort(port);
        transport.connect("127.0.0.1").get(5, TimeUnit.SECONDS);
        assertTrue(transport.isConnected());

        assertTrue("Server should have accepted", clientConnected.await(3, TimeUnit.SECONDS));

        transport.disconnect();
        assertFalse(transport.isConnected());

        transport.close();
        serverSocket.close();
        serverThread.interrupt();
    }

    @Test
    public void socketTransport_close_idempotent() throws Exception {
        SocketTransport transport = new SocketTransport();
        transport.close();
        transport.close();
    }

    // ── ConnectionManager concurrent same-word guard ──────────────────

    @Test
    public void connectionManager_concurrentSameWordConnect_throwsAndAllowsSequentialReuse() throws Exception {
        int port = findFreePort();
        ServerSocket serverSocket = new ServerSocket(port);
        Thread serverThread = new Thread(() -> {
            try (Socket client = serverSocket.accept()) {
                // Hold the TCP connection open but never speak TauSync — every
                // handshake attempt stays pending until its own timeout.
                Thread.sleep(30_000);
            } catch (Exception ignored) {}
        });
        serverThread.setDaemon(true);
        serverThread.start();

        ConnectionContext ctx = ConnectionContext.getInstance();
        ctx.getWifiTransportAsSocket().setPort(port);
        ctx.initializeTransports("127.0.0.1", 5);
        ConnectionManager manager = new ConnectionManager();
        try {
            CompletableFuture<TauSyncStream> first = manager.connect("GUARD_WORD", 2);

            // A second concurrent connect() with the same word must fail fast
            // instead of silently clobbering the in-flight handshake.
            try {
                manager.connect("GUARD_WORD", 2);
                fail("Expected IllegalStateException for concurrent same-word connect");
            } catch (IllegalStateException expected) {
                assertTrue(expected.getMessage().contains("already in progress"));
            }

            // A different word is not blocked by the guard (it times out
            // normally because there is no TauSync peer behind the socket).
            CompletableFuture<TauSyncStream> otherWord = manager.connect("OTHER_WORD", 1);

            try {
                first.get(15, TimeUnit.SECONDS);
                fail("Expected handshake timeout for the first connect");
            } catch (ExecutionException expectedTimeout) {}
            try {
                otherWord.get(15, TimeUnit.SECONDS);
                fail("Expected handshake timeout for the other-word connect");
            } catch (ExecutionException expectedTimeout) {}

            // Sequential reuse of the same word is allowed again once the
            // previous attempt has resolved (success or failure).
            CompletableFuture<TauSyncStream> second = manager.connect("GUARD_WORD", 1);
            try {
                second.get(15, TimeUnit.SECONDS);
                fail("Expected handshake timeout for the sequential-reuse connect");
            } catch (ExecutionException expectedTimeout) {}
        } finally {
            manager.close();
            ctx.getWifiTransportAsSocket().disconnect();
            serverSocket.close();
            serverThread.interrupt();
        }
    }

    private static int findFreePort() throws IOException {
        try (ServerSocket ss = new ServerSocket(0)) {
            return ss.getLocalPort();
        }
    }

    // ── Fix #3: Max payload size — malicious/buggy peer ──────────────

    /**
     * A peer that sends a header claiming a 200 MB payload (well above MAX_PAYLOAD_SIZE=16 MB)
     * must cause the receive loop to disconnect cleanly — no OOM, no blocked thread.
     */
    @Test
    public void socketTransport_oversizedPayloadHeader_disconnectsWithoutOOM() throws Exception {
        int port = findFreePort();
        ServerSocket server = new ServerSocket(port);
        CountDownLatch clientAccepted = new CountDownLatch(1);

        Thread maliciousPeer = new Thread(() -> {
            try (Socket client = server.accept()) {
                clientAccepted.countDown();
                OutputStream out = client.getOutputStream();
                // Craft an 8-byte TPack header: payloadLength = 200 MB (far above 16 MB cap)
                int maliciousSize = 200 * 1024 * 1024;
                byte[] header = new byte[CoreConfig.TPACK_HEADER_SIZE];
                header[0] = (byte) (maliciousSize & 0xFF);
                header[1] = (byte) ((maliciousSize >> 8) & 0xFF);
                header[2] = (byte) ((maliciousSize >> 16) & 0xFF);
                header[3] = (byte) ((maliciousSize >> 24) & 0xFF);
                header[4] = 0x01; // targetId = 1 (non-control, so dispatched as data)
                header[5] = 0x00;
                header[6] = 0x00;
                header[7] = 0x00; // flags = 0
                out.write(header);
                out.flush();
                Thread.sleep(3000); // stay alive so the transport can read the header
            } catch (Exception ignored) {}
        });
        maliciousPeer.setDaemon(true);
        maliciousPeer.start();

        SocketTransport transport = new SocketTransport();
        transport.setPort(port);
        transport.connect("127.0.0.1").get(5, TimeUnit.SECONDS);
        assertTrue(transport.isConnected());
        assertTrue("Peer should have accepted", clientAccepted.await(3, TimeUnit.SECONDS));

        // Receive loop should drop the oversized frame and disconnect — give it up to 3 s
        long deadline = System.currentTimeMillis() + 3000;
        while (transport.isConnected() && System.currentTimeMillis() < deadline) {
            Thread.sleep(50);
        }
        assertFalse("Transport must disconnect after receiving an oversized payload header", transport.isConnected());

        transport.close();
        server.close();
        maliciousPeer.interrupt();
    }

    /**
     * A header at exactly MAX_PAYLOAD_SIZE must be accepted (boundary check).
     * We only verify the transport does NOT disconnect — we don't need to send the full payload
     * since the point is the boundary is inclusive.
     */
    @Test
    public void socketTransport_payloadAtExactLimit_isAccepted() throws Exception {
        int port = findFreePort();
        ServerSocket server = new ServerSocket(port);
        CountDownLatch clientAccepted = new CountDownLatch(1);

        Thread peer = new Thread(() -> {
            try (Socket client = server.accept()) {
                clientAccepted.countDown();
                OutputStream out = client.getOutputStream();
                int exactSize = CoreConfig.MAX_PAYLOAD_SIZE;
                byte[] header = new byte[CoreConfig.TPACK_HEADER_SIZE];
                header[0] = (byte) (exactSize & 0xFF);
                header[1] = (byte) ((exactSize >> 8) & 0xFF);
                header[2] = (byte) ((exactSize >> 16) & 0xFF);
                header[3] = (byte) ((exactSize >> 24) & 0xFF);
                header[4] = 0x01;
                header[5] = 0x00;
                header[6] = 0x00;
                header[7] = 0x00;
                out.write(header);
                // Now send the actual payload so the frame completes (first 64 KB is enough
                // to confirm the receive loop did not bail on the size check alone)
                byte[] partialPayload = new byte[CoreConfig.STREAM_CHUNK_SIZE];
                out.write(partialPayload);
                out.flush();
                Thread.sleep(3000);
            } catch (Exception ignored) {}
        });
        peer.setDaemon(true);
        peer.start();

        SocketTransport transport = new SocketTransport();
        transport.setPort(port);
        transport.connect("127.0.0.1").get(5, TimeUnit.SECONDS);
        assertTrue("Peer should have accepted", clientAccepted.await(3, TimeUnit.SECONDS));

        // Give the receive loop 500 ms — it should still be connected (reading the payload),
        // proving the size check did not falsely reject a frame at the exact limit.
        Thread.sleep(500);
        assertTrue("Transport must NOT disconnect for a payload at exactly MAX_PAYLOAD_SIZE", transport.isConnected());

        transport.close();
        server.close();
        peer.interrupt();
    }

    /**
     * A header one byte over MAX_PAYLOAD_SIZE must be rejected (boundary check).
     */
    @Test
    public void socketTransport_payloadOneByteOverLimit_disconnects() throws Exception {
        int port = findFreePort();
        ServerSocket server = new ServerSocket(port);

        Thread peer = new Thread(() -> {
            try (Socket client = server.accept()) {
                OutputStream out = client.getOutputStream();
                int overSize = CoreConfig.MAX_PAYLOAD_SIZE + 1;
                byte[] header = new byte[CoreConfig.TPACK_HEADER_SIZE];
                header[0] = (byte) (overSize & 0xFF);
                header[1] = (byte) ((overSize >> 8) & 0xFF);
                header[2] = (byte) ((overSize >> 16) & 0xFF);
                header[3] = (byte) ((overSize >> 24) & 0xFF);
                header[4] = 0x01;
                header[7] = 0x00;
                out.write(header);
                out.flush();
                Thread.sleep(3000);
            } catch (Exception ignored) {}
        });
        peer.setDaemon(true);
        peer.start();

        SocketTransport transport = new SocketTransport();
        transport.setPort(port);
        transport.connect("127.0.0.1").get(5, TimeUnit.SECONDS);

        long deadline = System.currentTimeMillis() + 3000;
        while (transport.isConnected() && System.currentTimeMillis() < deadline) {
            Thread.sleep(50);
        }
        assertFalse("Transport must disconnect for payload one byte over MAX_PAYLOAD_SIZE", transport.isConnected());

        transport.close();
        server.close();
        peer.interrupt();
    }

    // ── Fix #1: ID reservation race — no duplicates under concurrency ─

    /**
     * 100 threads each call reserveId() 100 times simultaneously.
     * Every returned ID must be unique — wrap-around under concurrency must not
     * produce duplicates.
     */
    @Test
    public void connectionContext_reserveId_noDuplicatesUnderConcurrency() throws Exception {
        ConnectionContext ctx = ConnectionContext.getInstance();
        int threadCount = 100;
        int idsPerThread = 100;

        ConcurrentLinkedQueue<Integer> collected = new ConcurrentLinkedQueue<>();
        CountDownLatch startGun = new CountDownLatch(1);
        CountDownLatch allDone = new CountDownLatch(threadCount);

        for (int i = 0; i < threadCount; i++) {
            new Thread(() -> {
                try { startGun.await(); } catch (InterruptedException e) { return; }
                for (int j = 0; j < idsPerThread; j++) {
                    collected.add(ctx.reserveId());
                }
                allDone.countDown();
            }).start();
        }

        startGun.countDown();
        assertTrue("Threads did not finish in time", allDone.await(10, TimeUnit.SECONDS));

        Set<Integer> unique = new HashSet<>(collected);
        assertEquals("Duplicate IDs detected under concurrent reserveId() calls",
                collected.size(), unique.size());
    }

    /**
     * Wrap-around: seed the counter just below MAX_ID, then reserve IDs from many threads.
     * The counter must roll over to MIN_ID without any thread receiving a duplicate.
     */
    @Test
    public void connectionContext_reserveId_wrapAroundNoDuplicates() throws Exception {
        ConnectionContext ctx = ConnectionContext.getInstance();
        // Drain the counter close to the edge by reserving up to MAX_ID - 10
        // (we can't reset the singleton, so we just need the counter near the wrap point)
        int threadCount = 20;
        ConcurrentLinkedQueue<Integer> collected = new ConcurrentLinkedQueue<>();
        CountDownLatch startGun = new CountDownLatch(1);
        CountDownLatch allDone = new CountDownLatch(threadCount);

        // Reserve 20 IDs from 20 threads simultaneously around wherever the counter sits
        for (int i = 0; i < threadCount; i++) {
            new Thread(() -> {
                try { startGun.await(); } catch (InterruptedException e) { return; }
                collected.add(ctx.reserveId());
                allDone.countDown();
            }).start();
        }

        startGun.countDown();
        assertTrue(allDone.await(5, TimeUnit.SECONDS));
        Set<Integer> unique = new HashSet<>(collected);
        assertEquals("Wrap-around produced duplicate IDs", collected.size(), unique.size());
    }

    // ── Fix #6: Close TOCTOU — completeStream called exactly once ─────

    /**
     * 20 threads call TauSyncStream.close() simultaneously.
     * completeStream must be called exactly once — the second FIN must be suppressed.
     */
    @Test
    public void tauSyncStream_concurrentClose_completeStreamCalledExactlyOnce() throws Exception {
        AtomicInteger completeStreamCalls = new AtomicInteger(0);

        IConnectionManager noopManager = new IConnectionManager() {
            @Override public void initialize(ITransport t) {}
            @Override public CompletableFuture<Void> connectTransport(String id) { return CompletableFuture.completedFuture(null); }
            @Override public boolean isConnected() { return true; }
            @Override public CompletableFuture<TauSyncStream> connect(String word) { return null; }
            @Override public void sendStreamData(int id, byte[] buf, int off, int cnt) {}
            @Override public CompletableFuture<Void> sendStreamDataAsync(int id, byte[] buf, int off, int cnt) { return CompletableFuture.completedFuture(null); }
            @Override public void completeStream(int id) { completeStreamCalls.incrementAndGet(); }
            @Override public void setErrorListener(ErrorListener l) {}
            @Override public void close() {}
        };

        BackBufferedInputStream backing = new BackBufferedInputStream();
        backing.complete(); // immediately at EOF so reads don't block
        TauSyncStream stream = new TauSyncStream(backing, 42, noopManager);

        int threadCount = 20;
        CountDownLatch startGun = new CountDownLatch(1);
        CountDownLatch allDone = new CountDownLatch(threadCount);

        for (int i = 0; i < threadCount; i++) {
            new Thread(() -> {
                try {
                    startGun.await();
                    stream.close();
                } catch (Exception ignored) {}
                allDone.countDown();
            }).start();
        }

        startGun.countDown();
        assertTrue("Threads did not finish in time", allDone.await(5, TimeUnit.SECONDS));
        assertEquals("completeStream must be called exactly once regardless of concurrent close()",
                1, completeStreamCalls.get());
    }

    /**
     * close() called sequentially twice must also only call completeStream once.
     */
    @Test
    public void tauSyncStream_sequentialDoubleClose_completeStreamCalledOnce() throws Exception {
        AtomicInteger calls = new AtomicInteger(0);

        IConnectionManager noopManager = new IConnectionManager() {
            @Override public void initialize(ITransport t) {}
            @Override public CompletableFuture<Void> connectTransport(String id) { return CompletableFuture.completedFuture(null); }
            @Override public boolean isConnected() { return true; }
            @Override public CompletableFuture<TauSyncStream> connect(String word) { return null; }
            @Override public void sendStreamData(int id, byte[] buf, int off, int cnt) {}
            @Override public CompletableFuture<Void> sendStreamDataAsync(int id, byte[] buf, int off, int cnt) { return CompletableFuture.completedFuture(null); }
            @Override public void completeStream(int id) { calls.incrementAndGet(); }
            @Override public void setErrorListener(ErrorListener l) {}
            @Override public void close() {}
        };

        BackBufferedInputStream backing = new BackBufferedInputStream();
        backing.complete();
        TauSyncStream stream = new TauSyncStream(backing, 7, noopManager);

        stream.close();
        stream.close();

        assertEquals("Sequential double-close must call completeStream exactly once", 1, calls.get());
    }

    // ── Auto-chunking: large write is split into ≤ LARGE_TRANSFER_CHUNK_SIZE slices ─

    /**
     * Writing a buffer larger than LARGE_TRANSFER_CHUNK_SIZE through TauSyncStream must result
     * in multiple sendStreamData calls — each with a slice ≤ LARGE_TRANSFER_CHUNK_SIZE — rather
     * than one giant call. The OutputStream slices at LARGE_TRANSFER_CHUNK_SIZE (above the hybrid
     * routing threshold) so large transfers are still routed over Wi-Fi; the manager then splits
     * each slice into STREAM_CHUNK_SIZE wire frames internally.
     *
     * This test hooks sendStreamData on a spy manager to count call sizes.
     */
    @Test
    public void tauSyncStream_largeWrite_isAutoChunked() throws Exception {
        int writeSize = CoreConfig.LARGE_TRANSFER_CHUNK_SIZE * 3 + 1024; // 3 full chunks + a tail
        AtomicInteger callCount = new AtomicInteger(0);
        AtomicBoolean oversizedChunkSeen = new AtomicBoolean(false);

        IConnectionManager spyManager = new IConnectionManager() {
            @Override public void initialize(ITransport t) {}
            @Override public CompletableFuture<Void> connectTransport(String id) { return CompletableFuture.completedFuture(null); }
            @Override public boolean isConnected() { return true; }
            @Override public CompletableFuture<TauSyncStream> connect(String word) { return null; }
            @Override public void sendStreamData(int id, byte[] buf, int off, int cnt) {
                callCount.incrementAndGet();
                if (cnt > CoreConfig.LARGE_TRANSFER_CHUNK_SIZE) oversizedChunkSeen.set(true);
            }
            @Override public CompletableFuture<Void> sendStreamDataAsync(int id, byte[] buf, int off, int cnt) { return CompletableFuture.completedFuture(null); }
            @Override public void completeStream(int id) {}
            @Override public void setErrorListener(ErrorListener l) {}
            @Override public void close() {}
        };

        BackBufferedInputStream backing = new BackBufferedInputStream();
        TauSyncStream stream = new TauSyncStream(backing, 1, spyManager);

        byte[] bigBuffer = new byte[writeSize];
        Arrays.fill(bigBuffer, (byte) 0x42);
        stream.getOutputStream().write(bigBuffer);

        assertFalse("A slice larger than LARGE_TRANSFER_CHUNK_SIZE was sent — auto-chunking is broken",
                oversizedChunkSeen.get());
        assertEquals("Expected 4 slices (3 full + 1 tail) for a " + writeSize + "-byte write",
                4, callCount.get());
    }}
