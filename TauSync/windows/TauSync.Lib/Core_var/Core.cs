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
        /// <summary>TPack header size in bytes (Length 4B + CorrelationID 3B + Flags 1B).</summary>
        public const int TPackHeaderSize = 8;

        /// <summary>CorrelationID in header is 3 bytes (max 0xFFFFFF).</summary>
        public const int CorrelationIdBytes = 3;

        /// <summary>Control channel CorrelationID.</summary>
        public const int ControlChannelId = 0;

        /// <summary>FIN flag: bit 0 = 0x01.</summary>
        public const byte FlagFin = 0x01;

        /// <summary>Stream chunk size for send/receive (64 KB).</summary>
        public const int StreamChunkSize = 64 * 1024;

        /// <summary>Handshake timeout in seconds.</summary>
        public const int HandshakeTimeoutSeconds = 30;

        /// <summary>Default TCP port.</summary>
        public const int DefaultPort = 8888;
    }
}
