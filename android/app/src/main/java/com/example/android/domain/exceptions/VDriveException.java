package com.example.android.domain.exceptions;

import java.io.IOException;

/**
 * A virtual-drive failure carrying a stable, machine-readable error code.
 *
 * <p>The code travels to the PC in the op's JSON response and is translated into
 * an NTSTATUS by {@code VirtualDrive::ErrorToStatus} on the Windows side, so
 * Explorer can show a meaningful message. Only that fixed vocabulary is
 * understood — {@code access_denied}, {@code not_found}, {@code not_dir},
 * {@code exists}, {@code not_empty}, {@code io_error}, {@code timeout},
 * {@code not_connected}. Anything else degrades to a generic I/O device error.
 *
 * <p>The message is for logs and the response's {@code detail} field; it is
 * never parsed.
 */
public class VDriveException extends IOException {

    private final String code;

    public VDriveException(String code, String message) {
        super(message);
        this.code = code;
    }

    /** The stable error code {@code ErrorToStatus} matches on. */
    public String getCode() {
        return code;
    }
}
