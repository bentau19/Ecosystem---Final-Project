using System;
using System.Threading.Tasks;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Identifies which physical medium an <see cref="ITransport"/> carries bytes over.
    /// Lets higher layers (e.g. HybridConnectionManager) tell the two transports apart.
    /// </summary>
    public enum TransportKind { WiFi, Bluetooth }

    /// <summary>
    /// Transport layer interface — manages the physical connection.
    /// Implement as a singleton per medium (Bluetooth, WiFi).
    /// Per TauSync Protocol Spec: raw bytes only; framing and reassembly are defined here.
    /// </summary>
    public interface ITransport : IDisposable
    {
        /// <summary>The physical medium this transport carries bytes over.</summary>
        TransportKind TransportType { get; }

        /// <summary>
        /// True when this transport accepted a connection (server mode), false when it initiated one
        /// (client mode). Used by ConnectionManager for the simultaneous-connect race tiebreaker and
        /// by the hybrid coordinator to derive the Wi-Fi server/client role from the Bluetooth role.
        /// </summary>
        bool IsServerMode { get; }

        /// <summary>
        /// Connects to the target. When <paramref name="targetId"/> is null or empty, acts as server: listens and waits for the first incoming connection.
        /// </summary>
        /// <param name="targetId">IP address of the peer (client mode), or null/empty for server mode.</param>
        /// <returns>Task that completes when connected.</returns>
        Task Connect(string? targetId, int? timeoutSeconds = null);

        public void Disconnect();
        /// <summary>
        /// Sends raw binary data (full TPack: 8-byte header + payload). No extra length prefix.
        /// </summary>
        /// <param name="data">The complete TPack to send.</param>
        /// <returns>Task that completes when send is done.</returns>
        Task SendRaw(byte[] data);

        /// <summary>
        /// Returns the current connection status.
        /// </summary>
        bool IsConnected();

        /// <summary>
        /// Fired when a complete TPack has been received (after reassembly: 8-byte header + Length bytes payload).
        /// </summary>
        event EventHandler<byte[]>? OnDataReceived;
    }
}
