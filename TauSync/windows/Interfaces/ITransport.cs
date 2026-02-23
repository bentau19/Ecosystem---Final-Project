using System;

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
        /// <exception cref="ArgumentNullException">Thrown when targetId is null or empty.</exception>
        /// <exception cref="InvalidOperationException">Thrown when connection fails.</exception>
        void Connect(string targetId);

        /// <summary>
        /// Sends raw binary data through the transport channel.
        /// </summary>
        /// <param name="data">The binary data to send.</param>
        /// <exception cref="ArgumentNullException">Thrown when data is null.</exception>
        /// <exception cref="InvalidOperationException">Thrown when not connected or send fails.</exception>
        void SendRaw(byte[] data);

        /// <summary>
        /// Checks the connection status.
        /// </summary>
        /// <returns>True if connected, false otherwise.</returns>
        bool IsConnected();
    }
}
