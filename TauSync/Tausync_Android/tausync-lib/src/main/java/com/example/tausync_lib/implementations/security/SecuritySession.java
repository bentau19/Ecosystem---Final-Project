package com.example.tausync_lib.implementations.security;

import android.util.Base64;
import android.util.Log;

import com.example.tausync_lib.core.CoreConfig;

import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.X509EncodedKeySpec;

import javax.crypto.KeyAgreement;

/**
 * Per-session crypto state: runs the ephemeral ECDH (P-256) key agreement and, once a shared key is
 * derived, encrypts/decrypts frame payloads through a {@link SecureChannel} (AES-256-GCM).
 *
 * <p>Lifecycle: {@link #generateLocalPublicKey()} (start of a connection) → {@link #completeExchange}
 * (peer key arrived) flips {@link #isEncryptionActive()} on → {@link #clear()} on session teardown.
 * While inactive, encrypt/decrypt are pass-throughs so the key-exchange frames themselves travel in
 * plaintext.</p>
 *
 * <p>Only the payload is ever transformed — the TPack header (length/TargetID/flags) stays plaintext,
 * so routing never needs decryption. Matches C# SecuritySession.</p>
 */
public final class SecuritySession {

    private static final String LOG_TAG = "TauSync";
    private static final int KEY_SIZE_BYTES = 32; // AES-256
    private static final int ECDH_SECRET_BYTES = 32; // P-256 field element

    private final Object lock = new Object();
    private KeyPair localKeyPair;
    private SecureChannel secureChannel;
    private volatile boolean encryptionActive;

    /** True once the shared key has been derived and the channel initialised. */
    public boolean isEncryptionActive() {
        return encryptionActive;
    }

    /**
     * Generates the local ephemeral ECDH key pair and returns its public key as base64 DER
     * SubjectPublicKeyInfo (the {@link X509EncodedKeySpec} form, interoperable with the Windows
     * ExportSubjectPublicKeyInfo).
     */
    public String generateLocalPublicKey() {
        synchronized (lock) {
            try {
                KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
                generator.initialize(new ECGenParameterSpec(CoreConfig.KEY_EXCHANGE_CURVE));
                localKeyPair = generator.generateKeyPair();
                byte[] spki = localKeyPair.getPublic().getEncoded();
                return Base64.encodeToString(spki, Base64.NO_WRAP);
            } catch (Exception e) {
                throw new IllegalStateException("Failed to generate ECDH key pair.", e);
            }
        }
    }

    /**
     * Derives the shared AES-256 key from the peer's base64 DER public key and the local private key,
     * initialises the secure channel, and activates encryption. Idempotent: a second call once already
     * active is ignored.
     */
    public void completeExchange(String peerPublicKeyBase64) {
        if (peerPublicKeyBase64 == null || peerPublicKeyBase64.isEmpty()) {
            throw new IllegalArgumentException("Peer public key must not be null or empty.");
        }
        synchronized (lock) {
            if (encryptionActive) {
                return;
            }
            if (localKeyPair == null) {
                throw new IllegalStateException("generateLocalPublicKey must be called before completeExchange.");
            }
            try {
                byte[] der = Base64.decode(peerPublicKeyBase64, Base64.NO_WRAP);
                PublicKey peerPublic = KeyFactory.getInstance("EC")
                        .generatePublic(new X509EncodedKeySpec(der));

                KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
                agreement.init((PrivateKey) localKeyPair.getPrivate());
                agreement.doPhase(peerPublic, true);
                // Normalise to the fixed 32-byte field element (zero-padded) so SHA-256 hashes the same
                // bytes the .NET DeriveKeyFromHash(SHA256) hashes — cross-platform key match.
                byte[] sharedSecret = toFixedLength(agreement.generateSecret(), ECDH_SECRET_BYTES);
                byte[] key = MessageDigest.getInstance("SHA-256").digest(sharedSecret);
                if (key.length != KEY_SIZE_BYTES) {
                    throw new IllegalStateException("Derived key must be " + KEY_SIZE_BYTES + " bytes.");
                }

                SecureChannel channel = new SecureChannel();
                channel.initialize(key);

                // Debug aid: a short fingerprint of the derived key. The PC and the phone log the same
                // value when they agreed on the same key — proof the channel is encrypted end-to-end.
                String fingerprint = keyFingerprint(key);

                secureChannel = channel;
                localKeyPair = null;
                encryptionActive = true;

                Log.i(LOG_TAG, "[SECURITY] AES-256-GCM encryption ACTIVE — session key fingerprint " + fingerprint);
            } catch (Exception e) {
                throw new IllegalStateException("ECDH key derivation failed.", e);
            }
        }
    }

    /**
     * Encrypts a frame payload when encryption is active. Empty payloads (FIN, barriers) and frames
     * sent while inactive (the key exchange itself) pass through unchanged.
     */
    public byte[] encryptPayload(byte[] payload) {
        if (!encryptionActive || payload == null || payload.length == 0) {
            return payload;
        }
        SecureChannel channel = secureChannel;
        return channel == null ? payload : channel.encrypt(payload);
    }

    /**
     * Decrypts a frame payload when encryption is active. Empty payloads and frames received while
     * inactive (the key exchange itself) pass through unchanged.
     */
    public byte[] decryptPayload(byte[] payload) {
        if (!encryptionActive || payload == null || payload.length == 0) {
            return payload;
        }
        SecureChannel channel = secureChannel;
        return channel == null ? payload : channel.decrypt(payload);
    }

    /** Clears all crypto state (key, channel, key pair) and deactivates encryption. */
    public void clear() {
        synchronized (lock) {
            encryptionActive = false;
            if (secureChannel != null) {
                secureChannel.close();
                secureChannel = null;
            }
            localKeyPair = null;
        }
    }

    /** First 8 lowercase hex chars of SHA-256(key) — matches the C# SecuritySession fingerprint. */
    private static String keyFingerprint(byte[] key) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(key);
            StringBuilder sb = new StringBuilder(8);
            for (int i = 0; i < 4; i++) {
                sb.append(String.format("%02x", digest[i]));
            }
            return sb.toString();
        } catch (Exception e) {
            return "????????";
        }
    }

    private static byte[] toFixedLength(byte[] value, int length) {
        if (value.length == length) {
            return value;
        }
        byte[] fixed = new byte[length];
        if (value.length > length) {
            // Drop a leading sign byte some providers prepend; keep the low `length` bytes.
            System.arraycopy(value, value.length - length, fixed, 0, length);
        } else {
            // Left-pad with zeros so a stripped leading zero still hashes identically.
            System.arraycopy(value, 0, fixed, length - value.length, value.length);
        }
        return fixed;
    }
}
