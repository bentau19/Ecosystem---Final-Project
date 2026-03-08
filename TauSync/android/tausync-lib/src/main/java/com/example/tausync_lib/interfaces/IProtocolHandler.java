package com.tausync.interfaces;

import com.example.tausync_lib.models.TransferRequest;

import java.util.concurrent.CompletableFuture;
import java.util.function.Function;
import java.util.function.Supplier;

/**
 * Protocol handler — framing, parsing, and handshake (how data flows).
 * Does not decide which transport or when to connect; that is IConnectionManager's role.
 * Per TauSync Protocol Spec: 8-byte header (Length 4B + CorrelationID 3B + Flags 1B) + payload.
 * Matches C# IProtocolHandler.
 */
public interface IProtocolHandler {

    /**
     * Builds a TPack: 8-byte header (Length LE, CorrelationID 3B, Flags 1B) + payload.
     *
     * @param correlationId Stream/channel ID (0 = control). Java uses even IDs.
     * @param payload      Payload bytes (not encrypted in this pass).
     * @param flags        Flags byte (e.g. 0x01 for FIN). Default 0.
     * @return Complete TPack ready to send.
     */
    byte[] buildFrame(int correlationId, byte[] payload, byte flags);

    /**
     * Builds a TPack with flags = 0.
     */
    default byte[] buildFrame(int correlationId, byte[] payload) {
        return buildFrame(correlationId, payload, (byte) 0);
    }

    /**
     * Parses a complete TPack into CorrelationID, payload, and flags.
     *
     * @param rawPacket Full TPack (8-byte header + payload).
     * @return ParseResult with correlationId, payload, and flags (bit 0 = FIN).
     */
    ParseResult parseFrame(byte[] rawPacket);

    /**
     * Sends a TransferRequest on the control channel (CorrelationID 0) and waits for OK/REJECT.
     *
     * @param request         The request to send (serialized as JSON in payload).
     * @param sendRaw         Delegate to send raw TPack (async).
     * @param receiveResponse Delegate that returns the next control-channel payload (TPack with id 0).
     * @return CompletableFuture with true if response was "OK", false if "REJECT".
     */
    CompletableFuture<Boolean> sendHandshakeAsync(
            TransferRequest request,
            Function<byte[], CompletableFuture<Void>> sendRaw,
            Supplier<CompletableFuture<byte[]>> receiveResponse);

    /**
     * Result of parsing a TPack.
     */
    final class ParseResult {
        public final int correlationId;
        public final byte[] payload;
        public final byte flags;

        public ParseResult(int correlationId, byte[] payload, byte flags) {
            this.correlationId = correlationId;
            this.payload = payload;
            this.flags = flags;
        }
    }
}
