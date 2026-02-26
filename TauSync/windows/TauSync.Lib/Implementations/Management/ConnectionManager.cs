using System;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using TauSync.Interfaces;
using TauSync.Models;
using TauSync.Implementations.Transport;
using TauSync.Core;

namespace TauSync.Implementations.Management
{
    public class ConnectionManager : IConnectionManager
    {
        private const long LargeFileThreshold = 1024 * 1024; // 1MB
        private const int StreamChunkSize = 64 * 1024; // 64KB chunks for streaming
        private const int HandshakeTimeoutSeconds = 30;
        
        private SocketTransport? _transport;
        private bool _disposed = false;

        public event EventHandler<TransferRequest>? RequestReceived;
        public event EventHandler<Exception>? ErrorOccurred;
        public event EventHandler<DataChunkEventArgs>? DataChunkReceived;

        // Optional Python callback for interrupt handling
        private Action<byte[]>? _pythonMessageHandler;

        /// <summary>
        /// Default constructor - uses internal message handler
        /// </summary>
        public ConnectionManager()
        {
            _transport = new SocketTransport();
            Initialize(_transport);
        }

        /// <summary>
        /// Constructor that accepts a Python callback for interrupt handling.
        /// The callback will be called when an interrupt (unsolicited small message) is received.
        /// </summary>
        /// <param name="pythonMessageHandler">Python function that receives byte[] data when interrupt occurs</param>
        public ConnectionManager(Action<byte[]> pythonMessageHandler)
        {
            if (pythonMessageHandler == null)
                throw new ArgumentNullException(nameof(pythonMessageHandler), "Python message handler cannot be null.");

            _pythonMessageHandler = pythonMessageHandler;
            _transport = new SocketTransport();
            Initialize(_transport, pythonMessageHandler);
        }


        public string GetStatus()
        {
            return "regular";
        }

        public void SwitchStatus(ConnectionStatus status) { }


        public void Initialize(ITransport transport)
        {
            Initialize(transport, null);
        }

        /// <summary>
        /// Initialize with optional Python callback for interrupt handling
        /// </summary>
        public void Initialize(ITransport transport, Action<byte[]>? pythonMessageHandler)
        {
            if (transport == null)
                throw new ArgumentNullException(nameof(transport), "Transport cannot be null.");

            if (transport is not SocketTransport socketTransport)
                throw new ArgumentException("Transport must be a SocketTransport instance.", nameof(transport));

            _transport = socketTransport;
            _pythonMessageHandler = pythonMessageHandler;

            // Register message handler: use Python callback if provided, otherwise use internal handler
            if (_pythonMessageHandler != null)
            {
                // Use Python callback directly for interrupts
                _transport.RegisterMessageHandler(OnTransportMessageReceivedWithPython);
            }
            else
            {
                // Use internal handler
                _transport.RegisterMessageHandler(OnTransportMessageReceived);
            }

            // Register stream chunk handler for incoming large files
            _transport.RegisterStreamChunkHandler(OnTransportStreamChunkReceived);
        }

        /// <summary>
        /// Sends a TransferRequest with streaming data support.
        /// Implements handshake protocol: sends metadata, waits for OK/REJECT, then streams data.
        /// </summary>
        public async Task SmartSend(Stream dataStream, TransferRequest req)
        {
            if (dataStream == null)
                throw new ArgumentNullException(nameof(dataStream), "Data stream cannot be null.");
            if (req == null)
                throw new ArgumentNullException(nameof(req), "Transfer request cannot be null.");
            if (!req.IsValid())
                throw new ArgumentException("Transfer request is invalid.", nameof(req));
            if (_transport == null)
                throw new InvalidOperationException("Connection manager is not initialized. Call Initialize() first.");
                if (!_transport.IsConnected())
                    throw new InvalidOperationException("Transport is not connected.");

            // Generate RequestId if not provided
            if (string.IsNullOrWhiteSpace(req.RequestId))
            {
                req.RequestId = Guid.NewGuid().ToString("N")[..16]; // 16 chars for correlationId
            }

            try
            {
                // Step 1: Serialize TransferRequest metadata to JSON
                // Clear payload for metadata (will be streamed separately)
                byte[] originalPayload = req.Payload;
                req.Payload = Array.Empty<byte>(); // Metadata only, no payload in handshake
                
                string json = JsonSerializer.Serialize(req);
                byte[] metadataBytes = Encoding.UTF8.GetBytes(json);

                // Step 2: Handshake - Send metadata and wait for response
                byte[] handshakeResponse = await _transport.SendRequestAsync(
                    data: metadataBytes,
                    correlationId: req.RequestId,
                    timeout: TimeSpan.FromSeconds(HandshakeTimeoutSeconds)
                );

                // Step 3: Check handshake response
                string responseText = Encoding.UTF8.GetString(handshakeResponse).Trim().ToUpperInvariant();
                if (responseText != "OK")
                {
                    if (responseText == "REJECT")
                    {
                        throw new InvalidOperationException("Transfer request was rejected by the remote peer.");
                    }
                    throw new InvalidOperationException($"Unexpected handshake response: {responseText}");
                }

                // Step 4: Stream data in chunks (memory-efficient)
                await StreamDataAsync(dataStream);
            }
            catch (TaskCanceledException ex)
            {
                OnErrorOccurred(new TimeoutException("Handshake timeout: remote peer did not respond.", ex));
                throw;
            }
            catch (Exception ex)
            {
                OnErrorOccurred(ex);
                throw;
            }
        }

