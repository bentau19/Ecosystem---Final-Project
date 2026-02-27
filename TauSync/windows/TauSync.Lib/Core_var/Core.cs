namespace TauSync.Core
{
    // הגדרת הטיפוס הספציפי
    public enum ConnectionStatus
    {
        Disconnected,
        Scanning,
        Connecting,
        Connected,
        Error
    }

    /// <summary>
    /// Core configuration and protocol constants shared across TauSync.
    /// </summary>
    public static class CoreConfig
    {
        /// <summary>
        /// Threshold above which files will be sent using streaming (in bytes).
        /// </summary>
        public static readonly long LargeFileThreshold = 1024 * 1024; // 1MB

        /// <summary>
        /// Default chunk size used for streaming (in bytes).
        /// </summary>
        public static readonly int StreamChunkSize = 64 * 1024; // 64KB chunks for streaming

        /// <summary>
        /// Handshake timeout in seconds.
        /// </summary>
        public static readonly int HandshakeTimeoutSeconds = 30;


        
        public static readonly int DefaultPort = 8888;
        public static readonly int StreamingThreshold = 1024 * 1024; // 1MB - switch to streaming mode
        public static readonly int ChunkBufferSize = 64 * 1024; // 64KB chunks for streaming
        public static readonly int CorrelationIdLength = 16;
    }
}