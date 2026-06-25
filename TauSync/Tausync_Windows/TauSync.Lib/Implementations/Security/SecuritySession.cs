using System;
using System.Security.Cryptography;
using TauSync.Core;
using TauSync.Interfaces;

namespace TauSync.Implementations.Security
{
    /// <summary>
    /// Per-session crypto state: runs the ephemeral ECDH (P-256) key agreement and, once a shared key
    /// is derived, encrypts/decrypts frame payloads through an <see cref="ISecureChannel"/> (AES-256-GCM).
    ///
    /// <para>Lifecycle: <see cref="GenerateLocalPublicKey"/> (start of a connection) →
    /// <see cref="CompleteExchange"/> (peer key arrived) flips <see cref="IsEncryptionActive"/> on →
    /// <see cref="Clear"/> on session teardown. While inactive, encrypt/decrypt are pass-throughs so the
    /// key-exchange frames themselves travel in plaintext.</para>
    ///
    /// <para>Only the payload is ever transformed — the TPack header (length/TargetID/flags) stays
    /// plaintext, so routing never needs decryption.</para>
    /// </summary>
    public sealed class SecuritySession : IDisposable
    {
        private const int KeySizeBytes = 32; // AES-256

        private readonly object _lock = new object();
        private ECDiffieHellman? _ecdh;
        private ISecureChannel? _secureChannel;
        private volatile bool _encryptionActive;

        /// <summary>True once the shared key has been derived and the channel initialised.</summary>
        public bool IsEncryptionActive => _encryptionActive;

        /// <summary>
        /// Generates the local ephemeral ECDH key pair and returns its public key as base64 DER
        /// SubjectPublicKeyInfo (cross-platform interoperable with the Java X509EncodedKeySpec form).
        /// </summary>
        public string GenerateLocalPublicKey()
        {
            lock (_lock)
            {
                _ecdh?.Dispose();
                _ecdh = ECDiffieHellman.Create(ECCurve.NamedCurves.nistP256);
                byte[] spki = _ecdh.PublicKey.ExportSubjectPublicKeyInfo();
                return Convert.ToBase64String(spki);
            }
        }

        /// <summary>
        /// Derives the shared AES-256 key from the peer's base64 DER public key and the local private
        /// key, initialises the secure channel, and activates encryption. Idempotent: a second call
        /// once already active is ignored.
        /// </summary>
        public void CompleteExchange(string peerPublicKeyBase64)
        {
            if (string.IsNullOrEmpty(peerPublicKeyBase64))
                throw new ArgumentException("Peer public key cannot be null or empty.", nameof(peerPublicKeyBase64));

            lock (_lock)
            {
                if (_encryptionActive)
                    return;
                if (_ecdh == null)
                    throw new InvalidOperationException("GenerateLocalPublicKey must be called before CompleteExchange.");

                using var peer = ECDiffieHellman.Create();
                peer.ImportSubjectPublicKeyInfo(Convert.FromBase64String(peerPublicKeyBase64), out _);

                // DeriveKeyFromHash with SHA-256 hashes the raw P-256 secret agreement (the 32-byte X
                // coordinate) — matching the Java side's SHA-256(generateSecret()). Yields a 32-byte AES key.
                byte[] key = _ecdh.DeriveKeyFromHash(peer.PublicKey, HashAlgorithmName.SHA256);
                if (key.Length != KeySizeBytes)
                    throw new InvalidOperationException($"Derived key must be {KeySizeBytes} bytes, got {key.Length}.");

                var channel = new SecureChannel();
                channel.Initialize(key);

                // Debug aid: a short fingerprint of the derived key. The PC and the phone print the same
                // value when they agreed on the same key — proof the channel is encrypted end-to-end.
                string fingerprint = Convert.ToHexString(SHA256.HashData(key))[..8].ToLowerInvariant();
                Array.Clear(key, 0, key.Length);

                _secureChannel = channel;
                _ecdh.Dispose();
                _ecdh = null;
                _encryptionActive = true;

                Console.WriteLine($"[TauSync][SECURITY] AES-256-GCM encryption ACTIVE — session key fingerprint {fingerprint}");
                System.Diagnostics.Debug.WriteLine($"[TauSync][SECURITY] AES-256-GCM encryption ACTIVE — session key fingerprint {fingerprint}");
            }
        }

        /// <summary>
        /// Encrypts a frame payload when encryption is active. Empty payloads (FIN, barriers) and
        /// frames sent while inactive (the key exchange itself) pass through unchanged.
        /// </summary>
        public byte[] EncryptPayload(byte[] payload)
        {
            if (!_encryptionActive || payload == null || payload.Length == 0)
                return payload!;
            ISecureChannel? channel = _secureChannel;
            return channel == null ? payload : channel.Encrypt(payload);
        }

        /// <summary>
        /// Decrypts a frame payload when encryption is active. Empty payloads and frames received while
        /// inactive (the key exchange itself) pass through unchanged.
        /// </summary>
        public byte[] DecryptPayload(byte[] payload)
        {
            if (!_encryptionActive || payload == null || payload.Length == 0)
                return payload!;
            ISecureChannel? channel = _secureChannel;
            return channel == null ? payload : channel.Decrypt(payload);
        }

        /// <summary>Clears all crypto state (key, channel, key pair) and deactivates encryption.</summary>
        public void Clear()
        {
            lock (_lock)
            {
                _encryptionActive = false;
                _secureChannel?.Dispose();
                _secureChannel = null;
                _ecdh?.Dispose();
                _ecdh = null;
            }
        }

        public void Dispose() => Clear();
    }
}
