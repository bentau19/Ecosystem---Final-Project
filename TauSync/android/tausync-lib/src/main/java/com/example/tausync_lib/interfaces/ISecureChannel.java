package com.example.tausync_lib.interfaces;

/**
 * Security layer for payload encryption/decryption (AES-256-GCM).
 * Not yet wired into the frame pipeline.
 */
public interface ISecureChannel extends AutoCloseable {

    /**
     * Encrypts plaintext.
     *
     * @param plaintext the data to encrypt
     * @return IV (12B) + ciphertext + tag (16B)
     */
    byte[] encrypt(byte[] plaintext);

    /**
     * Decrypts ciphertext produced by {@link #encrypt(byte[])}.
     *
     * @param ciphertext the encrypted blob (IV + ciphertext + tag)
     * @return the original plaintext
     */
    byte[] decrypt(byte[] ciphertext);
}
