using System.Reflection;
using System.Text;
using TauSync.Core;
using TauSync.Implementations.Protocol;
using TauSync.Implementations.Transport;

// Phase 2 reconnect test (localhost TCP, no hardware required).
//
// Verifies the resilience contract:
//   1. Frames flow over a freshly established link.
//   2. An UNEXPECTED drop (OS kills the socket; neither side calls Disconnect) does NOT end
//      the session — both transports reconnect on their own and frames flow again on the very
//      same instances, with no re-handshake.
//   3. An EXPLICIT Disconnect() tears the session down cleanly.
//
// The drop is simulated by closing the client's underlying TcpClient via reflection, which is
// indistinguishable from the OS dropping the connection from the transport's point of view.

var protocol = new ProtocolHandler();
int failures = 0;

using var server = new SocketTransport();
using var client = new SocketTransport();

var serverInbox = new System.Collections.Concurrent.BlockingCollection<string>();
server.OnDataReceived += (_, frame) =>
{
    var (_, payload, _) = protocol.ParseFrame(frame);
    serverInbox.Add(Encoding.UTF8.GetString(payload));
};

Console.WriteLine("Starting server (listen) + client (connect 127.0.0.1)...");
Task serverAccepted = server.Connect(null);
await Task.Delay(200);
await client.Connect("127.0.0.1");
await serverAccepted;
Console.WriteLine("Connected.\n");

await SendFromClient("before-drop");
ExpectAtServer("baseline", "before-drop", 3000);

Console.WriteLine("\nForcing an UNEXPECTED drop (killing client socket, no Disconnect)...");
ForceKillUnderlyingSocket(client);

Console.WriteLine("Waiting for automatic reconnect...");
if (await WaitUntil(() => client.IsConnected() && server.IsConnected(), 25000))
    Pass("reconnect", "both transports reconnected on their own");
else
    Fail("reconnect", "transports did not reconnect in time");

await SendFromClient("after-drop");
ExpectAtServer("post-reconnect", "after-drop", 5000);

Console.WriteLine("\nExplicit Disconnect()...");
client.Disconnect();
server.Disconnect();
await Task.Delay(500);
if (!client.IsConnected() && !server.IsConnected())
    Pass("disconnect", "both transports closed cleanly");
else
    Fail("disconnect", "still reporting connected after Disconnect()");

Console.WriteLine("\nChecking ConnectionContext ref-counting (abort only on the last transport)...");
CheckRefCounting();

Console.WriteLine();
Console.WriteLine(failures == 0 ? "ALL CHECKS PASSED" : $"{failures} CHECK(S) FAILED");
Environment.Exit(failures == 0 ? 0 : 1);


void CheckRefCounting()
{
    var context = TauSync.Implementations.Management.ConnectionContext.Instance;
    context.Reset();

    // Two transports up; one open channel.
    context.NotifyTransportConnected();
    context.NotifyTransportConnected();
    context.RegisterHandler(1234, (_, _) => { });

    context.NotifyTransportDisconnected(); // one transport down, one still up
    if (context.HasHandlerFor(1234))
        Pass("refcount-keep", "channel survived the first transport disconnect");
    else
        Fail("refcount-keep", "channel was aborted while another transport was still up");

    context.NotifyTransportDisconnected(); // last transport down
    if (!context.HasHandlerFor(1234))
        Pass("refcount-clear", "channel aborted when the last transport disconnected");
    else
        Fail("refcount-clear", "channel was not cleared after the last disconnect");
}


async Task SendFromClient(string text)
{
    byte[] frame = protocol.BuildFrame(
        CoreConfig.ControlChannelId, Encoding.UTF8.GetBytes(text), CoreConfig.FlagControl);
    await client.SendRaw(frame);
}

void ExpectAtServer(string label, string expected, int timeoutMs)
{
    if (serverInbox.TryTake(out string? got, timeoutMs) && got == expected)
        Pass(label, $"server received \"{got}\"");
    else
        Fail(label, $"expected \"{expected}\"");
}

void Pass(string label, string detail) => Console.WriteLine($"  PASS {label}: {detail}");
void Fail(string label, string detail) { Console.WriteLine($"  FAIL {label}: {detail}"); failures++; }

static void ForceKillUnderlyingSocket(SocketTransport transport)
{
    FieldInfo? field = typeof(SocketTransport)
        .GetField("_tcpClient", BindingFlags.NonPublic | BindingFlags.Instance);
    (field?.GetValue(transport) as System.Net.Sockets.TcpClient)?.Close();
}

static async Task<bool> WaitUntil(Func<bool> condition, int timeoutMs)
{
    var stopwatch = System.Diagnostics.Stopwatch.StartNew();
    while (stopwatch.ElapsedMilliseconds < timeoutMs)
    {
        if (condition()) return true;
        await Task.Delay(100);
    }
    return condition();
}
