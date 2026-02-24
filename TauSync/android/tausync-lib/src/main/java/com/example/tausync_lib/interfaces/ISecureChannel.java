package com.tausync.interfaces;

/**
 * Security layer interface - responsible for handling encryption before the packet is sent.
 */
public interface ISecureChannel {
    /**
     * Encrypts plaintext data using AES-GCM encryption.
     *
     * @param plaintext The plaintext data to encrypt.
     * @return Encrypted data including the initialization vector and authentication tag.
     * @throws IllegalArgumentException If plaintext is null.
     * @throws IllegalStateException If not initialized or encryption fails.
     */
    byte[] encrypt(byte[] plaintext);

    /**
     * Decrypts and verifies ciphertext data using AES-GCM decryption.
     *
     * @param ciphertext The ciphertext data to decrypt (including IV and auth tag).
     * @return Decrypted plaintext data.
     * @throws IllegalArgumentException If ciphertext is null.
     * @throws IllegalStateException If not initialized, decryption fails, or authentication fails.
     */
    byte[] decrypt(byte[] ciphertext);
}
