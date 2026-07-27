package com.example.android.network.handlers;

import android.util.Log;

import com.example.android.enums.SessionChannels;
import com.example.android.network.transport.TransportManager;

/**
 * Answers the PC's post-connect hello — the moment both sides agree the session is real.
 *
 * <p>The transport handshake alone does not prove the peer is still there: each side only sees its
 * own socket, and a Bluetooth link can stay half-open long after the other end has walked away. So
 * the PC opens this channel as its last connect step and waits for a reply before calling itself
 * connected. Replying here is therefore the phone's own proof that the session came up, which is
 * why remembering the PC ({@code onSessionEstablished}) happens here and not at bonding time — a
 * PC that never accepted us must not be redialled on every launch.
 */
public class SessionHelloChannelHandler implements ChannelHandler {

    private static final String TAG = "SessionHelloHandler";

    /** Reply the PC reads back; its content is irrelevant, its arrival is the whole point. */
    private static final String ACKNOWLEDGEMENT = "ok";

    private final TransportManager transportManager;
    private final Runnable onSessionEstablished;

    public SessionHelloChannelHandler(TransportManager transportManager,
                                      Runnable onSessionEstablished) {
        this.transportManager = transportManager;
        this.onSessionEstablished = onSessionEstablished;
    }

    @Override
    public String getChannelName() {
        return SessionChannels.SESSION_HELLO.getValue();
    }

    @Override
    public void onPeerRequest() {
        try {
            // serveJsonExchange reads the PC's newline-terminated line and writes the reply on the
            // same stream. Both sides reading to EOF would deadlock, which is why the exchange is
            // line-then-reply rather than a plain read.
            transportManager.serveJsonExchange(
                    SessionChannels.SESSION_HELLO.getValue(), request -> ACKNOWLEDGEMENT);
            Log.d(TAG, "Session hello answered — the PC now has a confirmed session");
            onSessionEstablished.run();
        } catch (Exception e) {
            // The PC treats a missing reply as "phone is gone" and re-listens, so there is nothing
            // to recover here; the connection simply does not become established.
            Log.e(TAG, "Failed to answer the session hello: " + e.getMessage(), e);
        }
    }

    @Override
    public void onShutdown() {
        Log.d(TAG, "Session hello handler shut down");
    }
}
