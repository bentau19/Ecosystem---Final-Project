package com.example.tausync_lib.implementations.transport;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.content.Context;

import androidx.annotation.RequiresPermission;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.management.ConnectionContext;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.interfaces.ITransport;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Semaphore;

/**
 * Bluetooth Classic (RFCOMM) transport. Protocol-agnostic: reads frames via
 * {@link IProtocolHandler} only, exactly like {@link SocketTransport}.
 * The RFCOMM byte stream is a drop-in replacement for the TCP stream, so the framing,
 * dispatch, and send-lock logic are identical to the Wi-Fi transport.
 *
 * <p>Android always acts as the RFCOMM <b>client</b>: it connects out to a paired Windows
 * device by MAC address. Server mode is not supported here — Windows is always the RFCOMM
 * server. Requires {@link Manifest.permission#BLUETOOTH_CONNECT} (API 31+).
 *
 * <p>Matches C# BluetoothTransport.
 */
public class BluetoothTransport implements ITransport {

    private final Context context;
    private final IProtocolHandler protocolHandler;

    private BluetoothSocket btSocket;
    private InputStream inputStream;
    private OutputStream outputStream;
    private volatile boolean connected;
    private volatile boolean disposed;
    private Thread receiveThread;
    private final Semaphore sendLock = new Semaphore(1);
    private OnDataReceivedListener dataReceivedListener;

    /**
     * Serializes every transition of the connection state machine — {@link #connect},
     * {@link #disconnect}, and {@link #handleConnectionDropped} — so an unexpected drop's teardown and
     * an explicit disconnect cannot interleave. Never held across the receive-thread join (which calls
     * handleConnectionDropped).
     */
    private final Object stateLock = new Object();

    /** True only while an explicit {@link #disconnect()} is tearing the transport down — distinguishes a deliberate close from an unexpected drop (which converges to a clean reset). */
    private volatile boolean intentionalClose;

    /** True once this transport has been counted in {@link ConnectionContext}, so the matching disconnect decrements exactly once. */
    private volatile boolean counted;

    /**
     * Completed while a live connection exists; replaced with an incomplete future during a
     * reconnect so a send issued mid-drop waits for the link to come back instead of failing.
     * {@link #sendRaw(byte[])} waits on this before writing.
     */
    private volatile CompletableFuture<Void> sendGate = new CompletableFuture<>();

    public BluetoothTransport(Context context) {
        this(context, null);
    }

    /**
     * @param context        used to obtain the {@link BluetoothManager}
     * @param protocolHandler framing handler; defaults to {@link ProtocolHandler}
     */
    public BluetoothTransport(Context context, IProtocolHandler protocolHandler) {
        this.context = context.getApplicationContext();
        this.protocolHandler = protocolHandler != null ? protocolHandler : new ProtocolHandler();
    }

    @Override
    public boolean isServerMode() {
        return false; // Android is always the RFCOMM client.
    }

    @Override
    public TransportKind getTransportType() {
        return TransportKind.BLUETOOTH;
    }

    @Override
    public CompletableFuture<Void> connect(String targetId) {
        return connect(targetId, null);
    }

    /**
     * Connects to the paired Windows server identified by its Bluetooth MAC address.
     *
     * @param targetId       peer Bluetooth MAC address (e.g. "AA:BB:CC:DD:EE:FF")
     * @param timeoutSeconds max seconds to wait for the RFCOMM connect; null uses
     *                       {@link CoreConfig#BT_CONNECT_TIMEOUT_MS}
     */
    @Override
    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    public CompletableFuture<Void> connect(String targetId, Integer timeoutSeconds) {
        if (disposed) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport disposed"));
        }
        if (targetId == null || targetId.trim().isEmpty()) {
            return CompletableFuture.failedFuture(new UnsupportedOperationException(
                    "BluetoothTransport is client-only; targetId must be a peer MAC address."));
        }
        if (connected) {
            disconnect();
        }

