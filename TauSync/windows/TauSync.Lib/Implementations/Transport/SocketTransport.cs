using System;
using System.Buffers;
using System.Collections.Concurrent;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Transport
{
    public class SocketTransport : ITransport
    {
        private TcpClient? _tcpClient;
        private TcpListener? _tcpListener;
        private NetworkStream? _stream;
        private string? _targetId;
        private bool _isConnected = false;
        private bool _disposed = false;
        private CancellationTokenSource? _receiveCancellation;
        private Task? _receiveTask;
        private Task? _acceptTask;

        // Thread-safety for sending
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);

        // Request-response tracking
        private readonly ConcurrentDictionary<string, TaskCompletionSource<byte[]>> _pendingRequests = new();

        // Protocol constants
        public static readonly int DefaultPort = CoreConfig.DefaultPort;
        public static readonly int StreamingThreshold = CoreConfig.StreamingThreshold;
        public static readonly int ChunkBufferSize = CoreConfig.ChunkBufferSize;
        public static readonly int CorrelationIdLength = CoreConfig.CorrelationIdLength;

        public int Port { get; set; } = DefaultPort;

        // Legacy event for backward compatibility (buffers entire message)
        public event EventHandler<byte[]>? DataReceived;

        // New events for efficient handling
        public event EventHandler<byte[]>? OnMessageReceived; // For small messages (< 1MB)
        public event EventHandler<StreamChunkEventArgs>? OnStreamChunkReceived; // For large files (streaming)

        // Dependency injection: Action-based handlers
        private Action<byte[]>? _messageHandler;
        private Action<byte[], int, bool>? _streamChunkHandler;
        public SocketTransport()
        {
            Initialize();
        }
        public void Initialize()
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(SocketTransport));

            if (_tcpListener != null)
                throw new InvalidOperationException("Server is already initialized.");

            try
            {
                _tcpListener = new TcpListener(System.Net.IPAddress.Any, Port);
                _tcpListener.Start();
                _receiveCancellation = new CancellationTokenSource();
                _acceptTask = Task.Run(() => AcceptLoop(_receiveCancellation.Token));
                
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException($"Failed to start server on port {Port}", ex);
            }
        }

        /// <summary>
        /// Registers a handler for small messages (metadata, JSON, etc.)
        /// </summary>
        public void RegisterMessageHandler(Action<byte[]> handler)
        {
            _messageHandler = handler ?? throw new ArgumentNullException(nameof(handler));
        }

        /// <summary>
        /// Registers a handler for streaming chunks: (chunk, bytesRead, isFinal)
        /// </summary>
        public void RegisterStreamChunkHandler(Action<byte[], int, bool> handler)
        {
            _streamChunkHandler = handler ?? throw new ArgumentNullException(nameof(handler));
        }

        /// <summary>
        /// Sends a request and waits for a response with the specified correlationId.
        /// </summary>
        /// <param name="data">The data to send (will be prefixed with correlationId)</param>
        /// <param name="correlationId">Unique identifier for request-response matching</param>
        /// <param name="timeout">Timeout for waiting for response</param>
        /// <returns>The response data (without correlationId header)</returns>
        public async Task<byte[]> SendRequestAsync(byte[] data, string correlationId, TimeSpan timeout)
        {
            if (data == null)
                throw new ArgumentNullException(nameof(data));
            if (string.IsNullOrWhiteSpace(correlationId))
                throw new ArgumentException("CorrelationId cannot be null or empty.", nameof(correlationId));
            if (correlationId.Length > CorrelationIdLength)
                throw new ArgumentException($"CorrelationId cannot exceed {CorrelationIdLength} bytes.", nameof(correlationId));

            if (!_isConnected || _stream == null)
                throw new InvalidOperationException("Not connected. Call Connect() or Initialize() first.");

            // Create TaskCompletionSource for this request
            var tcs = new TaskCompletionSource<byte[]>();
            var cts = new CancellationTokenSource(timeout);

            // Register timeout cancellation
            cts.Token.Register(() =>
            {
                if (_pendingRequests.TryRemove(correlationId, out var removedTcs))
                {
                    removedTcs.TrySetException(new TimeoutException($"Request with correlationId '{correlationId}' timed out after {timeout.TotalSeconds} seconds."));
                }
            });

            // Add to pending requests
            if (!_pendingRequests.TryAdd(correlationId, tcs))
            {
                throw new InvalidOperationException($"A request with correlationId '{correlationId}' is already pending.");
            }

            try
            {
                // Encode correlationId to bytes (pad or truncate to CorrelationIdLength)
                byte[] correlationBytes = EncodeCorrelationId(correlationId);

                // Prepend correlationId to data
                byte[] messageWithHeader = new byte[CorrelationIdLength + data.Length];
                Buffer.BlockCopy(correlationBytes, 0, messageWithHeader, 0, CorrelationIdLength);
                Buffer.BlockCopy(data, 0, messageWithHeader, CorrelationIdLength, data.Length);

                // Send the message (thread-safe)
                await SendRawAsync(messageWithHeader);

                // Wait for response
                return await tcs.Task;
            }
            catch
            {
                // Clean up on error
                _pendingRequests.TryRemove(correlationId, out _);
                throw;
            }
            finally
            {
                cts.Dispose();
            }
        }

        private byte[] EncodeCorrelationId(string correlationId)
        {
            byte[] bytes = new byte[CorrelationIdLength];
            byte[] idBytes = System.Text.Encoding.UTF8.GetBytes(correlationId);
            int copyLength = Math.Min(idBytes.Length, CorrelationIdLength);
            Buffer.BlockCopy(idBytes, 0, bytes, 0, copyLength);
            return bytes;
        }

        private string DecodeCorrelationId(byte[] header)
        {
            // Find null terminator or use full length
            int length = 0;
            for (int i = 0; i < CorrelationIdLength; i++)
            {
                if (header[i] == 0)
                {
                    length = i;
                    break;
                }
            }
            if (length == 0) length = CorrelationIdLength;
            return System.Text.Encoding.UTF8.GetString(header, 0, length);
        }

        private bool IsUnsolicitedMessage(byte[] correlationIdBytes)
        {
            // Check if all bytes are zero (unsolicited message)
            for (int i = 0; i < CorrelationIdLength; i++)
            {
                if (correlationIdBytes[i] != 0)
                    return false;
            }
            return true;
        }

        private async Task AcceptLoop(CancellationToken cancellationToken)
        {
            while (!cancellationToken.IsCancellationRequested && _tcpListener != null)
            {
                try
                {
                    _tcpClient = await _tcpListener.AcceptTcpClientAsync();
                    _stream = _tcpClient.GetStream();
                    _isConnected = true;
                    System.Console.WriteLine("Someone connected!!!!");
                    _receiveCancellation = new CancellationTokenSource();
                    _receiveTask = Task.Run(() => ReceiveLoop(_receiveCancellation.Token));
                    break;
                }
                catch (Exception)
                {
                    break;
                }
            }
        }

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
        /// Thread-safe synchronous send (uses semaphore internally)
        /// </summary>
        public void SendRaw(byte[] data)
        {
            SendRawAsync(data).GetAwaiter().GetResult();
        }

        /// <summary>
        /// Thread-safe asynchronous send using SemaphoreSlim
        /// </summary>
        private async Task SendRawAsync(byte[] data)
        {
            if (data == null)
                throw new ArgumentNullException(nameof(data), "Data cannot be null.");

            if (_disposed)
                throw new ObjectDisposedException(nameof(SocketTransport));

            if (!_isConnected || _stream == null)
                throw new InvalidOperationException("Not connected. Call Connect() or Initialize() first.");

            // Acquire semaphore to ensure thread-safe sending
            await _sendLock.WaitAsync();
            try
            {
                // Send data length first (4 bytes)
                byte[] lengthBytes = BitConverter.GetBytes(data.Length);
                if (BitConverter.IsLittleEndian)
                    Array.Reverse(lengthBytes);
                await _stream.WriteAsync(lengthBytes, 0, lengthBytes.Length);

                // Send actual data
                await _stream.WriteAsync(data, 0, data.Length);
                await _stream.FlushAsync();
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("Failed to send data via socket.", ex);
            }
            finally
            {
                _sendLock.Release();
            }
        }

        public bool IsConnected()
        {
            return _isConnected && !_disposed && _tcpClient?.Connected == true;
        }

        public void Disconnect()
        {
            if (_isConnected)
            {
                _isConnected = false;

                // Cancel all pending requests
                foreach (var kvp in _pendingRequests)
                {
                    kvp.Value.TrySetException(new InvalidOperationException("Connection closed."));
                }
                _pendingRequests.Clear();

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

        private async Task ReceiveLoop(CancellationToken cancellationToken)
        {
            // Use ArrayPool for efficient memory management
            var arrayPool = ArrayPool<byte>.Shared;
            byte[] lengthBuffer = arrayPool.Rent(4);

            try
            {
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

                        if (BitConverter.IsLittleEndian)
                            Array.Reverse(lengthBuffer, 0, 4);
                        int dataLength = BitConverter.ToInt32(lengthBuffer, 0);

                        if (dataLength < 0 || dataLength > int.MaxValue) // Max 2GB (int limit)
                        {
                            throw new InvalidOperationException($"Invalid data length: {dataLength}");
                        }

                        // Decide: streaming mode or buffered mode
                        if (dataLength > StreamingThreshold)
                        {
                            // Streaming mode: read in chunks and forward immediately
                            await ReceiveStreaming(dataLength, cancellationToken);
                        }
                        else
                        {
                            // Buffered mode: read entire message into memory
                            await ReceiveBuffered(dataLength, cancellationToken);
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
            }
            finally
            {
                arrayPool.Return(lengthBuffer);
            }

            if (_isConnected)
            {
                Disconnect();
            }
        }

        private async Task ReceiveBuffered(int dataLength, CancellationToken cancellationToken)
        {
            var arrayPool = ArrayPool<byte>.Shared;
            byte[] data = arrayPool.Rent(dataLength);

            try
            {
                int totalRead = 0;
                while (totalRead < dataLength && !cancellationToken.IsCancellationRequested)
                {
                    int read = await _stream!.ReadAsync(data, totalRead, dataLength - totalRead, cancellationToken);
                    if (read == 0)
                    {
                        break;
                    }
                    totalRead += read;
                }

                if (totalRead == dataLength)
                {
                    // Extract correlationId from header (first CorrelationIdLength bytes)
                    if (dataLength >= CorrelationIdLength)
                    {
                        byte[] correlationIdBytes = new byte[CorrelationIdLength];
                        Buffer.BlockCopy(data, 0, correlationIdBytes, 0, CorrelationIdLength);

                        // Check if this is a response to a pending request
                        if (!IsUnsolicitedMessage(correlationIdBytes))
                        {
                            string correlationId = DecodeCorrelationId(correlationIdBytes);

                            // Try to find and resolve pending request
                            if (_pendingRequests.TryRemove(correlationId, out var tcs))
                            {
                                // Extract payload (without correlationId header)
                                byte[] payload = new byte[dataLength - CorrelationIdLength];
                                Buffer.BlockCopy(data, CorrelationIdLength, payload, 0, payload.Length);

                                // Resolve the TaskCompletionSource
                                tcs.TrySetResult(payload);
                                return; // Don't trigger general events for responses
                            }
                        }

                        // Extract payload for unsolicited messages (strip 16-byte correlation ID)
                        byte[] unsolicitedPayload = new byte[dataLength - CorrelationIdLength];
                        Buffer.BlockCopy(data, CorrelationIdLength, unsolicitedPayload, 0, unsolicitedPayload.Length);

                        // Smart routing based on message size:
                        // - Large messages (>= ChunkBufferSize/2) are likely stream data -> route to stream handler
                        // - Small messages (< ChunkBufferSize/2) are likely control messages/interrupts -> route to message handler
                        bool isLikelyStreamData = unsolicitedPayload.Length >= (ChunkBufferSize / 2); // Use half chunk size as threshold
                        
                        if (isLikelyStreamData && _streamChunkHandler != null)
                        {
                            // Route large unsolicited messages to streaming handler (likely stream chunks)
                            int bytesRead = unsolicitedPayload.Length;
                            bool isFinal = false;
                            
                            _streamChunkHandler.Invoke(unsolicitedPayload, bytesRead, isFinal);
                            // Also invoke event if subscribers exist
                            OnStreamChunkReceived?.Invoke(this, new StreamChunkEventArgs(unsolicitedPayload, bytesRead, isFinal));
                            // CRITICAL: DO NOT invoke OnMessageReceived - this is exclusive routing
                            return; // Exit early to prevent any other handlers from being called
                        }
                        else if (isLikelyStreamData && OnStreamChunkReceived != null)
                        {
                            // Event subscribers exist but no handler registered
                            int bytesRead = unsolicitedPayload.Length;
                            bool isFinal = false;
                            OnStreamChunkReceived.Invoke(this, new StreamChunkEventArgs(unsolicitedPayload, bytesRead, isFinal));
                            // CRITICAL: DO NOT invoke OnMessageReceived - this is exclusive routing
                            return; // Exit early to prevent any other handlers from being called
                        }
                        else
                        {
                            // Small messages or no stream handler registered -> treat as regular message/interrupt
                            _messageHandler?.Invoke(unsolicitedPayload);
                            OnMessageReceived?.Invoke(this, unsolicitedPayload);
                            DataReceived?.Invoke(this, unsolicitedPayload); // Legacy event for backward compatibility
                        }
                    }
                    else
                    {
                        // Message too short to have correlationId header, treat as legacy/unsolicited
                        byte[] shortMessage = new byte[dataLength];
                        Buffer.BlockCopy(data, 0, shortMessage, 0, dataLength);

                        // Exclusive routing: If stream handler is registered, route ONLY there
                        // Otherwise, route to general message handler
                        // CRITICAL: Check _streamChunkHandler first (registered by ConnectionManager)
                        if (_streamChunkHandler != null)
                        {
                            // Route exclusively to streaming handler
                            _streamChunkHandler.Invoke(shortMessage, shortMessage.Length, true);
                            OnStreamChunkReceived?.Invoke(this, new StreamChunkEventArgs(shortMessage, shortMessage.Length, true));
                            // DO NOT invoke OnMessageReceived - this is exclusive routing
                        }
                        else if (OnStreamChunkReceived != null)
                        {
                            // Event subscribers exist but no handler registered
                            OnStreamChunkReceived.Invoke(this, new StreamChunkEventArgs(shortMessage, shortMessage.Length, true));
                            // DO NOT invoke OnMessageReceived - this is exclusive routing
                        }
                        else
                        {
                            // No stream handler registered, treat as regular message/interrupt
                            _messageHandler?.Invoke(shortMessage);
                            OnMessageReceived?.Invoke(this, shortMessage);
                            DataReceived?.Invoke(this, shortMessage);
                        }
                    }
                }
            }
            finally
            {
                arrayPool.Return(data);
            }
        }

        private async Task ReceiveStreaming(int dataLength, CancellationToken cancellationToken)
        {
            var arrayPool = ArrayPool<byte>.Shared;
            byte[] chunkBuffer = arrayPool.Rent(ChunkBufferSize);

            try
            {
                int totalRead = 0;
                int remainingBytes = dataLength;
                byte[]? correlationIdBytes = null;
                string? correlationId = null;
                TaskCompletionSource<byte[]>? responseTcs = null;

                // First, read the correlationId header if possible
                if (dataLength >= CorrelationIdLength)
                {
                    correlationIdBytes = new byte[CorrelationIdLength];
                    int headerBytesRead = 0;
                    while (headerBytesRead < CorrelationIdLength && !cancellationToken.IsCancellationRequested)
                    {
                        int read = await _stream!.ReadAsync(correlationIdBytes, headerBytesRead, CorrelationIdLength - headerBytesRead, cancellationToken);
                        if (read == 0) break;
                        headerBytesRead += read;
                        totalRead += read;
                        remainingBytes -= read;
                    }

                    if (headerBytesRead == CorrelationIdLength)
                    {
                        if (!IsUnsolicitedMessage(correlationIdBytes))
                        {
                            correlationId = DecodeCorrelationId(correlationIdBytes);
                            _pendingRequests.TryGetValue(correlationId, out responseTcs);
                        }
                    }
                }

                // Stream the remaining data
                while (remainingBytes > 0 && !cancellationToken.IsCancellationRequested)
                {
                    int chunkSize = Math.Min(ChunkBufferSize, remainingBytes);
                    int bytesRead = await _stream!.ReadAsync(chunkBuffer, 0, chunkSize, cancellationToken);

                    if (bytesRead == 0)
                    {
                        break;
                    }

                    totalRead += bytesRead;
                    remainingBytes -= bytesRead;
                    bool isFinal = (remainingBytes == 0);

                    // For streaming responses, we need to buffer and return at the end
                    // For now, streaming is treated as unsolicited (Python can handle it)
                    if (responseTcs == null)
                    {
                        // Create a copy of the chunk for handlers
                        byte[] chunk = new byte[bytesRead];
                        Buffer.BlockCopy(chunkBuffer, 0, chunk, 0, bytesRead);

                        // Exclusive routing: If stream handler is registered, route ONLY there
                        // CRITICAL: Check _streamChunkHandler first (registered by ConnectionManager)
                        if (_streamChunkHandler != null)
                        {
                            // Route exclusively to streaming handler (stream chunks)
                            _streamChunkHandler.Invoke(chunk, bytesRead, isFinal);
                            OnStreamChunkReceived?.Invoke(this, new StreamChunkEventArgs(chunk, bytesRead, isFinal));
                            // DO NOT invoke OnMessageReceived - this is exclusive routing
                        }
                        else if (OnStreamChunkReceived != null)
                        {
                            // Event subscribers exist but no handler registered
                            OnStreamChunkReceived.Invoke(this, new StreamChunkEventArgs(chunk, bytesRead, isFinal));
                            // DO NOT invoke OnMessageReceived - this is exclusive routing
                        }
                        else
                        {
                            // No stream handler registered - this shouldn't happen for large streams
                            // But if it does, we still need to handle it somehow
                            // For now, route to stream handler anyway (better than message handler)
                            _streamChunkHandler?.Invoke(chunk, bytesRead, isFinal);
                            OnStreamChunkReceived?.Invoke(this, new StreamChunkEventArgs(chunk, bytesRead, isFinal));
                        }
                    }
                    // Note: Streaming responses would require buffering all chunks, which defeats the purpose
                    // For now, streaming is only for unsolicited large messages
                }
            }
            finally
            {
                arrayPool.Return(chunkBuffer);
            }
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                Disconnect();
                _tcpListener?.Stop();
                _acceptTask?.Wait(1000);
                _receiveCancellation?.Dispose();
                _sendLock.Dispose();
                _disposed = true;
            }
        }
    }

}
