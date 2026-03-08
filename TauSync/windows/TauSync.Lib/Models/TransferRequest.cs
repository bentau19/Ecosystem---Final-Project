using System;
using System.Text.Json.Serialization;

namespace TauSync.Models
{
    /// <summary>
    /// Signaling message for task coordination. Sent as the payload of a TPack with header CorrelationID = 0.
    /// The CorrelationID inside this object is the stream ID we are listening to or negotiating.
    /// </summary>
    public class TransferRequest
    {
        /// <summary>Protocol identity: 0x54415553 ("TAUS").</summary>
        [JsonPropertyName("MagicBytes")]
        public uint MagicBytes { get; set; } = 0x54415553;

        /// <summary>Stream ID (odd in C#, even in Java).</summary>
        [JsonPropertyName("CorrelationID")]
        public int CorrelationID { get; set; }

        /// <summary>Task type (e.g. "FILE", "CLIPBOARD", "BACKUP").</summary>
        [JsonPropertyName("Type")]
        public string? Type { get; set; }

        /// <summary>Conversation state: REQ, PUSH, APPROVE, OK, REJECT, FIN.</summary>
        [JsonPropertyName("Status")]
        public string? Status { get; set; }

        /// <summary>Total payload size in bytes (64-bit).</summary>
        [JsonPropertyName("FileSize")]
        public long FileSize { get; set; }

        /// <summary>Optional inner JSON (e.g. {"FileName": "pic.jpg"}).</summary>
        [JsonPropertyName("Payload")]
        public string? Payload { get; set; }

        /// <summary>
        /// Validates the request per TauSync Protocol (MagicBytes, CorrelationID range for 3 bytes, Status/Type non-empty when required).
        /// </summary>
        public bool IsValid()
        {
            if (MagicBytes != 0x54415553) return false;
            if (CorrelationID < 0 || CorrelationID > 0xFFFFFF) return false; // 3-byte max
            if (string.IsNullOrWhiteSpace(Status)) return false;
            if (string.IsNullOrWhiteSpace(Type)) return false;
            if (FileSize < 0) return false;
            return true;
        }
    }
}
