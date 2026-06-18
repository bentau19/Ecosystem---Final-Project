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

    /**
     * First delay before retrying after an unexpected transport drop. Each subsequent
     * retry doubles the wait up to {@link #RECONNECT_MAX_DELAY_MS}. Reconnect keeps
     * retrying until it succeeds or the app explicitly disconnects — an unexpected drop
     * never ends the session.
     */
    public static final int RECONNECT_INITIAL_DELAY_MS = 1_000;

    /** Cap on the exponential reconnect back-off between retry attempts. */
    public static final int RECONNECT_MAX_DELAY_MS = 30_000;

    /**
     * Max time a queued send waits for the transport to come back after an unexpected
     * drop before failing. Lets a write issued mid-reconnect resume transparently.
     */
    public static final int SEND_RECONNECT_WAIT_MS = 30_000;

    /** Max queued REQs per word before the service is registered. */
    public static final int MAX_PENDING_DISCOVERY_PER_WORD = 64;

    /** Minimum valid local ID (0 is reserved for control channel). */
    public static final int MIN_ID = 1;

    /** Maximum valid local ID (3-byte uint24). */
    public static final int MAX_ID = 0xFFFFFF;

    /**
     * Maximum accepted payload size per frame (16 MB). A peer can advertise any 32-bit
     * payload length in the header; without this cap a crafted header could trigger a
     * multi-gigabyte allocation and OOM the receiver.
     */
    public static final int MAX_PAYLOAD_SIZE = 16 * 1024 * 1024;

    // ── Bluetooth transport (must match Windows CoreConfig) ──────────────

    /** BLE service UUID advertised by Windows for first-time discovery/pairing. */
    public static final String BLE_SERVICE_UUID = "12345678-1234-5678-1234-56789abcde01";

    /** RFCOMM service UUID both platforms use for SDP lookup of the data channel. */
    public static final String RFCOMM_SERVICE_UUID = "12345678-1234-5678-1234-56789abcde02";

    /** Max time to wait for an RFCOMM connection to establish. */
    public static final int BT_CONNECT_TIMEOUT_MS = 15_000;

    /** Max time the Wi-Fi client waits for SESSION_JOIN_ACK after joining. */
    public static final int SESSION_JOIN_ACK_TIMEOUT_MS = 10_000;

    /**
     * Guide threshold (64 KB) the app uses to pick the Eco (BT) vs Performance (Wi-Fi)
     * manager per channel in Hybrid mode. HybridConnectionManager never routes on this.
     */
    public static final int HYBRID_SMALL_THRESHOLD_BYTES = 65_536;
}
