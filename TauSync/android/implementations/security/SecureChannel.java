package com.tausync.implementations.security;

import com.tausync.interfaces.ISecureChannel;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.security.SecureRandom;

/**
 * Implementation of ISecureChannel using AES-GCM encryption.
 */
public class SecureChannel implements ISecureChannel {
    private static final int KEY_SIZE = 256; // AES-256
    private static final int IV_SIZE = 12; // 96 bits for GCM
    private static final int TAG_SIZE = 128; // 128 bits authentication tag
    private static final String ALGORITHM = "AES";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";

    private SecretKeySpec secretKey;
    private boolean initialized = false;

    /**
     * Initializes the secure channel with a shared secret key.
     */
    public void initialize(byte[] sharedKey) {
        if (sharedKey == null || sharedKey.length == 0) {
            throw new IllegalArgumentException("Shared key cannot be null or empty.");
        }
        if (sharedKey.length != KEY_SIZE / 8) {
            throw new IllegalArgumentException("Shared key must be " + (KEY_SIZE / 8) + " bytes for AES-" + KEY_SIZE + ".");
        }
        this.secretKey = new SecretKeySpec(sharedKey, ALGORITHM);
        this.initialized = true;
    }

    @Override
    public byte[] encrypt(byte[] plaintext) {
        if (plaintext == null) {
            throw new IllegalArgumentException("Plaintext cannot be null.");
        }
        if (!initialized) {
            throw new IllegalStateException("Secure channel is not initialized. Call initialize() first.");
        }

        try {
            // Generate a unique IV for each encryption
            byte[] iv = new byte[IV_SIZE];
            SecureRandom secureRandom = new SecureRandom();
            secureRandom.nextBytes(iv);

            // Initialize cipher for encryption
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            GCMParameterSpec parameterSpec = new GCMParameterSpec(TAG_SIZE, iv);
            cipher.init(Cipher.ENCRYPT_MODE, secretKey, parameterSpec);

            // Encrypt the plaintext
            byte[] ciphertext = cipher.doFinal(plaintext);

            // Combine IV and ciphertext (tag is appended by GCM)
            byte[] result = new byte[IV_SIZE + ciphertext.length];
            System.arraycopy(iv, 0, result, 0, IV_SIZE);
            System.arraycopy(ciphertext, 0, result, IV_SIZE, ciphertext.length);

            return result;
        } catch (Exception ex) {
            throw new IllegalStateException("Encryption failed.", ex);
        }
    }

    @Override
    public byte[] decrypt(byte[] ciphertext) {
        if (ciphertext == null) {
            throw new IllegalArgumentException("Ciphertext cannot be null.");
        }
        if (ciphertext.length < IV_SIZE + TAG_SIZE / 8) {
            throw new IllegalArgumentException("Ciphertext must be at least " + (IV_SIZE + TAG_SIZE / 8) + " bytes (IV + Tag).");
        }
        if (!initialized) {
            throw new IllegalStateException("Secure channel is not initialized. Call initialize() first.");
        }

        try {
            // Extract IV and encrypted data
            byte[] iv = new byte[IV_SIZE];
            byte[] encryptedData = new byte[ciphertext.length - IV_SIZE];

            System.arraycopy(ciphertext, 0, iv, 0, IV_SIZE);
            System.arraycopy(ciphertext, IV_SIZE, encryptedData, 0, encryptedData.length);

            // Initialize cipher for decryption
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            GCMParameterSpec parameterSpec = new GCMParameterSpec(TAG_SIZE, iv);
            cipher.init(Cipher.DECRYPT_MODE, secretKey, parameterSpec);

            // Decrypt and verify
            return cipher.doFinal(encryptedData);
        } catch (javax.crypto.AEADBadTagException ex) {
            throw new IllegalStateException("Decryption failed - authentication tag verification failed.", ex);
        } catch (Exception ex) {
            throw new IllegalStateException("Decryption failed.", ex);
        }
    }

    public static byte[] extractIV(byte[] encryptedData) {
        if (encryptedData == null || encryptedData.length < IV_SIZE) {
            throw new IllegalArgumentException("Encrypted data must be at least " + IV_SIZE + " bytes.");
        }
        byte[] iv = new byte[IV_SIZE];
        System.arraycopy(encryptedData, 0, iv, 0, IV_SIZE);
        return iv;
    }
}
