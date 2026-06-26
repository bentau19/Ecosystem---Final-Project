using System.Text;
using System.Text.Json;
using TauSync.Core;
using TauSync.Implementations.Management;
using TauSync.Implementations.Protocol;
using TauSync.Implementations.Transport;
using TauSync.Implementations.Util;
using TauSync.Interfaces;
using TauSync.Models;

// Phase 3 in-process tests (no Bluetooth hardware, no second machine).
//
// A full two-endpoint hybrid run needs two ConnectionContext instances, but it is a process-wide
// singleton — so the complete lazy-Wi-Fi flow is validated on real Windows+Android hardware. What
// runs here is everything checkable from a single context:
//   1. session-token lifecycle
//   2. the session-control dispatch hook (routes session frames, ignores meeting words / bad magic)
//   3. the BT_MAGIC handshake minting a token on the server
//   4. size-based routing (small -> Bluetooth)
//   5. the server-side Wi-Fi bring-up announcing WIFI_CONNECT_READY with the token + address
//   6. NetworkUtils

int failures = 0;
var protocol = new ProtocolHandler();
var ctx = ConnectionContext.Instance;

void Pass(string label, string detail) => Console.WriteLine($"  PASS {label}: {detail}");
void Fail(string label, string detail) { Console.WriteLine($"  FAIL {label}: {detail}"); failures++; }

byte[] SessionBody(string type, string? token = null, string? host = null, int port = 0)
{
    var message = new SessionControlMessage
    {
        Type = type, MagicBytes = CoreConfig.MagicBytes, SessionToken = token, WifiHost = host, WifiPort = port
    };
    return Encoding.UTF8.GetBytes(JsonSerializer.Serialize(message));
}

byte[] MeetingWordReqBody(string word, int senderId)
{
    var request = new TransferRequest
    {
        MagicBytes = CoreConfig.MagicBytes, SenderID = senderId, Type = word, Status = "REQ"
    };
    return Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request));
}

// ── Test 1: session-token lifecycle ────────────────────────────────────
ctx.Reset();
ctx.SetSessionToken("tok-123");
if (ctx.GetSessionToken() == "tok-123") Pass("token-set", "stored and retrieved");
else Fail("token-set", "not stored");
ctx.Reset();
if (ctx.GetSessionToken() == null) Pass("token-reset", "cleared by Reset()");
else Fail("token-reset", "still set after Reset()");

// ── Test 2: dispatch hook routes session control, ignores meeting words ─
ctx.Reset();
var received = new System.Collections.Concurrent.ConcurrentQueue<SessionControlMessage>();
ctx.RegisterSessionControlListener(received.Enqueue);

ctx.Dispatch(0, SessionBody(SessionControlMessage.TypeBtMagic), CoreConfig.FlagControl);
if (received.Count == 1 && received.TryPeek(out var got) && got.Type == SessionControlMessage.TypeBtMagic)
    Pass("hook-routes", "BT_MAGIC reached the session listener");
else
    Fail("hook-routes", $"expected one BT_MAGIC, got {received.Count}");

int beforeReq = received.Count;
ctx.Dispatch(0, MeetingWordReqBody("CLIPBOARD", 5), CoreConfig.FlagControl);
if (received.Count == beforeReq) Pass("hook-discriminates", "meeting-word REQ did not hit the session listener");
else Fail("hook-discriminates", "meeting-word REQ leaked to the session listener");
if (ctx.GetPeerWaitingWords().Contains("CLIPBOARD")) Pass("hook-fallthrough", "meeting-word REQ fell through to discovery");
else Fail("hook-fallthrough", "meeting-word REQ was not queued for discovery");

int beforeBadMagic = received.Count;
ctx.Dispatch(0, Encoding.UTF8.GetBytes("{\"MagicBytes\":1,\"Type\":\"BT_MAGIC\"}"), CoreConfig.FlagControl);
if (received.Count == beforeBadMagic) Pass("hook-magic", "frame with wrong MagicBytes rejected");
else Fail("hook-magic", "frame with wrong magic routed to the session listener");
ctx.UnregisterSessionControlListener();

// ── Test 3: BT_MAGIC handshake mints a token on the server ─────────────
ctx.Reset();
var bluetooth = new FakeBluetoothTransport(protocol, isServer: true);
var wifi = new SocketTransport { Port = 5599 };
var coordinator = new HybridSessionCoordinator(bluetooth, wifi, protocol);
ctx.RegisterSessionControlListener(coordinator.OnSessionControl);

bluetooth.Connect(null).GetAwaiter().GetResult();
Task handshake = coordinator.StartBtSessionAsync();

