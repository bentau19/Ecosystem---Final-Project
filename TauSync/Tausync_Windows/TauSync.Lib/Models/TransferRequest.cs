using System;
using System.Text.Json.Serialization;

namespace TauSync.Models
{
    /// <summary>
    /// Signaling message for task coordination (v3.0). Sent as payload of a TPack with TargetID=0 and Flags=CONTROL.
    /// SenderID = local ID of the sender (the ID the peer should send back to). Type = "Meeting Word". Status = REQ | OK | REJECT.
    /// </summary>
    public class TransferRequest
    {
        /// <summary>Protocol identity: 0x54415553 ("TAUS").</summary>
        [JsonPropertyName("MagicBytes")]
        public uint MagicBytes { get; set; } = 0x54415553;

        /// <summary>The local ID of the sender (the ID the peer should send back to).</summary>
        [JsonPropertyName("SenderID")]
        public int SenderID { get; set; }

        /// <summary>Meeting Word (e.g. "CLIPBOARD", "FILE").</summary>
        [JsonPropertyName("Type")]
        public string? Type { get; set; }

        /// <summary>REQ (initial), OK (accept), REJECT (deny).</summary>
        [JsonPropertyName("Status")]
        public string? Status { get; set; }

        /// <summary>
        /// Validates the request per TauSync v3: MagicBytes, SenderID in range, Status in { REQ, OK, REJECT }, Type non-empty when REQ.
        /// </summary>
        public bool IsValid()
        {
            if (MagicBytes != 0x54415553) return false;
            if (SenderID < 0 || SenderID > 0xFFFFFF) return false;
            if (string.IsNullOrWhiteSpace(Status)) return false;
            var status = Status.Trim().ToUpperInvariant();
            if (status != "REQ" && status != "OK" && status != "REJECT") return false;
            if (status == "REQ" && string.IsNullOrWhiteSpace(Type)) return false;
            return true;
        }
    }
}
