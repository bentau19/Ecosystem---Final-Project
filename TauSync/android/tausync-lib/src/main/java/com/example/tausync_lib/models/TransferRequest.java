package com.example.tausync_lib.models;

import com.google.gson.annotations.SerializedName;

/**
 * Signaling message for task coordination per TauSync Protocol Spec.
 * Sent as the payload of a TPack with header CorrelationID = 0.
 * CorrelationID = stream ID assigned by this process. ParentID = ID of the message we are responding to (0 when initiating).
 */
public class TransferRequest {

    /** Protocol identity: 0x54415553 ("TAUS"). */
    @SerializedName("MagicBytes")
    private long magicBytes = 0x54415553L;

    /** Stream ID assigned by this process (1..0xFFFFFF). */
    @SerializedName("CorrelationID")
    private int correlationID;

    /** When responding (OK/REJECT/APPROVE), the CorrelationID of the request we are responding to. 0 when initiating. */
    @SerializedName("ParentID")
    private int parentID;

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
        if (parentID < 0 || parentID > 0xFFFFFF) return false;
        if (status == null || status.trim().isEmpty()) return false;
        if (type == null || type.trim().isEmpty()) return false;
        if (fileSize < 0) return false;
        return true;
    }
}
