import com.example.tausync_lib.implementations.management.ConnectionContext;
import com.example.tausync_lib.implementations.management.ConnectionManager;
import com.example.tausync_lib.implementations.management.TauSyncStream;

import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.TimeUnit;

/**
 * Cross-platform test client (Java/Android side).
 * Connects to the Python/C# server, exchanges messages and binary data.
 */
public class JavaClient {

    public static void main(String[] args) throws Exception {
        String serverIp = args.length > 0 ? args[0] : "127.0.0.1";
        System.out.println("[client] Connecting to " + serverIp + ":8888 ...");

        ConnectionContext ctx = ConnectionContext.getInstance();
        ctx.initializeTransports(serverIp);
        System.out.println("[client] Transport connected.");

        ConnectionManager mgr = new ConnectionManager();

        testMessageExchange(mgr);
        testBinaryTransfer(mgr);

        System.out.println("\n=== ALL CROSS-PLATFORM TESTS PASSED (Java side) ===");
        Thread.sleep(2000);
        System.exit(0);
    }

    private static void testMessageExchange(ConnectionManager mgr) throws Exception {
        System.out.println("[client] Connecting on 'test_word' ...");
        TauSyncStream stream = mgr.connect("test_word").get(30, TimeUnit.SECONDS);
        System.out.println("[client] Connected on 'test_word'.");

        InputStream in = stream.getInputStream();
        OutputStream out = stream.getOutputStream();

        byte[] buf = new byte[4096];
        StringBuilder sb = new StringBuilder();
        int b;
        while ((b = in.read()) != -1) {
            if (b == '\n') break;
            sb.append((char) b);
        }
        String msg = sb.toString();
        System.out.println("[client] Received: " + msg);
        assert msg.equals("Hello from C# server") :
                "Expected 'Hello from C# server', got '" + msg + "'";

        String reply = "Hello from Java client\n";
        out.write(reply.getBytes(StandardCharsets.UTF_8));
        System.out.println("[client] Sent greeting.");

        stream.close();
        System.out.println("[client] test_word stream closed.");
    }

    private static void testBinaryTransfer(ConnectionManager mgr) throws Exception {
        System.out.println("[client] Connecting on 'binary_test' ...");
        TauSyncStream stream = mgr.connect("binary_test").get(30, TimeUnit.SECONDS);
        System.out.println("[client] Connected on 'binary_test'.");

        InputStream in = stream.getInputStream();
        OutputStream out = stream.getOutputStream();

        byte[] lenBuf = readExactly(in, 4);
        int length = ByteBuffer.wrap(lenBuf).order(ByteOrder.LITTLE_ENDIAN).getInt();
        System.out.println("[client] Expecting " + length + " bytes ...");

        byte[] data = readExactly(in, length);
        String sha = sha256Hex(data);
        System.out.println("[client] Received " + data.length + " bytes, SHA256=" + sha.substring(0, 16) + "...");

        ByteBuffer header = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN);
        header.putInt(data.length);
        out.write(header.array());
        out.write(data);
        System.out.println("[client] Echoed " + data.length + " bytes back.");

        stream.close();
        System.out.println("[client] binary_test stream closed.");
    }

    private static byte[] readExactly(InputStream in, int count) throws Exception {
        byte[] buf = new byte[count];
        int total = 0;
        while (total < count) {
            int n = in.read(buf, total, count - total);
            if (n < 0) throw new RuntimeException("EOF after " + total + " of " + count + " bytes");
            total += n;
        }
        return buf;
    }

    private static String sha256Hex(byte[] data) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder sb = new StringBuilder(hash.length * 2);
        for (byte b : hash) sb.append(String.format("%02x", b & 0xFF));
        return sb.toString();
    }
}
