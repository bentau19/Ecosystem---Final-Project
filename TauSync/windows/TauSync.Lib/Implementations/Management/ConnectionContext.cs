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
        private readonly ConcurrentBag<int> _releasedIds = new();

        /// <summary>LocalID -> handler(payload, flags). Handler decides DATA vs in-band CONTROL.</summary>
        private readonly ConcurrentDictionary<int, Action<byte[], byte>> _routingMap = new();

        /// <summary>LocalID -> PeerID. For sending: use TargetID = _targetMap[localId] in TPack header.</summary>
        private readonly ConcurrentDictionary<int, int> _targetMap = new();

        /// <summary>Meeting Word -> callback(localId, peerSenderId, stream). Invoked when REQ arrives on TargetID=0.</summary>
        private readonly ConcurrentDictionary<string, Action<int, int, Stream>> _serviceRegistry =
            new ConcurrentDictionary<string, Action<int, int, Stream>>(StringComparer.OrdinalIgnoreCase);

        private readonly ITransport _wifiTransport;

        private ConnectionContext()
        {
            _wifiTransport = new SocketTransport();
        }

        public async Task InitializeTransports(string?targetId)
        {
            if (_wifiTransport.IsConnected())
                throw new InvalidOperationException("Transport already connected.");
            if (_wifiTransport == null)
                throw new InvalidOperationException("Not initialized.");
            await _wifiTransport.Connect(targetId).ConfigureAwait(false);
            
        }

        public ITransport? GetWifiTransport() => _wifiTransport as ITransport;
        public SocketTransport? GetWifiTransportAsSocket() => _wifiTransport as SocketTransport;

        public int ReserveId()
        {
            if (_releasedIds.TryTake(out int reused))
                return reused;
            int id = Interlocked.Increment(ref _nextCorrelationId) - 1;
            if (id < MinId || id > MaxId)
            {
                Interlocked.Exchange(ref _nextCorrelationId, MinId + 1);
                id = MinId;
            }
            return id;
        }

        /// <summary>Releases ID to pool; removes from _routingMap and _targetMap (§0.2).</summary>
        public void ReleaseId(int id)
        {
            if (id < MinId || id > MaxId)
                return;
            _routingMap.TryRemove(id, out _);
            _targetMap.TryRemove(id, out _);
            _releasedIds.Add(id);
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
            _serviceRegistry[word.Trim()] = callback;
        }

        public void UnregisterService(string word)
        {
            if (string.IsNullOrWhiteSpace(word)) return;
            _serviceRegistry.TryRemove(word.Trim(), out _);
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
                return false;

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
