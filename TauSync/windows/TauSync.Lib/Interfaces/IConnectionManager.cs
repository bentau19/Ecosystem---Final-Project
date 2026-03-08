using System;
using System.IO;
using System.Threading.Tasks;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Connection manager — which connection and when; dispatcher and routing map.
    /// Routes incoming TPack by CorrelationID to registered handlers. Control channel = 0.
    /// Per TauSync Protocol Spec: Routing Map maps int CorrelationID to Action&lt;byte[]&gt;.
    /// </summary>
    public interface IConnectionManager : IDisposable
    {
        /// <summary>
        /// Initializes the manager with the transport to use. Subscribes to transport.OnDataReceived
        /// and performs TPack reassembly and dispatch. Use this when the caller provides the transport.
        /// Alternatively, use <see cref="Connect"/> to let the manager create and own the transport.
        /// </summary>
        /// <param name="transport">The transport (e.g. SocketTransport).</param>
        void Initialize(ITransport transport);

        /// <summary>
        /// Connects to the target by creating and managing the transport internally.
        /// Pass null or empty <paramref name="targetId"/> for server mode (wait for incoming connection).
        /// </summary>
        /// <param name="targetId">Target address (client mode), or null/empty for server mode.</param>
        /// <returns>Task that completes when connected.</returns>
        Task Connect(string? targetId);

        /// <summary>
        /// Returns whether the underlying transport is connected.
        /// </summary>
        bool IsConnected();

        /// <summary>
        /// Pushes data: handshake on channel 0, then streams content on a dedicated CorrelationID.
        /// </summary>
        /// <param name="source">Stream to read from (e.g. clipboard content).</param>
        /// <param name="type">Task type (e.g. "CLIPBOARD").</param>
        /// <param name="payload">Optional JSON (e.g. {"FileName": "x"}).</param>
        /// <returns>Task that completes when the transfer is finished.</returns>
        Task SmartSend(Stream source, string type, string? payload = null);

        /// <summary>
        /// Pulls data: double handshake on channel 0, then returns a stream fed by incoming TPack for the agreed CorrelationID.
        /// </summary>
        /// <param name="type">Task type (e.g. "BACKUP").</param>
        /// <param name="payload">Optional JSON (e.g. {"FileName": "target.jpg"}).</param>
        /// <returns>A stream that can be read as data arrives.</returns>
        Task<Stream> GetStream(string type, string? payload = null);

        /// <summary>
        /// Registers a handler for a CorrelationID. When a TPack arrives with that ID, payload is passed to the callback.
        /// </summary>
        /// <param name="correlationId">Channel/stream ID.</param>
        /// <param name="callback">Invoked with (decrypted) payload for that channel.</param>
        void RegisterHandler(int correlationId, Action<byte[]> callback);

        /// <summary>
        /// Unregisters the handler for the given CorrelationID (e.g. after FIN or error).
        /// </summary>
        void UnregisterHandler(int correlationId);

        /// <summary>
        /// Fired when an error occurs (e.g. handshake timeout, reject, dispatch failure).
        /// </summary>
        event EventHandler<Exception>? ErrorOccurred;
    }
}
