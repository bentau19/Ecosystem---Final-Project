package com.example.tausync_lib.models;

import com.google.gson.annotations.SerializedName;

/**
 * Hybrid-session signaling message, sent as the payload of a TPack with TargetID=0 and
 * Flags=CONTROL. Distinct from {@link TransferRequest} (meeting-word discovery): these frames
 * coordinate the Bluetooth↔Wi-Fi session and are recognised by their {@link #getType()} being one
 * of the {@code TYPE_*} constants below, so they never collide with a meeting word.
 *
 * <p>JSON field names use PascalCase to match the C# side exactly (wire-compatibility requirement).
 */
public class SessionControlMessage {

    /** Exchanged both ways right after RFCOMM opens to confirm both peers are TauSync. */
    public static final String TYPE_BT_MAGIC = "BT_MAGIC";

    /** Sent over BT by whichever side first needs Wi-Fi (a large payload is queued). */
    public static final String TYPE_WIFI_CONNECT_REQ = "WIFI_CONNECT_REQ";

    /** Reply from the Wi-Fi server over BT carrying the session token and TCP address. */
    public static final String TYPE_WIFI_CONNECT_READY = "WIFI_CONNECT_READY";

    /** First frame the Wi-Fi client sends on the new TCP socket; carries the token. */
    public static final String TYPE_SESSION_JOIN = "SESSION_JOIN";

    /** Server's confirmation that the SESSION_JOIN token matched. */
    public static final String TYPE_SESSION_JOIN_ACK = "SESSION_JOIN_ACK";

    /** Server → client: the operator declined the connection. The client aborts without reconnecting. */
    public static final String TYPE_SESSION_REJECT = "SESSION_REJECT";

    /** Client → server: echoed after the client receives the server's BT_MAGIC, proving the link is
     * still live (not a half-open socket the peer abandoned during a slow approval). */
    public static final String TYPE_SESSION_CONFIRM = "SESSION_CONFIRM";

    /** Server → client: the connection is waiting on the PC operator's approval. The client should
     * keep the handshake alive for the full approval window instead of applying its normal
     * (much shorter) connect timeout. */
    public static final String TYPE_APPROVAL_PENDING = "APPROVAL_PENDING";

    @SerializedName("MagicBytes")
    private long magicBytes = 0x54415553L;

    @SerializedName("Type")
    private String type;

    @SerializedName("SessionToken")
    private String sessionToken;

    @SerializedName("WifiHost")
    private String wifiHost;

    @SerializedName("WifiPort")
    private int wifiPort;

    @SerializedName("DeviceName")
    private String deviceName;

    public SessionControlMessage() {}

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

    public String getSessionToken() {
        return sessionToken;
    }

    public void setSessionToken(String sessionToken) {
        this.sessionToken = sessionToken;
    }

    public String getWifiHost() {
        return wifiHost;
    }

    public void setWifiHost(String wifiHost) {
        this.wifiHost = wifiHost;
    }

    public int getWifiPort() {
        return wifiPort;
    }

    public void setWifiPort(int wifiPort) {
        this.wifiPort = wifiPort;
    }

    public String getDeviceName() {
        return deviceName;
    }

    public void setDeviceName(String deviceName) {
        this.deviceName = deviceName;
    }
}
