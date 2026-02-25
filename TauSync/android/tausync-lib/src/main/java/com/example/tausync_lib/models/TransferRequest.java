package com.tausync.models;

import com.google.gson.annotations.SerializedName;

/**
 * Represents a data transfer request in the TauSync protocol.
 * All information passed through the TauSync protocol is packaged within this object (in JSON format).
 */
public class TransferRequest {
    @SerializedName("MagicBytes")
    private long magicBytes = 0x54415553L;

    @SerializedName("Version")
    private int version = 1;

    @SerializedName("Payload")
    private byte[] payload = new byte[0];

    @SerializedName("Priority")
    private int priority = 0;

    @SerializedName("IsCompressed")
    private boolean isCompressed = false;

    @SerializedName("CryptoIV")
    private byte[] cryptoIV = new byte[0];

    @SerializedName("RequestId")
    private String requestId;

    public TransferRequest() {
    }

    public long getMagicBytes() {
        return magicBytes;
    }

    public void setMagicBytes(long magicBytes) {
        this.magicBytes = magicBytes;
    }

    public int getVersion() {
        return version;
    }

    public void setVersion(int version) {
        this.version = version;
    }

    public byte[] getPayload() {
        return payload;
    }

    public void setPayload(byte[] payload) {
        this.payload = payload != null ? payload : new byte[0];
    }

    public int getPriority() {
        return priority;
    }

    public void setPriority(int priority) {
        this.priority = priority;
    }

    public boolean isCompressed() {
        return isCompressed;
    }

    public void setCompressed(boolean compressed) {
        isCompressed = compressed;
    }

    public byte[] getCryptoIV() {
        return cryptoIV;
    }

    public void setCryptoIV(byte[] cryptoIV) {
        this.cryptoIV = cryptoIV != null ? cryptoIV : new byte[0];
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public boolean isValid() {
        if (magicBytes != 0x54415553L) {
            return false;
        }
        if (version != 1) {
            return false;
        }
        if (priority < 0 || priority > 1) {
            return false;
        }
        if (payload == null) {
            return false;
        }
        // CryptoIV can be empty if no encryption is used
        if (cryptoIV == null) {
            return false;
        }
        return true;
    }

    public long getPayloadSize() {
        return payload != null ? payload.length : 0;
    }
}
