using System;
using System.Text.Json.Serialization;

namespace TauSync.Models
{
    /// <summary>
    /// Represents a data transfer request in the TauSync protocol.
    /// All information passed through the TauSync protocol is packaged within this object (in JSON format).
    /// </summary>
    public class TransferRequest
    {
        /// <summary>
        /// Magic bytes identifier. Always 0x54415553 ("TAUS" in ASCII).
        /// </summary>
        [JsonPropertyName("MagicBytes")]
        public uint MagicBytes { get; set; } = 0x54415553;

        /// <summary>
        /// Current protocol version (always 1).
        /// </summary>
        [JsonPropertyName("Version")]
        public int Version { get; set; } = 1;

        /// <summary>
        /// Raw data (file/message) after encryption.
        /// </summary>
        [JsonPropertyName("Payload")]
        public byte[] Payload { get; set; } = Array.Empty<byte>();

        /// <summary>
        /// Priority level: 0 (Low/BT), 1 (High/WiFi).
        /// </summary>
        [JsonPropertyName("Priority")]
        public int Priority { get; set; } = 0;

        /// <summary>
        /// Whether the Payload has been compressed with GZip.
        /// </summary>
        [JsonPropertyName("IsCompressed")]
        public bool IsCompressed { get; set; } = false;

        /// <summary>
        /// Initialization Vector used for encrypting the Payload.
        /// Must be unique (Random) for each transmission.
        /// </summary>
        [JsonPropertyName("CryptoIV")]
        public byte[] CryptoIV { get; set; } = Array.Empty<byte>();

        /// <summary>
        /// Validates the TransferRequest structure.
        /// </summary>
        /// <returns>True if valid, false otherwise.</returns>
        public bool IsValid()
        {
            if (MagicBytes != 0x54415553)
                return false;

            if (Version != 1)
                return false;

            if (Priority < 0 || Priority > 1)
                return false;

            if (Payload == null)
                return false;

            // CryptoIV can be empty if no encryption is used
            if (CryptoIV == null)
                return false;

            return true;
        }

        /// <summary>
        /// Gets the size of the payload in bytes.
        /// </summary>
        /// <returns>Payload size in bytes.</returns>
        public long GetPayloadSize()
        {
            return Payload?.Length ?? 0;
        }
    }
}