        synchronized (stateLock) {
            // Re-arm for a fresh session: a prior disconnect()/drop left intentionalClose set, and the
            // gate must start incomplete until this connection succeeds.
            intentionalClose = false;
            sendGate = new CompletableFuture<>();
        }

        long timeoutMs = timeoutSeconds != null
                ? timeoutSeconds * 1000L
                : CoreConfig.BT_CONNECT_TIMEOUT_MS;
        return connectAsync(targetId.trim(), timeoutMs);
    }

    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private CompletableFuture<Void> connectAsync(String deviceAddress, long timeoutMs) {
        CompletableFuture<Void> connectionFuture = new CompletableFuture<>();

        Thread connectThread = new Thread(() -> {
            try {
                openRfcommSocket(deviceAddress);
                inputStream = btSocket.getInputStream();
                outputStream = btSocket.getOutputStream();
                connected = true;
                startReceiveLoop();
                markInitialConnection();
                connectionFuture.complete(null);
            } catch (Exception e) {
                closeQuietly(btSocket);
                connectionFuture.completeExceptionally(e);
            }
        }, "TauSync-BT-Connect");
        connectThread.setDaemon(true);
        connectThread.start();

        // btSocket.connect() blocks with no built-in timeout. Closing the socket from this
        // watchdog unblocks it, so a black-holed peer cannot hang the caller forever.
        startConnectWatchdog(connectionFuture, timeoutMs);
        return connectionFuture;
    }

    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private void openRfcommSocket(String deviceAddress) throws IOException {
        BluetoothManager manager =
                (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter adapter = manager != null ? manager.getAdapter() : null;
        if (adapter == null) {
            throw new IOException("Bluetooth not available on this device.");
        }

        BluetoothDevice device = adapter.getRemoteDevice(deviceAddress);
        if (device.getBondState() != BluetoothDevice.BOND_BONDED) {
            throw new BondLostException(deviceAddress);
        }

        // Cancel any active inquiry scan before creating the socket — discovery contends with
        // RFCOMM and dramatically increases connect latency and failure rate.
        adapter.cancelDiscovery();

        UUID serviceUuid = UUID.fromString(CoreConfig.RFCOMM_SERVICE_UUID);
        try {
            btSocket = device.createRfcommSocketToServiceRecord(serviceUuid);
            btSocket.connect();
        } catch (IOException secureException) {
            // Secure RFCOMM failed. Many Android versions and device combinations reject it
            // even on a bonded pair ("read failed, socket might closed or timeout, read ret: -1").
            // Fall back to an insecure channel, which skips the link-key authentication step
            // while still going through SDP to resolve the correct channel number.
            closeQuietly(btSocket);
            btSocket = device.createInsecureRfcommSocketToServiceRecord(serviceUuid);
            btSocket.connect();
        }
    }

    private void startConnectWatchdog(CompletableFuture<Void> connectionFuture, long timeoutMs) {
        Thread watchdog = new Thread(() -> {
            try {
                Thread.sleep(timeoutMs);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
                return;
            }
            if (!connectionFuture.isDone()) {
                closeQuietly(btSocket); // unblocks btSocket.connect()
                connectionFuture.completeExceptionally(
                        new java.util.concurrent.TimeoutException(
                                "Bluetooth connect timed out after " + timeoutMs + " ms."));
            }
        }, "TauSync-BT-ConnectWatchdog");
        watchdog.setDaemon(true);
        watchdog.start();
    }

    @Override
    public CompletableFuture<Void> sendRaw(byte[] data) {
        if (data == null) {
            return CompletableFuture.failedFuture(new IllegalArgumentException("data must not be null"));
        }
        if (disposed) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport disposed"));
        }

        try {
            // Block briefly if an unexpected drop is being healed, so a write issued during
            // the reconnect window resumes on the new link instead of failing.
            waitForConnection();
        } catch (Exception e) {
            return CompletableFuture.failedFuture(e);
        }
        if (!connected || outputStream == null) {
            return CompletableFuture.failedFuture(new IllegalStateException("Not connected"));
        }

        try {
            sendLock.acquire();
            try {
                outputStream.write(data);
                outputStream.flush();
            } finally {
                sendLock.release();
            }
            return CompletableFuture.completedFuture(null);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(new RuntimeException("Send interrupted", e));
        } catch (IOException e) {
            return CompletableFuture.failedFuture(new RuntimeException("Send failed", e));
        }
    }

    /**
     * Blocks until the send gate opens (connection live) or the wait budget elapses.
     * Returns immediately during normal operation; only parks during a reconnect window.
     */
    private void waitForConnection() throws Exception {
        CompletableFuture<Void> gate = sendGate;
        if (gate.isDone()) return;
        try {
            gate.get(CoreConfig.SEND_RECONNECT_WAIT_MS, java.util.concurrent.TimeUnit.MILLISECONDS);
        } catch (java.util.concurrent.ExecutionException e) {
            Throwable cause = e.getCause();
            throw cause instanceof Exception ? (Exception) cause : e;
        }
    }

    @Override
    public boolean isConnected() {
        return connected && !disposed && btSocket != null && btSocket.isConnected();
    }

    @Override
    public void setOnDataReceivedListener(OnDataReceivedListener listener) {
        this.dataReceivedListener = listener;
    }

    // ── Receive Loop ──────────────────────────────────────────────────

    private void startReceiveLoop() {
        receiveThread = new Thread(this::receiveLoop, "TauSync-BT-Receive");
        receiveThread.setDaemon(true);
        receiveThread.start();
    }

    private void receiveLoop() {
        int headerSize = protocolHandler.getHeaderSize();
        byte[] headerBuffer = new byte[headerSize];

        while (connected && !disposed && inputStream != null) {
            try {
                int headerRead = readExactly(inputStream, headerBuffer, 0, headerSize);
                if (headerRead != headerSize) break;

                int payloadLength = protocolHandler.getPayloadLength(headerBuffer);
                if (payloadLength < 0 || payloadLength > CoreConfig.MAX_PAYLOAD_SIZE) break;

                int totalFrameSize = headerSize + payloadLength;
                byte[] frame = new byte[totalFrameSize];
                System.arraycopy(headerBuffer, 0, frame, 0, headerSize);

                if (payloadLength > 0) {
                    int payloadRead = readExactly(inputStream, frame, headerSize, payloadLength);
                    if (payloadRead != payloadLength) break;
                }

                IProtocolHandler.ParseResult result = protocolHandler.parseFrame(frame);
                dispatchFrame(result.getTargetId(), result.getPayload(), result.getFlags(), frame);

            } catch (Exception e) {
                break;
            }
        }

        handleConnectionDropped();
    }

    private void dispatchFrame(int targetId, byte[] payload, byte flags, byte[] rawFrame) {
        if (protocolHandler.isControlFrame(targetId, flags)) {
            boolean handled = ConnectionContext.getInstance().dispatch(targetId, payload, flags);
            if (!handled && dataReceivedListener != null) {
                dataReceivedListener.onDataReceived(rawFrame);
            }
            return;
        }
        ConnectionContext.getInstance().dispatch(targetId, payload, flags);
    }

    /**
     * Reads exactly {@code count} bytes from the stream, looping until done or EOF.
     *
     * @return number of bytes actually read (less than count only on EOF)
     */
    private static int readExactly(InputStream stream, byte[] buffer, int offset, int count)
            throws IOException {
        int totalRead = 0;
        while (totalRead < count) {
            int r = stream.read(buffer, offset + totalRead, count - totalRead);
            if (r < 0) return totalRead;
            totalRead += r;
        }
        return totalRead;
    }

    // ── Lifecycle ─────────────────────────────────────────────────────

    /**
     * Marks this transport connected exactly once and counts it in {@link ConnectionContext}.
     * Called only on the FIRST successful connect — reconnects after a drop reuse the same
     * count, so the session is never double-counted.
     */
    private void markInitialConnection() {
        if (!counted) {
            counted = true;
            ConnectionContext.getInstance().notifyTransportConnected();
        }
        sendGate.complete(null);
    }

    /**
     * Explicit, app-initiated teardown. Ends the session for this transport: stops any
     * reconnect attempt and notifies {@link ConnectionContext}, which aborts the open channels
     * and resets state only if this was the last live transport.
     */
    public void disconnect() {
        Thread rt;
        synchronized (stateLock) {
            if (intentionalClose) return;
            intentionalClose = true;
            connected = false;

            // Release a sender parked on the gate. Because handleConnectionDropped also takes
            // stateLock and re-checks intentionalClose, a receive loop exiting right now cannot race
            // this teardown.
            sendGate.complete(null);

            // Close the streams to unblock the receive thread's blocking read so the join below
            // returns promptly.
            closeQuietly(inputStream);
            closeQuietly(outputStream);
            closeQuietly(btSocket);

            rt = receiveThread;
        }

        // Join the receive loop OUTSIDE the lock — it calls handleConnectionDropped on exit, which
        // needs the lock; holding it here would deadlock.
        if (rt != null && rt != Thread.currentThread()) {
            rt.interrupt();
            try { rt.join(2000); } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }

        synchronized (stateLock) {
            // Decrement the transport count exactly once. Channels are aborted (synthetic FIN so
            // blocked read() calls return EOF) and state reset only when the count hits zero.
            if (counted) {
                counted = false;
                ConnectionContext.getInstance().notifyTransportDisconnected();
            }

            inputStream = null;
            outputStream = null;
            btSocket = null;
        }
    }

    /**
     * Handles the receive loop exiting on a broken RFCOMM link (the peer vanished, moved out of
     * range, or its own stack reset). Unlike Wi-Fi, the Bluetooth primary does <b>not</b> silently
     * reconnect: that is incompatible with the per-session ECDH key exchange and the connection
     * approval, both of which the peer re-runs from scratch on every reconnect. A transport-level
     * "resume" would adopt the peer's fresh handshake into the old (already-encrypted) session, so the
     * new KEY_EXCHANGE is ignored and the link can never re-establish. Instead we converge to a clean
     * disconnected state and notify the context, which (when this was the last live transport) aborts
     * the channels and resets the session — clearing the derived key and routing. The app then
     * re-establishes, so the next attempt runs a brand-new handshake.
     */
    private void handleConnectionDropped() {
        boolean notifyDisconnected = false;
        synchronized (stateLock) {
            // Re-check under the lock: an explicit disconnect may have just set intentionalClose and
            // is already doing this teardown — don't double it.
            if (intentionalClose || disposed) return;
            if (!connected) return;
            connected = false;

            // Fresh incomplete gate so a send issued during the drop fails fast instead of writing
            // into a dead socket.
            sendGate = new CompletableFuture<>();

            closeQuietly(inputStream);
            closeQuietly(outputStream);
            closeQuietly(btSocket);
            inputStream = null;
            outputStream = null;
            btSocket = null;

            if (counted) {
                counted = false;
                notifyDisconnected = true;
            }
        }

        // Notify OUTSIDE the lock: notifyTransportDisconnected may abort channels and reset() the
        // singleton (when the count hits zero), which must not run under this transport's lock.
        if (notifyDisconnected) {
            ConnectionContext.getInstance().notifyTransportDisconnected();
        }
    }

    @Override
    public void close() {
        if (disposed) return;
        disposed = true;
        disconnect();
    }

    private static void closeQuietly(AutoCloseable closeable) {
        if (closeable == null) return;
        try { closeable.close(); } catch (Exception ignored) {}
    }

    /**
     * Thrown when {@link #connect} is called for a device that is no longer bonded.
     * The caller (or the Activity layer) should invoke {@code BleDiscovery.startDiscovery()}
     * to re-pair, save the address, and retry the connect.
     */
    public static final class BondLostException extends java.io.IOException {
        /** The MAC address of the device whose bond was lost. */
        public final String deviceAddress;

        public BondLostException(String deviceAddress) {
            super("Device " + deviceAddress + " is not bonded. Re-pair via BleDiscovery first.");
            this.deviceAddress = deviceAddress;
        }
    }
}
