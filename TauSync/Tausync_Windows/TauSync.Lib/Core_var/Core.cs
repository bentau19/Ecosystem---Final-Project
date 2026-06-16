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
        /// Maximum accepted payload size per frame (16 MB). A peer can advertise any 32-bit
        /// payload length in the header; without this cap a crafted header could trigger a
        /// multi-gigabyte allocation and OOM the receiver.
        /// </summary>
        public const int MaxPayloadSize = 16 * 1024 * 1024;
    }
}
