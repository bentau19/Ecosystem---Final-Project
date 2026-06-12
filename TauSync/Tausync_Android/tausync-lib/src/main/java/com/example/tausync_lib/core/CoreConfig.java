package com.example.tausync_lib.core;

/**
 * Protocol and implementation constants per TauSync Protocol Spec v3.1.
 * Both platforms (C# and Java) must use identical values.
 */
public final class CoreConfig {

    private CoreConfig() {}

    /** TPack header size in bytes: 4B length + 3B TargetID + 1B flags. */
    public static final int TPACK_HEADER_SIZE = 8;

    /** TargetID field width in bytes (max value 0xFFFFFF). */
    public static final int CORRELATION_ID_BYTES = 3;

    /** ASCII "TAUS" — protocol identity in every signaling JSON. */
    public static final long MAGIC_BYTES = 0x54415553L;

    /** Reserved TargetID for discovery/handshake frames. */
    public static final int CONTROL_CHANNEL_ID = 0;

    /** Bit 0 — final packet of a logical stream. Triggers cleanup. */
    public static final byte FLAG_FIN = 0x01;

    /** Bit 1 — payload is a TransferRequest JSON (signaling). */
    public static final byte FLAG_CONTROL = 0x02;

    /** Recommended max payload per data frame (64 KB). */
    public static final int STREAM_CHUNK_SIZE = 64 * 1024;

    /** Max time to wait for a handshake OK before timing out. */
    public static final int HANDSHAKE_TIMEOUT_SECONDS = 30;

    /** TCP port used by SocketTransport. */
    public static final int DEFAULT_PORT = 8888;

    /** Delay between TCP connection retries in client mode. */
    public static final int CLIENT_CONNECT_RETRY_DELAY_SECONDS = 2;

    /** Max queued REQs per word before the service is registered. */
    public static final int MAX_PENDING_DISCOVERY_PER_WORD = 64;

    /** Minimum valid local ID (0 is reserved for control channel). */
    public static final int MIN_ID = 1;

    /** Maximum valid local ID (3-byte uint24). */
    public static final int MAX_ID = 0xFFFFFF;
}
