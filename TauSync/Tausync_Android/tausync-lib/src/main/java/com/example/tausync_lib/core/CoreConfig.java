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

    /**
     * Bit 2 — BARRIER: an empty channel frame the sender emits on the link it is leaving when a stream
     * switches transports. It asks the peer to confirm (via {@link #FLAG_BARRIER_ACK}) that it has
     * drained this channel's data on that link, so the new (faster) link's data cannot overtake the old
     * link's data at the receiver.
     */
    public static final byte FLAG_BARRIER = 0x04;

    /** Bit 3 — BARRIER_ACK: the peer's reply to a {@link #FLAG_BARRIER} frame. */
    public static final byte FLAG_BARRIER_ACK = 0x08;

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

    /**
     * BLE discovery beacon — Windows advertises this as manufacturer-specific data and Android filters
     * on it (instead of a 128-bit service UUID, which WinRT legacy advertising cannot carry). 0xFFFF is
     * the reserved internal/interoperability-test company ID; payload "TAUS" is the TauSync magic.
     * Must match Windows {@code BleBeaconCompanyId} / {@code BleBeaconPayload}.
     */
    public static final int BLE_BEACON_COMPANY_ID = 0xFFFF;
    public static final byte[] BLE_BEACON_PAYLOAD = { 0x54, 0x41, 0x55, 0x53 }; // "TAUS"

    /** RFCOMM service UUID both platforms use for SDP lookup of the data channel. */
    public static final String RFCOMM_SERVICE_UUID = "12345678-1234-5678-1234-56789abcde02";

    /** Max time to wait for an RFCOMM connection to establish. */
    public static final int BT_CONNECT_TIMEOUT_MS = 15_000;

    /** Max time the Wi-Fi client waits for SESSION_JOIN_ACK after joining. */
    public static final int SESSION_JOIN_ACK_TIMEOUT_MS = 10_000;

    /**
     * Max time a transport switch waits for the peer's BARRIER_ACK before proceeding anyway. On
     * timeout the send continues (degrading to the unordered cross-transport behaviour) rather than
     * hanging — a lost ACK must never deadlock a write.
     */
    public static final int BARRIER_ACK_TIMEOUT_MS = 5_000;

    /**
     * Hybrid routing threshold: payloads at or below this size go over the Bluetooth (primary)
     * transport; larger payloads trigger the lazy Wi-Fi connect and are sent over Wi-Fi. Set to one
     * byte below a full wire chunk so that any payload of {@link #STREAM_CHUNK_SIZE} (64 KB) or more —
     * including everything previously sent at the old 64 KB default — routes over Wi-Fi, while smaller
     * messages (strings, control) stay on Bluetooth.
     */
    public static final int HYBRID_SMALL_THRESHOLD_BYTES = STREAM_CHUNK_SIZE - 1;

    /**
     * Default chunk size for bulk file transfers (256 KB). Deliberately larger than
     * {@link #HYBRID_SMALL_THRESHOLD_BYTES} so that, in hybrid mode, each file chunk crosses the
     * threshold and the stream is routed over the high-throughput Wi-Fi link — whereas small writes
     * (strings, control) stay below it and ride Bluetooth. Keep this strictly greater than the
     * threshold or file transfers will fall back to Bluetooth.
     */
    public static final int LARGE_TRANSFER_CHUNK_SIZE = 4 * STREAM_CHUNK_SIZE;

    /**
     * How long the Wi-Fi link may sit with no received frame before the hybrid manager
     * disconnects it (60 s). Bluetooth stays up; the next large payload re-runs the
     * WIFI_CONNECT_REQ handshake from scratch.
     */
    public static final int WIFI_IDLE_TIMEOUT_MS = 60_000;

    /**
     * How many times {@code ConnectionManager.connect} retries automatically after a handshake
     * timeout before giving up. Total maximum wait = (CONNECT_RETRY_COUNT + 1) × HANDSHAKE_TIMEOUT_SECONDS.
     */
    public static final int CONNECT_RETRY_COUNT = 3;

    /**
     * How many times the hybrid coordinator retries bringing Wi-Fi up before falling back to
     * Bluetooth for the current send. Each attempt waits up to BT_CONNECT_TIMEOUT_MS.
     */
    public static final int WIFI_RECONNECT_MAX_ATTEMPTS = 3;
}
