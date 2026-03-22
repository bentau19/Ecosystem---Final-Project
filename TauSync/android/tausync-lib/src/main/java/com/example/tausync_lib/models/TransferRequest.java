package com.example.tausync_lib.models;

import com.google.gson.annotations.SerializedName;

/**
 * Signaling message for TauSync v3 coordination.
 * Sent as the payload of a TPack with TargetID=0 and Flags=CONTROL.
 *
 * <p>JSON field names use PascalCase to match the C# side exactly
 * (wire-compatibility requirement).
 */
public class TransferRequest {

    @SerializedName("MagicBytes")
    private long magicBytes = 0x54415553L;

    @SerializedName("SenderID")
    private int senderID;

    @SerializedName("Type")
    private String type;

    @SerializedName("Status")
    private String status;

    public TransferRequest() {}

    public long getMagicBytes() {
        return magicBytes;
    }

    public void setMagicBytes(long magicBytes) {
        this.magicBytes = magicBytes;
    }

    public int getSenderID() {
        return senderID;
    }

    public void setSenderID(int senderID) {
        this.senderID = senderID;
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

    /**
     * Validates the request per TauSync Protocol Spec section 3.1.
     *
     * @return true when all mandatory fields pass validation
     */
    public boolean isValid() {
        if (magicBytes != 0x54415553L) return false;
        if (senderID < 0 || senderID > 0xFFFFFF) return false;
        if (status == null || status.trim().isEmpty()) return false;

        String normalised = status.trim().toUpperCase();
        if (!normalised.equals("REQ") && !normalised.equals("OK") && !normalised.equals("REJECT")) {
            return false;
        }
        if (normalised.equals("REQ") && (type == null || type.trim().isEmpty())) {
            return false;
        }
        return true;
    }
}
