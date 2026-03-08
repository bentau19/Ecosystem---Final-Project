package com.example.tausync_lib.implementations.protocol;

import com.tausync.core.CoreConfig;
import com.tausync.interfaces.IProtocolHandler;
import com.example.tausync_lib.models.TransferRequest;
import com.google.gson.Gson;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;
import java.util.function.Supplier;

/**
 * Implements TauSync TPack: 8-byte header (Length 4B LE + CorrelationID 3B + Flags 1B) + payload.
 * Handshake on control channel (CorrelationID 0). No encryption in this implementation.
 * Matches C# ProtocolHandler.
 */
public class ProtocolHandler implements IProtocolHandler {

    private final Gson gson = new Gson();

    @Override
    public byte[] buildFrame(int correlationId, byte[] payload, byte flags) {
        if (payload == null) {
            throw new IllegalArgumentException("payload cannot be null");
        }
        if (correlationId < 0 || correlationId > 0xFFFFFF) {
            throw new IllegalArgumentException("CorrelationID must fit in 3 bytes (0..0xFFFFFF)");
        }
        byte[] header = new byte[CoreConfig.TPACK_HEADER_SIZE];
        int len = payload.length;
        header[0] = (byte) (len & 0xFF);
        header[1] = (byte) ((len >> 8) & 0xFF);
        header[2] = (byte) ((len >> 16) & 0xFF);
        header[3] = (byte) ((len >> 24) & 0xFF);
        header[4] = (byte) (correlationId & 0xFF);
        header[5] = (byte) ((correlationId >> 8) & 0xFF);
        header[6] = (byte) ((correlationId >> 16) & 0xFF);
        header[7] = flags;

        byte[] frame = new byte[CoreConfig.TPACK_HEADER_SIZE + payload.length];
        System.arraycopy(header, 0, frame, 0, CoreConfig.TPACK_HEADER_SIZE);
        System.arraycopy(payload, 0, frame, CoreConfig.TPACK_HEADER_SIZE, payload.length);
        return frame;
    }

    @Override
    public ParseResult parseFrame(byte[] rawPacket) {
        if (rawPacket == null) {
            throw new IllegalArgumentException("rawPacket cannot be null");
        }
        if (rawPacket.length < CoreConfig.TPACK_HEADER_SIZE) {
            throw new IllegalArgumentException("Packet too small: need at least " + CoreConfig.TPACK_HEADER_SIZE + " bytes");
        }
        int length = (rawPacket[0] & 0xFF) | ((rawPacket[1] & 0xFF) << 8) | ((rawPacket[2] & 0xFF) << 16) | ((rawPacket[3] & 0xFF) << 24);
        int correlationId = (rawPacket[4] & 0xFF) | ((rawPacket[5] & 0xFF) << 8) | ((rawPacket[6] & 0xFF) << 16);
        byte flags = rawPacket[7];

        if (rawPacket.length != CoreConfig.TPACK_HEADER_SIZE + length) {
            throw new IllegalArgumentException("Packet length mismatch: header says payload length " + length + ", total bytes " + rawPacket.length);
        }
        byte[] payload = new byte[length];
        if (length > 0) {
            System.arraycopy(rawPacket, CoreConfig.TPACK_HEADER_SIZE, payload, 0, length);
        }
        return new ParseResult(correlationId, payload, flags);
    }

    @Override
    public CompletableFuture<Boolean> sendHandshakeAsync(
            TransferRequest request,
            Function<byte[], CompletableFuture<Void>> sendRaw,
            Supplier<CompletableFuture<byte[]>> receiveResponse) {
        if (request == null) throw new IllegalArgumentException("request cannot be null");
        if (sendRaw == null) throw new IllegalArgumentException("sendRaw cannot be null");
        if (receiveResponse == null) throw new IllegalArgumentException("receiveResponse cannot be null");
        if (!request.isValid()) throw new IllegalArgumentException("TransferRequest is invalid");

        String json = gson.toJson(request);
        byte[] jsonBytes = json.getBytes(StandardCharsets.UTF_8);
        byte[] frame = buildFrame(CoreConfig.CONTROL_CHANNEL_ID, jsonBytes, (byte) 0);

        return sendRaw.apply(frame)
                .thenCompose(v -> receiveResponse.get())
                .thenApply(responsePayload -> {
                    String jsonResponse = new String(responsePayload, StandardCharsets.UTF_8);
                    TransferRequest response = gson.fromJson(jsonResponse, TransferRequest.class);
                    return response != null && "OK".equalsIgnoreCase(response.getStatus());
                });
    }
}
