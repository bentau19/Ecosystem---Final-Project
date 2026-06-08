package com.example.tausync_lib.implementations.management;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.protocol.ProtocolHandler;
import com.example.tausync_lib.interfaces.IConnectionManager;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.interfaces.ITransport;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Connection manager per TauSync v3: both sides call {@link #connect(String)} with the
 * same Meeting Word; when two peers use the same word they are paired and each gets a
 * bidirectional {@link TauSyncStream}.
 *
 * <p>Matches C# ConnectionManager.
 */
public class ConnectionManager implements IConnectionManager {

    private ITransport wifiTransport;
    private final IProtocolHandler protocolHandler;
    private final Gson gson = new Gson();

    /** Per-word queue of incoming connections (peer sent REQ before us or simultaneously). */
    private final ConcurrentHashMap<String, LinkedBlockingQueue<TauSyncStream>> incomingByWord =
            new ConcurrentHashMap<>();

    /**
     * Dedicated pool for blocking handshake operations. Avoids starving the
     * default ForkJoinPool.commonPool() on Android devices with few cores.
     */
    private static final ExecutorService HANDSHAKE_POOL =
            Executors.newCachedThreadPool(r -> {
                Thread t = new Thread(r, "TauSync-Handshake");
                t.setDaemon(true);
                return t;
            });

    private volatile boolean disposed;
    private volatile ErrorListener errorListener;

    public ConnectionManager() {
        protocolHandler = new ProtocolHandler();
        ITransport transport = ConnectionContext.getInstance().getWifiTransport();
        if (transport == null) {
            throw new IllegalStateException("ConnectionContext has no transport.");
        }
        initialize(transport);
    }

    @Override
    public void initialize(ITransport transport) {
        if (transport == null) throw new IllegalArgumentException("transport must not be null");
        if (wifiTransport != null) throw new IllegalStateException("Already initialized.");
        wifiTransport = transport;
    }

    @Override
    public CompletableFuture<Void> connectTransport(String targetId) {
        return CompletableFuture.runAsync(() -> {
            try {
                ConnectionContext.getInstance().initializeTransports(targetId);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });
    }

    @Override
    public boolean isConnected() {
        return wifiTransport != null && wifiTransport.isConnected();
    }

    @Override
    public CompletableFuture<TauSyncStream> connect(String word) {
        validateConnectState(word);
        String wordTrimmed = word.trim();

        LinkedBlockingQueue<TauSyncStream> wordChannel = getOrCreateWordChannel(wordTrimmed);
        registerWordListener(wordTrimmed, wordChannel);

        ConnectionContext ctx = ConnectionContext.getInstance();
        ConnectAttempt attempt = createConnectAttempt(ctx);

        return sendWordRequestAsync(wordTrimmed, attempt.localId)
                .thenCompose(ignored -> resolveConnectRaceAsync(ctx, wordChannel, attempt))
                .whenComplete((stream, ex) -> {
                    // Unregister the service listener after the connection resolves (success or failure).
                    //
                    // Without this cleanup, the callback registered by registerWordListener stays in
                    // ConnectionContext.serviceRegistry after the first use. On a second transfer using
                    // the same word, the incoming REQ is handled directly (bypassing pendingDiscoveryByWord),
                    // so getPeerWaitingWords() never surfaces the word again and the app's polling loop
                    // cannot trigger a second connect() call — causing the desktop to hang forever.
                    ConnectionContext.getInstance().unregisterService(wordTrimmed);
                });
    }

    // ── Connect internals ─────────────────────────────────────────────

    private void validateConnectState(String word) {
        if (word == null || word.trim().isEmpty()) {
            throw new IllegalArgumentException("Word cannot be null or empty.");
        }
        if (wifiTransport == null || !wifiTransport.isConnected()) {
            throw new IllegalStateException("Transport not connected. connectTransport first.");
        }
        if (disposed) {
            throw new IllegalStateException("ConnectionManager is disposed.");
        }
    }

    private LinkedBlockingQueue<TauSyncStream> getOrCreateWordChannel(String wordKey) {
        return incomingByWord.computeIfAbsent(wordKey, k -> new LinkedBlockingQueue<>());
    }

    private void registerWordListener(String wordKey, LinkedBlockingQueue<TauSyncStream> channel) {
        ConnectionContext.getInstance().registerService(wordKey, (localId, peerSenderId, stream) ->
                handleWordRequest(wordKey, channel, localId, peerSenderId, stream));
    }

    private ConnectAttempt createConnectAttempt(ConnectionContext ctx) {
        int localId = ctx.reserveId();
        BackBufferedInputStream backStream = new BackBufferedInputStream();
        CompletableFuture<byte[]> responseFuture = new CompletableFuture<>();

        ctx.registerHandler(localId, (payload, flags) -> {
            if ((flags & CoreConfig.FLAG_CONTROL) != 0) {
                responseFuture.complete(payload != null ? payload : new byte[0]);
                return;
            }
            if (payload != null && payload.length > 0) {
                backStream.writeChunk(payload);
            }
            if ((flags & CoreConfig.FLAG_FIN) != 0) {
                backStream.complete();
            }
        });

        return new ConnectAttempt(localId, backStream, responseFuture);
    }

    /**
     * Resolves the simultaneous-connect race deterministically using the transport role:
     * TCP client prefers the outgoing (own REQ->OK) path,
     * TCP server prefers the incoming (peer REQ->service callback) path.
     * Falls back to the other path if the preferred one fails.
     */
    private CompletableFuture<TauSyncStream> resolveConnectRaceAsync(
            ConnectionContext ctx,
            LinkedBlockingQueue<TauSyncStream> channel,
            ConnectAttempt attempt) {

        int timeoutSec = CoreConfig.HANDSHAKE_TIMEOUT_SECONDS;

        CompletableFuture<TauSyncStream> ownPath =
                waitForOkAndBuildStreamAsync(attempt.responseFuture, ctx, attempt.localId, attempt.backStream);

        CompletableFuture<TauSyncStream> peerPath = CompletableFuture.supplyAsync(() -> {
            try {
                long deadlineNanos = System.nanoTime() + TimeUnit.SECONDS.toNanos(timeoutSec);
                while (!disposed) {
                    long remainingNanos = deadlineNanos - System.nanoTime();
                    if (remainingNanos <= 0) {
                        throw new RuntimeException(new TimeoutException("Peer path timed out"));
                    }
                    long pollMs = Math.min(500, TimeUnit.NANOSECONDS.toMillis(remainingNanos));
                    if (pollMs <= 0) pollMs = 1;
                    TauSyncStream stream = channel.poll(pollMs, TimeUnit.MILLISECONDS);
                    if (stream != null) return stream;
                }
                throw new RuntimeException(
                        new IllegalStateException("ConnectionManager disposed during handshake"));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(e);
            }
        }, HANDSHAKE_POOL);

        boolean preferOwnPath = !ctx.isTransportServerMode();

        if (preferOwnPath) {
            return ownPath
                    .orTimeout(timeoutSec, TimeUnit.SECONDS)
                    .handle((stream, ex) -> {
                        if (ex == null) return CompletableFuture.completedFuture(stream);
                        cleanupLosingOutgoingAttempt(ctx, attempt);
                        return peerPath;
                    })
                    .thenCompose(f -> f);
        }

        return peerPath
                .handle((stream, ex) -> {
                    if (ex == null) {
                        cleanupLosingOutgoingAttempt(ctx, attempt);
                        return CompletableFuture.completedFuture(stream);
                    }
                    return ownPath.orTimeout(timeoutSec, TimeUnit.SECONDS);
                })
                .thenCompose(f -> f);
    }

    private static void cleanupLosingOutgoingAttempt(ConnectionContext ctx, ConnectAttempt attempt) {
        ctx.releaseId(attempt.localId);
        ctx.unregisterHandler(attempt.localId);
        try { attempt.backStream.close(); } catch (Exception ignored) {}
    }

    private void handleWordRequest(String wordKey, LinkedBlockingQueue<TauSyncStream> channel,
                                   int localId, int peerSenderId, InputStream stream) {
        try {
            byte[] frame = buildOkFrame(wordKey, localId, peerSenderId);
            wifiTransport.sendRaw(frame).get();

            TauSyncStream duplex = new TauSyncStream(stream, localId, this);
            channel.offer(duplex);
        } catch (Exception ex) {
            ErrorListener listener = errorListener;
            if (listener != null) {
                listener.onError(ex instanceof Exception ? (Exception) ex : new RuntimeException(ex));
            }
        }
    }

    private byte[] buildOkFrame(String word, int localId, int peerSenderId) {
        TransferRequest ok = new TransferRequest();
        ok.setMagicBytes(CoreConfig.MAGIC_BYTES);
        ok.setSenderID(localId);
        ok.setType(word);
        ok.setStatus("OK");

        String json = gson.toJson(ok);
        byte[] body = json.getBytes(StandardCharsets.UTF_8);
        return protocolHandler.buildFrame(peerSenderId, body, CoreConfig.FLAG_CONTROL);
    }

    private CompletableFuture<Void> sendWordRequestAsync(String word, int localId) {
        TransferRequest request = new TransferRequest();
        request.setMagicBytes(CoreConfig.MAGIC_BYTES);
        request.setSenderID(localId);
        request.setType(word);
        request.setStatus("REQ");

        String json = gson.toJson(request);
        byte[] reqBody = json.getBytes(StandardCharsets.UTF_8);
        byte[] reqFrame = protocolHandler.buildFrame(CoreConfig.CONTROL_CHANNEL_ID, reqBody, CoreConfig.FLAG_CONTROL);
        return wifiTransport.sendRaw(reqFrame);
    }

    private CompletableFuture<TauSyncStream> waitForOkAndBuildStreamAsync(
            CompletableFuture<byte[]> responseTask,
            ConnectionContext ctx,
            int localId,
            BackBufferedInputStream backStream) {

        return responseTask.thenApply(payload -> {
            TransferRequest response = parseTransferResponse(payload);
            if (response == null || response.getStatus() == null
                    || !response.getStatus().trim().equalsIgnoreCase("OK")) {
                ctx.releaseId(localId);
                ctx.unregisterHandler(localId);
                try { backStream.close(); } catch (Exception ignored) {}
                throw new RuntimeException("Connect rejected by peer.");
            }
            ctx.setTargetForSend(localId, response.getSenderID());
            return new TauSyncStream(backStream, localId, this);
        });
    }

    // ── Stream Data ───────────────────────────────────────────────────

    @Override
    public void sendStreamData(int localId, byte[] buffer, int offset, int count) {
        if (disposed) throw new IllegalStateException("ConnectionManager is disposed.");
        if (wifiTransport == null) throw new IllegalStateException("Transport not initialized.");
        if (buffer == null) throw new IllegalArgumentException("buffer must not be null");
        if (offset < 0 || count < 0 || offset + count > buffer.length) {
            throw new IndexOutOfBoundsException("Invalid offset/count");
        }
        if (count == 0) return;

        Integer peerId = ConnectionContext.getInstance().getPeerIdFor(localId);
        if (peerId == null) {
            throw new IllegalStateException(
                    "No peer route for localId " + localId
                            + ". Handshake may not have completed; do not write before connect(word) finishes.");
        }

        byte[] chunk = new byte[count];
        System.arraycopy(buffer, offset, chunk, 0, count);
        byte[] frame = protocolHandler.buildFrame(peerId, chunk, (byte) 0);
        try {
            wifiTransport.sendRaw(frame).get();
        } catch (Exception e) {
            throw new RuntimeException("Failed to send stream data", e);
        }
    }

    @Override
    public CompletableFuture<Void> sendStreamDataAsync(int localId, byte[] buffer, int offset, int count) {
        if (disposed) {
            return CompletableFuture.failedFuture(new IllegalStateException("ConnectionManager is disposed."));
        }
        if (wifiTransport == null) {
            return CompletableFuture.failedFuture(new IllegalStateException("Transport not initialized."));
        }
        if (buffer == null) {
            return CompletableFuture.failedFuture(new IllegalArgumentException("buffer must not be null"));
        }
        if (offset < 0 || count < 0 || offset + count > buffer.length) {
            return CompletableFuture.failedFuture(new IndexOutOfBoundsException("Invalid offset/count"));
        }
        if (count == 0) return CompletableFuture.completedFuture(null);

        Integer peerId = ConnectionContext.getInstance().getPeerIdFor(localId);
        if (peerId == null) {
            return CompletableFuture.failedFuture(new IllegalStateException(
                    "No peer route for localId " + localId));
        }

        byte[] chunk = new byte[count];
        System.arraycopy(buffer, offset, chunk, 0, count);
        byte[] frame = protocolHandler.buildFrame(peerId, chunk, (byte) 0);
        return wifiTransport.sendRaw(frame);
    }

    @Override
    public void completeStream(int localId) {
        if (disposed) return;
        if (wifiTransport == null) return;

        Integer peerId = ConnectionContext.getInstance().getPeerIdFor(localId);
        if (peerId != null) {
            byte[] finFrame = protocolHandler.buildFrame(peerId, new byte[0], CoreConfig.FLAG_FIN);
            try {
                wifiTransport.sendRaw(finFrame).get();
            } catch (Exception ignored) {}
        }
        ConnectionContext.getInstance().releaseId(localId);
    }

    @Override
    public void setErrorListener(ErrorListener listener) {
        this.errorListener = listener;
    }

    // ── Lifecycle ─────────────────────────────────────────────────────

    @Override
    public void close() {
        if (disposed) return;
        disposed = true;
        incomingByWord.clear();
    }

    /**
     * Snapshot of words the peer has fired REQ for but we have not yet paired
     * with locally. Mirrors C# {@code ConnectionManager.GetPeerWaitingWords}.
     */
    public java.util.List<String> getPeerWaitingWords() {
        return ConnectionContext.getInstance().getPeerWaitingWords();
    }

    // ── Helpers ───────────────────────────────────────────────────────

    private TransferRequest parseTransferResponse(byte[] payload) {
        if (payload == null || payload.length == 0) return null;
        try {
            String json = new String(payload, StandardCharsets.UTF_8);
            return gson.fromJson(json, TransferRequest.class);
        } catch (Exception e) {
            return null;
        }
    }

    private static final class ConnectAttempt {
        final int localId;
        final BackBufferedInputStream backStream;
        final CompletableFuture<byte[]> responseFuture;

        ConnectAttempt(int localId, BackBufferedInputStream backStream,
                       CompletableFuture<byte[]> responseFuture) {
            this.localId = localId;
            this.backStream = backStream;
            this.responseFuture = responseFuture;
        }
    }
}
