namespace TauSync.Core
{
    /// <summary>
    /// Connection state for UI/diagnostics (optional).
    /// </summary>
    public enum ConnectionStatus
    {
        Disconnected,
        Scanning,
        Connecting,
        Connected,
        Error
    }

    /// <summary>
    /// Protocol and implementation constants per TauSync Protocol Spec.
    /// </summary>
    public static class CoreConfig
    {
        /// <summary>TPack header size in bytes (Length 4B + TargetID 3B + Flags 1B).</summary>
        public const int TPackHeaderSize = 8;

        /// <summary>TargetID in header is 3 bytes (max 0xFFFFFF).</summary>
        public const int CorrelationIdBytes = 3;

        public const uint MagicBytes = 0x54415553;
        /// <summary>Control channel / discovery: TargetID = 0.</summary>
        public const int ControlChannelId = 0;

        /// <summary>FIN flag: bit 0 = 0x01.</summary>
        public const byte FlagFin = 0x01;

        /// <summary>CONTROL flag: bit 1 = 0x02. Payload is TransferRequest JSON when set.</summary>
        public const byte FlagControl = 0x02;

        /// <summary>Stream chunk size for send/receive (64 KB).</summary>
        public const int StreamChunkSize = 64 * 1024;

        /// <summary>Handshake timeout in seconds.</summary>
        public const int HandshakeTimeoutSeconds = 30;

        /// <summary>Default TCP port.</summary>
        public const int DefaultPort = 8888;
        public const int ClientConnectRetryDelaySeconds = 2;

        /// <summary>
        /// First delay before retrying after an unexpected transport drop. Each subsequent
        /// retry doubles the wait up to <see cref="ReconnectMaxDelayMs"/>. Reconnect keeps
        /// retrying until it succeeds or the app explicitly disconnects — an unexpected drop
        /// never ends the session.
        /// </summary>
        public const int ReconnectInitialDelayMs = 1_000;

        /// <summary>Cap on the exponential reconnect back-off between retry attempts.</summary>
        public const int ReconnectMaxDelayMs = 30_000;

        /// <summary>
        /// Max time a queued send waits for the transport to come back after an unexpected
        /// drop before failing. Lets a write issued mid-reconnect resume transparently.
        /// </summary>
        public const int SendReconnectWaitMs = 30_000;

        /// <summary>
        /// Maximum accepted payload size per frame (16 MB). A peer can advertise any 32-bit
        /// payload length in the header; without this cap a crafted header could trigger a
        /// multi-gigabyte allocation and OOM the receiver.
        /// </summary>
        public const int MaxPayloadSize = 16 * 1024 * 1024;

        // ── Bluetooth transport (must match Android CoreConfig) ──────────────

        /// <summary>BLE service UUID advertised by Windows for first-time discovery/pairing.</summary>
        public static readonly Guid BleServiceUuid = new Guid("12345678-1234-5678-1234-56789abcde01");

        /// <summary>RFCOMM service UUID both platforms use for SDP lookup of the data channel.</summary>
        public static readonly Guid RfcommServiceUuid = new Guid("12345678-1234-5678-1234-56789abcde02");

        /// <summary>Max time to wait for an RFCOMM connection to establish.</summary>
        public const int BtConnectTimeoutMs = 15_000;

        /// <summary>Max time the Wi-Fi client waits for SESSION_JOIN_ACK after joining.</summary>
        public const int SessionJoinAckTimeoutMs = 10_000;

        /// <summary>
        /// Hybrid routing threshold (64 KB): payloads at or below this size are sent over the
        /// Bluetooth (primary) transport; larger payloads trigger the lazy Wi-Fi connect and are
        /// sent over Wi-Fi. The constant exists so the cutoff can be tuned without touching logic.
        /// </summary>
        public const int HybridSmallThresholdBytes = 65_536;

        /// <summary>
        /// Default chunk size for bulk file transfers (256 KB). Deliberately larger than
        /// <see cref="HybridSmallThresholdBytes"/> so that, in hybrid mode, each file chunk crosses the
        /// threshold and the stream is routed over the high-throughput Wi-Fi link — whereas small
        /// writes (strings, control) stay below it and ride Bluetooth. Keep this strictly greater than
        /// the threshold or file transfers will fall back to Bluetooth.
        /// </summary>
        public const int LargeTransferChunkSize = 4 * StreamChunkSize;

        /// <summary>
        /// How long the Wi-Fi link may sit with no received frame before the hybrid manager
        /// disconnects it (60 s). Bluetooth stays up; the next large payload re-runs the
        /// WIFI_CONNECT_REQ handshake from scratch.
        /// </summary>
        public const int WifiIdleTimeoutMs = 60_000;

        /// <summary>
        /// How many times <see cref="ConnectionManager.Connect"/> retries automatically after a
        /// handshake timeout before giving up. Each attempt uses <see cref="HandshakeTimeoutSeconds"/>,
        /// so the total maximum wait is (ConnectRetryCount + 1) × HandshakeTimeoutSeconds.
        /// </summary>
        public const int ConnectRetryCount = 3;

        /// <summary>
        /// How many times the hybrid coordinator retries bringing Wi-Fi up before falling back to
        /// Bluetooth for the current send. Each attempt waits up to <see cref="BtConnectTimeoutMs"/>.
        /// </summary>
        public const int WifiReconnectMaxAttempts = 3;
    }
}
