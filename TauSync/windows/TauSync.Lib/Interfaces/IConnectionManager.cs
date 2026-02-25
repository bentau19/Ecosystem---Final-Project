using System;
using System.IO;
using System.Threading.Tasks;
using TauSync.Models;
using TauSync.Core;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Connection management layer interface - the brain that decides which ITransport to use.
    /// </summary>
    public interface IConnectionManager : IDisposable
    {
        /// <summary>
        /// Sends a TransferRequest with streaming data support (async).
        /// Implements handshake protocol: sends metadata, waits for OK/REJECT, then streams data.
        /// </summary>
        /// <param name="dataStream">The stream containing data to send</param>
        /// <param name="req">The transfer request metadata</param>
        /// <returns>Task that completes when the transfer is finished</returns>
        Task SmartSend(Stream dataStream, TransferRequest req);

        /// <summary>
        /// Legacy SmartSend for backward compatibility (sends TransferRequest with payload in memory).
        /// </summary>
        /// <param name="req">The transfer request with payload</param>
        void SmartSend(TransferRequest req);

        /// <summary>
        /// Handles incoming raw data and processes it.
        /// </summary>
        /// <param name="rawData">The raw binary data received</param>
        void HandleIncoming(byte[] rawData);

        /// <summary>
        /// Gets the current connection status.
        /// </summary>
        /// <returns>Status string</returns>
        string GetStatus();

        /// <summary>
        /// Switches the connection status.
        /// </summary>
        /// <param name="status">The new connection status</param>
        void SwitchStatus(ConnectionStatus status);

        /// <summary>
        /// Event fired when a TransferRequest is received (after handshake acceptance).
        /// </summary>
        event EventHandler<TransferRequest> RequestReceived;

        /// <summary>
        /// Event fired when an error occurs.
        /// </summary>
        event EventHandler<Exception> ErrorOccurred;

        /// <summary>
        /// Event fired when a data chunk is received during streaming (for large files).
        /// </summary>
        event EventHandler<DataChunkEventArgs> DataChunkReceived;
    }
}
