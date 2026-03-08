package com.example.tausync_lib.models;

import com.google.gson.annotations.SerializedName;

/**
 * Signaling message for task coordination per TauSync Protocol Spec.
 * Sent as the payload of a TPack with header CorrelationID = 0.
 * The CorrelationID inside this object is the stream ID we are listening to or negotiating.
 */
public class TransferRequest {

    /** Protocol identity: 0x54415553 ("TAUS"). */
    @SerializedName("MagicBytes")
    private long magicBytes = 0x54415553L;

    /** Stream ID (odd in C#, even in Java). */
    @SerializedName("CorrelationID")
    private int correlationID;

    /** Task type (e.g. "FILE", "CLIPBOARD", "BACKUP"). */
    @SerializedName("Type")
    private String type;

    /** Conversation state: REQ, PUSH, APPROVE, OK, REJECT, FIN. */
    @SerializedName("Status")
    private String status;

    /** Total payload size in bytes (64-bit). */
    @SerializedName("FileSize")
    private long fileSize;

    /** Optional inner JSON (e.g. {"FileName": "pic.jpg"}). */
    @SerializedName("Payload")
    private String payload;

    public TransferRequest() {
    }

    public long getMagicBytes() {
        return magicBytes;
    }

    public void setMagicBytes(long magicBytes) {
        this.magicBytes = magicBytes;
    }

    public int getCorrelationID() {
        return correlationID;
    }

    public void setCorrelationID(int correlationID) {
        this.correlationID = correlationID;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public long getFileSize() {
        return fileSize;
    }

    public void setFileSize(long fileSize) {
        this.fileSize = fileSize;
    }

    public String getPayload() {
        return payload;
    }

    public void setPayload(String payload) {
        this.payload = payload;
    }

    /**
     * Validates the request per TauSync Protocol (MagicBytes, CorrelationID range for 3 bytes, Status/Type non-empty when required).
     */
    public boolean isValid() {
        if (magicBytes != 0x54415553L) return false;
        if (correlationID < 0 || correlationID > 0xFFFFFF) return false;
        if (status == null || status.trim().isEmpty()) return false;
        if (type == null || type.trim().isEmpty()) return false;
        if (fileSize < 0) return false;
        return true;
    }
}
