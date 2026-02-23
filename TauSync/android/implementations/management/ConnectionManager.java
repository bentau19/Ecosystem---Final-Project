package com.tausync.implementations.management;

import com.google.gson.Gson;
import com.tausync.implementations.transport.SocketTransport;
import com.tausync.interfaces.IConnectionManager;
import com.tausync.interfaces.ITransport;
import com.tausync.models.TransferRequest;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

/**
 * Connection manager implementation (no encryption version).
 */
public class ConnectionManager implements IConnectionManager {
    private static final long LARGE_FILE_THRESHOLD = 1024 * 1024; // 1MB

    private ITransport transport;
    private Gson gson;
    private RequestReceivedListener requestReceivedListener;
    private ErrorOccurredListener errorOccurredListener;

    public ConnectionManager() {
        this.gson = new Gson();
    }

    /**
     * Initializes the connection manager with transport (no secure channel needed).
     */
    public void initialize(ITransport transport) {
        if (transport == null) {
            throw new IllegalArgumentException("Transport cannot be null.");
        }

        this.transport = transport;

        // Set up transport listeners
        if (transport instanceof SocketTransport) {
            ((SocketTransport) transport).setDataReceivedListener(this::onTransportDataReceived);
        }
    }

    @Override
    public void smartSend(TransferRequest req) {
        if (req == null) {
            throw new IllegalArgumentException("Transfer request cannot be null.");
        }
        if (!req.isValid()) {
            throw new IllegalArgumentException("Transfer request is invalid.");
        }
        if (transport == null) {
            throw new IllegalStateException("Connection manager is not initialized. Call initialize() first.");
        }

        try {
            if (!transport.isConnected()) {
                throw new IllegalStateException("Transport is not connected.");
            }

            // No encryption - use payload as-is
            byte[] payload = req.getPayload();
            
            // Compress if needed (for large files)
            boolean shouldCompress = req.getPayloadSize() > LARGE_FILE_THRESHOLD && !req.isCompressed();
            if (shouldCompress) {
                payload = compress(payload);
            }

            req.setPayload(payload);
            req.setCompressed(shouldCompress || req.isCompressed());

            // Serialize to JSON
            String json = gson.toJson(req);
            byte[] jsonBytes = json.getBytes("UTF-8");

            // Send via transport
            transport.sendRaw(jsonBytes);
        } catch (Exception ex) {
            notifyErrorOccurred(ex);
            throw new IllegalStateException("Failed to send transfer request.", ex);
        }
    }

    @Override
    public void handleIncoming(byte[] rawData) {
        if (rawData == null) {
            throw new IllegalArgumentException("Raw data cannot be null.");
        }
        if (transport == null) {
            throw new IllegalStateException("Connection manager is not initialized. Call initialize() first.");
        }

        try {
            String json = new String(rawData, "UTF-8");
            TransferRequest req = gson.fromJson(json, TransferRequest.class);

            if (req == null) {
                throw new IllegalStateException("Failed to deserialize transfer request.");
            }
            if (!req.isValid()) {
                throw new IllegalStateException("Received invalid transfer request.");
            }

            // Decompress if needed
            if (req.isCompressed()) {
                req.setPayload(decompress(req.getPayload()));
                req.setCompressed(false);
            }

            // No decryption needed - payload is already plaintext
            notifyRequestReceived(req);
        } catch (Exception ex) {
            notifyErrorOccurred(ex);
            throw new IllegalStateException("Failed to process incoming data.", ex);
        }
    }

    @Override
    public void setRequestReceivedListener(RequestReceivedListener listener) {
        this.requestReceivedListener = listener;
    }

    @Override
    public void setErrorOccurredListener(ErrorOccurredListener listener) {
        this.errorOccurredListener = listener;
    }

    private byte[] compress(byte[] data) {
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            try (GZIPOutputStream gzipOut = new GZIPOutputStream(baos)) {
                gzipOut.write(data);
            }
            return baos.toByteArray();
        } catch (IOException ex) {
            throw new IllegalStateException("Compression failed.", ex);
        }
    }

    private byte[] decompress(byte[] compressedData) {
        try {
            ByteArrayInputStream bais = new ByteArrayInputStream(compressedData);
            try (GZIPInputStream gzipIn = new GZIPInputStream(bais);
                 ByteArrayOutputStream baos = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[1024];
                int len;
                while ((len = gzipIn.read(buffer)) != -1) {
                    baos.write(buffer, 0, len);
                }
                return baos.toByteArray();
            }
        } catch (IOException ex) {
            throw new IllegalStateException("Decompression failed.", ex);
        }
    }

    private void onTransportDataReceived(byte[] data) {
        handleIncoming(data);
    }

    private void notifyRequestReceived(TransferRequest req) {
        if (requestReceivedListener != null) {
            requestReceivedListener.onRequestReceived(req);
        }
    }

    private void notifyErrorOccurred(Exception ex) {
        if (errorOccurredListener != null) {
            errorOccurredListener.onErrorOccurred(ex);
        }
    }
}
