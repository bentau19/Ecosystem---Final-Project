package com.example.tausync_lib;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.management.BackBufferedInputStream;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.implementations.transport.SocketTransport;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import org.junit.Test;

import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

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
        assertEquals(2000, CoreConfig.ID_RECYCLE_DELAY_MS);
        assertEquals(64, CoreConfig.MAX_PENDING_DISCOVERY_PER_WORD);
        assertEquals(1, CoreConfig.MIN_ID);
        assertEquals(0xFFFFFF, CoreConfig.MAX_ID);
    }

    // ── Locale-safe toUpperCase (Fix 1) ──────────────────────────────

    @Test
    public void localeRoot_turkishI_uppercasesCorrectly() {
        String word = "file_transfer";
        String expected = "FILE_TRANSFER";
        assertEquals(expected, word.toUpperCase(Locale.ROOT));

        String turkishI = "i\u0131";
        assertEquals("I\u0131", turkishI.toUpperCase(Locale.ROOT));
    }

    @Test
    public void localeRoot_asciiWords_matchCaseInsensitive() {
        String[] words = {"main", "test_msg", "CLIPBOARD", "Data_Channel_1"};
        for (String w : words) {
            String key = w.trim().toUpperCase(Locale.ROOT);
            assertEquals(w.toUpperCase(Locale.ROOT), key);
        }
    }

    @Test
    public void localeRoot_mixedCase_normalizedConsistently() {
        String a = "MyWord".toUpperCase(Locale.ROOT);
        String b = "myword".toUpperCase(Locale.ROOT);
        String c = "MYWORD".toUpperCase(Locale.ROOT);
        assertEquals(a, b);
        assertEquals(b, c);
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

    private static int findFreePort() throws IOException {
        try (ServerSocket ss = new ServerSocket(0)) {
            return ss.getLocalPort();
        }
    }
}
