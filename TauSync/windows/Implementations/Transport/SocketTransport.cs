using System;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Interfaces;

namespace TauSync.Implementations.Transport
{
    /// <summary>
    /// Simple TCP Socket transport implementation.
    /// Provides basic socket-based communication for TauSync protocol.
    /// </summary>
    public class SocketTransport : ITransport
    {
        private TcpClient? _tcpClient;
        private NetworkStream? _stream;
        private string? _targetId;
        private bool _isConnected = false;
        private bool _disposed = false;
        private CancellationTokenSource? _receiveCancellation;
        private Task? _receiveTask;

        /// <summary>
        /// Default port for TauSync communication.
        /// </summary>
        public const int DefaultPort = 8888;

        /// <summary>
        /// Gets or sets the port number for socket connection.
        /// </summary>
        public int Port { get; set; } = DefaultPort;

        /// <summary>
        /// Event raised when data is received from the socket.
        /// </summary>
        public event EventHandler<byte[]>? DataReceived;

        /// <summary>
        /// Creates an initial connection to the target device via TCP socket.
        /// </summary>
        /// <param name="targetId">The IP address or hostname of the target device.</param>
        /// <exception cref="ArgumentNullException">Thrown when targetId is null or empty.</exception>
        /// <exception cref="InvalidOperationException">Thrown when connection fails.</exception>
        public void Connect(string targetId)
        {
            if (string.IsNullOrWhiteSpace(targetId))
                throw new ArgumentNullException(nameof(targetId), "Target ID cannot be null or empty.");

            if (_disposed)
                throw new ObjectDisposedException(nameof(SocketTransport));

            if (_isConnected)
            {
                Disconnect();
            }

            try
            {
                _targetId = targetId;
                _tcpClient = new TcpClient();
                _tcpClient.Connect(targetId, Port);
                _stream = _tcpClient.GetStream();
                _isConnected = true;

                // Start receiving data in background
                _receiveCancellation = new CancellationTokenSource();
                _receiveTask = Task.Run(() => ReceiveLoop(_receiveCancellation.Token));
            }
            catch (SocketException ex)
            {
                _isConnected = false;
                throw new InvalidOperationException($"Failed to connect to {targetId}:{Port}", ex);
            }
            catch (Exception ex)
            {
                _isConnected = false;
                throw new InvalidOperationException($"Failed to connect to {targetId}:{Port}", ex);
            }
        }

        /// <summary>
        /// Sends raw binary data through the socket.
        /// </summary>
        /// <param name="data">The binary data to send.</param>
        /// <exception cref="ArgumentNullException">Thrown when data is null.</exception>
        /// <exception cref="InvalidOperationException">Thrown when not connected or send fails.</exception>
        public void SendRaw(byte[] data)
        {
            if (data == null)
                throw new ArgumentNullException(nameof(data), "Data cannot be null.");

            if (_disposed)
                throw new ObjectDisposedException(nameof(SocketTransport));

            if (!_isConnected || _stream == null)
                throw new InvalidOperationException("Not connected. Call Connect() first.");

            try
            {
                // Send data length first (4 bytes)
                byte[] lengthBytes = BitConverter.GetBytes(data.Length);
                _stream.Write(lengthBytes, 0, lengthBytes.Length);

                // Send actual data
                _stream.Write(data, 0, data.Length);
                _stream.Flush();
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("Failed to send data via socket.", ex);
            }
        }

        /// <summary>
        /// Checks the socket connection status.
        /// </summary>
        /// <returns>True if connected, false otherwise.</returns>
        public bool IsConnected()
        {
            return _isConnected && !_disposed && _tcpClient?.Connected == true;
        }

        /// <summary>
        /// Disconnects from the current socket connection.
        /// </summary>
        public void Disconnect()
        {
            if (_isConnected)
            {
                _isConnected = false;

                // Stop receiving
                _receiveCancellation?.Cancel();
                _receiveTask?.Wait(1000);

                // Close stream and client
                _stream?.Close();
                _tcpClient?.Close();

                _stream = null;
                _tcpClient = null;
                _targetId = null;
            }
        }

        /// <summary>
        /// Background task that receives data from the socket.
        /// </summary>
        private async Task ReceiveLoop(CancellationToken cancellationToken)
        {
            byte[] lengthBuffer = new byte[4];

            while (!cancellationToken.IsCancellationRequested && _isConnected && _stream != null)
            {
                try
                {
                    // Read data length (4 bytes)
                    int bytesRead = await _stream.ReadAsync(lengthBuffer, 0, 4, cancellationToken);
                    if (bytesRead != 4)
                    {
                        break;
                    }

                    int dataLength = BitConverter.ToInt32(lengthBuffer, 0);
                    if (dataLength < 0 || dataLength > 10 * 1024 * 1024) // Max 10MB
                    {
                        throw new InvalidOperationException($"Invalid data length: {dataLength}");
                    }

                    // Read actual data
                    byte[] data = new byte[dataLength];
                    int totalRead = 0;
                    while (totalRead < dataLength)
                    {
                        int read = await _stream.ReadAsync(data, totalRead, dataLength - totalRead, cancellationToken);
                        if (read == 0)
                        {
                            break;
                        }
                        totalRead += read;
                    }

                    if (totalRead == dataLength)
                    {
                        DataReceived?.Invoke(this, data);
                    }
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception)
                {
                    break;
                }
            }

            if (_isConnected)
            {
                Disconnect();
            }
        }

        /// <summary>
        /// Disposes of resources and disconnects.
        /// </summary>
        public void Dispose()
        {
            if (!_disposed)
            {
                Disconnect();
                _receiveCancellation?.Dispose();
                _disposed = true;
            }
        }
    }
}
