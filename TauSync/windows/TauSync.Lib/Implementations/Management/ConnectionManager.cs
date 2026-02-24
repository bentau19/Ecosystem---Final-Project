using System;
using System.IO;
using System.IO.Compression;
using System.Text.Json;
using TauSync.Interfaces;
using TauSync.Models;
using TauSync.Implementations.Transport;
using TauSync.Core;
namespace TauSync.Implementations.Management
{
    public class ConnectionManager : IConnectionManager
    {
        private const long LargeFileThreshold = 1024 * 1024; // 1MB
        private ITransport? _transport;
        private bool _disposed = false;

        public event EventHandler<TransferRequest>? RequestReceived;


        public event EventHandler<Exception>? ErrorOccurred;
        public String GetStatus(){
            return "regular";
        }

        public void SwitchStatus(ConnectionStatus status){}

        public void Initialize(ITransport transport)
        {
            if (transport == null)
                throw new ArgumentNullException(nameof(transport), "Transport cannot be null.");

            _transport = transport;

            // Subscribe to transport events
            if (_transport is SocketTransport socketTransport)
            {
                socketTransport.DataReceived += OnTransportDataReceived;
            }
        }

        public void SmartSend(TransferRequest req)
        {
            if (req == null)
                throw new ArgumentNullException(nameof(req), "Transfer request cannot be null.");

            if (!req.IsValid())
                throw new ArgumentException("Transfer request is invalid.", nameof(req));

            if (_transport == null)
                throw new InvalidOperationException("Connection manager is not initialized. Call Initialize() first.");

            try
            {
                if (!_transport.IsConnected())
                    throw new InvalidOperationException("Transport is not connected.");

                // No encryption - use payload as-is
                byte[] payload = req.Payload;

                // Compress if needed (for large files)
                bool shouldCompress = req.GetPayloadSize() > LargeFileThreshold && !req.IsCompressed;
                if (shouldCompress)
                {
                    payload = Compress(payload);
                }

                req.Payload = payload;
                req.IsCompressed = shouldCompress || req.IsCompressed;

                // Serialize to JSON
                string json = JsonSerializer.Serialize(req);
                byte[] jsonBytes = System.Text.Encoding.UTF8.GetBytes(json);

                // Send via transport
                _transport.SendRaw(jsonBytes);
            }
            catch (Exception ex)
            {
                OnErrorOccurred(ex);
                throw new InvalidOperationException("Failed to send transfer request.", ex);
            }
        }


        public void HandleIncoming(byte[] rawData)
        {
            if (rawData == null)
                throw new ArgumentNullException(nameof(rawData), "Raw data cannot be null.");

            if (_transport == null)
                throw new InvalidOperationException("Connection manager is not initialized. Call Initialize() first.");

            try
            {
                // Deserialize JSON to TransferRequest
                string json = System.Text.Encoding.UTF8.GetString(rawData);
                TransferRequest? req = JsonSerializer.Deserialize<TransferRequest>(json);

                if (req == null)
                    throw new InvalidOperationException("Failed to deserialize transfer request.");

                if (!req.IsValid())
                    throw new InvalidOperationException("Received invalid transfer request.");

                // Decompress if needed
                if (req.IsCompressed)
                {
                    req.Payload = Decompress(req.Payload);
                    req.IsCompressed = false;
                }

                // No decryption needed - payload is already plaintext
                OnRequestReceived(req);
            }
            catch (JsonException ex)
            {
                throw new InvalidOperationException("Failed to parse incoming data as JSON.", ex);
            }
            catch (Exception ex)
            {
                OnErrorOccurred(ex);
                throw new InvalidOperationException("Failed to process incoming data.", ex);
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


        private void OnTransportDataReceived(object? sender, byte[] data)
        {
            HandleIncoming(data);
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
                if (_transport is SocketTransport socketTransport)
                {
                    socketTransport.DataReceived -= OnTransportDataReceived;
                }
                _transport?.Dispose();
                _disposed = true;
            }
        }
    }
}
