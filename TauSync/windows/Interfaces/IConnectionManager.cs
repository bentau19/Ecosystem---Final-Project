using System;
using TauSync.Models;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Connection management layer interface - the brain that decides which ITransport to use.
    /// </summary>
    public interface IConnectionManager : IDisposable
    {
        /// <summary>
        /// Smart send logic that selects the appropriate transport medium and sends the request.
        /// </summary>
        /// <param name="req">The transfer request to send.</param>
        /// <exception cref="ArgumentNullException">Thrown when req is null.</exception>
        /// <exception cref="ArgumentException">Thrown when req is invalid.</exception>
        /// <exception cref="InvalidOperationException">Thrown when no transport is available or send fails.</exception>
        void SmartSend(TransferRequest req);

        /// <summary>
        /// Handles incoming raw data and processes it.
        /// </summary>
        /// <param name="rawData">The raw binary data received.</param>
        /// <exception cref="ArgumentNullException">Thrown when rawData is null.</exception>
        /// <exception cref="InvalidOperationException">Thrown when processing fails.</exception>
        void HandleIncoming(byte[] rawData);

        /// <summary>
        /// Event raised when a transfer request is successfully received and processed.
        /// </summary>
        event EventHandler<TransferRequest> RequestReceived;

        /// <summary>
        /// Event raised when an error occurs during processing.
        /// </summary>
        event EventHandler<Exception> ErrorOccurred;
    }
}
