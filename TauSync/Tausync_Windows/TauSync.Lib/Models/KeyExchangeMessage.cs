using System.Text.Json.Serialization;

namespace TauSync.Models
{
    /// <summary>
    /// Security key-exchange message, sent as the payload of a TPack with TargetID=0 and Flags=CONTROL
    /// as the very first frame on the primary transport. Carries the sender's ephemeral ECDH (P-256)
    /// public key so both peers can derive the shared AES-256-GCM session key. It travels in plaintext
    /// because it runs before encryption is active; recognised by <see cref="Type"/> == <see cref="TypeKeyExchange"/>.
    /// Distinct from <see cref="TransferRequest"/> (meeting-word discovery) and
    /// <see cref="SessionControlMessage"/> (hybrid signalling).
    /// </summary>
    public class KeyExchangeMessage
    {
        /// <summary>Identifies a key-exchange frame.</summary>
        public const string TypeKeyExchange = "KEY_EXCHANGE";

        /// <summary>Protocol identity: 0x54415553 ("TAUS").</summary>
        [JsonPropertyName("MagicBytes")]
        public uint MagicBytes { get; set; } = 0x54415553;

        /// <summary>Always <see cref="TypeKeyExchange"/>.</summary>
        [JsonPropertyName("Type")]
        public string? Type { get; set; }

        /// <summary>Base64-encoded DER SubjectPublicKeyInfo of the sender's ephemeral ECDH public key.</summary>
        [JsonPropertyName("PublicKey")]
        public string? PublicKey { get; set; }
    }
}