        /// <summary>
        /// Legacy SmartSend for backward compatibility (sends TransferRequest with payload in memory)
        /// </summary>
        public void SmartSend(TransferRequest req)
        {
            if (req == null)
                throw new ArgumentNullException(nameof(req), "Transfer request cannot be null.");

            // Convert payload to stream and use async version
            using (var stream = new MemoryStream(req.Payload ?? Array.Empty<byte>()))
            {
                SmartSend(stream, req).GetAwaiter().GetResult();
            }
        }

        /// <summary>
        /// Streams data from the provided stream in 64KB chunks.
        /// Memory-efficient: doesn't load entire stream into RAM.
        /// Protocol: Each chunk is sent with [16-byte CorrelationID (all zeros)][Payload]
        /// The receiver will identify zeros as unsolicited stream chunks and route to DataChunkReceived.
        /// </summary>
        private async Task StreamDataAsync(Stream dataStream)
        {
            var arrayPool = System.Buffers.ArrayPool<byte>.Shared;
            byte[] buffer = arrayPool.Rent(StreamChunkSize);
            
            // 16-byte zero header for unsolicited stream chunks (protocol requirement)
            byte[] zeroHeader = new byte[16]; // All zeros by default - indicates unsolicited message

            try
            {
                // CRITICAL: Reset stream position to start (in case it was read before)
                if (dataStream.CanSeek)
                {
                    dataStream.Position = 0;
                }
                
                long totalBytesSent = 0;
                int chunkCount = 0;
                int bytesRead;
                
                while ((bytesRead = await dataStream.ReadAsync(buffer, 0, StreamChunkSize)) > 0)
                {
                    // Create packet with exact size: 16 (header) + bytesRead (data)
                    byte[] packet = new byte[16 + bytesRead];
                    
                    // Prepend 16-byte zero header (unsolicited message indicator)
                    Buffer.BlockCopy(zeroHeader, 0, packet, 0, 16);
                    
                    // Copy actual data chunk after the header
                    Buffer.BlockCopy(buffer, 0, packet, 16, bytesRead);
                    
                    // Send packet (SocketTransport will add 4-byte length prefix automatically)
                    // Final format: [4-byte Length][16-byte CorrelationID (zeros)][Payload]
                    // Use async send to avoid blocking
                    await Task.Run(() => _transport!.SendRaw(packet));
                    
                    totalBytesSent += bytesRead;
                    chunkCount++;
                }
                
                // If no data was read, the stream might be at the end or empty
                if (totalBytesSent == 0)
                {
                    throw new InvalidOperationException("StreamDataAsync: No data was read from the stream. Stream might be empty or at the end.");
                }
            }
            catch (Exception ex)
            {
                OnErrorOccurred(new InvalidOperationException($"StreamDataAsync failed: {ex.Message}", ex));
                throw;
            }
            finally
            {
                arrayPool.Return(buffer);
            }
        }

        /// <summary>
        /// Handles incoming messages from transport (small messages < 1MB)
        /// </summary>
        private void OnTransportMessageReceived(byte[] message)
        {
            try
            {
                // Deserialize JSON to TransferRequest
                string json = Encoding.UTF8.GetString(message);
                TransferRequest? req = JsonSerializer.Deserialize<TransferRequest>(json);

                if (req == null)
                {
                    throw new InvalidOperationException("Failed to deserialize transfer request.");
                }

                if (!req.IsValid())
                {
                    throw new InvalidOperationException("Received invalid transfer request.");
                }

                // Decompress if needed
                if (req.IsCompressed && req.Payload.Length > 0)
                {
                    req.Payload = Decompress(req.Payload);
                    req.IsCompressed = false;
                }

                // Trigger RequestReceived event
                OnRequestReceived(req);
            }
            catch (JsonException ex)
            {
                OnErrorOccurred(new InvalidOperationException("Failed to parse incoming data as JSON.", ex));
            }
            catch (Exception ex)
            {
                OnErrorOccurred(ex);
            }
        }

