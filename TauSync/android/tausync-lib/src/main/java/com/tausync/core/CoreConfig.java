package com.tausync.core;

/**
 * Protocol and implementation constants per TauSync Protocol Spec.
 * Matches C# CoreConfig (TPack header 8 bytes, CorrelationID 3 bytes, etc.).
 */
public final class CoreConfig {
    private CoreConfig() {}

    /** TPack header size in bytes (Length 4B + CorrelationID 3B + Flags 1B). */
    public static final int TPACK_HEADER_SIZE = 8;

    /** CorrelationID in header is 3 bytes (max 0xFFFFFF). */
    public static final int CORRELATION_ID_BYTES = 3;

    /** Control channel CorrelationID. */
    public static final int CONTROL_CHANNEL_ID = 0;

    /** FIN flag: bit 0 = 0x01. */
    public static final byte FLAG_FIN = 0x01;

    /** Stream chunk size for send/receive (64 KB). */
    public static final int STREAM_CHUNK_SIZE = 64 * 1024;

    /** Handshake timeout in seconds. */
    public static final int HANDSHAKE_TIMEOUT_SECONDS = 30;

    /** Default TCP port. */
    public static final int DEFAULT_PORT = 8888;
}
