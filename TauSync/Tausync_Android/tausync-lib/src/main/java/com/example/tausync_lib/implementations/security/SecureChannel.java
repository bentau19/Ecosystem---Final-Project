package com.example.tausync_lib.implementations.security;

import com.example.tausync_lib.interfaces.ISecureChannel;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.security.SecureRandom;
import java.util.Arrays;

/**
 * AES-256-GCM encryption/decryption.
 * Not yet wired into the frame pipeline.
 * Matches C# SecureChannel.
 */
public class SecureChannel implements ISecureChannel {

    private static final int KEY_SIZE_BYTES = 32;
    private static final int IV_SIZE = 12;
    private static final int TAG_BITS = 128;
    private static final String ALGORITHM = "AES";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";

    private SecretKeySpec secretKey;
    private boolean initialized;

    /**
     * Initialises the channel with a shared 256-bit key.
     *
     * @param sharedKey 32-byte AES key
     */
    public void initialize(byte[] sharedKey) {
        if (sharedKey == null || sharedKey.length != KEY_SIZE_BYTES) {
            throw new IllegalArgumentException("Key must be exactly " + KEY_SIZE_BYTES + " bytes.");
        }
        this.secretKey = new SecretKeySpec(sharedKey, ALGORITHM);
        this.initialized = true;
    }

    @Override
    public byte[] encrypt(byte[] plaintext) {
        if (plaintext == null) throw new IllegalArgumentException("plaintext must not be null");
        if (!initialized) throw new IllegalStateException("Call initialize() first.");

        try {
            byte[] iv = new byte[IV_SIZE];
            new SecureRandom().nextBytes(iv);

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, secretKey, new GCMParameterSpec(TAG_BITS, iv));
            byte[] ciphertext = cipher.doFinal(plaintext);

            byte[] result = new byte[IV_SIZE + ciphertext.length];
            System.arraycopy(iv, 0, result, 0, IV_SIZE);
            System.arraycopy(ciphertext, 0, result, IV_SIZE, ciphertext.length);
            return result;
        } catch (Exception e) {
            throw new IllegalStateException("Encryption failed.", e);
        }
    }

    @Override
    public byte[] decrypt(byte[] ciphertext) {
        if (ciphertext == null) throw new IllegalArgumentException("ciphertext must not be null");
        if (ciphertext.length < IV_SIZE + TAG_BITS / 8) {
            throw new IllegalArgumentException("Ciphertext too short.");
        }
        if (!initialized) throw new IllegalStateException("Call initialize() first.");

        try {
            byte[] iv = Arrays.copyOfRange(ciphertext, 0, IV_SIZE);
            byte[] encrypted = Arrays.copyOfRange(ciphertext, IV_SIZE, ciphertext.length);

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, secretKey, new GCMParameterSpec(TAG_BITS, iv));
            return cipher.doFinal(encrypted);
        } catch (javax.crypto.AEADBadTagException e) {
            throw new IllegalStateException("Authentication tag verification failed.", e);
        } catch (Exception e) {
            throw new IllegalStateException("Decryption failed.", e);
        }
    }

    @Override
    public void close() {
        secretKey = null;
        initialized = false;
    }
}
