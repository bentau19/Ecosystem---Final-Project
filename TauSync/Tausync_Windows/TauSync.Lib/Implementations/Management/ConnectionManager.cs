using System;
using System.Collections.Concurrent;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Channels;
using TauSync.Core;
using TauSync.Implementations.Protocol;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Management
{
    /// <summary>
    /// Connection manager per TauSync v3: both sides call Connect(word); when two peers use the same word they are paired and get a stream.
    /// </summary>
    public class ConnectionManager : IConnectionManager
    {
        private ITransport? _wifiTransport;
        private readonly IProtocolHandler _protocolHandler;
        /// <summary>Per-word queue of incoming connections (when the other side sent REQ first).</summary>
        private readonly ConcurrentDictionary<string, Channel<Stream>> _incomingByWord = new();
        private bool _disposed;

        public event EventHandler<Exception>? ErrorOccurred;

        public ConnectionManager()
        {
            _protocolHandler = new ProtocolHandler();
            ITransport? transport = ConnectionContext.Instance.GetWifiTransport();
            if (transport == null)
                throw new InvalidOperationException("ConnectionContext has no transport.");
            Initialize(transport);
        }

        /// <inheritdoc />
        public void Initialize(ITransport transport)
        {

            if (transport == null)
                throw new ArgumentNullException(nameof(transport));
            if (_wifiTransport != null)
                throw new InvalidOperationException("Already initialized.");
            _wifiTransport = transport;
        }

        /// <inheritdoc />
        public async Task ConnectTransport(string? targetId, int? timeoutSeconds = null)
        {
            await ConnectionContext.Instance.InitializeTransports(targetId, timeoutSeconds).ConfigureAwait(false);
        }

        /// <inheritdoc />
        public bool IsConnected() => _wifiTransport?.IsConnected() ?? false;


        public void Disconnect()  {
            if (_disposed || !IsConnected()) {
                    return;
            }
            _wifiTransport.Disconnect();

        }

        /// <inheritdoc />
        public async Task<Stream> Connect(string word, int? timeoutSeconds = null)
        {
            ValidateConnectState(word);
            string wordTrimmed = word.Trim();
            Channel<Stream> channel = GetOrCreateWordChannel(wordTrimmed);
            RegisterWordListener(wordTrimmed, channel);

            var ctx = ConnectionContext.Instance;
            ConnectAttempt attempt = CreateConnectAttempt(ctx);
            await SendWordRequestAsync(wordTrimmed, attempt.LocalId).ConfigureAwait(false);
            return await ResolveConnectRaceAsync(ctx, channel, attempt, timeoutSeconds).ConfigureAwait(false);
        }

        private void ValidateConnectState(string word)
        {
            if (string.IsNullOrWhiteSpace(word))
                throw new ArgumentException("Word cannot be null or empty.", nameof(word));
            if (_wifiTransport == null || !_wifiTransport.IsConnected())
                throw new InvalidOperationException("Transport not connected. ConnectTransport first.");
            if (_disposed)
                throw new ObjectDisposedException(nameof(ConnectionManager));
        }

        private Channel<Stream> GetOrCreateWordChannel(string word)
        {
            return _incomingByWord.GetOrAdd(word, _ =>
                Channel.CreateUnbounded<Stream>(new UnboundedChannelOptions { SingleReader = false, SingleWriter = false }));
        }

        private ConnectAttempt CreateConnectAttempt(ConnectionContext ctx)
        {
            int localId = ctx.ReserveId();
            var backStream = new BackBufferedStream();
            var responseTcs = new TaskCompletionSource<byte[]>();

            void Handler(byte[] payload, byte flags)
            {
                if ((flags & CoreConfig.FlagControl) != 0)
                {
                    responseTcs.TrySetResult(payload ?? Array.Empty<byte>());
                    return;
                }

                if (payload != null && payload.Length > 0)
                    backStream.WriteChunk(payload);
                if ((flags & CoreConfig.FlagFin) != 0)
                    backStream.Complete();
            }

            ctx.RegisterHandler(localId, Handler);
            return new ConnectAttempt(localId, backStream, responseTcs);
        }

        /// <summary>
        /// Resolves the simultaneous-connect race deterministically using the transport role:
        /// the TCP client always uses the outgoing (own REQ→OK) path,
        /// the TCP server always uses the incoming (peer REQ→service callback) path.
        /// This guarantees both sides pick complementary streams so data flows correctly.
        /// Falls back to the other path if the preferred one fails.
        /// </summary>
        private async Task<Stream> ResolveConnectRaceAsync(ConnectionContext ctx, Channel<Stream> channel, ConnectAttempt attempt, int? timeoutSeconds)
        {
            using var timeoutCts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds ?? CoreConfig.HandshakeTimeoutSeconds));
            timeoutCts.Token.Register(() => attempt.ResponseTcs.TrySetException(new TimeoutException("Handshake timeout.")));

            Task<Stream> streamFromOwnRequest = WaitForOkAndBuildStreamAsync(attempt.ResponseTcs.Task, ctx, attempt.LocalId, attempt.BackStream);
            Task<Stream> streamFromPeerRequest = channel.Reader.ReadAsync(CancellationToken.None).AsTask();

            bool preferOwnPath = !ctx.IsTransportServerMode;

            if (preferOwnPath)
            {
                try
                {
                    return await streamFromOwnRequest.ConfigureAwait(false);
                }
                catch
                {
                    CleanupLosingOutgoingAttempt(ctx, attempt);
                    return await streamFromPeerRequest.ConfigureAwait(false);
                }
            }

            try
            {
                Stream result = await streamFromPeerRequest.ConfigureAwait(false);
                CleanupLosingOutgoingAttempt(ctx, attempt);
                return result;
            }
            catch
            {
                return await streamFromOwnRequest.ConfigureAwait(false);
            }
        }

        private static void CleanupLosingOutgoingAttempt(ConnectionContext ctx, ConnectAttempt attempt)
        {
            ctx.ReleaseId(attempt.LocalId);
            ctx.UnregisterHandler(attempt.LocalId);
            attempt.BackStream.Dispose();
        }

        /// <summary>
        /// Registers a per-word callback ("listener") that accepts incoming REQ handshakes,
        /// responds with OK, and publishes the created duplex stream to the word channel.
        /// </summary>
        private void RegisterWordListener(string word, Channel<Stream> channel)
        {
            ConnectionContext.Instance.RegisterService(word, (localId, peerSenderId, stream) =>
            {
                HandleWordRequest(word, channel, localId, peerSenderId, stream);
            });
        }

        private void HandleWordRequest(string word, Channel<Stream> channel, int localId, int peerSenderId, Stream stream)
        {
            try
            {
                byte[] frame = BuildOkFrame(word, localId, peerSenderId);
                _wifiTransport!.SendRaw(frame).GetAwaiter().GetResult();

                var duplex = new DuplexStream(stream, localId, this);
                channel.Writer.TryWrite(duplex);
            }
            catch (Exception ex)
            {
                ErrorOccurred?.Invoke(this, ex);
            }
        }

        private byte[] BuildOkFrame(string word, int localId, int peerSenderId)
        {
            var ok = new TransferRequest
            {
                MagicBytes = CoreConfig.MagicBytes,
                SenderID = localId,
                Type = word,
                Status = "OK"
            };

            string json = JsonSerializer.Serialize(ok);
            byte[] body = Encoding.UTF8.GetBytes(json);
            return _protocolHandler.BuildFrame(peerSenderId, body, CoreConfig.FlagControl);
        }

        /// <summary>
        /// Sends a REQ control handshake frame for the given word and local id.
        /// </summary>
        private async Task SendWordRequestAsync(string word, int localId)
        {
            var request = new TransferRequest
            {
                MagicBytes = CoreConfig.MagicBytes,
                SenderID = localId,
                Type = word,
                Status = "REQ"
            };

            byte[] reqBody = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request));
            byte[] reqFrame = _protocolHandler.BuildFrame(CoreConfig.ControlChannelId, reqBody, CoreConfig.FlagControl);
            await _wifiTransport!.SendRaw(reqFrame).ConfigureAwait(false);
        }

        private async Task<Stream> WaitForOkAndBuildStreamAsync(Task<byte[]> responseTask, ConnectionContext ctx, int localId, BackBufferedStream backStream)
        {
            byte[] payload = await responseTask.ConfigureAwait(false);
            TransferRequest? response = ParseTransferResponse(payload);
            if (response == null || !string.Equals(response.Status?.Trim(), "OK", StringComparison.OrdinalIgnoreCase))
            {
                ctx.ReleaseId(localId);
                ctx.UnregisterHandler(localId);
                backStream.Dispose();
                throw new InvalidOperationException("Connect rejected by peer.");
            }
            ctx.SetTargetForSend(localId, response.SenderID);
            return new DuplexStream(backStream, localId, this);
        }

        /// <inheritdoc />
        public void SendStreamData(int localId, byte[] buffer, int offset, int count)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(ConnectionManager));
            if (_wifiTransport == null)
                throw new InvalidOperationException("Transport not initialized.");
            if (buffer == null)
                throw new ArgumentNullException(nameof(buffer));
            if (offset < 0 || count < 0 || offset + count > buffer.Length)
                throw new ArgumentOutOfRangeException(nameof(buffer));
            if (count <= 0)
                return;

            int? peerId = ConnectionContext.Instance.GetPeerIdFor(localId);
            if (peerId == null)
                throw new InvalidOperationException(
                    $"No peer route for localId {localId}. Handshake may not have completed; do not write before Connect(word) finishes.");

            int sent = 0;
            while (sent < count)
            {
                int sliceLen = Math.Min(CoreConfig.StreamChunkSize, count - sent);
                byte[] chunk = new byte[sliceLen];
                Buffer.BlockCopy(buffer, offset + sent, chunk, 0, sliceLen);
                byte[] frame = _protocolHandler.BuildFrame(peerId.Value, chunk, 0);
                _wifiTransport.SendRaw(frame).GetAwaiter().GetResult();
                sent += sliceLen;
            }
        }

        /// <inheritdoc />
        public async Task SendStreamDataAsync(int localId, byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(ConnectionManager));
            if (_wifiTransport == null)
                throw new InvalidOperationException("Transport not initialized.");
            if (buffer == null)
                throw new ArgumentNullException(nameof(buffer));
            if (offset < 0 || count < 0 || offset + count > buffer.Length)
                throw new ArgumentOutOfRangeException(nameof(buffer));
            if (count <= 0)
                return;

            int? peerId = ConnectionContext.Instance.GetPeerIdFor(localId);
            if (peerId == null)
                throw new InvalidOperationException(
                    $"No peer route for localId {localId}. Handshake may not have completed; do not write before Connect(word) finishes.");

            int sent = 0;
            while (sent < count)
            {
                cancellationToken.ThrowIfCancellationRequested();
                int sliceLen = Math.Min(CoreConfig.StreamChunkSize, count - sent);
                byte[] chunk = new byte[sliceLen];
                Buffer.BlockCopy(buffer, offset + sent, chunk, 0, sliceLen);
                byte[] frame = _protocolHandler.BuildFrame(peerId.Value, chunk, 0);
                await _wifiTransport.SendRaw(frame).ConfigureAwait(false);
                sent += sliceLen;
            }
        }

        /// <inheritdoc />
        public void CompleteStream(int localId)
        {
            if (_disposed)
                return;
            if (_wifiTransport == null)
                return;

            int? peerId = ConnectionContext.Instance.GetPeerIdFor(localId);
            if (peerId != null)
            {
                byte[] finFrame = _protocolHandler.BuildFrame(peerId.Value, Array.Empty<byte>(), CoreConfig.FlagFin);
                _wifiTransport.SendRaw(finFrame).GetAwaiter().GetResult();
            }
            ConnectionContext.Instance.ReleaseId(localId);
        }

        private static TransferRequest? ParseTransferResponse(byte[] payload)
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

        private sealed class ConnectAttempt
        {
            public int LocalId { get; }
            public BackBufferedStream BackStream { get; }
            public TaskCompletionSource<byte[]> ResponseTcs { get; }

            public ConnectAttempt(int localId, BackBufferedStream backStream, TaskCompletionSource<byte[]> responseTcs)
            {
                LocalId = localId;
                BackStream = backStream;
                ResponseTcs = responseTcs;
            }
        }

        public IReadOnlyList<string> GetPeerWaitingWords()
        {
            return ConnectionContext.Instance.GetPeerWaitingWords();
        }


        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            foreach (Channel<Stream> ch in _incomingByWord.Values)
                ch.Writer.Complete();
            _incomingByWord.Clear();
            _wifiTransport?.Dispose();
        }
    }

    /// <summary>
    /// Duplex stream: read from a backing stream (e.g. BackBufferedStream), write sends TPack with TargetID = peer for the given localId.
    /// On dispose, sends FIN and releases the local ID.
    /// </summary>
    internal sealed class DuplexStream : Stream
    {
        private readonly Stream _readStream;
        private readonly int _localId;
        private readonly IConnectionManager _connectionManager;
        private int _disposeState;  // 0 = live, 1 = disposed; flipped atomically so only one thread sends FIN
        private bool _disposed => Volatile.Read(ref _disposeState) != 0;
        private bool _finSent;

        public DuplexStream(Stream readStream, int localId, IConnectionManager connectionManager)
        {
            _readStream = readStream ?? throw new ArgumentNullException(nameof(readStream));
            _localId = localId;
            _connectionManager = connectionManager ?? throw new ArgumentNullException(nameof(connectionManager));
        }

        public override bool CanRead => true;
        public override bool CanWrite => true;
        public override bool CanSeek => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }

        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();

        public override int Read(byte[] buffer, int offset, int count)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            return _readStream.Read(buffer, offset, count);
        }


        public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            return await _readStream.ReadAsync(buffer, offset, count, cancellationToken).ConfigureAwait(false);
        }

        public override void Write(byte[] buffer, int offset, int count)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            if (_finSent) return;
            int sent = 0;
            while (sent < count)
            {
                int slice = Math.Min(CoreConfig.StreamChunkSize, count - sent);
                _connectionManager.SendStreamData(_localId, buffer, offset + sent, slice);
                sent += slice;
            }
        }

        public override async Task WriteAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(DuplexStream));
            if (_finSent) return;
            int sent = 0;
            while (sent < count)
            {
                cancellationToken.ThrowIfCancellationRequested();
                int slice = Math.Min(CoreConfig.StreamChunkSize, count - sent);
                await _connectionManager.SendStreamDataAsync(_localId, buffer, offset + sent, slice, cancellationToken).ConfigureAwait(false);
                sent += slice;
            }
        }

        public override void Flush() => _readStream?.Flush();

        protected override void Dispose(bool disposing)
        {
            if (Interlocked.Exchange(ref _disposeState, 1) != 0)
                return;  // Already disposed by another thread — don't send a second FIN.

            if (disposing)
            {
                _finSent = true;
                _connectionManager.CompleteStream(_localId);
                _readStream?.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
