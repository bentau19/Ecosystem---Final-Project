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

        public void Initialize(byte[] sharedKey)
        {
            if (sharedKey == null || sharedKey.Length == 0)
                throw new ArgumentNullException(nameof(sharedKey), "Shared key cannot be null or empty.");

            if (sharedKey.Length != KeySize / 8)
                throw new ArgumentException($"Shared key must be {KeySize / 8} bytes for AES-{KeySize}.", nameof(sharedKey));

            _sharedKey = new byte[sharedKey.Length];
            Array.Copy(sharedKey, _sharedKey, sharedKey.Length);
        }

        public byte[] Encrypt(byte[] plaintext)
        {
            if (plaintext == null)
                throw new ArgumentNullException(nameof(plaintext), "Plaintext cannot be null.");

            if (_sharedKey == null)
                throw new InvalidOperationException("Secure channel is not initialized. Call Initialize() first.");

            try
            {
                // התיקון: הוספת TagSize כפרמטר שני למניעת אזהרת SYSLIB0053
                using (var aes = new AesGcm(_sharedKey, TagSize))
                {
                    byte[] iv = new byte[IVSize];
                    using (var rng = RandomNumberGenerator.Create())
                    {
                        rng.GetBytes(iv);
                    }

                    byte[] ciphertext = new byte[plaintext.Length];
                    byte[] tag = new byte[TagSize];

                    aes.Encrypt(iv, plaintext, ciphertext, tag);

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
                // התיקון: הוספת TagSize כפרמטר שני למניעת אזהרת SYSLIB0053
                using (var aes = new AesGcm(_sharedKey, TagSize))
                {
                    byte[] iv = new byte[IVSize];
                    byte[] tag = new byte[TagSize];
                    byte[] encryptedData = new byte[ciphertext.Length - IVSize - TagSize];

                    Buffer.BlockCopy(ciphertext, 0, iv, 0, IVSize);
                    Buffer.BlockCopy(ciphertext, IVSize, encryptedData, 0, encryptedData.Length);
                    Buffer.BlockCopy(ciphertext, IVSize + encryptedData.Length, tag, 0, TagSize);

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

        public static byte[] ExtractIV(byte[] encryptedData)
        {
            if (encryptedData == null || encryptedData.Length < IVSize)
                throw new ArgumentException($"Encrypted data must be at least {IVSize} bytes.", nameof(encryptedData));

            byte[] iv = new byte[IVSize];
            Buffer.BlockCopy(encryptedData, 0, iv, 0, IVSize);
            return iv;
        }

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