if (Wait(() => bluetooth.Sent.Any(m => m.Type == SessionControlMessage.TypeBtMagic), 2000))
    Pass("bt-magic-sent", "coordinator sent BT_MAGIC over Bluetooth");
else
    Fail("bt-magic-sent", "coordinator never sent its BT_MAGIC");

ctx.Dispatch(0, SessionBody(SessionControlMessage.TypeBtMagic), CoreConfig.FlagControl);
try { handshake.Wait(3000); } catch { }
if (ctx.GetSessionToken() != null) Pass("token-mint", "server minted a session token after BT_MAGIC");
else Fail("token-mint", "no token minted");

// ── Test 4: small payload routes over Bluetooth ────────────────────────
ITransport smallTarget = coordinator.TransportForSend(1024);
if (ReferenceEquals(smallTarget, bluetooth)) Pass("route-small", "payload <= 64 KB routed to Bluetooth");
else Fail("route-small", "small payload did not route to Bluetooth");

// ── Test 5: large payload makes the server announce WIFI_CONNECT_READY ──
bluetooth.ClearSent();
_ = Task.Run(() => coordinator.TransportForSend(200_000)); // blocks waiting for Wi-Fi; we only check the announce
if (Wait(() => bluetooth.Sent.Any(m => m.Type == SessionControlMessage.TypeWifiConnectReady), 4000))
    Pass("wifi-announce", "server announced WIFI_CONNECT_READY for a large payload");
else
    Fail("wifi-announce", "no WIFI_CONNECT_READY announced");

var ready = bluetooth.Sent.FirstOrDefault(m => m.Type == SessionControlMessage.TypeWifiConnectReady);
if (ready != null && ready.SessionToken == ctx.GetSessionToken() && !string.IsNullOrEmpty(ready.WifiHost))
    Pass("wifi-ready-fields", $"READY carries the token + address {ready.WifiHost}:{ready.WifiPort}");
else
    Fail("wifi-ready-fields", "READY missing token or host");

coordinator.Dispose();
wifi.Dispose();
ctx.UnregisterSessionControlListener();
ctx.Reset();

// ── Test 6: NetworkUtils does not throw ────────────────────────────────
try
{
    string? ip = NetworkUtils.GetLocalWifiIpAddress();
    Pass("netutils", $"local Wi-Fi IP = {ip ?? "(none found)"}");
}
catch (Exception ex)
{
    Fail("netutils", "threw: " + ex.Message);
}

// ── Test 7: Invalid SESSION_JOIN token → reject without crash ───────────
//
// When a SESSION_JOIN arrives with a token that does not match the one minted
// by the server, HandleSessionJoinAsync must (a) not throw, (b) not send an
// ACK, and (c) reset _wifiActivating so the coordinator can try again.
ctx.Reset();
var bt7 = new FakeBluetoothTransport(protocol, isServer: true);
var wifi7 = new SocketTransport { Port = 5600 };
var coord7 = new HybridSessionCoordinator(bt7, wifi7, protocol);
ctx.RegisterSessionControlListener(coord7.OnSessionControl);
bt7.Connect(null).GetAwaiter().GetResult();

// Complete BT_MAGIC so _isServer is set and the server mints its token.
// HandleSessionJoinAsync only runs when _isServer == true; without this
// the coordinator silently ignores the SESSION_JOIN and the test trivially passes.
Task handshake7 = coord7.StartBtSessionAsync();
ctx.Dispatch(0, SessionBody(SessionControlMessage.TypeBtMagic), CoreConfig.FlagControl);
try { handshake7.Wait(3000); } catch { }
string? mintedToken7 = ctx.GetSessionToken();

bool threw7 = false;
try
{
    ctx.Dispatch(0, SessionBody(SessionControlMessage.TypeSessionJoin, token: "wrong-token-7"),
                 CoreConfig.FlagControl);
    Thread.Sleep(300); // let HandleSessionJoinAsync complete
}
catch { threw7 = true; }

if (!threw7) Pass("invalid-token-no-crash", "invalid SESSION_JOIN did not propagate an exception");
else         Fail("invalid-token-no-crash", "exception propagated to the dispatcher caller");

if (ctx.GetSessionToken() == mintedToken7)
    Pass("invalid-token-intact", "session token unchanged after invalid SESSION_JOIN");
else
    Fail("invalid-token-intact",
         $"token changed from '{mintedToken7}' to '{ctx.GetSessionToken() ?? "(null)"}'");

