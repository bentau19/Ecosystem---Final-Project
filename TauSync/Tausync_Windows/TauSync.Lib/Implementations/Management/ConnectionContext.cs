using System;
using System.Collections.Concurrent;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Implementations.Transport;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Management
{
    /// <summary>
    /// Central hub (Singleton) for ID management and packet routing per TauSync v3.
    /// Branch on TargetID first; TargetID=0 = discovery (require CONTROL + MagicBytes); TargetID&gt;0 = pass to handler.
    /// FIN cleanup: remove from both _routingMap and _targetMap, then ReleaseId.
    /// </summary>
    public sealed class ConnectionContext
    {
        private static readonly ConnectionContext _instance = new ConnectionContext();

        public static ConnectionContext Instance => _instance;

        private const int MinId = 1;
        private const int MaxId = 0xFFFFFF;

        private int _nextCorrelationId = MinId;

        /// <summary>
        /// IDs eligible for reuse, keyed for idempotent add (prevents double-recycle when both
        /// FIN-dispatch and <see cref="ConnectionManager.CompleteStream"/> release the same ID).
        /// IDs are added only after a grace period so that in-flight FIN frames targeting a recycled
        /// ID don't corrupt the new handler registered for that ID.
        /// </summary>
        private readonly ConcurrentDictionary<int, byte> _releasedIds = new();

        private const int IdRecycleDelayMs = 2000;

        /// <summary>LocalID -> handler(payload, flags). Handler decides DATA vs in-band CONTROL.</summary>
        private readonly ConcurrentDictionary<int, Action<byte[], byte>> _routingMap = new();

        /// <summary>LocalID -> PeerID. For sending: use TargetID = _targetMap[localId] in TPack header.</summary>
        private readonly ConcurrentDictionary<int, int> _targetMap = new();

        /// <summary>Meeting Word -> callback(localId, peerSenderId, stream). Invoked when REQ arrives on TargetID=0.</summary>
        private readonly ConcurrentDictionary<string, Action<int, int, Stream>> _serviceRegistry = new();

        /// <summary>
        /// REQ payloads queued per word when a discovery frame arrives before <see cref="RegisterService"/> was called
        /// (e.g. client calls <c>Connect(word)</c> before the server has registered the same word). Drained when the service registers.
        /// </summary>
        private readonly ConcurrentDictionary<string, ConcurrentQueue<byte[]>> _pendingDiscoveryByWord = new();

        private const int MaxPendingDiscoveryPerWord = 64;

        private readonly ITransport _wifiTransport;

        private ConnectionContext()
        {
            _wifiTransport = new SocketTransport();
        }

        public async Task InitializeTransports(string?targetId, int? timeoutSeconds = null)
        {
            if (_wifiTransport.IsConnected())
                throw new InvalidOperationException("Transport already connected.");
            if (_wifiTransport == null)
                throw new InvalidOperationException("Not initialized.");
            await _wifiTransport.Connect(targetId, timeoutSeconds).ConfigureAwait(false);     
        }

        public ITransport? GetWifiTransport() => _wifiTransport as ITransport;
        public SocketTransport? GetWifiTransportAsSocket() => _wifiTransport as SocketTransport;

        /// <summary>
        /// Returns true when the underlying transport accepted a connection (server mode).
        /// Used by <see cref="ConnectionManager"/> to deterministically break the simultaneous-connect race:
        /// the server side prefers the incoming (peer) path, the client side prefers the outgoing (own) path.
        /// </summary>
        public bool IsTransportServerMode =>
            (_wifiTransport as SocketTransport)?.IsServerMode ?? false;

        public int ReserveId()
        {
            foreach (var key in _releasedIds.Keys)
            {
                if (_releasedIds.TryRemove(key, out _))
                    return key;
            }

            int id = Interlocked.Increment(ref _nextCorrelationId) - 1;
            if (id < MinId || id > MaxId)
            {
                Interlocked.Exchange(ref _nextCorrelationId, MinId + 1);
                id = MinId;
            }
            return id;
        }


        public IReadOnlyList<string> GetPeerWaitingWords()
        {
            var result = new List<string>();
            foreach (var kvp in _pendingDiscoveryByWord)
            {
                if (kvp.Value.Count > 0)
                    result.Add(kvp.Key);
            }
            return result;
        }




        /// <summary>
        /// Releases ID: clears routing/target maps immediately, then schedules the ID
        /// for recycling after <see cref="IdRecycleDelayMs"/> so that in-flight FIN frames
        /// are processed before another handler can claim the same ID.
        /// </summary>
        public void ReleaseId(int id)
        {
            if (id < MinId || id > MaxId)
                return;
            _routingMap.TryRemove(id, out _);
            _targetMap.TryRemove(id, out _);
            _ = RecycleIdAfterDelayAsync(id);
        }

        private async Task RecycleIdAfterDelayAsync(int id)
        {
            await Task.Delay(IdRecycleDelayMs).ConfigureAwait(false);
            _releasedIds[id] = 0;
        }

        /// <summary>PeerID to use when sending for this local task. Returns null if not bound.</summary>
        public int? GetPeerIdFor(int localId)
        {
            return _targetMap.TryGetValue(localId, out int peerId) ? peerId : null;
        }

        /// <summary>Binds localId -> peerId for sending (e.g. after initiator receives OK).</summary>
        public void SetTargetForSend(int localId, int peerId)
        {
            if (localId < MinId || localId > MaxId) return;
            _targetMap[localId] = peerId;
        }

        public void RegisterHandler(int correlationId, Action<byte[], byte> handler)
        {
            if (handler == null) throw new ArgumentNullException(nameof(handler));
            _routingMap.AddOrUpdate(correlationId, handler, (_, __) => handler);
        }

        public void UnregisterHandler(int correlationId)
        {
            _routingMap.TryRemove(correlationId, out _);
        }

        /// <summary>Registers a listener for a Meeting Word. Callback receives (localId, peerSenderId, stream).</summary>
        public void RegisterService(string word, Action<int, int, Stream> callback)
        {
            if (string.IsNullOrWhiteSpace(word)) throw new ArgumentException("Word cannot be null or empty.", nameof(word));
            if (callback == null) throw new ArgumentNullException(nameof(callback));
            string key = word.Trim();
            _serviceRegistry[key] = callback;
            DrainPendingDiscovery(key);
        }

        public void UnregisterService(string word)
        {
            if (string.IsNullOrWhiteSpace(word)) return;
            string key = word.Trim();
            _serviceRegistry.TryRemove(key, out _);
            _pendingDiscoveryByWord.TryRemove(key, out _);
        }

        /// <summary>Dispatch: check TargetID first (§0.1). targetId=0 requires CONTROL+MagicBytes; targetId&gt;0 pass to handler. FIN: cleanup both maps + ReleaseId (§0.2).</summary>
        public bool Dispatch(int targetId, byte[] payload, byte flags)
        {
            payload ??= Array.Empty<byte>();
            if (targetId > 0)
                return DispatchToExistingChannel(targetId, payload, flags);

            return DispatchDiscoveryRequest(payload, flags);
        }

        private bool DispatchToExistingChannel(int targetId, byte[] payload, byte flags)
        {
            if (!_routingMap.TryGetValue(targetId, out var handler))
                return false;

            handler(payload, flags);
            if ((flags & CoreConfig.FlagFin) != 0)
            {
                _routingMap.TryRemove(targetId, out _);
                _targetMap.TryRemove(targetId, out _);
                ReleaseId(targetId);
            }
            return true;
        }

        private bool DispatchDiscoveryRequest(byte[] payload, byte flags)
        {
            if ((flags & CoreConfig.FlagControl) == 0)
                return false;
            if (!TryParseDiscoveryRequest(payload, out TransferRequest request))
                return false;
            if (!TryResolveServiceCallback(request, out Action<int, int, Stream> callback))
            {
                // Peer sent REQ before we registered this word — queue and report handled so the frame is not dropped.
                string? word = request.Type?.Trim();
                if (!string.IsNullOrEmpty(word))
                {
                    EnqueuePendingDiscovery(word, payload);
                    return true;
                }
                return false;
            }

            return CompleteDiscoveryHandshake(request, callback);
        }

        private void EnqueuePendingDiscovery(string word, byte[] payload)
        {
            ConcurrentQueue<byte[]> queue = _pendingDiscoveryByWord.GetOrAdd(word, _ => new ConcurrentQueue<byte[]>());
            byte[] copy = new byte[payload.Length];
            Buffer.BlockCopy(payload, 0, copy, 0, payload.Length);
            while (queue.Count >= MaxPendingDiscoveryPerWord && queue.TryDequeue(out _)) { }
            queue.Enqueue(copy);
        }

        private void DrainPendingDiscovery(string word)
        {
            if (!_pendingDiscoveryByWord.TryGetValue(word, out ConcurrentQueue<byte[]>? queue) || queue == null)
                return;

            while (queue.TryDequeue(out byte[]? payload))
            {
                if (payload == null || payload.Length == 0)
                    continue;
                if (!TryParseDiscoveryRequest(payload, out TransferRequest request))
                    continue;
                if (!TryResolveServiceCallback(request, out Action<int, int, Stream> callback))
                    continue;
                CompleteDiscoveryHandshake(request, callback);
            }
        }

        private bool CompleteDiscoveryHandshake(TransferRequest request, Action<int, int, Stream> callback)
        {
            int localId = ReserveId();
            _targetMap[localId] = request.SenderID;

            var stream = new BackBufferedStream();
            _routingMap[localId] = CreateIncomingChannelHandler(localId, stream);

            ScheduleServiceCallback(callback, localId, request.SenderID, stream);
            return true;
        }

        private Action<byte[], byte> CreateIncomingChannelHandler(int localId, BackBufferedStream stream)
        {
            return (payload, flags) =>
            {
                if (payload != null && payload.Length > 0)
                    stream.WriteChunk(payload);
                if ((flags & CoreConfig.FlagFin) != 0)
                {
                    stream.Complete();
                    CleanupLocalId(localId);
                }
            };
        }

        private void ScheduleServiceCallback(Action<int, int, Stream> callback, int localId, int peerSenderId, BackBufferedStream stream)
        {
            _ = Task.Run(() =>
            {
                try
                {
                    callback(localId, peerSenderId, stream);
                }
                catch
                {
                    CleanupLocalId(localId);
                    stream.Dispose();
                    throw;
                }
            });
        }

        private void CleanupLocalId(int localId)
        {
            _routingMap.TryRemove(localId, out _);
            _targetMap.TryRemove(localId, out _);
            ReleaseId(localId);
        }

        private bool TryParseDiscoveryRequest(byte[] payload, out TransferRequest request)
        {
            request = default!;
            TransferRequest? parsed = ParseTransferRequest(payload);
            if (parsed == null)
                return false;
            if (parsed.MagicBytes != CoreConfig.MagicBytes)
                return false;
            if (!string.Equals(parsed.Status?.Trim(), "REQ", StringComparison.OrdinalIgnoreCase))
                return false;

            request = parsed;
            return true;
        }

        private bool TryResolveServiceCallback(TransferRequest request, out Action<int, int, Stream> callback)
        {
            callback = null!;
            string? word = request.Type?.Trim();
            if (string.IsNullOrEmpty(word))
                return false;

            if (_serviceRegistry.TryGetValue(word, out var resolved))
            {
                callback = resolved;
                return true;
            }

            callback = null!;
            return false;
        }

        public bool HasHandlerFor(int id)
        {
            return _routingMap.ContainsKey(id);
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
    }
}
