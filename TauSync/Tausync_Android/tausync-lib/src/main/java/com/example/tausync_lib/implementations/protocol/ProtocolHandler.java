package com.example.tausync_lib.implementations.protocol;

import com.example.tausync_lib.core.CoreConfig;
import com.example.tausync_lib.implementations.management.ConnectionContext;
import com.example.tausync_lib.interfaces.IProtocolHandler;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;
import java.util.function.Supplier;

/**
 * Implements TauSync TPack: 8-byte header (Length 4B LE + TargetID 3B LE + Flags 1B) + payload.
 * Matches C# ProtocolHandler.
 */
public class ProtocolHandler implements IProtocolHandler {

    private final Gson gson = new Gson();

    @Override
    public byte[] buildFrame(int targetId, byte[] payload, byte flags) {
        if (payload == null) {
            throw new IllegalArgumentException("payload must not be null");
        }
        if (targetId < 0 || targetId > 0xFFFFFF) {
            throw new IllegalArgumentException("TargetID must fit in 3 bytes (0..0xFFFFFF), got: " + targetId);
        }

        // Encrypt the payload only (no-op until the session key is active, and for empty payloads / the
        // key-exchange frames). The header is built over the resulting ciphertext length and always stays
        // plaintext, so the receiver routes by TargetID/flags without decrypting.
        payload = ConnectionContext.getInstance().encryptPayload(payload);

        int len = payload.length;
        byte[] frame = new byte[CoreConfig.TPACK_HEADER_SIZE + len];
        frame[0] = (byte) (len & 0xFF);
        frame[1] = (byte) ((len >> 8) & 0xFF);
        frame[2] = (byte) ((len >> 16) & 0xFF);
        frame[3] = (byte) ((len >> 24) & 0xFF);
        frame[4] = (byte) (targetId & 0xFF);
        frame[5] = (byte) ((targetId >> 8) & 0xFF);
        frame[6] = (byte) ((targetId >> 16) & 0xFF);
        frame[7] = flags;

        if (len > 0) {
            System.arraycopy(payload, 0, frame, CoreConfig.TPACK_HEADER_SIZE, len);
        }
        return frame;
    }

    @Override
    public ParseResult parseFrame(byte[] rawPacket) {
        if (rawPacket == null) {
            throw new IllegalArgumentException("rawPacket must not be null");
        }
        if (rawPacket.length < CoreConfig.TPACK_HEADER_SIZE) {
            throw new IllegalArgumentException(
                    "Packet too small: need at least " + CoreConfig.TPACK_HEADER_SIZE + " bytes, got " + rawPacket.length);
        }

        int length = (rawPacket[0] & 0xFF)
                | ((rawPacket[1] & 0xFF) << 8)
                | ((rawPacket[2] & 0xFF) << 16)
                | ((rawPacket[3] & 0xFF) << 24);

        int targetId = (rawPacket[4] & 0xFF)
                | ((rawPacket[5] & 0xFF) << 8)
                | ((rawPacket[6] & 0xFF) << 16);

        byte flags = rawPacket[7];

        if (rawPacket.length != CoreConfig.TPACK_HEADER_SIZE + length) {
            throw new IllegalArgumentException(
                    "Packet length mismatch: header says payload " + length + ", total bytes " + rawPacket.length);
        }

        byte[] payload = new byte[length];
        if (length > 0) {
            System.arraycopy(rawPacket, CoreConfig.TPACK_HEADER_SIZE, payload, 0, length);
        }
        return new ParseResult(targetId, payload, flags);
    }

    @Override
    public int getHeaderSize() {
        return CoreConfig.TPACK_HEADER_SIZE;
    }

    @Override
    public int getPayloadLength(byte[] header) {
        if (header == null || header.length < CoreConfig.TPACK_HEADER_SIZE) {
            return 0;
        }
        return (header[0] & 0xFF)
                | ((header[1] & 0xFF) << 8)
                | ((header[2] & 0xFF) << 16)
                | ((header[3] & 0xFF) << 24);
    }

    @Override
    public boolean isControlFrame(int targetId, byte flags) {
        return targetId == CoreConfig.CONTROL_CHANNEL_ID;
    }

    @Override
    public CompletableFuture<TransferRequest> sendHandshakeAsync(
            TransferRequest request,
            Function<byte[], CompletableFuture<Void>> sendRaw,
            Supplier<CompletableFuture<byte[]>> receiveResponse) {

        if (request == null) throw new IllegalArgumentException("request must not be null");
        if (sendRaw == null) throw new IllegalArgumentException("sendRaw must not be null");
        if (receiveResponse == null) throw new IllegalArgumentException("receiveResponse must not be null");
        if (!request.isValid()) throw new IllegalArgumentException("TransferRequest is invalid");

        String json = gson.toJson(request);
        byte[] jsonBytes = json.getBytes(StandardCharsets.UTF_8);
        byte[] frame = buildFrame(CoreConfig.CONTROL_CHANNEL_ID, jsonBytes, CoreConfig.FLAG_CONTROL);

        return sendRaw.apply(frame)
                .thenCompose(ignored -> receiveResponse.get())
                .thenApply(responsePayload -> {
                    if (responsePayload == null || responsePayload.length == 0) {
                        return null;
                    }
                    try {
                        String responseJson = new String(responsePayload, StandardCharsets.UTF_8);
                        return gson.fromJson(responseJson, TransferRequest.class);
                    } catch (Exception e) {
                        return null;
                    }
                });
    }
}
