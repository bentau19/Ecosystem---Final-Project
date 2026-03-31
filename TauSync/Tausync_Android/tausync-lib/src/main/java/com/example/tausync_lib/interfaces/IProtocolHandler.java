package com.example.tausync_lib.interfaces;

import com.example.tausync_lib.models.TransferRequest;

import java.util.concurrent.CompletableFuture;
import java.util.function.Function;
import java.util.function.Supplier;

/**
 * Protocol handler — framing, parsing, and handshake.
 *
 * <p>Implements the TPack wire format: 8-byte header
 * (Length 4B LE + TargetID 3B LE + Flags 1B) followed by payload bytes.
 * Matches C# IProtocolHandler.
 */
public interface IProtocolHandler {

    /** @return fixed header size in bytes (always 8) */
    int getHeaderSize();

    /**
     * Reads the payload length from a raw header.
     *
     * @param header at least {@link #getHeaderSize()} bytes
     * @return payload length (little-endian uint32 from bytes 0-3)
     */
    int getPayloadLength(byte[] header);

    /**
     * @return true when the frame is a control-channel frame (TargetID == 0)
     */
    boolean isControlFrame(int targetId, byte flags);

    /**
     * Constructs a complete TPack frame (header + payload).
     *
     * @param targetId receiver's local ID (0..0xFFFFFF)
     * @param payload  raw payload bytes
     * @param flags    bitmask (FIN, CONTROL, etc.)
     * @return the assembled frame
     */
    byte[] buildFrame(int targetId, byte[] payload, byte flags);

    /**
     * Convenience overload with flags = 0.
     */
    default byte[] buildFrame(int targetId, byte[] payload) {
        return buildFrame(targetId, payload, (byte) 0);
    }

    /**
     * Parses a complete raw frame into its components.
     *
     * @param rawPacket the full frame (header + payload)
     * @return parsed result containing targetId, payload, and flags
     */
    ParseResult parseFrame(byte[] rawPacket);

    /**
     * Builds and sends a signaling frame, then awaits and parses the response.
     *
     * @param request         the TransferRequest to serialise
     * @param sendRaw         function that sends raw bytes over the transport
     * @param receiveResponse supplier that awaits and returns the response payload
     * @return future containing the parsed response, or null on failure
     */
    CompletableFuture<TransferRequest> sendHandshakeAsync(
            TransferRequest request,
            Function<byte[], CompletableFuture<Void>> sendRaw,
            Supplier<CompletableFuture<byte[]>> receiveResponse);

    /**
     * Immutable result of {@link #parseFrame(byte[])}.
     */
    final class ParseResult {
        private final int targetId;
        private final byte[] payload;
        private final byte flags;

        public ParseResult(int targetId, byte[] payload, byte flags) {
            this.targetId = targetId;
            this.payload = payload;
            this.flags = flags;
        }

        public int getTargetId() { return targetId; }
        public byte[] getPayload() { return payload; }
        public byte getFlags() { return flags; }
    }
}
