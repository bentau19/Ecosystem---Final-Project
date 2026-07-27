package com.example.tausync_lib.implementations.management;

import java.io.IOException;

/**
 * Thrown when the PC operator explicitly declines a hybrid (Bluetooth) connection
 * (the server sent SESSION_REJECT). Callers should surface the rejection and NOT
 * auto-retry — redialing would only re-prompt the operator with the same request.
 */
public class ConnectionDeclinedException extends IOException {

    public ConnectionDeclinedException() {
        super("The connection was declined on the PC.");
    }

    /**
     * @return true when {@code error} or any link of its cause chain is a
     * {@link ConnectionDeclinedException} — connect failures cross several
     * executor/future boundaries, each wrapping the original exception.
     */
    public static boolean isDeclined(Throwable error) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof ConnectionDeclinedException) {
                return true;
            }
        }
        return false;
    }
}
