using System;
using System.Collections.Concurrent;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Implementations.Protocol;
using TauSync.Implementations.Transport;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Management
{
    /// <summary>
    /// Connection manager per TauSync Protocol Spec: which connection and when; dispatcher and routing map.
    /// Routes incoming TPack by CorrelationID. Control channel = 0. No encryption in this implementation.
    /// </summary>
    public class ConnectionManager : IConnectionManager
    {
        private ITransport? _transport;
        private bool _ownsTransport;
        private readonly IProtocolHandler _protocolHandler;
        private bool _disposed;

        /// <summary>Routing map: CorrelationID -> handler. Thread-safe.</summary>
        private readonly ConcurrentDictionary<int, Action<byte[]>> _routingMap = new();

        /// <summary>When FIN is received for a CorrelationID, this action is invoked (e.g. complete BackBufferedStream).</summary>
        private readonly ConcurrentDictionary<int, Action> _onFinByCorrelationId = new();

        /// <summary>Waiter for the next control-channel payload (handshake response).</summary>
        private TaskCompletionSource<byte[]>? _pendingControlWaiter;
        private readonly object _controlLock = new object();

        /// <summary>Next CorrelationID for C# (odd: 1, 3, 5, ...). Falls back to increment when no released ID available.</summary>
        private int _nextCorrelationId = 1;

        /// <summary>Released odd CorrelationIDs returned to the pool when handlers are unregistered (avoids exhausting 3-byte space in long-running services).</summary>
        private readonly ConcurrentBag<int> _releasedCorrelationIds = new();

        public event EventHandler<Exception>? ErrorOccurred;

        public ConnectionManager() : this(null) { }

        public ConnectionManager(IProtocolHandler? protocolHandler)
        {
            _protocolHandler = protocolHandler ?? new ProtocolHandler();
        }

        /// <inheritdoc />
        public void Initialize(ITransport transport)
        {
            if (transport == null)
                throw new ArgumentNullException(nameof(transport));
            if (_transport != null)
                throw new InvalidOperationException("Already initialized.");

            _transport = transport;
            _ownsTransport = false;
            _transport.OnDataReceived += OnTransportDataReceived;
        }

        /// <inheritdoc />
        public async Task Connect(string? targetId)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(ConnectionManager));

            if (_transport != null)
            {
                _transport.OnDataReceived -= OnTransportDataReceived;
                if (_ownsTransport)
                    _transport.Dispose();
                _transport = null;
            }

            var transport = new SocketTransport();
            _transport = transport;
            _ownsTransport = true;
            _transport.OnDataReceived += OnTransportDataReceived;
            await _transport.Connect(targetId).ConfigureAwait(false);
        }

        /// <inheritdoc />
        public bool IsConnected() => _transport?.IsConnected() ?? false;

        /// <inheritdoc />
        public void RegisterHandler(int correlationId, Action<byte[]> callback)
        {
            if (callback == null)
                throw new ArgumentNullException(nameof(callback));
            _routingMap.AddOrUpdate(correlationId, callback, (_, __) => callback);
        }

        /// <inheritdoc />
        public void UnregisterHandler(int correlationId)
        {
            _routingMap.TryRemove(correlationId, out _);
        }

        /// <inheritdoc />
        public async Task SmartSend(Stream source, string type, string? payload = null)
        {
            if (source == null)
                throw new ArgumentNullException(nameof(source));
            if (string.IsNullOrWhiteSpace(type))
                throw new ArgumentException("Type cannot be null or empty.", nameof(type));
            if (_transport == null || !_transport.IsConnected())
                throw new InvalidOperationException("Transport not connected. Initialize and connect first.");

            int correlationId = AllocateCorrelationId();
            var request = new TransferRequest
            {
                CorrelationID = correlationId,
                Type = type,
                Status = "PUSH",
                FileSize = source.CanSeek ? source.Length : 0,
                Payload = payload
            };

            bool ok = await RunHandshakeAsync(request).ConfigureAwait(false);
            if (!ok)
            {
                ReleaseCorrelationIdIfOurs(correlationId);
                UnregisterHandler(correlationId);
                throw new InvalidOperationException("Handshake rejected by peer.");
            }

            try
            {
                await StreamDataAsync(source, correlationId).ConfigureAwait(false);
            }
            finally
            {
                UnregisterHandler(correlationId);
            }
        }

        /// <inheritdoc />
        public async Task<Stream> GetStream(string type, string? payload = null)
        {
            if (string.IsNullOrWhiteSpace(type))
                throw new ArgumentException("Type cannot be null or empty.", nameof(type));
            if (_transport == null || !_transport.IsConnected())
                throw new InvalidOperationException("Transport not connected. Initialize and connect first.");

            int correlationId = AllocateCorrelationId();
            var backStream = new BackBufferedStream();

            void Handler(byte[] data)
            {
                backStream.WriteChunk(data);
            }

            RegisterHandler(correlationId, Handler);
            _onFinByCorrelationId[correlationId] = () => backStream.Complete();

            var request = new TransferRequest
            {
                CorrelationID = correlationId,
                Type = type,
                Status = "REQ",
                Payload = payload
            };

            byte[] controlResponse = await WaitForControlResponseAsync().ConfigureAwait(false);
            TransferRequest? approval = ParseTransferRequest(controlResponse);
            if (approval == null || approval.Status != "APPROVE")
            {
                ReleaseCorrelationIdIfOurs(correlationId);
                UnregisterHandler(correlationId);
                backStream.Dispose();
                throw new InvalidOperationException("GetStream: expected APPROVE from peer.");
            }

            await SendControlResponseAsync(correlationId, "OK").ConfigureAwait(false);

            _ = Task.Run(async () =>
            {
                try
                {
                    await WaitForStreamFinAsync(correlationId, backStream).ConfigureAwait(false);
                }
                catch (Exception ex)
                {
                    OnError(new InvalidOperationException("GetStream receive failed.", ex));
                }
                finally
                {
                    ReleaseCorrelationIdIfOurs(correlationId);
                    UnregisterHandler(correlationId);
                    _onFinByCorrelationId.TryRemove(correlationId, out _);
                }
            });

            return backStream;
        }

        /// <summary>
        /// Called by transport when a complete TPack is received.
        /// Reassembly (buffer until 8-byte header + Length bytes payload) is done in the Transport layer (e.g. SocketTransport);
        /// this method always receives a full TPack, never a fragment.
        /// </summary>
        private void OnTransportDataReceived(object? sender, byte[] rawPacket)
        {
            if (rawPacket == null || _protocolHandler == null) return;

            try
            {
                (int correlationId, byte[] payload, byte flags) = _protocolHandler.ParseFrame(rawPacket);

                if (correlationId == CoreConfig.ControlChannelId)
                {
                    lock (_controlLock)
                    {
                        if (_pendingControlWaiter != null)
                        {
                            var tcs = _pendingControlWaiter;
                            _pendingControlWaiter = null;
                            tcs.TrySetResult(payload);
                            return;
                        }
                    }

                    TryHandleIncomingHandshake(payload);
                    return;
                }

                if (_routingMap.TryGetValue(correlationId, out var handler))
                {
                    handler(payload);
                    if ((flags & CoreConfig.FlagFin) != 0)
                    {
                        if (_onFinByCorrelationId.TryRemove(correlationId, out var onFin))
                            onFin();
                        UnregisterHandler(correlationId);
                    }
                    return;
                }

                TryHandleIncomingHandshake(payload);
            }
            catch (Exception ex)
            {
                OnError(new InvalidOperationException("HandleIncoming failed.", ex));
            }
        }

        private void TryHandleIncomingHandshake(byte[] payload)
        {
            TransferRequest? req = ParseTransferRequest(payload);
            if (req == null || !req.IsValid())
                return;

            if (req.Status == "REQ" || req.Status == "PUSH")
            {
                if (!_routingMap.ContainsKey(req.CorrelationID))
                {
                    var defaultHandler = new Action<byte[]>(_ => { });
                    RegisterHandler(req.CorrelationID, defaultHandler);
                }
                _ = SendControlResponseAsync(req.CorrelationID, "OK", req.Type);
            }
        }

        private async Task<bool> RunHandshakeAsync(TransferRequest request)
        {
            return await _protocolHandler.SendHandshakeAsync(
                request,
                data => _transport!.SendRaw(data),
                () => WaitForControlResponseAsync()).ConfigureAwait(false);
        }

        private Task<byte[]> WaitForControlResponseAsync()
        {
            var cts = new CancellationTokenSource(TimeSpan.FromSeconds(CoreConfig.HandshakeTimeoutSeconds));
            TaskCompletionSource<byte[]> tcs;
            lock (_controlLock)
            {
                if (_pendingControlWaiter != null)
                    throw new InvalidOperationException("A handshake is already pending.");
                _pendingControlWaiter = tcs = new TaskCompletionSource<byte[]>();
            }

            cts.Token.Register(() => tcs.TrySetException(new TimeoutException("Handshake timeout.")));
            return tcs.Task;
        }

        private async Task SendControlResponseAsync(int requestCorrelationId, string status, string? type = null)
        {
            var response = new TransferRequest
            {
                MagicBytes = 0x54415553,
                CorrelationID = requestCorrelationId,
                Type = type ?? string.Empty,
                Status = status,
                FileSize = 0
            };
            string json = JsonSerializer.Serialize(response);
            byte[] body = Encoding.UTF8.GetBytes(json);
            byte[] frame = _protocolHandler.BuildFrame(CoreConfig.ControlChannelId, body);
            await _transport!.SendRaw(frame).ConfigureAwait(false);
        }

        private async Task StreamDataAsync(Stream source, int correlationId)
        {
            byte[] buffer = new byte[CoreConfig.StreamChunkSize];
            long totalSent = 0;
            int read;
            bool first = true;

            while ((read = await source.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false)) > 0)
            {
                byte[] chunk = new byte[read];
                Buffer.BlockCopy(buffer, 0, chunk, 0, read);
                byte[] frame = _protocolHandler.BuildFrame(correlationId, chunk);
                await _transport!.SendRaw(frame).ConfigureAwait(false);
                totalSent += read;
                first = false;
            }

            if (first && totalSent == 0)
                return;

            byte[] finFrame = _protocolHandler.BuildFrame(correlationId, Array.Empty<byte>(), CoreConfig.FlagFin);
            await _transport!.SendRaw(finFrame).ConfigureAwait(false);
        }

        /// <summary>
        /// Stub: stream EOF is signaled when a TPack with FIN flag is received in <see cref="OnTransportDataReceived"/>,
        /// which invokes the callback in <see cref="_onFinByCorrelationId"/> and calls <see cref="BackBufferedStream.Complete"/>.
        /// The Python (or other) reader then sees end-of-stream and does not block indefinitely.
        /// </summary>
        private async Task WaitForStreamFinAsync(int correlationId, BackBufferedStream backStream)
        {
            await Task.CompletedTask.ConfigureAwait(false);
        }

        /// <summary>
        /// Returns an odd CorrelationID for C#. Reuses released IDs first to avoid exhausting 3-byte space in long-running services.
        /// </summary>
        private int AllocateCorrelationId()
        {
            if (_releasedCorrelationIds.TryTake(out int reused))
                return reused;

            int id = Interlocked.Add(ref _nextCorrelationId, 2) - 2;
            if (id <= 0) id = 1;
            if (id > 0xFFFFFF) { Interlocked.Exchange(ref _nextCorrelationId, 1); id = 1; }
            return id;
        }

        /// <summary>
        /// Returns a CorrelationID to the pool when it is one we allocated (odd) and in valid range, so it can be reused.
        /// </summary>
        private void ReleaseCorrelationIdIfOurs(int correlationId)
        {
            if (correlationId > 0 && correlationId <= 0xFFFFFF && (correlationId & 1) != 0)
                _releasedCorrelationIds.Add(correlationId);
        }

        private static TransferRequest? ParseTransferRequest(byte[] payload)
        {
            if (payload == null || payload.Length == 0) return null;
            try
            {
                string json = Encoding.UTF8.GetString(payload);
                return JsonSerializer.Deserialize<TransferRequest>(json);
            }
            catch
            {
                return null;
            }
        }

        private void OnError(Exception ex)
        {
            ErrorOccurred?.Invoke(this, ex);
        }

        public void Dispose()
        {
            if (_disposed) return;
            if (_transport != null)
            {
                _transport.OnDataReceived -= OnTransportDataReceived;
                if (_ownsTransport)
                    _transport.Dispose();
                _transport = null;
            }
            _routingMap.Clear();
            _onFinByCorrelationId.Clear();
            lock (_controlLock)
            {
                _pendingControlWaiter?.TrySetCanceled();
            }
            _disposed = true;
        }
    }
}
