using System;
using System.Security.Cryptography;
using TauSync.Interfaces;

namespace TauSync.Implementations.Security
{
    /// <summary>
    /// Implementation of ISecureChannel using AES-GCM encryption.
    /// Provides authenticated encryption with associated data (AEAD).
    /// </summary>
    public class SecureChannel : ISecureChannel
    {
        private const int KeySize = 256; // AES-256
        private const int IVSize = 12; // 96 bits for GCM
        private const int TagSize = 16; // 128 bits authentication tag
        private byte[]? _sharedKey;
        private bool _disposed = false;

        /// <summary>
        /// Initializes the secure channel with a shared secret key.
        /// </summary>
        /// <param name="sharedKey">The shared secret key (must be 32 bytes for AES-256).</param>
        /// <exception cref="ArgumentNullException">Thrown when sharedKey is null or empty.</exception>
        /// <exception cref="ArgumentException">Thrown when sharedKey length is invalid.</exception>
        public void Initialize(byte[] sharedKey)
        {
            if (sharedKey == null || sharedKey.Length == 0)
                throw new ArgumentNullException(nameof(sharedKey), "Shared key cannot be null or empty.");

            if (sharedKey.Length != KeySize / 8)
                throw new ArgumentException($"Shared key must be {KeySize / 8} bytes for AES-{KeySize}.", nameof(sharedKey));

            _sharedKey = new byte[sharedKey.Length];
            Array.Copy(sharedKey, _sharedKey, sharedKey.Length);
        }

        /// <summary>
        /// Encrypts plaintext data using AES-GCM encryption.
        /// </summary>
        /// <param name="plaintext">The plaintext data to encrypt.</param>
        /// <returns>Encrypted data with format: [IV (12 bytes)][Ciphertext][Tag (16 bytes)].</returns>
        /// <exception cref="ArgumentNullException">Thrown when plaintext is null.</exception>
        /// <exception cref="InvalidOperationException">Thrown when not initialized or encryption fails.</exception>
        public byte[] Encrypt(byte[] plaintext)
        {
            if (plaintext == null)
                throw new ArgumentNullException(nameof(plaintext), "Plaintext cannot be null.");

            if (_sharedKey == null)
                throw new InvalidOperationException("Secure channel is not initialized. Call Initialize() first.");

            try
            {
                using (var aes = new AesGcm(_sharedKey))
                {
                    // Generate a unique IV for each encryption
                    byte[] iv = new byte[IVSize];
                    using (var rng = RandomNumberGenerator.Create())
                    {
                        rng.GetBytes(iv);
                    }

                    // Encrypt the plaintext
                    byte[] ciphertext = new byte[plaintext.Length];
                    byte[] tag = new byte[TagSize];

                    aes.Encrypt(iv, plaintext, ciphertext, tag);

                    // Combine IV, ciphertext, and tag
                    byte[] result = new byte[IVSize + ciphertext.Length + TagSize];
                    Buffer.BlockCopy(iv, 0, result, 0, IVSize);
                    Buffer.BlockCopy(ciphertext, 0, result, IVSize, ciphertext.Length);
                    Buffer.BlockCopy(tag, 0, result, IVSize + ciphertext.Length, TagSize);

                    return result;
                }
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("Encryption failed.", ex);
            }
        }

        /// <summary>
        /// Decrypts and verifies ciphertext data using AES-GCM decryption.
        /// </summary>
        /// <param name="ciphertext">The ciphertext data with format: [IV (12 bytes)][Ciphertext][Tag (16 bytes)].</param>
        /// <returns>Decrypted plaintext data.</returns>
        /// <exception cref="ArgumentNullException">Thrown when ciphertext is null.</exception>
        /// <exception cref="ArgumentException">Thrown when ciphertext format is invalid.</exception>
        /// <exception cref="InvalidOperationException">Thrown when not initialized, decryption fails, or authentication fails.</exception>
        public byte[] Decrypt(byte[] ciphertext)
        {
            if (ciphertext == null)
                throw new ArgumentNullException(nameof(ciphertext), "Ciphertext cannot be null.");

            if (ciphertext.Length < IVSize + TagSize)
                throw new ArgumentException($"Ciphertext must be at least {IVSize + TagSize} bytes (IV + Tag).", nameof(ciphertext));

            if (_sharedKey == null)
                throw new InvalidOperationException("Secure channel is not initialized. Call Initialize() first.");

            try
            {
                using (var aes = new AesGcm(_sharedKey))
                {
                    // Extract IV, ciphertext, and tag
                    byte[] iv = new byte[IVSize];
                    byte[] tag = new byte[TagSize];
                    byte[] encryptedData = new byte[ciphertext.Length - IVSize - TagSize];

                    Buffer.BlockCopy(ciphertext, 0, iv, 0, IVSize);
                    Buffer.BlockCopy(ciphertext, IVSize, encryptedData, 0, encryptedData.Length);
                    Buffer.BlockCopy(ciphertext, IVSize + encryptedData.Length, tag, 0, TagSize);

                    // Decrypt and verify
                    byte[] plaintext = new byte[encryptedData.Length];
                    aes.Decrypt(iv, encryptedData, tag, plaintext);

                    return plaintext;
                }
            }
            catch (CryptographicException ex)
            {
                throw new InvalidOperationException("Decryption failed - authentication tag verification failed.", ex);
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("Decryption failed.", ex);
            }
        }

        /// <summary>
        /// Extracts the IV from encrypted data for use in TransferRequest.
        /// </summary>
        /// <param name="encryptedData">The encrypted data from Encrypt method.</param>
        /// <returns>The IV used for encryption.</returns>
        /// <exception cref="ArgumentException">Thrown when encrypted data format is invalid.</exception>
        public static byte[] ExtractIV(byte[] encryptedData)
        {
            if (encryptedData == null || encryptedData.Length < IVSize)
                throw new ArgumentException($"Encrypted data must be at least {IVSize} bytes.", nameof(encryptedData));

            byte[] iv = new byte[IVSize];
            Buffer.BlockCopy(encryptedData, 0, iv, 0, IVSize);
            return iv;
        }

        /// <summary>
        /// Disposes of resources.
        /// </summary>
        public void Dispose()
        {
            if (!_disposed)
            {
                if (_sharedKey != null)
                {
                    Array.Clear(_sharedKey, 0, _sharedKey.Length);
                    _sharedKey = null;
                }
                _disposed = true;
            }
        }
    }
}
