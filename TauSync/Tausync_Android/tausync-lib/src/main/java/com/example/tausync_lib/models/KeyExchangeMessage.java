package com.example.tausync_lib.models;

import com.google.gson.annotations.SerializedName;

/**
 * Security key-exchange message, sent as the payload of a TPack with TargetID=0 and Flags=CONTROL as
 * the very first frame on the primary transport. Carries the sender's ephemeral ECDH (P-256) public
 * key so both peers can derive the shared AES-256-GCM session key. It travels in plaintext because it
 * runs before encryption is active; recognised by {@link #getType()} == {@link #TYPE_KEY_EXCHANGE}.
 *
 * <p>JSON field names use PascalCase to match the C# side exactly (wire-compatibility requirement).
 */
public class KeyExchangeMessage {

    /** Identifies a key-exchange frame. */
    public static final String TYPE_KEY_EXCHANGE = "KEY_EXCHANGE";

    @SerializedName("MagicBytes")
    private long magicBytes = 0x54415553L;

    @SerializedName("Type")
    private String type;

    /** Base64-encoded DER SubjectPublicKeyInfo of the sender's ephemeral ECDH public key. */
    @SerializedName("PublicKey")
    private String publicKey;

    public KeyExchangeMessage() {}

    public long getMagicBytes() {
        return magicBytes;
    }

    public void setMagicBytes(long magicBytes) {
        this.magicBytes = magicBytes;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public String getPublicKey() {
        return publicKey;
    }

    public void setPublicKey(String publicKey) {
        this.publicKey = publicKey;
    }
}
