package com.example.tausync_lib.implementations.management;

import com.tausync.core.CoreConfig;
import com.tausync.interfaces.IConnectionManager;
import com.tausync.interfaces.IProtocolHandler;
import com.tausync.interfaces.ITransport;
import com.tausync.implementations.transport.SocketTransport;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * Connection manager per TauSync Protocol Spec: which connection and when; dispatcher and routing map.
 * Routes incoming TPack by CorrelationID. Control channel = 0. No encryption in this implementation.
 * Java uses same CorrelationID pool (1, 2, 3, ...). Matches C# ConnectionManager.
 */
public class ConnectionManager implements IConnectionManager {

    private ITransport transport;
    private boolean ownsTransport;
    private final IProtocolHandler protocolHandler;
    private final ConcurrentHashMap<Integer, Consumer<byte[]>> routingMap = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<Integer, Runnable> onFinByCorrelationId = new ConcurrentHashMap<>();
    private volatile CompletableFuture<byte[]> pendingControlWaiter;
    private final Object controlLock = new Object();
    private final AtomicInteger nextCorrelationId = new AtomicInteger(1);
    private final ConcurrentLinkedQueue<Integer> releasedCorrelationIds = new ConcurrentLinkedQueue<>();
    private volatile boolean disposed;
    private final Gson gson = new Gson();
    private final ExecutorService executor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r);
        t.setDaemon(true);
        return t;
    });
    private ErrorOccurredListener errorOccurredListener;
    private IConnectionManager.ClipboardReceivedListener clipboardReceivedListener;

    public ConnectionManager() {
        this(null);
    }

    public ConnectionManager(IProtocolHandler protocolHandler) {
        this.protocolHandler = protocolHandler != null ? protocolHandler : new ProtocolHandler();
    }

    @Override
    public void initialize(ITransport transport) {
        if (transport == null) throw new IllegalArgumentException("transport cannot be null");
        if (this.transport != null) throw new IllegalStateException("Already initialized");
        this.transport = transport;
        this.ownsTransport = false;
        transport.setOnDataReceivedListener(this::onTransportDataReceived);
    }

    @Override
    public CompletableFuture<Void> connect(String targetId) {
        if (disposed) {
            return CompletableFuture.failedFuture(new IllegalStateException("ConnectionManager is disposed"));
        }
        if (transport != null) {
            transport.setOnDataReceivedListener(null);
            if (ownsTransport && transport instanceof AutoCloseable) {
                try {
                    ((AutoCloseable) transport).close();
                } catch (Exception ignored) {
                }
            }
            transport = null;
        }
        SocketTransport st = new SocketTransport();
        transport = st;
        ownsTransport = true;
        transport.setOnDataReceivedListener(this::onTransportDataReceived);
        return transport.connect(targetId);
    }

    @Override
    public boolean isConnected() {
        return transport != null && transport.isConnected();
    }

    @Override
    public void registerHandler(int correlationId, Consumer<byte[]> callback) {
        if (callback == null) throw new IllegalArgumentException("callback cannot be null");
        routingMap.put(correlationId, callback);
    }

    @Override
    public void unregisterHandler(int correlationId) {
        routingMap.remove(correlationId);
    }

    @Override
    public void setErrorOccurredListener(ErrorOccurredListener listener) {
        this.errorOccurredListener = listener;
    }

    @Override
    public void setOnClipboardReceivedListener(IConnectionManager.ClipboardReceivedListener listener) {
        this.clipboardReceivedListener = listener;
    }

    @Override
    public CompletableFuture<Void> smartSend(InputStream source, String type, String payload) {
        if (source == null) throw new IllegalArgumentException("source cannot be null");
        if (type == null || type.trim().isEmpty()) throw new IllegalArgumentException("type cannot be null or empty");
        if (transport == null || !transport.isConnected()) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport not connected. Initialize and connect first."));
        }

        int correlationId = allocateCorrelationId();
        TransferRequest request = new TransferRequest();
        request.setCorrelationID(correlationId);
        request.setType(type);
        request.setStatus("PUSH");
        request.setFileSize(0);
        request.setPayload(payload);

        return runHandshakeAsync(request)
                .thenCompose(ok -> {
                    if (!ok) {
                        releaseCorrelationIdIfOurs(correlationId);
                        unregisterHandler(correlationId);
                        return CompletableFuture.<Void>failedFuture(new IllegalStateException("Handshake rejected by peer."));
                    }
                    return streamDataAsync(source, correlationId)
                            .whenComplete((v, e) -> unregisterHandler(correlationId));
                });
    }

    @Override
    public CompletableFuture<InputStream> getStream(String type, String payload) {
        if (type == null || type.trim().isEmpty()) throw new IllegalArgumentException("type cannot be null or empty");
        if (transport == null || !transport.isConnected()) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport not connected. Initialize and connect first."));
        }

        int correlationId = allocateCorrelationId();
        BackBufferedInputStream backStream = new BackBufferedInputStream();

        registerHandler(correlationId, backStream::writeChunk);
        onFinByCorrelationId.put(correlationId, backStream::complete);

        TransferRequest request = new TransferRequest();
        request.setCorrelationID(correlationId);
        request.setParentID(0);
        request.setType(type);
        request.setStatus("REQ");
        request.setPayload(payload);

        byte[] requestJson = gson.toJson(request).getBytes(StandardCharsets.UTF_8);
        byte[] frame = protocolHandler.buildFrame(CoreConfig.CONTROL_CHANNEL_ID, requestJson);
        return transport.sendRaw(frame)
                .thenCompose(v -> waitForControlResponseAsync())
                .thenCompose(controlResponse -> {
                    TransferRequest approval = parseTransferRequest(controlResponse);
                    if (approval == null || !"APPROVE".equals(approval.getStatus())) {
                        releaseCorrelationIdIfOurs(correlationId);
                        unregisterHandler(correlationId);
                        onFinByCorrelationId.remove(correlationId);
                        try { backStream.close(); } catch (IOException ignored) {}
                        return CompletableFuture.<InputStream>failedFuture(new IllegalStateException("GetStream: expected APPROVE from peer."));
                    }
                    return sendControlResponseAsync(correlationId, "OK", null)
                            .thenApply(v2 -> {
                                executor.execute(() -> {
                                    try {
                                        releaseCorrelationIdIfOurs(correlationId);
                                        unregisterHandler(correlationId);
                                        onFinByCorrelationId.remove(correlationId);
                                    } catch (Exception ex) {
                                        onError(new IllegalStateException("GetStream receive failed.", ex));
                                    }
                                });
                                return (InputStream) backStream;
                            });
                });
    }

    private void onTransportDataReceived(byte[] rawPacket) {
        if (rawPacket == null || protocolHandler == null) return;
        try {
            IProtocolHandler.ParseResult parsed = protocolHandler.parseFrame(rawPacket);
            int correlationId = parsed.correlationId;
            byte[] payload = parsed.payload;
            byte flags = parsed.flags;

            if (correlationId == CoreConfig.CONTROL_CHANNEL_ID) {
                synchronized (controlLock) {
                    if (pendingControlWaiter != null) {
                        CompletableFuture<byte[]> w = pendingControlWaiter;
                        pendingControlWaiter = null;
                        w.complete(payload);
                        return;
                    }
                }
                tryHandleIncomingHandshake(payload);
                return;
            }

            Consumer<byte[]> handler = routingMap.get(correlationId);
            if (handler != null) {
                handler.accept(payload);
                if ((flags & CoreConfig.FLAG_FIN) != 0) {
                    Runnable onFin = onFinByCorrelationId.remove(correlationId);
                    if (onFin != null) onFin.run();
                    unregisterHandler(correlationId);
                }
                return;
            }

            tryHandleIncomingHandshake(payload);
        } catch (Exception ex) {
            onError(new IllegalStateException("HandleIncoming failed.", ex));
        }
    }

    private void tryHandleIncomingHandshake(byte[] payload) {
        TransferRequest req = parseTransferRequest(payload);
        if (req == null || !req.isValid()) return;
        if ("REQ".equals(req.getStatus()) || "PUSH".equals(req.getStatus())) {
            int correlationId = req.getCorrelationID();
            if (!routingMap.containsKey(correlationId)) {
                if ("PUSH".equals(req.getStatus()) && "CLIPBOARD".equals(req.getType()) && clipboardReceivedListener != null) {
                    ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                    registerHandler(correlationId, data -> {
                        if (data != null && data.length > 0) {
                            try {
                                buffer.write(data);
                            } catch (IOException ignored) {}
                        }
                    });
                    onFinByCorrelationId.put(correlationId, () -> {
                        String text = new String(buffer.toByteArray(), StandardCharsets.UTF_8);
                        clipboardReceivedListener.onClipboardReceived(text);
                    });
                } else {
                    registerHandler(correlationId, b -> {});
                }
            }
            sendControlResponseAsync(correlationId, "OK", req.getType());
        }
    }

    private CompletableFuture<Boolean> runHandshakeAsync(TransferRequest request) {
        return protocolHandler.sendHandshakeAsync(
                request,
                data -> transport.sendRaw(data),
                this::waitForControlResponseAsync);
    }

    private CompletableFuture<byte[]> waitForControlResponseAsync() {
        CompletableFuture<byte[]> future;
        synchronized (controlLock) {
            if (pendingControlWaiter != null) {
                throw new IllegalStateException("A handshake is already pending.");
            }
            pendingControlWaiter = future = new CompletableFuture<>();
        }
        future.orTimeout(CoreConfig.HANDSHAKE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        return future;
    }

    private CompletableFuture<Void> sendControlResponseAsync(int requestCorrelationId, String status, String type) {
        TransferRequest response = new TransferRequest();
        response.setMagicBytes(0x54415553L);
        response.setCorrelationID(requestCorrelationId);
        response.setType(type != null ? type : "");
        response.setStatus(status);
        response.setFileSize(0);
        String json = gson.toJson(response);
        byte[] body = json.getBytes(StandardCharsets.UTF_8);
        byte[] frame = protocolHandler.buildFrame(CoreConfig.CONTROL_CHANNEL_ID, body);
        return transport.sendRaw(frame);
    }

    private CompletableFuture<Void> streamDataAsync(InputStream source, int correlationId) {
        return CompletableFuture.runAsync(() -> {
            byte[] buffer = new byte[CoreConfig.STREAM_CHUNK_SIZE];
            long totalSent = 0;
            boolean first = true;
            try {
                int read;
                while ((read = source.read(buffer)) > 0) {
                    byte[] chunk = new byte[read];
                    System.arraycopy(buffer, 0, chunk, 0, read);
                    byte[] frame = protocolHandler.buildFrame(correlationId, chunk);
                    transport.sendRaw(frame).join();
                    totalSent += read;
                    first = false;
                }
                if (first && totalSent == 0) return;
                byte[] finFrame = protocolHandler.buildFrame(correlationId, new byte[0], CoreConfig.FLAG_FIN);
                transport.sendRaw(finFrame).join();
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        }, executor);
    }

    private int allocateCorrelationId() {
        Integer reused = releasedCorrelationIds.poll();
        if (reused != null) return reused;
        int id = nextCorrelationId.getAndIncrement();
        if (id <= 0) id = 1;
        if (id > 0xFFFFFF) {
            nextCorrelationId.set(2);
            id = 1;
        }
        return id;
    }

    private void releaseCorrelationIdIfOurs(int correlationId) {
        if (correlationId > 0 && correlationId <= 0xFFFFFF) {
            releasedCorrelationIds.add(correlationId);
        }
    }

    private TransferRequest parseTransferRequest(byte[] payload) {
        if (payload == null || payload.length == 0) return null;
        try {
            String json = new String(payload, StandardCharsets.UTF_8);
            return gson.fromJson(json, TransferRequest.class);
        } catch (Exception e) {
            return null;
        }
    }

    private void onError(Exception ex) {
        if (errorOccurredListener != null) {
            errorOccurredListener.onErrorOccurred(ex);
        }
    }

    @Override
    public void close() {
        if (disposed) return;
        disposed = true;
        if (transport != null) {
            transport.setOnDataReceivedListener(null);
            if (ownsTransport && transport instanceof AutoCloseable) {
                try {
                    ((AutoCloseable) transport).close();
                } catch (Exception ignored) {
                }
            }
            transport = null;
        }
        routingMap.clear();
        onFinByCorrelationId.clear();
        synchronized (controlLock) {
            if (pendingControlWaiter != null) {
                pendingControlWaiter.cancel(false);
                pendingControlWaiter = null;
            }
        }
        executor.shutdown();
    }
}
