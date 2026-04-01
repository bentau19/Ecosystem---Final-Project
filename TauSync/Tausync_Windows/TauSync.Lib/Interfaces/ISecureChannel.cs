using System;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Security layer interface - responsible for handling encryption before the packet is sent.
    /// </summary>
    public interface ISecureChannel : IDisposable
    {
        /// <summary>
        /// Encrypts plaintext data using AES-GCM encryption.
        /// </summary>
        /// <param name="plaintext">The plaintext data to encrypt.</param>
        /// <returns>Encrypted data including the initialization vector and authentication tag.</returns>
        /// <exception cref="ArgumentNullException">Thrown when plaintext is null.</exception>
        /// <exception cref="InvalidOperationException">Thrown when encryption fails.</exception>
        byte[] Encrypt(byte[] plaintext);

        /// <summary>
        /// Decrypts and verifies ciphertext data using AES-GCM decryption.
        /// </summary>
        /// <param name="ciphertext">The ciphertext data to decrypt (including IV and auth tag).</param>
        /// <returns>Decrypted plaintext data.</returns>
        /// <exception cref="ArgumentNullException">Thrown when ciphertext is null.</exception>
        /// <exception cref="InvalidOperationException">Thrown when decryption fails or authentication fails.</exception>
        byte[] Decrypt(byte[] ciphertext);
    }
}
