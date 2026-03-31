using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Connection manager per TauSync v3: transport connect and word-based Listen/Connect.
    /// </summary>
    public interface IConnectionManager : IDisposable
    {
        /// <summary>
        /// Initializes the manager with the transport to use. Call once before ConnectTransport / Listen / Connect.
        /// </summary>
        void Initialize(ITransport transport);

        /// <summary>
        /// Connects at transport level. Pass null or empty for server (listen for one client); otherwise client to that address.
        /// </summary>
        Task ConnectTransport(string? targetId);

        /// <summary>
        /// Returns whether the underlying transport is connected.
        /// </summary>
        bool IsConnected();

        /// <summary>
        /// Connects on a Meeting Word. Both sides call Connect with the same word; when two peers have called
        /// Connect with the same word they are paired and each gets a duplex stream to the other. No Listen or Accept.
        /// </summary>
        /// <param name="word">Meeting Word (e.g. "CLIPBOARD"). Case-insensitive.</param>
        /// <returns>A duplex stream to the peer that connected on the same word.</returns>
        Task<Stream> Connect(string word);

        /// <summary>
        /// Fired when an error occurs (e.g. handshake timeout, reject, dispatch failure).
        /// </summary>
        event EventHandler<Exception>? ErrorOccurred;

        /// <summary>
        /// Sends data over an existing logical stream identified by localId.
        /// </summary>
        void SendStreamData(int localId, byte[] buffer, int offset, int count);

        /// <summary>
        /// Sends data over an existing logical stream identified by localId (async).
        /// </summary>
        Task SendStreamDataAsync(int localId, byte[] buffer, int offset, int count, CancellationToken cancellationToken);

        /// <summary>
        /// Completes a logical stream by sending FIN and releasing local resources.
        /// </summary>
        void CompleteStream(int localId);
    }
}