// After ResetWifiActivation(), TriggerWifiConnect must work again:
// a fresh large-payload request should re-announce WIFI_CONNECT_READY.
bt7.ClearSent();
_ = Task.Run(() => coord7.TransportForSend(200_000));
if (Wait(() => bt7.Sent.Any(m => m.Type == SessionControlMessage.TypeWifiConnectReady), 4000))
    Pass("invalid-token-recovery", "coordinator re-announced WIFI_CONNECT_READY after bad-token rejection");
else
    Fail("invalid-token-recovery", "coordinator stuck — no WIFI_CONNECT_READY after bad-token rejection");

coord7.Dispose();
wifi7.Dispose();
ctx.UnregisterSessionControlListener();
ctx.Reset();

// ── Test 8: Both transports disconnect → reset called exactly once ───────
//
// The ref-count in ConnectionContext.NotifyTransportDisconnected ensures that
// AbortAllChannels() + Reset() fire only when the LAST live transport is torn
// down. Disconnecting one transport while the other stays up must leave all
// channel handlers and session state intact.
ctx.Reset();
ctx.NotifyTransportConnected(); // transport 1 up
ctx.NotifyTransportConnected(); // transport 2 up

int localId8 = ctx.ReserveId();
ctx.RegisterHandler(localId8, (_, __) => { /* handler present to detect reset */ });
ctx.SetSessionToken("session-8");

ctx.NotifyTransportDisconnected(); // count → 1: no reset yet
bool handlerStillThere = ctx.HasHandlerFor(localId8);
bool tokenStillSet     = ctx.GetSessionToken() == "session-8";

if (handlerStillThere && tokenStillSet)
    Pass("ref-count-one-down", "channels and token survive first disconnect (count still 1)");
else
    Fail("ref-count-one-down",
         $"handler={handlerStillThere} token={tokenStillSet} — expected both true when count→1");

ctx.NotifyTransportDisconnected(); // count → 0: AbortAllChannels() + Reset() must fire
bool handlerGone   = !ctx.HasHandlerFor(localId8);
bool tokenCleared  = ctx.GetSessionToken() == null;

if (handlerGone && tokenCleared)
    Pass("ref-count-both-down", "channels aborted and state reset only after last transport disconnects");
else
    Fail("ref-count-both-down",
         $"handlerGone={handlerGone} tokenCleared={tokenCleared} — expected both true when count→0");

Console.WriteLine();
Console.WriteLine(failures == 0 ? "ALL CHECKS PASSED" : $"{failures} CHECK(S) FAILED");
Environment.Exit(failures == 0 ? 0 : 1);


static bool Wait(Func<bool> condition, int timeoutMs)
{
    var stopwatch = System.Diagnostics.Stopwatch.StartNew();
    while (stopwatch.ElapsedMilliseconds < timeoutMs)
    {
        if (condition()) return true;
        Thread.Sleep(50);
    }
    return condition();
}


/// <summary>
/// Stand-in for the Bluetooth primary transport: records every frame the coordinator sends (parsed
/// back into a <see cref="SessionControlMessage"/>) and lets the test simulate the peer by feeding
/// frames through <see cref="ConnectionContext.Dispatch"/>. No real socket involved.
/// </summary>
sealed class FakeBluetoothTransport : ITransport
{
    private readonly IProtocolHandler _protocol;
    private readonly System.Collections.Concurrent.ConcurrentQueue<SessionControlMessage> _sent = new();
    private bool _connected;

    public FakeBluetoothTransport(IProtocolHandler protocol, bool isServer)
    {
        _protocol = protocol;
        IsServerMode = isServer;
    }

    public TransportKind TransportType => TransportKind.Bluetooth;
    public bool IsServerMode { get; }

#pragma warning disable CS0067 // event is part of the interface but unused by the fake
    public event EventHandler<byte[]>? OnDataReceived;
#pragma warning restore CS0067

    public Task Connect(string? targetId, int? timeoutSeconds = null) { _connected = true; return Task.CompletedTask; }
    public void Disconnect() => _connected = false;
    public bool IsConnected() => _connected;

    public Task SendRaw(byte[] data)
    {
        try
        {
            (_, byte[] payload, _) = _protocol.ParseFrame(data);
            var message = JsonSerializer.Deserialize<SessionControlMessage>(Encoding.UTF8.GetString(payload));
            if (message != null) _sent.Enqueue(message);
        }
        catch { /* non-session frame — ignore */ }
        return Task.CompletedTask;
    }

    public SessionControlMessage[] Sent => _sent.ToArray();
    public void ClearSent() { while (_sent.TryDequeue(out _)) { } }
    public void Dispose() { }
}
