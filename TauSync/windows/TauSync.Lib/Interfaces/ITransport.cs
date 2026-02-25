using System;
using System.Threading.Tasks;
using TauSync.Models;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Transport layer interface - the pipe through which bytes flow.
    /// Each side (Windows/Android) must implement this for WiFi and Bluetooth.
    /// </summary>
    public interface ITransport : IDisposable
    {
        /// <summary>
        /// Creates an initial connection to the target device.
        /// </summary>
        /// <param name="targetId">The identifier of the target device to connect to.</param>
        void Connect(string targetId);

        /// <summary>
        /// Sends raw binary data through the transport channel (thread-safe).
        /// </summary>
        /// <param name="data">The binary data to send.</param>
        void SendRaw(byte[] data);

        /// <summary>
        /// Checks the connection status.
        /// </summary>
        /// <returns>True if connected, false otherwise.</returns>
        bool IsConnected();

        /// <summary>
        /// Sends a request and waits for a response with the specified correlationId.
        /// </summary>
        /// <param name="data">The data to send (will be prefixed with correlationId)</param>
        /// <param name="correlationId">Unique identifier for request-response matching (max 16 bytes)</param>
        /// <param name="timeout">Timeout for waiting for response</param>
        /// <returns>Task that completes with the response data (without correlationId header)</returns>
        Task<byte[]> SendRequestAsync(byte[] data, string correlationId, TimeSpan timeout);

        /// <summary>
        /// Registers a handler for small messages (metadata, JSON, etc.) - dependency injection.
        /// </summary>
        /// <param name="handler">Action that receives the message data</param>
        void RegisterMessageHandler(Action<byte[]> handler);

        /// <summary>
        /// Registers a handler for streaming chunks: (chunk, bytesRead, isFinal) - dependency injection.
        /// </summary>
        /// <param name="handler">Action that receives chunk data, bytes read, and final flag</param>
        void RegisterStreamChunkHandler(Action<byte[], int, bool> handler);

        /// <summary>
        /// Event for small messages received (< 1MB) - for event-based subscriptions.
        /// </summary>
        event EventHandler<byte[]>? OnMessageReceived;

        /// <summary>
        /// Event for streaming chunks received (>= 1MB) - for event-based subscriptions.
        /// </summary>
        event EventHandler<StreamChunkEventArgs>? OnStreamChunkReceived;

        /// <summary>
        /// Legacy event for backward compatibility (buffers entire message).
        /// </summary>
        event EventHandler<byte[]>? DataReceived;
    }
}
