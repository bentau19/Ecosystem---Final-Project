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
    private Thread reconnectThread;
    private final Semaphore sendLock = new Semaphore(1);
    private OnDataReceivedListener dataReceivedListener;

    /** True only while an explicit {@link #disconnect()} is tearing the transport down — distinguishes a deliberate close (ends the session) from an unexpected drop (triggers reconnect). */
    private volatile boolean intentionalClose;

    /** True once this transport has been counted in {@link ConnectionContext}, so the matching disconnect decrements exactly once. */
    private volatile boolean counted;

    /** Peer MAC saved on connect so the reconnect loop can re-open the RFCOMM socket. */
    private volatile String lastDeviceAddress;

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

        // Re-arm for a fresh session: a prior disconnect() left intentionalClose set, and the
        // gate must start incomplete until this connection succeeds.
        intentionalClose = false;
        sendGate = new CompletableFuture<>();

        long timeoutMs = timeoutSeconds != null
                ? timeoutSeconds * 1000L
                : CoreConfig.BT_CONNECT_TIMEOUT_MS;
        lastDeviceAddress = targetId.trim();
        return connectAsync(lastDeviceAddress, timeoutMs);
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
            // TODO(Phase 5): trigger BleDiscovery to re-pair, then retry. Until then the
            // caller must pair the device (system settings / CompanionDeviceManager) first.
            throw new IOException("Device " + deviceAddress + " is not bonded; pair it before connecting.");
        }

        btSocket = device.createRfcommSocketToServiceRecord(
                UUID.fromString(CoreConfig.RFCOMM_SERVICE_UUID));
        // Active discovery dramatically slows down an RFCOMM connect — always cancel it first.
        adapter.cancelDiscovery();
        btSocket.connect(); // blocks until connected or throws
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
        if (intentionalClose) return;
        intentionalClose = true;
        connected = false;

        // Stop any in-flight reconnect and release a sender parked on the gate.
        Thread rc = reconnectThread;
        if (rc != null) rc.interrupt();
        sendGate.complete(null);

        closeQuietly(inputStream);
        closeQuietly(outputStream);
        closeQuietly(btSocket);

        // Decrement the transport count exactly once. Channels are aborted (synthetic FIN so
        // blocked read() calls return EOF) and state reset only when the count hits zero.
        if (counted) {
            counted = false;
            ConnectionContext.getInstance().notifyTransportDisconnected();
        }

        Thread rt = receiveThread;
        if (rt != null && rt != Thread.currentThread()) {
            rt.interrupt();
            try { rt.join(2000); } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }

        inputStream = null;
        outputStream = null;
        btSocket = null;
    }

    /**
     * Handles the receive loop exiting on a broken RFCOMM link. An explicit disconnect ends
     * the session; an unexpected drop instead tears down only the dead socket — keeping the
     * channels, handlers, and transport count intact — and re-opens the RFCOMM connection so
     * the session resumes transparently.
     */
    private void handleConnectionDropped() {
        if (intentionalClose || disposed) return;
        if (!connected) return;
        connected = false;

        // Fresh incomplete gate so sends block until the link is back.
        sendGate = new CompletableFuture<>();

        closeQuietly(inputStream);
        closeQuietly(outputStream);
        closeQuietly(btSocket);
        inputStream = null;
        outputStream = null;
        btSocket = null;

        startReconnectLoop();
    }

    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private void startReconnectLoop() {
        reconnectThread = new Thread(this::reconnectLoop, "TauSync-BT-Reconnect");
        reconnectThread.setDaemon(true);
        reconnectThread.start();
    }

    /**
     * Re-opens the RFCOMM connection with exponential back-off until it succeeds or an
     * explicit disconnect stops it. On success it restarts the receive loop and opens the send
     * gate, all on the same channel handlers — the layers above never see the gap.
     */
    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private void reconnectLoop() {
        int delayMs = CoreConfig.RECONNECT_INITIAL_DELAY_MS;
        while (!disposed && !intentionalClose) {
            try {
                openRfcommSocket(lastDeviceAddress);
                inputStream = btSocket.getInputStream();
                outputStream = btSocket.getOutputStream();
                connected = true;
                startReceiveLoop();
                sendGate.complete(null);
                return;
            } catch (Exception e) {
                closeQuietly(btSocket);
            }
            try {
                Thread.sleep(delayMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            delayMs = Math.min(delayMs * 2, CoreConfig.RECONNECT_MAX_DELAY_MS);
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
}