        /// <summary>
        /// Handles incoming messages with Python callback support.
        /// First tries to parse as TransferRequest (handshake), if fails - calls Python callback (interrupt).
        /// </summary>
        private void OnTransportMessageReceivedWithPython(byte[] message)
        {
            try
            {
                // Try to parse as TransferRequest (handshake message)
                string json = Encoding.UTF8.GetString(message);
                TransferRequest? req = JsonSerializer.Deserialize<TransferRequest>(json);

                if (req != null && req.IsValid())
                {
                    // This is a valid TransferRequest (handshake) - handle normally
                    // Decompress if needed
                    if (req.IsCompressed && req.Payload.Length > 0)
                    {
                        req.Payload = Decompress(req.Payload);
                        req.IsCompressed = false;
                    }

                    // Trigger RequestReceived event
                    OnRequestReceived(req);
                    return; // Handled as handshake, don't call Python callback
                }
            }
            catch (JsonException)
            {
                // Not JSON - likely an interrupt, continue to Python callback
            }
            catch (Exception ex)
            {
                // Other error - log and continue to Python callback
                OnErrorOccurred(ex);
            }

            // Not a valid TransferRequest - this is likely an interrupt
            // Call Python callback if provided
            if (_pythonMessageHandler != null)
            {
                try
                {
                    _pythonMessageHandler.Invoke(message);
                }
                catch (Exception ex)
                {
                    OnErrorOccurred(new InvalidOperationException("Python message handler threw an exception.", ex));
                }
            }
        }

        /// <summary>
        /// Handles incoming stream chunks from transport (large files)
        /// </summary>
        private void OnTransportStreamChunkReceived(byte[] chunk, int bytesRead, bool isFinal)
        {
            try
            {
                // CRITICAL FIX: Check if this is actually a TransferRequest (JSON) instead of raw data
                // This can happen when the handshake message is routed to the stream handler
                // Check for small messages that might be JSON (regardless of isFinal flag)
                if (bytesRead < 1024 * 10) // Small message, might be JSON
                {
                    try
                    {
                        string json = Encoding.UTF8.GetString(chunk, 0, bytesRead);
                        if (json.TrimStart().StartsWith("{") && json.Contains("\"MagicBytes\""))
                        {
                            // This is a TransferRequest, route it to the message handler
                            OnTransportMessageReceived(chunk.Take(bytesRead).ToArray());
                            return;
                        }
                    }
                    catch
                    {
                        // Not JSON, continue as stream chunk
                    }
                }
                
                // Create a copy for event handlers
                byte[] chunkCopy = new byte[bytesRead];
                Buffer.BlockCopy(chunk, 0, chunkCopy, 0, bytesRead);

                // Trigger DataChunkReceived event for Python UI
                DataChunkReceived?.Invoke(this, new DataChunkEventArgs(chunkCopy, isFinal));
            }
            catch (Exception ex)
            {
                OnErrorOccurred(ex);
            }
        }

        public void HandleIncoming(byte[] rawData)
        {
            // This method is now handled by RegisterMessageHandler
            // Keeping for interface compatibility
            if (rawData != null)
            {
                OnTransportMessageReceived(rawData);
            }
        }

        private byte[] Compress(byte[] data)
        {
            using (var output = new MemoryStream())
            {
                using (var gzip = new GZipStream(output, CompressionMode.Compress))
                {
                    gzip.Write(data, 0, data.Length);
                }
                return output.ToArray();
            }
        }

        private byte[] Decompress(byte[] compressedData)
        {
            using (var input = new MemoryStream(compressedData))
            using (var gzip = new GZipStream(input, CompressionMode.Decompress))
            using (var output = new MemoryStream())
            {
                gzip.CopyTo(output);
                return output.ToArray();
            }
        }

        protected virtual void OnRequestReceived(TransferRequest req)
        {
            RequestReceived?.Invoke(this, req);
        }

        protected virtual void OnErrorOccurred(Exception ex)
        {
            ErrorOccurred?.Invoke(this, ex);
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                _transport?.Dispose();
                _disposed = true;
            }
        }
    }

}
