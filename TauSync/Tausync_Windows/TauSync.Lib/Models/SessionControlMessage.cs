using System.Text.Json.Serialization;

namespace TauSync.Models
{
    /// <summary>
    /// Hybrid-session signaling message, sent as the payload of a TPack with TargetID=0 and
    /// Flags=CONTROL. Distinct from <see cref="TransferRequest"/> (meeting-word discovery): these
    /// frames coordinate the Bluetooth↔Wi-Fi session and are recognised by their <see cref="Type"/>
    /// being one of the <c>Type*</c> constants below, so they never collide with a meeting word.
    /// </summary>
    public class SessionControlMessage
    {
        /// <summary>Exchanged both ways right after RFCOMM opens to confirm both peers are TauSync.</summary>
        public const string TypeBtMagic = "BT_MAGIC";

        /// <summary>Sent over BT by whichever side first needs Wi-Fi (a large payload is queued).</summary>
        public const string TypeWifiConnectReq = "WIFI_CONNECT_REQ";

        /// <summary>Reply from the Wi-Fi server over BT carrying the session token and TCP address.</summary>
        public const string TypeWifiConnectReady = "WIFI_CONNECT_READY";

        /// <summary>First frame the Wi-Fi client sends on the new TCP socket; carries the token.</summary>
        public const string TypeSessionJoin = "SESSION_JOIN";

        /// <summary>Server's confirmation that the SESSION_JOIN token matched.</summary>
        public const string TypeSessionJoinAck = "SESSION_JOIN_ACK";

        /// <summary>Server → client: the operator declined the connection. The client aborts and does
        /// not auto-reconnect. Sent over Bluetooth before the server drops the link.</summary>
        public const string TypeSessionReject = "SESSION_REJECT";

        /// <summary>Client → server: echoed back after the client receives the server's BT_MAGIC, so the
        /// server can prove the link is still live and not a half-open socket the peer abandoned during
        /// a slow approval. Without this echo the server can declare a dead session "connected".</summary>
        public const string TypeSessionConfirm = "SESSION_CONFIRM";

        /// <summary>Server → client: the connection is waiting on the PC operator's approval. The
        /// client should keep the handshake alive for the full approval window instead of applying
        /// its normal (much shorter) connect timeout.</summary>
        public const string TypeApprovalPending = "APPROVAL_PENDING";

        /// <summary>Either side → peer, over Bluetooth: "I am about to close the idle Wi-Fi link."
        /// The receiver tears its Wi-Fi side down intentionally too, so neither side mistakes the
        /// close for an unexpected drop (which would trigger reconnect dialing against a closed
        /// port — the SYN/RST bursts).</summary>
        public const string TypeWifiIdleClose = "WIFI_IDLE_CLOSE";

        /// <summary>Protocol identity: 0x54415553 ("TAUS").</summary>
        [JsonPropertyName("MagicBytes")]
        public uint MagicBytes { get; set; } = 0x54415553;

        /// <summary>One of the <c>Type*</c> constants.</summary>
        [JsonPropertyName("Type")]
        public string? Type { get; set; }

        /// <summary>Session token (present on WIFI_CONNECT_READY and SESSION_JOIN).</summary>
        [JsonPropertyName("SessionToken")]
        public string? SessionToken { get; set; }

        /// <summary>Wi-Fi server IPv4 address (present on WIFI_CONNECT_READY).</summary>
        [JsonPropertyName("WifiHost")]
        public string? WifiHost { get; set; }

        /// <summary>Wi-Fi server TCP port (present on WIFI_CONNECT_READY).</summary>
        [JsonPropertyName("WifiPort")]
        public int WifiPort { get; set; }

        /// <summary>Sender's friendly Bluetooth name (present on BT_MAGIC), shown in the PC's
        /// connection-approval dialog so the operator knows which phone is connecting.</summary>
        [JsonPropertyName("DeviceName")]
        public string? DeviceName { get; set; }
    }
}
